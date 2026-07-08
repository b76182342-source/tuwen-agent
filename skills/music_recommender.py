"""
配乐推荐 Skill
根据标签和文案推荐匹配的抖音配乐。

数据源（按优先级）：
1. 抖音官方音乐榜单 API（热歌榜/飙升榜/原创榜）→ DeepSeek 语义匹配
2. 规则映射回退（TAG_TO_STYLE → STYLE_TO_MUSIC 华语经典曲库）
"""
import os
import re
import json
import requests
from pathlib import Path
from typing import List, Dict, Optional

from utils.config import (
    PROXY, get_chat_model, get_deepseek_api_key,
    get_douyin_client_key, get_douyin_client_secret,
)
from backend.schemas import MusicSearchKeywords, MusicMatchList

# 抖音 token 缓存
_douyin_token_cache = {"token": None, "expires_at": 0}

# 情绪 → 音乐风格映射
EMOTION_TO_STYLE = {
    "搞笑": ["欢快卡点", "搞笑音效", "魔性循环", "轻松搞怪"],
    "温馨": ["轻音乐", "治愈系", "抒情慢歌", "甜蜜旋律"],
    "伤感": ["抒情慢歌", "钢琴曲", "伤感BGM", "走心BGM"],
    "励志": ["动感活力", "大气磅礴", "节奏感强", "史诗BGM"],
    "日常": ["轻松舒缓", "生活BGM", "轻快旋律", "民谣"],
    "吐槽": ["搞笑音效", "魔性循环", "轻松搞怪", "轻松活泼"],
    "兴奋": ["电子音乐", "节奏感强", "动感活力", "鼓点"],
    "浪漫": ["浪漫BGM", "甜蜜旋律", "钢琴曲", "轻音乐"],
    "恐怖": ["悬疑BGM", "低音氛围", "恐怖音效"],
    "怀旧": ["复古BGM", "经典老歌", "钢琴曲", "民谣"],
    "时尚": ["电子音乐", "潮流BGM", "节奏感强", "时尚BGM"],
    "美食": ["轻松舒缓", "美食BGM", "烹饪节奏", "轻松活力"],
    "旅行": ["轻音乐", "自然音效", "治愈系", "大气磅礴"],
}


def _emotion_to_styles(emotion: Dict) -> List[str]:
    """将情绪分析结果转换为音乐风格列表"""
    mood = emotion.get("mood", "日常")
    energy = emotion.get("energy", "medium")
    keywords = emotion.get("keywords", [])

    styles = set()

    # 主情绪映射
    for mood_key, style_list in EMOTION_TO_STYLE.items():
        if mood_key in mood or mood in mood_key:
            styles.update(style_list[:2])
            break

    if not styles:
        styles.update(EMOTION_TO_STYLE.get("日常", [])[:2])

    # 能量调整
    if energy == "high":
        styles.update(["动感活力", "节奏感强"])
    elif energy == "low":
        styles.update(["轻音乐", "舒缓"])

    # 关键词补充
    for kw in keywords:
        for mood_key, style_list in EMOTION_TO_STYLE.items():
            if kw in mood_key or mood_key in kw:
                styles.add(style_list[0])
                break

    return list(styles)[:5]


TAG_TO_STYLE = {
    "萌宠": ["欢快卡点", "搞笑音效", "轻松活泼"],
    "搞笑": ["欢快卡点", "搞笑音效", "魔性循环"],
    "犯二": ["搞笑音效", "魔性循环", "轻松搞怪"],
    "猫咪": ["欢快卡点", "轻松活泼", "软萌可爱"],
    "狗狗": ["欢快卡点", "轻松活泼", "动感活力"],
    "宠物": ["欢快卡点", "轻松活泼", "软萌可爱"],
    
    "美食": ["轻松舒缓", "美食BGM", "烹饪节奏"],
    "教程": ["轻松舒缓", "知识BGM", "教学节奏"],
    "日常": ["轻松舒缓", "生活BGM", "轻快旋律"],
    "做饭": ["美食BGM", "烹饪节奏", "轻松活力"],
    
    "旅行": ["轻音乐", "自然音效", "治愈系"],
    "风景": ["轻音乐", "自然音效", "大气磅礴"],
    "治愈": ["轻音乐", "自然音效", "治愈系"],
    "自然": ["轻音乐", "自然音效", "森林之声"],
    
    "情感": ["抒情慢歌", "钢琴曲", "伤感BGM"],
    "伤感": ["抒情慢歌", "钢琴曲", "伤感BGM"],
    "语录": ["抒情慢歌", "钢琴曲", "走心BGM"],
    "爱情": ["抒情慢歌", "浪漫BGM", "甜蜜旋律"],
    
    "时尚": ["电子音乐", "节奏感强", "潮流BGM"],
    "穿搭": ["电子音乐", "节奏感强", "时尚BGM"],
    "潮流": ["电子音乐", "节奏感强", "潮流BGM"],
    
    "励志": ["激昂", "励志BGM", "正能量"],
    "成长": ["激昂", "励志BGM", "正能量"],
    "勇气": ["激昂", "励志BGM", "热血BGM"],
    
    "文学": ["安静", "民谣", "书香BGM"],
    "读书": ["安静", "民谣", "书香BGM"],
    "感悟": ["安静", "民谣", "思考BGM"],
    
    "毕业": ["怀旧", "青春BGM", "校园风"],
    "青春": ["怀旧", "青春BGM", "校园风"],
    "校园": ["怀旧", "青春BGM", "校园风"],

    "入夏": ["治愈系", "轻音乐", "民谣"],
    "夏天": ["治愈系", "轻音乐", "轻快旋律"],
    "花开": ["治愈系", "轻音乐", "钢琴曲"],
    "海棠": ["治愈系", "民谣", "轻音乐"],
    "蝉鸣": ["自然音效", "治愈系", "安静"],
    "季节": ["轻音乐", "安静", "民谣"],
    "自然": ["轻音乐", "自然音效", "治愈系"],
    "慢生活": ["安静", "民谣", "治愈系"],
    "生活记录": ["民谣", "安静", "轻松舒缓"],
    "文字": ["安静", "民谣", "钢琴曲"],
    "文案": ["安静", "民谣", "钢琴曲"],
    "图文": ["民谣", "安静", "轻松舒缓"],
}

MOOD_TO_STYLE = {
    "开心": ["欢快卡点", "轻松活泼", "动感活力"],
    "快乐": ["欢快卡点", "轻松活泼", "动感活力"],
    "搞笑": ["搞笑音效", "魔性循环", "轻松搞怪"],
    "悲伤": ["抒情慢歌", "钢琴曲", "伤感BGM"],
    "难过": ["抒情慢歌", "钢琴曲", "伤感BGM"],
    "感动": ["抒情慢歌", "钢琴曲", "治愈系"],
    "励志": ["激昂", "励志BGM", "正能量"],
    "热血": ["激昂", "励志BGM", "热血BGM"],
    "安静": ["轻音乐", "安静", "民谣"],
    "治愈": ["轻音乐", "治愈系", "自然音效"],
}

STYLE_TO_MUSIC = {
    "欢快卡点": [
        {"name": "欢快卡点", "mood": "轻松、搞笑", "reason": "节奏明快，提升完播率"},
        {"name": "快乐崇拜", "mood": "开心、活泼", "reason": "经典欢快曲目，受众广"},
    ],
    "搞笑音效": [
        {"name": "搞怪音效", "mood": "搞笑、夸张", "reason": "增强喜剧效果"},
        {"name": "魔性笑声", "mood": "搞笑、幽默", "reason": "引发观众共鸣"},
    ],
    "轻松活泼": [
        {"name": "阳光彩虹小白马", "mood": "快乐、阳光", "reason": "旋律轻快，适合日常"},
        {"name": "小跳蛙", "mood": "俏皮、可爱", "reason": "充满童趣"},
    ],
    "轻松舒缓": [
        {"name": "晚风心里吹", "mood": "放松、温暖", "reason": "适合日常记录"},
        {"name": "这世界那么多人", "mood": "温暖、治愈", "reason": "氛围感强"},
    ],
    "美食BGM": [
        {"name": "干饭人之歌", "mood": "开心、期待", "reason": "增强食欲"},
        {"name": "舌尖上的中国", "mood": "认真、专注", "reason": "经典美食配乐"},
    ],
    "轻音乐": [
        {"name": "菊次郎的夏天", "mood": "治愈、温暖", "reason": "适合风景视频"},
        {"name": "天空之城", "mood": "宁静、深远", "reason": "经典钢琴曲"},
    ],
    "自然音效": [
        {"name": "森林鸟鸣", "mood": "宁静、放松", "reason": "沉浸式体验"},
        {"name": "海浪声声", "mood": "平静、治愈", "reason": "缓解压力"},
    ],
    "抒情慢歌": [
        {"name": "后来", "mood": "伤感、回忆", "reason": "引发情感共鸣"},
        {"name": "遗憾也值得", "mood": "遗憾、释然", "reason": "适合情感语录"},
    ],
    "钢琴曲": [
        {"name": "卡农", "mood": "浪漫、优美", "reason": "经典钢琴曲"},
        {"name": "梦中的婚礼", "mood": "浪漫、憧憬", "reason": "浪漫氛围"},
    ],
    "电子音乐": [
        {"name": "夜曲", "mood": "酷炫、动感", "reason": "节奏感强"},
        {"name": "Fade", "mood": "电子、沉浸", "reason": "流行电子音乐"},
    ],
    "节奏感强": [
        {"name": "野狼disco", "mood": "动感、洗脑", "reason": "节奏强烈"},
        {"name": "无价之姐", "mood": "自信、活力", "reason": "适合时尚穿搭"},
    ],
    "激昂": [
        {"name": "追梦赤子心", "mood": "励志、热血", "reason": "激发斗志"},
        {"name": "平凡之路", "mood": "励志、坚持", "reason": "引发共鸣"},
    ],
    "励志BGM": [
        {"name": "Victory", "mood": "激昂、史诗", "reason": "大气磅礴"},
        {"name": "We Will Rock You", "mood": "热血、团结", "reason": "经典励志"},
    ],
    "安静": [
        {"name": "南山南", "mood": "安静、深沉", "reason": "适合思考类内容"},
        {"name": "成都", "mood": "怀旧、温暖", "reason": "民谣风格"},
    ],
    "民谣": [
        {"name": "成都", "mood": "温暖、怀旧", "reason": "民谣经典"},
        {"name": "南方姑娘", "mood": "温柔、思乡", "reason": "情感细腻"},
    ],
    "怀旧": [
        {"name": "同桌的你", "mood": "青春、回忆", "reason": "校园经典"},
        {"name": "那些年", "mood": "青春、遗憾", "reason": "引发回忆"},
    ],
    "青春BGM": [
        {"name": "起风了", "mood": "青春、追梦", "reason": "充满希望"},
        {"name": "少年", "mood": "青春、活力", "reason": "充满正能量"},
    ],
    "魔性循环": [
        {"name": "江南皮革厂", "mood": "搞笑、魔性", "reason": "洗脑循环"},
        {"name": "PPAP", "mood": "搞怪、洗脑", "reason": "魔性舞蹈"},
    ],
    "软萌可爱": [
        {"name": "可爱颂", "mood": "可爱、俏皮", "reason": "软萌风格"},
        {"name": "学猫叫", "mood": "可爱、治愈", "reason": "适合萌宠"},
    ],
    "治愈系": [
        {"name": "Lemon", "mood": "治愈、温暖", "reason": "日系治愈"},
        {"name": "小幸运", "mood": "幸运、美好", "reason": "温馨治愈"},
    ],
}


def _generate_search_keywords(tags: List[str], text: str = "") -> List[Dict[str, str]]:
    """通过 DeepSeek API 分析标签和文案，生成音乐搜索关键词

    Returns:
        List of dicts like [{"keyword": "民谣 怀旧", "style": "民谣/怀旧", "mood": "安静、深沉"}, ...]
        失败时返回空列表
    """
    if not get_deepseek_api_key():
        print("[搜索词] 未设置 DEEPSEEK_API_KEY，跳过 DeepSeek")
        return []

    prompt = f"""你是一个音乐搜索专家。根据以下标签和文案，生成3个适合在华语音乐平台搜索的中文关键词组合。

标签：{tags}
文案：{text}

要求：
1. keyword 是适合在华语音乐平台搜索的中文短语（如 "民谣 怀旧"、"轻快 可爱"、"励志 摇滚"）
2. style 是音乐风格描述（如 "民谣/怀旧"、"欢快/卡点"、"激昂/摇滚"）
3. mood 是情绪描述（如 "安静、深沉"、"轻松、治愈"、"热血、励志"）"""

    try:
        llm = get_chat_model(temperature=0.7, max_tokens=500)
        structured = llm.with_structured_output(MusicSearchKeywords, method="function_calling")
        result = structured.invoke([
            {"role": "system", "content": "你是一个严格的音乐搜索关键词生成器。"},
            {"role": "user", "content": prompt},
        ])
        if isinstance(result, MusicSearchKeywords):
            converted = [{"keyword": k.keyword, "style": k.style, "mood": k.mood} for k in result.keywords]
            print(f"[搜索词] DeepSeek 生成 {len(converted)} 个搜索关键词: {[k['keyword'] for k in converted]}")
            return converted[:3]
    except Exception as e:
        print(f"[搜索词] DeepSeek 失败: {e}")
    return []


def _search_gd_music(keyword: str, source: str = "netease", count: int = 5) -> List[Dict]:
    """通过 GD Studio Music API 搜索真实歌曲

    Args:
        keyword: 中文搜索关键词
        source: 音乐平台 (netease/tencent/kuwo/kugou/migu)
        count: 返回数量

    Returns:
        List of dicts like [{"song_id": "123", "name": "...", "artist": "...",
                             "album": "...", "platform": "netease"}, ...]
        失败时返回空列表
    """
    url = "https://music-api.gdstudio.xyz/api.php"
    params = {
        "types": "search",
        "source": source,
        "name": keyword,
        "count": count
    }

    try:
        resp = requests.get(url, params=params, proxies=PROXY if PROXY else None, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list) and len(data) > 0:
                results = []
                for item in data:
                    raw_artist = item.get("artist", item.get("singers", ""))
                    if isinstance(raw_artist, list):
                        raw_artist = "、".join(str(a) for a in raw_artist)
                    results.append({
                        "song_id": str(item.get("id", "")),
                        "name": item.get("name", item.get("songname", "")),
                        "artist": raw_artist,
                        "album": item.get("album", ""),
                        "platform": item.get("source", source)
                    })
                print(f"[GD API] 关键词'{keyword}' 返回 {len(results)} 首歌曲")
                return results
            else:
                print(f"[GD API] 关键词'{keyword}' 无搜索结果")
        else:
            print(f"[GD API] HTTP {resp.status_code} for '{keyword}'")
    except requests.exceptions.Timeout:
        print(f"[GD API] 关键词'{keyword}' 请求超时")
    except requests.exceptions.RequestException as e:
        print(f"[GD API] 关键词'{keyword}' 网络错误: {e}")
    except Exception as e:
        print(f"[GD API] 关键词'{keyword}' 异常: {e}")

    return []


def _fetch_music_url(song_id: str, source: str = "netease") -> Optional[str]:
    """获取歌曲可播放 URL

    Args:
        song_id: 歌曲 ID
        source: 音乐平台

    Returns:
        可播放 URL 字符串，失败返回 None
    """
    url = "https://music-api.gdstudio.xyz/api.php"
    params = {
        "types": "url",
        "source": source,
        "id": song_id,
        "br": 320
    }

    try:
        resp = requests.get(url, params=params, proxies=PROXY if PROXY else None, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            play_url = data.get("url", "")
            if play_url:
                print(f"[GD API] 获取 URL 成功: {song_id}")
                return play_url
            else:
                print(f"[GD API] 歌曲 {song_id} 无可用 URL")
        else:
            print(f"[GD API] 获取 URL HTTP {resp.status_code}: {song_id}")
    except requests.exceptions.Timeout:
        print(f"[GD API] 获取 URL 超时: {song_id}")
    except requests.exceptions.RequestException as e:
        print(f"[GD API] 获取 URL 网络错误: {e}")
    except Exception as e:
        print(f"[GD API] 获取 URL 异常: {e}")

    return None


def _recommend_via_gd_api(
    tags: List[str],
    text: str = "",
    source: str = "netease",
    fetch_urls: bool = False
) -> List[Dict]:
    """通过 GD Studio Music API 获取真实歌曲推荐

    三阶段流水线：
    1. DeepSeek 分析内容 → 生成搜索关键词 + style/mood
    2. GD API 按关键词搜索真实歌曲
    3. (可选) 获取可播放 URL

    Args:
        tags: 标签列表
        text: 文案
        source: 音乐平台 (netease/tencent/kuwo/kugou/migu)
        fetch_urls: 是否获取可播放 URL

    Returns:
        真实歌曲推荐列表，失败返回空列表
    """
    # 阶段 1：生成搜索关键词
    keywords = _generate_search_keywords(tags, text)
    if not keywords:
        print("[GD API] 无搜索关键词，跳过真实搜索")
        return []

    # 阶段 2：按关键词搜索真实歌曲
    all_songs = []
    for kw_info in keywords:
        kw = kw_info["keyword"]
        songs = _search_gd_music(kw, source, count=5)
        for song in songs:
            song["style"] = kw_info["style"]
            song["mood"] = kw_info["mood"]
            artist_display = song.get("artist", "未知歌手")
            song["reason"] = f"关键词'{kw}'匹配，{artist_display}演唱"
            song["source"] = song["platform"]
            song["url"] = None
            all_songs.append(song)

    if not all_songs:
        print("[GD API] 所有关键词均无搜索结果")
        return []

    # 阶段 3：按 song_id 去重，取 top 5
    seen_ids = set()
    unique_songs = []
    for song in all_songs:
        sid = song["song_id"]
        if sid and sid not in seen_ids:
            seen_ids.add(sid)
            unique_songs.append(song)
    unique_songs = unique_songs[:5]

    # 阶段 4（默认启用）：获取播放 URL
    if fetch_urls:
        print(f"[GD API] 正在获取 {len(unique_songs)} 首歌曲的播放 URL...")
        for song in unique_songs:
            song["url"] = _fetch_music_url(song["song_id"], song["platform"])
            # 标准化预览字段
            song["preview_url"] = song.get("url")
            song["can_preview"] = bool(song.get("url"))
    else:
        for song in unique_songs:
            song["preview_url"] = None
            song["can_preview"] = False

    print(f"[GD API] 最终推荐 {len(unique_songs)} 首真实歌曲")
    return unique_songs


# ==================== 抖音官方榜单 API ====================

def _get_douyin_access_token() -> Optional[str]:
    """获取抖音开放平台 access_token（OAuth 2.0 client_credentials）

    缓存 2 小时，过期自动刷新。

    Returns:
        access_token 字符串，失败返回 None
    """
    global _douyin_token_cache
    import time

    # 检查缓存
    if _douyin_token_cache["token"] and time.time() < _douyin_token_cache["expires_at"]:
        return _douyin_token_cache["token"]

    client_key = get_douyin_client_key()
    client_secret = get_douyin_client_secret()
    if not client_key or not client_secret:
        print("[抖音] 未设置 DOUYIN_CLIENT_KEY / DOUYIN_CLIENT_SECRET，回退到规则映射")
        return None

    url = "https://open.douyin.com/oauth/client_token/"
    payload = {
        "client_key": client_key,
        "client_secret": client_secret,
        "grant_type": "client_credentials"
    }

    try:
        resp = requests.post(url, data=payload, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            token = data.get("data", {}).get("access_token", "")
            expires_in = data.get("data", {}).get("expires_in", 7200)
            if token:
                _douyin_token_cache = {
                    "token": token,
                    "expires_at": time.time() + expires_in - 300  # 提前 5 分钟刷新
                }
                print(f"[抖音] 获取 access_token 成功，有效期 {expires_in}s")
                return token
            else:
                print(f"[抖音] token 响应异常: {data.get('data', {}).get('description', data)}")
        else:
            print(f"[抖音] 获取 token HTTP {resp.status_code}: {resp.text[:100]}")
    except Exception as e:
        print(f"[抖音] 获取 token 异常: {e}")

    return None


def _get_douyin_music_chart(chart_type: str = "hot", access_token: str = "") -> List[Dict]:
    """获取抖音官方音乐榜单

    Args:
        chart_type: 榜单类型
            - hot: 热歌榜
            - rising: 飙升榜
            - original: 原创榜
        access_token: OAuth token

    Returns:
        标准化歌曲列表 [{song_id, name, artist, cover, duration, usage_count, share_url}]
        失败返回 []
    """
    if not access_token:
        print("[抖音] 无 access_token，跳过榜单获取")
        return []

    # 抖音开放平台榜单 API（实际路径以官方文档为准）
    url = "https://open.douyin.com/data/external/billboard/music/"
    headers = {
        "access-token": access_token,
        "Content-Type": "application/json"
    }
    params = {
        "billboard_type": chart_type
    }

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            songs = data.get("data", {}).get("list", [])
            if not songs:
                print(f"[抖音] 榜单 '{chart_type}' 无数据")
                return []

            results = []
            for item in songs:
                results.append({
                    "song_id": str(item.get("music_id", "")),
                    "name": item.get("title", ""),
                    "artist": item.get("author", ""),
                    "cover": item.get("cover", ""),
                    "duration": item.get("duration", 0),
                    "usage_count": item.get("use_count", 0),
                    "share_url": item.get("share_url", ""),
                })
            print(f"[抖音] 榜单 '{chart_type}' 返回 {len(results)} 首歌曲")
            return results
        elif resp.status_code == 401:
            print("[抖音] access_token 过期或无效")
        else:
            print(f"[抖音] 榜单 HTTP {resp.status_code}: {resp.text[:100]}")
    except Exception as e:
        print(f"[抖音] 榜单获取异常: {e}")

    return []


def _recommend_via_douyin(
    tags: List[str],
    text: str = "",
    chart_type: str = "all"
) -> List[Dict]:
    """通过抖音官方榜单 API 获取配乐推荐

    流程：
    1. 获取抖音热歌榜 + 飙升榜（去重）
    2. DeepSeek 分析内容 → 从榜单中匹配最合适的歌曲
    3. 失败时回退到规则映射

    Args:
        tags: 标签列表
        text: 文案
        chart_type: 榜单类型 (hot/rising/original/all)

    Returns:
        推荐列表，失败返回 []
    """
    # Step 1: 获取 access_token
    token = _get_douyin_access_token()
    if not token:
        return []

    # Step 2: 拉榜单
    chart_types = ["hot", "rising", "original"] if chart_type == "all" else [chart_type]
    all_songs = []
    seen_ids = set()

    for ct in chart_types:
        songs = _get_douyin_music_chart(ct, token)
        for song in songs:
            sid = song["song_id"]
            if sid and sid not in seen_ids:
                seen_ids.add(sid)
                all_songs.append(song)

    if not all_songs:
        print("[抖音] 所有榜单无数据")
        return []

    print(f"[抖音] 榜单去重后共 {len(all_songs)} 首候选歌曲")

    # Step 3: DeepSeek 匹配（从榜单中选最合适的）
    if not get_deepseek_api_key():
        print("[抖音] 无 DeepSeek API Key，返回榜单 Top 5")
        top5 = all_songs[:5]
        for s in top5:
            s["style"] = "热门"
            s["mood"] = "流行"
            s["reason"] = f"抖音热歌榜 Top {all_songs.index(s) + 1}"
            s["source"] = "抖音曲库"
            s["url"] = None
        return top5

    # 构建候选歌曲列表（只传歌名和歌手给 DeepSeek 做匹配）
    candidates = []
    for i, song in enumerate(all_songs[:30]):
        candidates.append(f"{i + 1}. {song['name']} - {song['artist']} (使用量: {song.get('usage_count', 0)})")
    candidates_str = "\n".join(candidates)

    prompt = f"""你是一个抖音配乐推荐专家。以下是抖音当前热门歌曲榜单和用户的内容，请从榜单中选出最匹配的 5 首配乐。

## 用户内容
标签：{tags}
文案：{text}

## 抖音热门歌曲榜单（候选）
{candidates_str}

## 要求
1. 从以上候选歌曲中挑选 5 首最匹配用户内容的
2. 每首给出：selected_index（候选序号数字）、style（风格）、mood（情绪）、reason（推荐理由，20字以内）"""

    try:
        llm = get_chat_model(temperature=0.7, max_tokens=600, timeout=20)
        structured = llm.with_structured_output(MusicMatchList, method="function_calling")
        result = structured.invoke([
            {"role": "system", "content": "你是一个严格的配乐匹配器。"},
            {"role": "user", "content": prompt},
        ])
    except Exception as e:
        print(f"[抖音] DeepSeek 匹配失败: {e}")
        result = None

    if isinstance(result, MusicMatchList):
        results = []
        for m in result.matches[:5]:
            idx = m.selected_index - 1
            if 0 <= idx < len(all_songs):
                song = all_songs[idx]
                results.append({
                    "name": song["name"],
                    "artist": song.get("artist", ""),
                    "cover": song.get("cover", ""),
                    "share_url": song.get("share_url", ""),
                    "song_id": song["song_id"],
                    "platform": "douyin",
                    "style": m.style,
                    "mood": m.mood,
                    "reason": m.reason,
                    "source": "抖音曲库",
                    "url": None
                })
        print(f"[抖音] DeepSeek 匹配完成，推荐 {len(results)} 首")
        return results

    # DeepSeek 匹配失败，返回榜单 Top 5
    print("[抖音] DeepSeek 匹配失败，返回榜单 Top 5")
    top5 = all_songs[:5]
    for i, s in enumerate(top5):
        s["style"] = "热门"
        s["mood"] = "流行"
        s["reason"] = f"抖音热歌榜 Top {i + 1}"
        s["source"] = "抖音曲库"
        s["url"] = None
    return top5


def _analyze_mood_from_text(text: str) -> str:
    """简单分析文案情绪"""
    mood_keywords = {
        "开心": ["开心", "快乐", "高兴", "哈哈", "笑", "幸福"],
        "搞笑": ["搞笑", "搞怪", "幽默", "笑话", "逗比"],
        "悲伤": ["悲伤", "难过", "伤心", "哭", "泪"],
        "感动": ["感动", "泪目", "暖心", "治愈"],
        "励志": ["励志", "加油", "奋斗", "坚持", "勇气"],
        "安静": ["安静", "宁静", "深夜", "独处"],
    }
    for mood, keywords in mood_keywords.items():
        if any(k in text for k in keywords):
            return mood
    return ""


def _recommend_via_rules(tags: List[str], text: str = "", extra_styles: List[str] = None) -> List[Dict]:
    """基于规则映射生成配乐推荐（支持情绪驱动的补充风格）"""
    matched_styles = set()

    # 标签 → 风格
    for tag in tags:
        tag_clean = tag.replace("#", "")
        for keyword, styles in TAG_TO_STYLE.items():
            if keyword in tag_clean:
                matched_styles.update(styles)

    # 情绪驱动的风格（优先级更高）
    if extra_styles:
        matched_styles.update(extra_styles)

    # 文本情绪分析（回退）
    mood = _analyze_mood_from_text(text)
    if mood and mood in MOOD_TO_STYLE:
        matched_styles.update(MOOD_TO_STYLE[mood])

    if not matched_styles:
        matched_styles = {"治愈系", "民谣", "轻音乐"}
    
    music_list = []
    for style in matched_styles:
        if style in STYLE_TO_MUSIC:
            for music in STYLE_TO_MUSIC[style]:
                music_list.append({
                    "name": music["name"],
                    "style": style,
                    "mood": music["mood"],
                    "reason": music["reason"],
                    "source": "抖音曲库"
                })
    
    return music_list


def _deduplicate(music_list: List[Dict]) -> List[Dict]:
    """去重：优先按 song_id，无 song_id 时按 name"""
    seen_ids = set()
    seen_names = set()
    unique = []
    for m in music_list:
        sid = m.get("song_id", "")
        if sid:
            if sid not in seen_ids:
                seen_ids.add(sid)
                unique.append(m)
        else:
            name = m.get("name", "")
            if name and name not in seen_names:
                seen_names.add(name)
                unique.append(m)
    return unique


def recommend_music(
    tags: List[str],
    text: str = "",
    use_api: bool = True,
    source: str = "netease",
    fetch_urls: bool = False,
    chart_type: str = "all",
    emotion: Optional[Dict] = None,
) -> List[Dict]:
    """主函数：优先抖音官方榜单 API，失败则用规则映射

    Args:
        tags: 标签列表（如 ["#猫咪日常", "#萌宠"]）
        text: 文案（可选）
        use_api: 是否使用 API
        source: 数据源
        fetch_urls: 是否获取可播放 URL
        chart_type: 抖音榜单类型
        emotion: 情绪分析结果（从 analyze_emotion 获取）

    Returns:
        推荐配乐列表
    """
    music_list = []

    # 情绪驱动的风格标签
    emotion_styles = []
    if emotion:
        emotion_styles = _emotion_to_styles(emotion)
        print(f"[配乐] 情绪分析: {emotion.get('mood', '?')} → {emotion_styles}")

    if use_api:
        if source == "douyin":
            api_result = _recommend_via_douyin(tags, text, chart_type)
        else:
            api_result = _recommend_via_gd_api(tags, text, source, fetch_urls)
        if api_result:
            music_list = api_result

    if not music_list:
        print("[配乐推荐] 使用规则映射")
        music_list = _recommend_via_rules(tags, text, extra_styles=emotion_styles)

    music_list = _deduplicate(music_list)[:5]

    try:
        from utils.memory import MemoryManager
        memory = MemoryManager(Path(__file__).parent.parent)
        for music in music_list:
            tags_for_memory = [
                music.get("style", ""),
                music.get("mood", ""),
                music.get("artist", ""),
                music.get("album", ""),
                music.get("platform", "")
            ]
            record_name = f"{music.get('song_id', '')}_{music['name']}".strip("_")
            memory.record_material(record_name, "music", tags_for_memory)
    except Exception as e:
        print(f"[记忆层] 记录失败: {e}")

    return music_list


def _print_results(music_list: List[Dict]) -> None:
    """打印推荐结果"""
    print("\n" + "=" * 60)
    print("配乐推荐结果")
    print("=" * 60)

    for i, music in enumerate(music_list, 1):
        print(f"\n{i}. {music['name']}")
        artist = music.get("artist", "")
        if artist:
            print(f"   歌手: {artist}")
        album = music.get("album", "")
        if album:
            print(f"   专辑: {album}")
        print(f"   风格: {music['style']}")
        print(f"   情绪: {music['mood']}")
        print(f"   推荐理由: {music['reason']}")
        platform = music.get("platform", music.get("source", ""))
        print(f"   来源: {platform}")
        share_url = music.get("share_url", "")
        if share_url:
            print(f"   抖音链接: {share_url}")
        url = music.get("url")
        if url:
            print(f"   播放: {url[:80]}...")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="配乐推荐 - 默认使用抖音官方音乐榜单 API")
    parser.add_argument("tags", help="标签列表，逗号分隔（如 '#猫咪日常,#萌宠'）")
    parser.add_argument("text", nargs="?", default="", help="文案")
    parser.add_argument("--no-api", action="store_true", help="不使用 API（仅规则映射）")
    parser.add_argument("--source", default="netease",
                        choices=["netease", "tencent", "kuwo", "kugou", "migu", "douyin"],
                        help="数据源：netease等(GD Studio API，默认) / douyin(抖音官方榜单)")
    parser.add_argument("--chart", default="all",
                        choices=["all", "hot", "rising", "original"],
                        help="抖音榜单类型（默认 all，拉全部榜单）")
    parser.add_argument("--fetch-urls", action="store_true", help="获取可播放 URL（仅 GD API）")
    parser.add_argument("--json", action="store_true", help="输出 JSON 格式")

    args = parser.parse_args()

    tags = [t.strip() for t in args.tags.split(",")]
    text = args.text
    use_api = not args.no_api

    result = recommend_music(tags, text, use_api, args.source, args.fetch_urls, args.chart)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        _print_results(result)
