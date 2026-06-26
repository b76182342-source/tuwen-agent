"""
分析层：固定执行的自然语言处理流程

功能：
1. NLP分析（关键词、情感、主题、基调）
2. 标签相似度分析
3. 数据搜集（热点话题、热门音乐、历史案例）
"""
import json
from pathlib import Path
from typing import List, Dict

from skills.content_evaluator import _fetch_douyin_hot_topics, _fetch_douyin_hot_music
from utils.memory import MemoryManager
from utils.config import extract_keywords

_CONFIG_PATH = Path(__file__).parent.parent / "config" / "analysis_rules.json"


def _load_analysis_rules() -> Dict:
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


_ANALYSIS_RULES = _load_analysis_rules()


class AnalysisLayer:
    """分析层：固定执行的自然语言处理流程"""

    def __init__(self, memory: MemoryManager = None):
        self.memory = memory or MemoryManager()

    def analyze(self, user_input: dict, context: dict = None) -> dict:
        """
        执行分析流程

        Args:
            user_input: {
                "text": str,
                "tags": List[str],
                "images": List[dict],
                "music": List[dict]
            }
            context: 对话上下文（可选）

        Returns:
            分析结果
        """
        text = user_input.get("text", "")
        tags = user_input.get("tags", [])

        # 如果有上下文，考虑历史对话
        if context and context.get("last_user_input"):
            print(f"[AnalysisLayer] 考虑历史上下文: {context['message_count']} 条消息")
            # 可以在这里添加基于上下文的分析逻辑
            # 例如：分析用户意图的变化、话题的延续性等

        # Step 1: NLP分析
        nlp_features = self._nlp_analysis(text)

        # Step 2: 标签相似度分析
        tag_similarity = self._tag_similarity_analysis(tags, nlp_features)

        # Step 3: 数据搜集
        collected_data = self._collect_relevant_data(nlp_features, tag_similarity)

        return {
            "nlp_features": nlp_features,
            "tag_similarity": tag_similarity,
            "collected_data": collected_data
        }

    def _nlp_analysis(self, text: str) -> dict:
        """NLP分析"""
        return {
            "keywords": self._extract_keywords(text),
            "sentiment": self._analyze_sentiment(text),
            "topic": self._detect_topic(text),
            "tone": self._detect_tone(text),
            "length": len(text),
            "has_question": "?" in text or "吗" in text,
            "has_emotion": self._has_emotion(text)
        }

    def _extract_keywords(self, text: str) -> List[str]:
        """提取关键词（委托共享 extract_keywords）"""
        return extract_keywords(text)

    def _analyze_sentiment(self, text: str) -> str:
        """分析情感（使用配置文件）"""
        sentiment_config = _ANALYSIS_RULES.get("sentiment", {})
        positive_words = sentiment_config.get("positive_words", [])
        negative_words = sentiment_config.get("negative_words", [])
        strong_threshold = sentiment_config.get("strong_threshold", 3)

        if not positive_words or not negative_words:
            positive_words = ["开心", "快乐", "喜欢", "爱", "棒", "好"]
            negative_words = ["难过", "伤心", "讨厌", "恨", "差", "坏"]

        positive_count = sum(1 for word in positive_words if word in text)
        negative_count = sum(1 for word in negative_words if word in text)

        if positive_count > negative_count:
            if positive_count >= negative_count + strong_threshold:
                return "强烈积极"
            return "积极"
        elif negative_count > positive_count:
            if negative_count >= positive_count + strong_threshold:
                return "强烈消极"
            return "消极"
        else:
            return "中性"

    def _detect_topic(self, text: str) -> str:
        """检测主题（使用配置文件）"""
        topic_keywords = _ANALYSIS_RULES.get("topics", {})

        if not topic_keywords:
            topic_keywords = {
                "美食": ["美食", "好吃", "做饭"],
                "旅行": ["旅行", "旅游", "风景"],
                "生活": ["日常", "生活", "分享"],
            }

        keywords = self._extract_keywords(text)
        if keywords:
            for topic, words in topic_keywords.items():
                if any(keyword in text for keyword in words):
                    return topic
            return keywords[0]
        return "生活"

    def _detect_tone(self, text: str) -> str:
        """检测基调（使用配置文件）"""
        tone_patterns = list(_ANALYSIS_RULES.get("tones", {}).items())

        if not tone_patterns:
            tone_patterns = [
                ("轻松搞笑", ["搞笑", "调皮", "哈哈"]),
                ("情感治愈", ["伤感", "难过", "治愈"]),
                ("生活分享", ["美食", "好吃", "日常"]),
            ]

        for tone, words in tone_patterns:
            if any(word in text for word in words):
                return tone

        if "?" in text or "吗" in text:
            return "提问互动"

        return "日常记录"

    def _has_emotion(self, text: str) -> bool:
        """是否包含情绪词（使用配置文件）"""
        emotion_words = _ANALYSIS_RULES.get("emotion_words", [])

        if not emotion_words:
            emotion_words = ["太", "好", "真", "啊", "！", "超"]

        return any(word in text for word in emotion_words)

    def _tag_similarity_analysis(self, tags: List[str], nlp_features: dict) -> dict:
        """标签相似度分析"""
        # 文案-标签相似度
        text_tag_similarity = self._calc_text_tag_similarity(tags, nlp_features)

        # 标签-标签相似度
        tag_tag_similarity = self._calc_tag_tag_similarity(tags)

        # 标签-热点相似度
        tag_hot_similarity = self._calc_tag_hot_similarity(tags)

        return {
            "text_tag_similarity": text_tag_similarity,
            "tag_tag_similarity": tag_tag_similarity,
            "tag_hot_similarity": tag_hot_similarity
        }

    def _calc_text_tag_similarity(self, tags: List[str], nlp_features: dict) -> float:
        """计算文案-标签相似度"""
        if not tags:
            return 0.0

        keywords = nlp_features.get("keywords", [])
        matched_tags = [tag for tag in tags if any(kw in tag for kw in keywords)]

        return len(matched_tags) / len(tags) if tags else 0.0

    def _calc_tag_tag_similarity(self, tags: List[str]) -> float:
        """计算标签-标签相似度"""
        if len(tags) < 2:
            return 1.0

        # 简化实现：检查标签是否有重复主题
        topics = [tag.replace("#", "") for tag in tags]
        unique_topics = set(topics)

        return len(unique_topics) / len(topics)

    def _calc_tag_hot_similarity(self, tags: List[str]) -> float:
        """计算标签-热点相似度"""
        hot_topics = _fetch_douyin_hot_topics()
        hot_tag_names = [t["tag"] for t in hot_topics]

        matched_tags = [tag for tag in tags if tag in hot_tag_names]

        return len(matched_tags) / len(tags) if tags else 0.0

    def _collect_relevant_data(self, nlp_features: dict, tag_similarity: dict) -> dict:
        """搜集相关数据"""
        topic = nlp_features.get("topic", "生活")
        tone = nlp_features.get("tone", "日常记录")

        # 获取热点话题
        hot_topics = _fetch_douyin_hot_topics()

        # 获取热门音乐
        hot_music = _fetch_douyin_hot_music()

        # 获取历史案例
        similar_cases = self._retrieve_similar_cases(nlp_features, tag_similarity)

        # 获取热门标签
        top_tags = self.memory.get_top_tags(10)

        return {
            "hot_topics": hot_topics,
            "hot_music": hot_music,
            "similar_cases": similar_cases,
            "top_tags": top_tags
        }

    def _retrieve_similar_cases(self, nlp_features: dict, tag_similarity: dict) -> List[dict]:
        """检索相似的历史案例"""
        topic = nlp_features.get("topic", "生活")

        # 从记忆层获取发布历史
        history = self.memory.get_publish_history(limit=20)

        # 筛选评分 >= 4.0 的案例
        success_cases = [h for h in history if h.get("evaluation_score", 0) >= 4.0]

        # 简化相似度计算：基于主题匹配
        similar_cases = []
        for case in success_cases:
            case_text = case.get("text") or ""
            if topic in case_text or any(kw in case_text for kw in (nlp_features.get("keywords") or [])):
                similar_cases.append(case)

        return similar_cases[:10]