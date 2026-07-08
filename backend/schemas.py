"""
Pydantic 结构化输出模型 — LangChain with_structured_output 使用

每个 LLM 调用点一个模型，消除手动 JSON 解析。
DeepSeek 不支持 response_format: json_schema，使用 method="function_calling"。
"""
from typing import List, Optional
from pydantic import BaseModel, Field


# ============================================================
# server.py 意图路由
# ============================================================

class IntentOutput(BaseModel):
    """LLM 意图分类结果"""
    intent: str = Field(
        description="意图类型: topic(用户给主题/想法需生成文案) | create(已有完整文案) | optimize(希望改进上一轮) | modify(想修改特定组件) | question(提问或闲聊)"
    )
    confidence: float = Field(default=0.5, description="置信度 0.0~1.0")


class CopyOutput(BaseModel):
    """LLM 生成的抖音文案"""
    copy_text: str = Field(description="生成的抖音文案正文，30-120字，不含标签和配乐名")


class ModifyFlags(BaseModel):
    """LLM 解析用户想修改/保留哪些组件"""
    change_copy: bool = Field(default=False, description="用户想修改/更换/优化文案")
    change_tags: bool = Field(default=False, description="用户想修改/更换标签")
    change_images: bool = Field(default=False, description="用户想修改/更换图片")
    change_music: bool = Field(default=False, description="用户想修改/更换配乐")
    keep_copy: bool = Field(default=False, description="用户明确要保留文案")
    keep_tags: bool = Field(default=False, description="用户明确要保留标签")
    keep_images: bool = Field(default=False, description="用户明确要保留图片")
    keep_music: bool = Field(default=False, description="用户明确要保留配乐")


class QuestionAnswer(BaseModel):
    """LLM 对用户问题的回答"""
    answer: str = Field(description="简洁的中文回答，2-4句话")


# ============================================================
# skills/content_evaluator.py
# ============================================================

class DimensionsScore(BaseModel):
    """各维度评分"""
    text_quality: float = Field(default=3.0, description="文案质量 1.0-5.0")
    tag_match: float = Field(default=3.0, description="标签匹配度 1.0-5.0")
    image_richness: float = Field(default=3.0, description="素材丰富度 1.0-5.0")
    music_harmony: float = Field(default=3.0, description="音乐协调性 1.0-5.0")
    completeness: float = Field(default=3.0, description="结构完整性 1.0-5.0")


class EvaluationOutput(BaseModel):
    """LLM 综合评估结果"""
    score: float = Field(description="综合评分 1.0-5.0，保留1位小数")
    level: str = Field(description="评级: 很差/较差/一般/中等偏下/中等/中等偏上/较好/很好")
    report: str = Field(description="Markdown 格式的详细评估报告")
    suggestions: List[str] = Field(default_factory=list, description="优化建议列表，最多3条")
    dimensions: DimensionsScore = Field(description="各维度评分")


# ============================================================
# skills/hashtag_recommender.py
# ============================================================

class TagRankItem(BaseModel):
    """单个标签推荐"""
    tag: str = Field(description="标签名，带 # 前缀，例如 #美食")
    reason: str = Field(description="推荐理由，10字以内")


class TagRankList(BaseModel):
    """LLM 精选的标签列表"""
    tags: List[TagRankItem] = Field(description="按相关度排序的标签列表")


class EmotionOutput(BaseModel):
    """LLM 文案情绪分析"""
    mood: str = Field(description="情绪描述: 搞笑/温馨/伤感/励志/日常/吐槽/兴奋/浪漫/恐怖/怀旧/时尚/美食/旅行等")
    intensity: float = Field(default=0.5, description="情绪强度 0.0-1.0")
    energy: str = Field(default="medium", description="能量级别: high/medium/low")
    keywords: List[str] = Field(default_factory=list, description="关键情绪词，最多5个")


# ============================================================
# skills/image_recommender.py
# ============================================================

class ImageKeywordsOutput(BaseModel):
    """LLM 生成的图片搜索关键词"""
    keywords: List[str] = Field(description="适合图片库搜索的英文关键词，3-5个")


# ============================================================
# skills/music_recommender.py
# ============================================================

class MusicSearchKeyword(BaseModel):
    """单个音乐搜索关键词"""
    keyword: str = Field(description="适合在华语音乐平台搜索的中文短语，如 '民谣 怀旧'")
    style: str = Field(description="音乐风格描述，如 '民谣/怀旧'")
    mood: str = Field(description="情绪描述，如 '安静、深沉'")


class MusicSearchKeywords(BaseModel):
    """LLM 生成的音乐搜索关键词列表"""
    keywords: List[MusicSearchKeyword] = Field(description="3个音乐搜索关键词")


class MusicMatch(BaseModel):
    """从榜单中选出的匹配歌曲"""
    selected_index: int = Field(description="候选歌曲序号，从1开始")
    style: str = Field(description="音乐风格")
    mood: str = Field(description="情绪")
    reason: str = Field(description="推荐理由，20字以内")


class MusicMatchList(BaseModel):
    """LLM 从抖音榜单中精选的匹配歌曲"""
    matches: List[MusicMatch] = Field(description="5首最匹配的歌曲")
