"""
LangChain @tool 包装 — 将现有 Skill 函数暴露为 LangChain Tool

核心逻辑不变，仅加 @tool 装饰器。
"""
import json
from typing import List, Optional

from langchain_core.tools import tool


@tool
def recommend_hashtags(text: str) -> str:
    """根据抖音文案推荐热门标签。

    Args:
        text: 抖音文案内容

    Returns:
        JSON 字符串: [{"tag": "#标签名", "reason": "推荐理由"}, ...]
    """
    from skills.hashtag_recommender import HashtagRecommender
    result = HashtagRecommender.recommend(text, count=10)
    return json.dumps(result, ensure_ascii=False)


@tool
def recommend_images_tool(text: str, count: int = 4) -> str:
    """根据文案推荐图片。

    Args:
        text: 抖音文案内容
        count: 推荐图片数量

    Returns:
        JSON 字符串: [{"url": "...", "description": "...", ...}, ...]
    """
    from skills.image_recommender import recommend_images
    result = recommend_images(text, count=count)
    return json.dumps(result, ensure_ascii=False, default=str)


@tool
def recommend_music_tool(tags: List[str], text: str = "") -> str:
    """根据标签和文案推荐配乐。

    Args:
        tags: 情绪标签列表，如 ["#美食", "#温馨"]
        text: 抖音文案内容

    Returns:
        JSON 字符串: [{"name": "...", "artist": "...", "style": "...", ...}, ...]
    """
    from skills.music_recommender import recommend_music
    result = recommend_music(tags, text, use_api=True, fetch_urls=True)
    return json.dumps(result, ensure_ascii=False, default=str)


@tool
def evaluate_content(text: str, tags: List[str],
                     images: Optional[List[dict]] = None,
                     music: Optional[List[dict]] = None) -> str:
    """综合评估创作内容质量。

    Args:
        text: 文案内容
        tags: 标签列表
        images: 图片列表
        music: 配乐列表

    Returns:
        JSON 字符串: {"score": 4.2, "level": "较好", "report": "...", ...}
    """
    from skills.content_evaluator import evaluate
    result = evaluate(text, tags, images=images or [], music=music or [])
    return json.dumps(result, ensure_ascii=False, default=str)


@tool
def analyze_emotion_tool(text: str) -> str:
    """分析文案情绪基调。

    Args:
        text: 抖音文案内容

    Returns:
        JSON 字符串: {"mood": "温馨", "energy": "medium", "keywords": ["..."], ...}
    """
    from skills.hashtag_recommender import analyze_emotion
    result = analyze_emotion(text)
    return json.dumps(result, ensure_ascii=False)


# 全部工具注册表（供 LangGraph Agent 使用）
ALL_TOOLS = [
    recommend_hashtags,
    recommend_images_tool,
    recommend_music_tool,
    evaluate_content,
    analyze_emotion_tool,
]
