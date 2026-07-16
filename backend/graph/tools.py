"""
LangChain @tool 包装 — 将现有 Skill 函数暴露为 LangChain Tool

两个用途：
  1. Agent 对话节点：LLM 在自由对话中按需调用工具
  2. Workflow 管线节点：保持确定性流程（当前仍直接 import skills）

enter_creation_workflow 是 Agent → Workflow 的桥梁：
  LLM 判断用户需要完整图文包时调用此工具，触发管线执行。
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
    """根据文案推荐图片素材。

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
    """综合评估创作内容质量，给出 1.0-5.0 评分和改进建议。
    当用户问"这个怎么样"、"帮我看看有什么问题"时使用此工具。

    Args:
        text: 文案内容
        tags: 标签列表
        images: 图片列表（可选）
        music: 配乐列表（可选）

    Returns:
        JSON 字符串: {"score": 4.2, "level": "较好", "report": "...", "dimensions": {...}, ...}
    """
    from skills.content_evaluator import evaluate
    result = evaluate(text, tags, images=images or [], music=music or [])
    return json.dumps(result, ensure_ascii=False, default=str)


@tool
def analyze_emotion_tool(text: str) -> str:
    """分析文案情绪基调，返回情绪类型、强度和关键词。

    Args:
        text: 抖音文案内容

    Returns:
        JSON 字符串: {"mood": "温馨", "energy": "medium", "keywords": ["..."], ...}
    """
    from skills.hashtag_recommender import analyze_emotion
    result = analyze_emotion(text)
    return json.dumps(result, ensure_ascii=False)


@tool
def enter_creation_workflow(reason: str, workflow_intent: str = "topic") -> str:
    """当用户想要生成完整的抖音图文创作素材包时调用此工具，
    进入自动化创作管线（文案生成 → 标签推荐 → 图片推荐 → 配乐推荐 → 综合评估）。

    调用时机：
    - 用户说"帮我写/做一段关于XXX的文案/图文"
    - 用户给了一个主题/想法，需要生成完整的发布素材
    - 对话中发现用户需要全套素材但没有明确说出

    不要滥用：如果用户只是闲聊、提问、或只需要单一建议，用其他工具回答即可。

    Args:
        reason: 为什么判断需要进入完整管线
        workflow_intent: 管线模式，"topic"=需要生成文案（用户只给了想法），"create"=用户已有文案只需补全
    """
    return json.dumps({
        "action": "enter_workflow",
        "reason": reason,
        "workflow_intent": workflow_intent,
    }, ensure_ascii=False)


# ============================================================
# 工具注册表
# ============================================================

ALL_TOOLS = [
    recommend_hashtags,
    recommend_images_tool,
    recommend_music_tool,
    evaluate_content,
    analyze_emotion_tool,
    enter_creation_workflow,
]

# 名称 → 工具映射（Agent 节点中按名查找执行）
TOOL_BY_NAME = {t.name: t for t in ALL_TOOLS}
