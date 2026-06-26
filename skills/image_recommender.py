"""
图片推荐 Skill
根据中文文案推荐相关图片，支持 Pexels/Unsplash API 和模拟数据回退
"""
import os
import re
import json
import random
import requests
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime

from utils.config import (
    PROXY, call_deepseek_json, is_safe_url,
    get_pexels_api_key, get_unsplash_access_key, get_deepseek_api_key,
    get_approved_images_dir, extract_keywords, KEYWORD_TRANSLATION,
)
from utils.vector_store import vector_store


# ==================== 模拟数据 ====================

def get_mock_keywords(text: str) -> List[str]:
    """从文案中提取关键词（委托共享 extract_keywords）"""
    matched = extract_keywords(text)
    return matched if matched else ["生活"]


def get_mock_images(query: str, count: int = 6) -> List[Dict]:
    """生成模拟图片数据"""
    mock_db = {
        "猫": [
            {"description": "橘猫在窗台上张望", "tags": ["猫咪", "室内", "暖色调"], "url": "", "source": "mock"},
            {"description": "黑白猫咪打哈欠", "tags": ["猫咪", "可爱", "特写"], "url": "", "source": "mock"},
            {"description": "小猫在阳光下睡觉", "tags": ["猫咪", "阳光", "温馨"], "url": "", "source": "mock"},
            {"description": "猫咪玩毛线球", "tags": ["猫咪", "玩耍", "动态"], "url": "", "source": "mock"},
        ],
        "狗": [
            {"description": "金毛在草地上奔跑", "tags": ["狗狗", "户外", "动态"], "url": "", "source": "mock"},
            {"description": "柯基趴在地上", "tags": ["狗狗", "可爱", "室内"], "url": "", "source": "mock"},
            {"description": "哈士奇歪头看镜头", "tags": ["狗狗", "搞笑", "特写"], "url": "", "source": "mock"},
        ],
        "宠物": [
            {"description": "可爱的小仓鼠", "tags": ["宠物", "可爱", "小动物"], "url": "", "source": "mock"},
            {"description": "兔子在吃草", "tags": ["宠物", "兔子", "户外"], "url": "", "source": "mock"},
        ],
        "美食": [
            {"description": "红烧肉特写", "tags": ["美食", "中式", "暖色调"], "url": "", "source": "mock"},
            {"description": "精致甜点摆盘", "tags": ["美食", "甜点", "精致"], "url": "", "source": "mock"},
            {"description": "火锅沸腾画面", "tags": ["美食", "火锅", "热气腾腾"], "url": "", "source": "mock"},
            {"description": "咖啡和甜点", "tags": ["美食", "咖啡", "下午茶"], "url": "", "source": "mock"},
        ],
        "旅行": [
            {"description": "海边日落风景", "tags": ["旅行", "海边", "日落"], "url": "", "source": "mock"},
            {"description": "山间小路晨雾", "tags": ["旅行", "山景", "清晨"], "url": "", "source": "mock"},
            {"description": "古镇夜景灯光", "tags": ["旅行", "古镇", "夜景"], "url": "", "source": "mock"},
        ],
        "生活": [
            {"description": "书桌上的咖啡和笔记本", "tags": ["生活", "办公", "温馨"], "url": "", "source": "mock"},
            {"description": "阳光洒进房间", "tags": ["生活", "室内", "阳光"], "url": "", "source": "mock"},
            {"description": "绿植在窗台生长", "tags": ["生活", "植物", "清新"], "url": "", "source": "mock"},
        ],
        "自然": [
            {"description": "山间云雾缭绕", "tags": ["自然", "山景", "云雾"], "url": "", "source": "mock"},
            {"description": "草原日落", "tags": ["自然", "草原", "日落"], "url": "", "source": "mock"},
            {"description": "森林小径", "tags": ["自然", "森林", "静谧"], "url": "", "source": "mock"},
        ],
    }
    
    results = []
    for keyword in query.split():
        if keyword in mock_db:
            results.extend(mock_db[keyword])
    
    # 去重
    seen = set()
    unique = []
    for item in results:
        key = item["description"]
        if key not in seen:
            seen.add(key)
            unique.append(item)
    
    # 如果没有匹配，返回生活类
    if not unique:
        unique = mock_db.get("生活", [])
    
    random.shuffle(unique)
    return unique[:count]


# ==================== DeepSeek API 语义理解 ====================

def generate_search_keywords_via_api(text: str) -> List[str]:
    """
    通过 DeepSeek API 理解文案，生成适合图片库搜索的英文关键词

    Args:
        text: 中文文案

    Returns:
        英文关键词列表（用于图片搜索）
    """
    if not get_deepseek_api_key():
        print("[API] 未设置 DEEPSEEK_API_KEY，回退到关键词匹配")
        return []

    prompt = f"""你是一个图片搜索专家。根据以下中文文案，生成3-5个适合在图片库搜索的英文关键词。

要求：
1. 输出必须是严格的 JSON 数组，只包含英文单词或短语
2. 每个关键词应该是简洁的英文单词（如 cat, food, travel）
3. 不要输出任何其他内容，只输出 JSON 数组
4. 关键词应该能准确反映文案的主题和情感

文案：{text}

示例输出：
["cat", "cute", "window", "sunlight", "cozy"]"""

    result = call_deepseek_json(
        system_prompt="你是一个严格的 JSON 输出器，只输出 JSON 数组，不输出其他内容。",
        user_prompt=prompt,
        temperature=0.7,
        max_tokens=100,
    )

    if isinstance(result, list) and all(isinstance(k, str) for k in result):
        print(f"[API] DeepSeek 生成搜索词: {result}")
        return result[:5]
    return []


# ==================== Unsplash API ====================

def search_unsplash(query: str, count: int = 6) -> List[Dict]:
    """
    通过 Unsplash API 搜索图片
    
    Args:
        query: 搜索关键词（英文）
        count: 返回数量
    
    Returns:
        图片列表
    """
    access_key = get_unsplash_access_key()
    
    if not access_key:
        print("[Unsplash] 未设置 UNSPLASH_ACCESS_KEY，使用模拟数据")
        return []
    
    url = "https://api.unsplash.com/search/photos"
    headers = {
        "Authorization": f"Client-ID {access_key}"
    }
    params = {
        "query": query,
        "per_page": count,
        "orientation": "portrait"  # 优先竖图，适合抖音
    }
    
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=15, proxies=PROXY if PROXY else None)

        if resp.status_code == 200:
            data = resp.json()
            results = []
            for photo in data.get("results", [])[:count]:
                results.append({
                    "url": photo["urls"]["regular"],
                    "thumb_url": photo["urls"]["thumb"],
                    "description": photo.get("description", "") or photo.get("alt_description", "图片"),
                    "author": photo.get("user", {}).get("name", "Unknown"),
                    "unsplash_id": photo["id"]
                })
            print(f"[Unsplash] 返回 {len(results)} 张图片")
            return results
        elif resp.status_code == 401:
            print("[Unsplash] API Key 无效，使用模拟数据")
        elif resp.status_code == 403:
            print("[Unsplash] API 配额用尽，使用模拟数据")
        else:
            print(f"[Unsplash] HTTP 错误 {resp.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"[Unsplash] 请求失败: {e}")
    
    return []


# ==================== Pexels API（中文搜索） ====================

def search_pexels(query: str, count: int = 6) -> List[Dict]:
    """
    通过 Pexels API 搜索图片（支持中文）
    
    Args:
        query: 搜索关键词（支持中文）
        count: 返回数量
    
    Returns:
        图片列表
    """
    pexels_key = get_pexels_api_key()
    if not pexels_key:
        print("[Pexels] 未设置 PEXELS_API_KEY，跳过")
        return []

    url = "https://api.pexels.com/v1/search"
    headers = {
        "Authorization": pexels_key
    }
    params = {
        "query": query,
        "per_page": count,
        "locale": "zh-CN"
    }
    
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=15, proxies=PROXY if PROXY else None)
        
        if resp.status_code == 200:
            data = resp.json()
            results = []
            for photo in data.get("photos", [])[:count]:
                results.append({
                    "url": photo["src"]["large"],
                    "thumb_url": photo["src"]["small"],
                    "description": photo.get("alt", "") or photo.get("photographer", "图片"),
                    "author": photo.get("photographer", "Unknown"),
                    "pexels_id": photo["id"],
                    "source": "pexels"
                })
            print(f"[Pexels] 返回 {len(results)} 张图片 (关键词: {query})")
            return results
        elif resp.status_code == 401:
            print("[Pexels] API Key 无效")
        elif resp.status_code == 429:
            print("[Pexels] API 配额用尽")
        else:
            print(f"[Pexels] HTTP 错误 {resp.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"[Pexels] 请求失败: {e}")
    
    return []


# ==================== 图虫创意 API（预留接口） ====================

def search_tuchong(query: str, count: int = 6) -> List[Dict]:
    """
    图虫创意搜索（预留接口）
    
    Args:
        query: 搜索关键词
        count: 返回数量
    
    Returns:
        图片列表（暂为空）
    """
    print("[图虫] 预留接口，尚未接入")
    return []


# ==================== 图片下载 ====================

def download_image(url: str, save_path: str) -> bool:
    """
    下载图片到本地（含 SSRF 防护）

    Args:
        url: 图片 URL
        save_path: 本地保存路径

    Returns:
        是否成功
    """
    if not is_safe_url(url):
        print(f"[下载] 拒绝不安全的 URL: {url[:80]}")
        return False

    try:
        os.makedirs(os.path.dirname(save_path), exist_ok=True)

        resp = requests.get(url, timeout=30, proxies=PROXY if PROXY else None, stream=True)
        resp.raise_for_status()
        
        with open(save_path, 'wb') as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        
        return True
    except Exception as e:
        print(f"[下载] 失败: {e}")
        return False


# ==================== 主函数 ====================

def recommend_images(
    text: str, 
    use_api: bool = True, 
    save_dir: str = "approved_images",
    count: int = 6
) -> List[Dict]:
    """
    根据文案推荐图片
    
    Args:
        text: 中文文案
        use_api: 是否使用 API（DeepSeek + Unsplash）
        save_dir: 图片保存目录
        count: 推荐图片数量
    
    Returns:
        图片列表，每项包含：
        - local_path: 本地路径
        - original_url: 原始 URL
        - description: 图片描述
        - record_tags: 记录标签
        - source: 来源 (unsplash/mock)
    """
    results = []
    source = "mock"

    # 搜索策略优先级：
    # 1. Qdrant 向量语义匹配（零成本）
    # 2. 中文原文 → Pexels（支持中文，命中率高）
    # 3. DeepSeek 关键词 → Unsplash（英文图库补充）
    # 4. 回退：本地模拟数据

    # 0. Qdrant 语义图片搜索
    qdrant_images = vector_store.search_images(text, limit=count)
    if qdrant_images:
        for img in qdrant_images:
            results.append({
                "local_path": img["url"],
                "original_url": img["url"],
                "description": img["description"],
                "search_tags": img["tags"],
                "source": "qdrant",
            })
        if len(results) >= count:
            return results[:count]

    if use_api:
        # 1. 优先使用 Pexels 中文搜索
        pexels_results = search_pexels(text, count=count)
        if pexels_results:
            for r in pexels_results:
                r["search_tags"] = get_mock_keywords(text)
            results.extend(pexels_results)
            source = "pexels"
            print(f"[搜索策略] 使用 Pexels 中文搜索")
        
        # 2. 如果 Pexels 结果不足，使用 DeepSeek + Unsplash 补充
        if len(results) < count:
            search_keywords = generate_search_keywords_via_api(text)
            
            if not search_keywords:
                print("[API] DeepSeek 失败，使用关键词翻译")
                mock_keywords = get_mock_keywords(text)
                search_keywords = [KEYWORD_TRANSLATION.get(k, k) for k in mock_keywords]
                print(f"[关键词翻译] {mock_keywords} -> {search_keywords}")
            
            if search_keywords:
                for keyword in search_keywords:
                    unsplash_results = search_unsplash(keyword, count=count - len(results))
                    if unsplash_results:
                        for r in unsplash_results:
                            r["search_tags"] = search_keywords
                        results.extend(unsplash_results)
                        if source == "pexels":
                            source = "mixed"
                        else:
                            source = "unsplash"
                        if len(results) >= count:
                            break
                print(f"[搜索策略] 使用 Unsplash 补充搜索")
    
    # 3. 回退到模拟数据
    if not results:
        print("[图片推荐] 使用模拟数据")
        mock_keywords = get_mock_keywords(text)
        query = " ".join(mock_keywords)
        mock_results = get_mock_images(query, count)
        
        for item in mock_results:
            results.append({
                "url": f"https://picsum.photos/800/1200?random={random.randint(1, 1000)}",
                "thumb_url": f"https://picsum.photos/200/300?random={random.randint(1, 1000)}",
                "description": item["description"],
                "author": "Picsum",
                "unsplash_id": "",
                "mock_tags": item["tags"]
            })
        source = "mock"
    
    # 4. 去重
    seen_urls = set()
    unique_results = []
    for item in results:
        if item["url"] not in seen_urls:
            seen_urls.add(item["url"])
            unique_results.append(item)
    
    # 5. 下载并保存
    final_results = []
    for i, item in enumerate(unique_results[:count], 1):
        # 生成文件名
        timestamp = datetime.now().strftime("%H%M%S")
        filename = f"img_{timestamp}_{i}.jpg"
        local_path = os.path.join(save_dir, filename)
        
        # 下载图片
        success = download_image(item["url"], local_path)
        
        if success:
            final_results.append({
                "local_path": local_path,
                "original_url": item["url"],
                "description": item["description"],
                "record_tags": item.get("search_tags") or item.get("mock_tags", ["图片"]),
                "source": source
            })
        else:
            # 下载失败也保留信息
            final_results.append({
                "local_path": local_path,
                "original_url": item["url"],
                "description": item["description"],
                "record_tags": item.get("mock_tags", ["图片"]),
                "source": f"{source}_failed"
            })
    
    # 6. 记录到记忆层
    try:
        from utils.memory import MemoryManager
        mm = MemoryManager()
        for img in final_results:
            mm.record_material(img["local_path"], "image", img["record_tags"])
    except Exception as e:
        print(f"[记忆层] 记录素材失败: {e}")
    
    return final_results


def display_images(images: List[Dict]) -> None:
    """
    展示推荐图片
    
    Args:
        images: 图片列表
    """
    print("\n" + "="*60)
    print("推荐图片列表")
    print("="*60)
    
    for i, img in enumerate(images, 1):
        print(f"\n{i}. {img['description']}")
        print(f"   路径: {img['local_path']}")
        print(f"   来源: {img['source']}")
        print(f"   标签: {', '.join(img['record_tags'])}")
        print(f"   原图: {img['original_url'][:50]}..." if len(img['original_url']) > 50 else f"   原图: {img['original_url']}")


def approve_images(images: List[Dict], auto_approve_count: int = 3) -> List[Dict]:
    """
    用户审核图片（原型阶段自动批准前 N 张）
    
    Args:
        images: 图片列表
        auto_approve_count: 自动批准的图片数量
    
    Returns:
        用户批准的图片列表
    """
    print("\n" + "="*60)
    print("图片审核")
    print("="*60)
    
    approved = []
    for i, img in enumerate(images, 1):
        print(f"\n图片 {i}: {img['description']}")
        print(f"标签: {', '.join(img['record_tags'])}")
        
        if i <= auto_approve_count:
            print("[OK] 已批准")
            approved.append(img)
        else:
            print("[SKIP] 已跳过")
    
    print(f"\n共批准 {len(approved)} 张图片")
    return approved


# ==================== 命令行入口 ====================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="抖音图片推荐器")
    parser.add_argument("text", nargs="?", help="文案内容")
    parser.add_argument("--count", type=int, default=6, help="推荐图片数量")
    parser.add_argument("--no-api", action="store_true", help="不使用 API（仅模拟数据）")
    parser.add_argument("--save-dir", default="approved_images", help="保存目录")
    parser.add_argument("--test", action="store_true", help="运行测试模式")
    
    args = parser.parse_args()
    
    if args.test or not args.text:
        # 测试模式
        test_cases = [
            "我家猫今天又把花瓶推倒了",
            "今天做了一道超级好吃的红烧肉",
            "周末和朋友一起去海边玩",
            "分享一下我的日常穿搭",
        ]
        
        print("="*60)
        print("图片推荐器 - 测试模式")
        print("="*60)
        
        for case in test_cases:
            print(f"\n文案: {case}")
            print("-"*60)
            
            images = recommend_images(case, use_api=False, count=4)
            display_images(images)
            approved = approve_images(images)
            print()
    else:
        # 正常模式
        use_api = not args.no_api
        images = recommend_images(
            args.text, 
            use_api=use_api, 
            save_dir=args.save_dir,
            count=args.count
        )
        display_images(images)
