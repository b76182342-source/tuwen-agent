# -*- coding: utf-8 -*-
"""
内容评估 Skill
评估图文内容的质量，综合评分 1.0~5.0，并与记忆层的循环机制集成

数据源（按优先级）：
1. 抖音公开数据 API（热点话题、热门音乐）
2. DeepSeek API 综合评估（结构化 JSON 输出）
3. 本地规则评分（维度加权计算）

TODO: [架构] 当前文件超过 900 行，包含抖音数据抓取、热点缓存、API 评估、本地规则评分、报告生成。
      待三库架构落地后，拆分为 douyin_data_client.py、evaluators/text_evaluator.py、
      evaluators/tag_evaluator.py、report_generator.py 等模块。拆分需重新设计接口契约。
"""
import re
import json
import time
import requests
from pathlib import Path
from typing import List, Dict, Optional

from utils.config import (
    PROXY, get_chat_model, get_deepseek_api_key, PROJECT_ROOT,
)
from utils.memory import MemoryManager
from backend.schemas import EvaluationOutput

try:
    from backend.graph.intelligent_blackbox import IntelligentBlackbox
except ImportError:
    IntelligentBlackbox = None

SCORE_THRESHOLD = 4.0

# 预编译正则表达式（提升性能）
_RE_QUESTION = re.compile(r"[？?]")
_RE_TAG_SYMBOLS = re.compile(r'[#@]')

# 抖音公开数据 API 配置
import threading

DOUYIN_API_BASE = "https://www.douyin.com"

# 数据缓存（线程安全）
_cache_lock = threading.Lock()
_cached_hot_topics = []
_cached_hot_music = []
_cache_time = 0
CACHE_DURATION = 300  # 5 分钟缓存

DIMENSION_WEIGHTS = {
    "text_quality": 0.30,
    "tag_match": 0.25,
    "image_richness": 0.20,
    "music_harmony": 0.15,
    "completeness": 0.10
}


# ==================== 抖音公开数据 API ====================

def _fetch_douyin_hot_topics() -> List[Dict]:
    """
    获取抖音热点话题列表（通过公开接口）

    Returns:
        热点话题列表，格式：
        [{"tag": "#热点话题", "hot_value": 12345678, "rank": 1, "is_hot": True}, ...]
    """
    global _cached_hot_topics, _cache_time

    # 检查缓存（读锁）
    with _cache_lock:
        if _cached_hot_topics and (time.time() - _cache_time) < CACHE_DURATION:
            return list(_cached_hot_topics)

    topics = []

    try:
        # 方式1：抖音网页端热点话题接口
        url = "https://www.douyin.com/aweme/v1/web/hot/search/list/"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.douyin.com/"
        }

        resp = requests.get(url, headers=headers, timeout=10, proxies=PROXY if PROXY else None)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("status_code") == 0:
                hot_list = data.get("data", {}).get("word_list", [])
                for item in hot_list[:20]:
                    topic = item.get("word", "")
                    hot_value = item.get("hot_value", 0)
                    rank = item.get("rank", 0)
                    if topic:
                        topics.append({
                            "tag": f"#{topic}",
                            "hot_value": hot_value,
                            "rank": rank,
                            "is_hot": rank <= 10
                        })
                print(f"[抖音数据] 获取到 {len(topics)} 个热点话题")

        # 如果方式1失败，尝试方式2
        if not topics:
            url = "https://www.douyin.com/api/v2/challenge/list/?cursor=0&count=20&type=0"
            resp = requests.get(url, headers=headers, timeout=10, proxies=PROXY if PROXY else None)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status_code") == 0:
                    for item in data.get("data", []):
                        topic = item.get("challenge_info", {}).get("cha_name", "")
                        hot_value = item.get("challenge_info", {}).get("hot_count", 0)
                        if topic:
                            topics.append({
                                "tag": f"#{topic}",
                                "hot_value": hot_value,
                                "rank": len(topics) + 1,
                                "is_hot": True
                            })
                    print(f"[抖音数据] 通过话题列表获取到 {len(topics)} 个热点")

    except Exception as e:
        print(f"[抖音数据] 获取热点话题失败: {e}")

    # 更新缓存（写锁）
    if topics:
        with _cache_lock:
            _cached_hot_topics = list(topics)
            _cache_time = time.time()

    return topics


def _fetch_douyin_hot_music() -> List[Dict]:
    """
    获取抖音热门音乐列表（通过公开接口）

    Returns:
        热门音乐列表，格式：
        [{"name": "歌曲名", "artist": "歌手", "play_count": 12345678, "is_hot": True}, ...]
    """
    global _cached_hot_music, _cache_time

    # 检查缓存（读锁）
    with _cache_lock:
        if _cached_hot_music and (time.time() - _cache_time) < CACHE_DURATION:
            return list(_cached_hot_music)

    music_list = []

    try:
        # 抖音热门音乐接口
        url = "https://www.douyin.com/aweme/v1/web/music/hot/list/"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.douyin.com/"
        }

        resp = requests.get(url, headers=headers, timeout=10, proxies=PROXY if PROXY else None)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("status_code") == 0:
                for item in data.get("data", [])[:20]:
                    music_info = item.get("music", item)
                    name = music_info.get("title", "") or music_info.get("name", "")
                    artist = music_info.get("author", "") or music_info.get("artist", "")
                    play_count = music_info.get("play_count", 0) or music_info.get("hot_count", 0)
                    if name:
                        music_list.append({
                            "name": name,
                            "artist": artist,
                            "play_count": play_count,
                            "is_hot": True
                        })
                print(f"[抖音数据] 获取到 {len(music_list)} 首热门音乐")

    except Exception as e:
        print(f"[抖音数据] 获取热门音乐失败: {e}")

    # 更新缓存（写锁）
    if music_list:
        with _cache_lock:
            _cached_hot_music = list(music_list)
            _cache_time = time.time()

    return music_list


def _is_hot_tag(tag: str, hot_topics: List[Dict] = None) -> bool:
    """
    判断标签是否为抖音热点话题

    Args:
        tag: 标签（带#或不带#）
        hot_topics: 热点话题列表（可选）

    Returns:
        是否为热点标签
    """
    if not hot_topics:
        hot_topics = _fetch_douyin_hot_topics()
    
    tag_clean = tag.replace("#", "")
    for topic in hot_topics:
        topic_clean = topic["tag"].replace("#", "")
        if tag_clean == topic_clean or tag_clean in topic_clean or topic_clean in tag_clean:
            return True
    
    return False


def _get_hot_tag_info(tag: str, hot_topics: List[Dict] = None) -> Optional[Dict]:
    """
    获取热点标签的详细信息

    Args:
        tag: 标签（带#或不带#）
        hot_topics: 热点话题列表（可选）

    Returns:
        热点信息字典，包含 hot_value, rank, is_hot
    """
    if not hot_topics:
        hot_topics = _fetch_douyin_hot_topics()
    
    tag_clean = tag.replace("#", "")
    for topic in hot_topics:
        topic_clean = topic["tag"].replace("#", "")
        if tag_clean == topic_clean or tag_clean in topic_clean or topic_clean in tag_clean:
            return {
                "hot_value": topic["hot_value"],
                "rank": topic["rank"],
                "is_hot": topic["is_hot"],
                "matched_topic": topic["tag"]
            }
    
    return None


def _is_hot_music(music_name: str, hot_music: List[Dict] = None) -> bool:
    """
    判断音乐是否为抖音热门音乐

    Args:
        music_name: 音乐名称
        hot_music: 热门音乐列表（可选）

    Returns:
        是否为热门音乐
    """
    if not hot_music:
        hot_music = _fetch_douyin_hot_music()
    
    name_clean = music_name.lower().strip()
    for music in hot_music:
        music_name_clean = music["name"].lower().strip()
        if name_clean == music_name_clean or name_clean in music_name_clean or music_name_clean in name_clean:
            return True
    
    return False


def _get_hot_music_info(music_name: str, hot_music: List[Dict] = None) -> Optional[Dict]:
    """
    获取热门音乐的详细信息

    Args:
        music_name: 音乐名称
        hot_music: 热门音乐列表（可选）

    Returns:
        音乐信息字典，包含 play_count, artist
    """
    if not hot_music:
        hot_music = _fetch_douyin_hot_music()
    
    name_clean = music_name.lower().strip()
    for music in hot_music:
        music_name_clean = music["name"].lower().strip()
        if name_clean == music_name_clean or name_clean in music_name_clean or music_name_clean in name_clean:
            return {
                "play_count": music["play_count"],
                "artist": music["artist"],
                "is_hot": music["is_hot"],
                "matched_name": music["name"]
            }
    
    return None


# ==================== 评估函数 ====================


def _evaluate_via_api(
    text: str,
    tags: List[str],
    images: List[Dict] = None,
    music: List[Dict] = None
) -> Optional[Dict]:
    """通过 DeepSeek API 进行综合评估"""
    if not get_deepseek_api_key():
        print("[API] 未设置 DEEPSEEK_API_KEY，回退到本地评分")
        return None

    images_info = ""
    if images:
        for i, img in enumerate(images, 1):
            images_info += f"图片{i}: {img.get('description', '未知描述')}\n"

    music_info = ""
    if music:
        for m in music:
            music_info += f"配乐: {m.get('name', '未知')} ({m.get('style', '')} {m.get('mood', '')}人)\n"

    prompt = f"""你是一个抖音内容质量评估专家。请对以下图文内容进行综合评估。

## 内容信息
文案：{text}
标签：{', '.join(tags)}
{images_info}{music_info}

## 评估要求
请从以下维度进行评估（每个维度 1.0~5.0）：
1. 文案质量（30%）：长度适中（30-100字最佳）、是否有问句/悬念/情绪词、原创性
2. 标签匹配度（25%）：标签与文案语义相关性、标签数量（3-8个最佳）
3. 素材丰富度（20%）：图片数量（≥2张加分）、图片描述与文案匹配度
4. 音乐协调性（15%）：配乐风格与内容情绪是否匹配
5. 结构完整性（10%）：是否具备文案+图片+标签+配乐全套"""

    try:
        llm = get_chat_model(temperature=0.3, max_tokens=1500, timeout=20)
        structured = llm.with_structured_output(EvaluationOutput, method="function_calling")
        result = structured.invoke([
            {"role": "system", "content": "你是一个抖音内容质量评估专家。"},
            {"role": "user", "content": prompt},
        ])
    except Exception as e:
        print(f"[API] DeepSeek 评估失败: {e}")
        return None

    if isinstance(result, EvaluationOutput):
        print(f"[API] DeepSeek 评估完成: {result.score}")
        return {
            "score": result.score,
            "level": result.level,
            "report": result.report,
            "suggestions": result.suggestions,
            "dimensions": {
                "text_quality": result.dimensions.text_quality,
                "tag_match": result.dimensions.tag_match,
                "image_richness": result.dimensions.image_richness,
                "music_harmony": result.dimensions.music_harmony,
                "completeness": result.dimensions.completeness,
            }
        }
    return None


def _evaluate_text(text: str) -> Dict:
    """评估文案质量"""
    score = 5.0
    analysis = []

    length = len(text)
    if length < 20:
        score -= 1.0
        analysis.append("文案过短")
    elif length > 200:
        score -= 0.5
        analysis.append("文案过长")
    elif length < 50:
        score -= 0.3
        analysis.append("文案偏短")
    elif 50 <= length <= 120:
        score += 0.2
        analysis.append("文案长度适中")

    if _RE_QUESTION.search(text):
        score += 0.3
        analysis.append("包含问句，增加互动性")

    emotion_words = ["太", "竟然", "真的", "居然", "终于", "又", "竟然会", "果然"]
    if any(word in text for word in emotion_words):
        score += 0.2
        analysis.append("包含情绪词")

    if _RE_TAG_SYMBOLS.search(text):
        score -= 0.3
        analysis.append("避免在文案中直接使用标签符号")

    return {"score": round(min(5.0, max(1.0, score)), 1), "analysis": "; ".join(analysis) if analysis else "文案质量良好"}


def _evaluate_tags(text: str, tags: List[str]) -> Dict:
    """评估标签匹配度（使用抖音真实热点数据）"""
    score = 5.0
    analysis = []

    tag_count = len(tags)
    if tag_count < 3:
        score -= 1.0
        analysis.append(f"标签数量不足（{tag_count}个）")
    elif tag_count > 10:
        score -= 0.5
        analysis.append(f"标签数量过多（{tag_count}个）")
    elif 3 <= tag_count <= 8:
        score += 0.2
        analysis.append(f"标签数量合适（{tag_count}个）")

    matched = 0
    for tag in tags:
        tag_clean = tag.replace("#", "")
        if any(word in text for word in [tag_clean, tag_clean[:2]]):
            matched += 1

    if tag_count > 0:
        match_ratio = matched / tag_count
        if match_ratio < 0.3:
            score -= 1.0
            analysis.append("标签与文案关联度低")
        elif match_ratio > 0.6:
            score += 0.3
            analysis.append("标签与文案关联度高")

    # 使用抖音真实热点数据评估标签热度
    hot_topics = _fetch_douyin_hot_topics()
    hot_tags_in_list = []
    hot_tag_details = []
    
    for tag in tags:
        hot_info = _get_hot_tag_info(tag, hot_topics)
        if hot_info:
            hot_tags_in_list.append(tag)
            hot_tag_details.append(hot_info)
    
    if hot_tags_in_list:
        # 基础加分：每个热点标签 +0.15，最多 +0.5
        bonus = min(0.5, len(hot_tags_in_list) * 0.15)
        score += bonus
        
        # 额外加分：排名前5的超级热点
        super_hot = [h for h in hot_tag_details if h["rank"] <= 5]
        if super_hot:
            score += 0.2 * len(super_hot)
            analysis.append(f"包含{len(super_hot)}个超级热点标签（排名前5）")
        
        # 显示热点详情
        hot_desc = []
        for h in hot_tag_details[:3]:
            rank_info = f"排名第{h['rank']}" if h["rank"] else ""
            hot_desc.append(f"{h['matched_topic']}({rank_info})")
        analysis.append(f"包含{len(hot_tags_in_list)}个抖音热点标签: {', '.join(hot_desc)}")
    
    # 尝试使用本地记忆层数据作为补充
    try:
        mm = MemoryManager(Path(__file__).parent.parent)
        top_tags = mm.get_top_tags(50)
        top_tag_names = [t["tag"] for t in top_tags]
        local_hot_tags = [t for t in tags if t in top_tag_names]
        if local_hot_tags and not hot_tags_in_list:
            score += 0.2 * min(1.0, len(local_hot_tags) / 3)
            analysis.append(f"包含{len(local_hot_tags)}个历史热门标签")
    except Exception:
        pass

    return {"score": round(min(5.0, max(1.0, score)), 1), "analysis": "; ".join(analysis) if analysis else "标签匹配良好"}


def _evaluate_images(images: List[Dict] = None) -> Dict:
    """评估素材丰富度"""
    score = 5.0
    analysis = []

    if not images:
        score -= 2.0
        analysis.append("无图片")
        return {"score": round(min(5.0, max(1.0, score)), 1), "analysis": "; ".join(analysis)}

    img_count = len(images)
    if img_count == 1:
        score -= 0.5
        analysis.append("仅1张图片，建议≥2张")
    elif img_count >= 3:
        score += 0.3
        analysis.append(f"图片数量充足（{img_count}张）")

    has_descriptions = sum(1 for img in images if img.get("description"))
    if has_descriptions / img_count < 0.5:
        score -= 0.5
        analysis.append("部分图片缺少描述")

    sources = set(img.get("source", "unknown") for img in images)
    if "unsplash" in sources:
        score += 0.2
        analysis.append("使用高质量 Unsplash 图片")

    return {"score": round(min(5.0, max(1.0, score)), 1), "analysis": "; ".join(analysis) if analysis else "素材丰富"}


def _evaluate_music(music: List[Dict] = None, tags: List[str] = None) -> Dict:
    """评估音乐协调性（使用抖音真实热门音乐数据）"""
    score = 5.0
    analysis = []

    if not music:
        score -= 1.5
        analysis.append("无配乐")
        return {"score": round(min(5.0, max(1.0, score)), 1), "analysis": "; ".join(analysis)}

    music_info = music[0] if music else {}
    music_name = music_info.get("name", "")
    music_style = music_info.get("style", "")
    music_mood = music_info.get("mood", "")

    # 使用抖音真实热门音乐数据评估
    hot_music = _fetch_douyin_hot_music()
    hot_info = _get_hot_music_info(music_name, hot_music)
    
    if hot_info:
        score += 0.4
        play_count = hot_info["play_count"]
        if play_count >= 10000000:
            score += 0.2
            analysis.append(f"使用抖音超级热门音乐《{hot_info['matched_name']}》（使用量超千万）")
        elif play_count >= 1000000:
            analysis.append(f"使用抖音热门音乐《{hot_info['matched_name']}》（使用量超百万）")
        else:
            analysis.append(f"使用抖音热门音乐《{hot_info['matched_name']}》")
    else:
        analysis.append("配乐非抖音当前热门")

    tag_text = "".join(tags) if tags else ""
    positive_tags = ["萌宠", "搞笑", "开心", "美食", "旅行", "时尚"]
    negative_tags = ["伤感", "悲伤", "情感"]

    if any(t in tag_text for t in positive_tags):
        if "欢快" in music_style or "轻松" in music_style or "搞笑" in music_style:
            score += 0.3
            analysis.append("配乐风格与内容情绪匹配")
    elif any(t in tag_text for t in negative_tags):
        if "抒情" in music_style or "钢琴" in music_style or "伤感" in music_style:
            score += 0.3
            analysis.append("配乐风格与内容情绪匹配")
        else:
            score -= 0.3
            analysis.append("配乐风格与内容情绪可能不匹配")

    if music_mood:
        score += 0.2
        analysis.append(f"配乐情绪：{music_mood}")

    return {"score": round(min(5.0, max(1.0, score)), 1), "analysis": "; ".join(analysis) if analysis else "配乐协调"}


def _evaluate_completeness(text: str, tags: List, images: List, music: List) -> Dict:
    """评估结构完整性"""
    score = 5.0
    analysis = []

    if not text:
        score -= 2.0
        analysis.append("缺少文案")
    else:
        analysis.append("文案完整")

    if not tags:
        score -= 1.0
        analysis.append("缺少标签")
    else:
        analysis.append("标签完整")

    if not images:
        score -= 1.0
        analysis.append("缺少图片")
    else:
        analysis.append("图片完整")

    if not music:
        score -= 1.0
        analysis.append("缺少配乐")
    else:
        analysis.append("配乐完整")

    return {"score": round(min(5.0, max(1.0, score)), 1), "analysis": "; ".join(analysis)}


def _generate_report(
    text: str,
    tags: List[str],
    images: List[Dict],
    music: List[Dict],
    dimensions: Dict
) -> str:
    """生成 Markdown 格式评估报告"""
    report = "## 内容质量评估报告\n\n"

    report += "### 内容概览\n"
    report += f"- 文案长度：{len(text)} 字\n"
    report += f"- 标签数量：{len(tags)} 个\n"
    report += f"- 图片数量：{len(images)} 张\n"
    report += f"- 配乐：{music[0].get('name', '未选择') if music else '未选择'}\n\n"

    report += "### 维度评分\n\n"
    report += "| 维度 | 得分 | 权重 | 说明 |\n"
    report += "|------|------|------|------|\n"

    dim_names = {
        "text_quality": "文案质量",
        "tag_match": "标签匹配",
        "image_richness": "素材丰富度",
        "music_harmony": "音乐协调",
        "completeness": "结构完整"
    }

    suggestions = []

    for dim_key, weight in DIMENSION_WEIGHTS.items():
        dim_data = dimensions.get(dim_key, {})
        score = dim_data.get("score", 0)
        analysis = dim_data.get("analysis", "")
        report += f"| {dim_names.get(dim_key, dim_key)} | {score} | {weight*100:.0f}% | {analysis} |\n"

        if score < 3.5:
            suggestions.append(f"**{dim_names.get(dim_key)}** 需要改进：{analysis}")

    report += "\n### 优化建议\n\n"
    if suggestions:
        for i, s in enumerate(suggestions[:3], 1):
            report += f"{i}. {s}\n"
    else:
        report += "内容质量良好，可直接发布。\n"

    exposure = _predict_exposure(dimensions.get("completeness", {}).get("score", 3.0), tags)
    report += f"\n### 预期效果\n\n"
    report += f"- 预测曝光范围：{exposure}\n"
    report += f"- 建议发布时段：{_suggest_time(tags)}\n"

    return report


def _predict_exposure(avg_score: float, tags: List[str]) -> str:
    """预测曝光范围"""
    base_views = 500

    if avg_score >= 4.5:
        multiplier = 3.0
        range_str = "5000~20000"
    elif avg_score >= 4.0:
        multiplier = 2.0
        range_str = "2000~8000"
    elif avg_score >= 3.5:
        multiplier = 1.5
        range_str = "1000~3000"
    elif avg_score >= 3.0:
        multiplier = 1.0
        range_str = "500~1500"
    else:
        multiplier = 0.5
        range_str = "100~500"

    try:
        mm = MemoryManager(Path(__file__).parent.parent)
        top_tags = mm.get_top_tags(10)
        top_tag_names = [t["tag"] for t in top_tags]
        if any(t in tags for t in top_tag_names):
            range_str = f"{int(int(range_str.split('~')[0]) * 1.5)}~{int(int(range_str.split('~')[1]) * 1.5)}"
    except Exception:
        pass

    return range_str


def _suggest_time(tags: List[str]) -> str:
    """建议发布时段"""
    tag_text = " ".join(tags)

    if any(t in tag_text for t in ["美食", "早餐", "午餐", "晚餐"]):
        return "11:00-13:00 或 17:00-19:00（饭点前）"
    elif any(t in tag_text for t in ["萌宠", "搞笑", "日常"]):
        return "12:00-13:00 或 21:00-23:00（休息时间）"
    elif any(t in tag_text for t in ["时尚", "穿搭", "美妆"]):
        return "10:00-12:00 或 20:00-22:00（购物时段）"
    elif any(t in tag_text for t in ["励志", "成长", "职场"]):
        return "08:00-09:00 或 22:00-23:00（通勤/睡前）"
    else:
        return "12:00-13:00 或 18:00-20:00（黄金时段）"


def _recommend_rollback(dimensions: Dict) -> str:
    """根据最低分维度推荐回滚 Skill"""
    dim_scores = {
        "tag_match": ("标签推荐", dimensions.get("tag_match", {}).get("score", 5.0) if isinstance(dimensions.get("tag_match"), dict) else dimensions.get("tag_match", 5.0)),
        "image_richness": ("图片推荐", dimensions.get("image_richness", {}).get("score", 5.0) if isinstance(dimensions.get("image_richness"), dict) else dimensions.get("image_richness", 5.0)),
        "music_harmony": ("配乐推荐", dimensions.get("music_harmony", {}).get("score", 5.0) if isinstance(dimensions.get("music_harmony"), dict) else dimensions.get("music_harmony", 5.0)),
    }

    sorted_dims = sorted(dim_scores.items(), key=lambda x: x[1][1])

    for dim_key, (skill_name, score) in sorted_dims:
        if score < 3.5:
            return skill_name

    return ""


def evaluate(
    text: str,
    tags: List[str],
    images: List[Dict] = None,
    music: List[Dict] = None,
    use_api: bool = True
) -> Dict:
    """
    主函数：评估内容质量

    Args:
        text: 文案
        tags: 标签列表
        images: 图片信息列表（可选）
        music: 配乐信息列表（可选）
        use_api: 是否使用 API

    Returns:
        评估结果字典
    """
    if use_api:
        api_result = _evaluate_via_api(text, tags, images, music)
        if api_result:
            result = api_result
            dimensions = result.get("dimensions", {})

            if not result.get("suggestions"):
                result["suggestions"] = []

            should_loop = result.get("score", 5.0) < SCORE_THRESHOLD
            if should_loop:
                rollback_skill = _recommend_rollback(dimensions)
                if rollback_skill:
                    result["suggestions"].append(f"建议回滚到 {rollback_skill} 重新生成")

            return result

    print("[评估] 使用本地规则评分")
    text_eval = _evaluate_text(text)
    tag_eval = _evaluate_tags(text, tags)
    image_eval = _evaluate_images(images)
    music_eval = _evaluate_music(music, tags)
    complete_eval = _evaluate_completeness(text, tags, images or [], music or [])

    dimensions = {
        "text_quality": text_eval,
        "tag_match": tag_eval,
        "image_richness": image_eval,
        "music_harmony": music_eval,
        "completeness": complete_eval
    }

    total_score = sum(
        dimensions[dim].get("score", 3.0) * weight
        for dim, weight in DIMENSION_WEIGHTS.items()
    )

    if total_score >= 4.5:
        level = "很好"
    elif total_score >= 4.0:
        level = "较好"
    elif total_score >= 3.5:
        level = "中等偏上"
    elif total_score >= 3.0:
        level = "中等"
    elif total_score >= 2.5:
        level = "中等偏下"
    elif total_score >= 2.0:
        level = "一般"
    elif total_score >= 1.5:
        level = "较差"
    else:
        level = "很差"

    suggestions = []
    for dim_key, dim_data in dimensions.items():
        if dim_data.get("score", 5.0) < 3.0:
            dim_name = {
                "text_quality": "文案质量",
                "tag_match": "标签匹配",
                "image_richness": "素材丰富度",
                "music_harmony": "音乐协调",
                "completeness": "结构完整"
            }.get(dim_key, dim_key)
            suggestions.append(f"{dim_name}较低：{dim_data.get('analysis', '')}")

    if not suggestions:
        suggestions.append("内容质量良好，可直接发布。")

    should_loop = total_score < SCORE_THRESHOLD
    if should_loop:
        rollback_skill = _recommend_rollback(dimensions)
        if rollback_skill:
            suggestions.append(f"建议回滚到 {rollback_skill} 重新生成")

    report = _generate_report(text, tags, images or [], music or [], dimensions)

    result = {
        "score": round(total_score, 1),
        "level": level,
        "report": report,
        "suggestions": suggestions[:3],
        "dimensions": dimensions
    }

    try:
        mm = MemoryManager(Path(__file__).parent.parent)
        mm.record_iteration(
            score=total_score,
            rollback_to=None if total_score >= SCORE_THRESHOLD else _recommend_rollback(dimensions),
            reason="",
            retained_skills=["标签推荐", "图片推荐", "配乐推荐"]
        )
    except Exception as e:
        print(f"[记忆层] 记录评估结果失败: {e}")

    return result


def _parse_images_arg(images_str: str) -> List[Dict]:
    """解析图片参数"""
    if not images_str:
        return []
    paths = [p.strip() for p in images_str.split(",")]
    return [{"path": p, "description": Path(p).stem} for p in paths if p]


def _parse_music_arg(music_str: str) -> List[Dict]:
    """解析配乐参数"""
    if not music_str:
        return []
    return [{"name": music_str, "style": "", "mood": ""}]


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="内容评估")
    parser.add_argument("text", help="文案内容")
    parser.add_argument("tags", help="标签列表，逗号分隔")
    parser.add_argument("images", nargs="?", default="", help="图片路径，逗号分隔")
    parser.add_argument("music", nargs="?", default="", help="配乐名称")
    parser.add_argument("--no-api", action="store_true", help="不使用 API")
    parser.add_argument("--threshold", type=float, default=4.0, help="分数门槛")

    args = parser.parse_args()

    tags = [t.strip() for t in args.tags.split(",")]
    images = _parse_images_arg(args.images)
    music = _parse_music_arg(args.music)
    use_api = not args.no_api
    
    if args.threshold != 4.0:
        from types import SimpleNamespace
        global_scope = globals()
        global_scope["SCORE_THRESHOLD"] = args.threshold
    
    result = evaluate(args.text, tags, images, music, use_api)
    
    print("\n" + "=" * 60)
    print(f"综合评分：{result['score']} ({result['level']})")
    print("=" * 60)

    if result['score'] < SCORE_THRESHOLD:
        print(f"\n[警告] 综合评分 {result['score']} 低于门槛 {SCORE_THRESHOLD}")

    print(result["report"])

    if result.get("suggestions"):
        print("\n### 优化建议\n")
        for i, s in enumerate(result["suggestions"], 1):
            print(f"{i}. {s}")


def evaluate_with_blackbox_option(
    text: str,
    tags: List[str],
    images: List[Dict] = None,
    music: List[Dict] = None,
    enable_blackbox: bool = False,
    context: dict = None
) -> Dict:
    """
    评估内容，支持智能黑箱选项

    Args:
        enable_blackbox: 用户是否启用智能黑箱
        context: 对话上下文（可选）
    """
    # 正常评估流程
    result = evaluate(text, tags, images, music)

    # 如果评估不通过且用户启用黑箱
    if result["score"] < SCORE_THRESHOLD and enable_blackbox and IntelligentBlackbox:
        blackbox = IntelligentBlackbox(MemoryManager())

        # 执行 RAG 推理
        blackbox_result = blackbox.execute(
            text=text,
            current_state={
                "text": text,
                "tags": tags,
                "images": images,
                "music": music
            }
        )

        # 将黑箱结果添加到评估结果
        result["blackbox_recommendation"] = blackbox_result

        # 提示用户
        result["blackbox_prompt"] = (
            f"智能黑箱已分析 {blackbox_result['similar_cases_count']} 个相似成功案例，"
            f"置信度 {blackbox_result['confidence_score']:.0%}。\n"
            f"推荐执行路径: {blackbox_result['recommended_path']}\n"
            f"是否按照推荐路径重新执行？"
        )

    return result
