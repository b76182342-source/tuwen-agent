"""
智能黑箱：基于 RAG 的自动路径推理

功能：
1. 检索成功案例
2. 提取成功模式
3. 推荐最优执行路径
"""
import json
from typing import List, Dict

from utils.memory import MemoryManager
from utils.config import extract_keywords


class IntelligentBlackbox:
    """智能黑箱：基于 RAG 的自动路径推理"""

    def __init__(self, memory_manager: MemoryManager = None):
        self.memory = memory_manager or MemoryManager()

    def execute(self, text: str, current_state: dict) -> Dict:
        """
        执行智能黑箱：完整的 RAG 流程

        Args:
            text: 原始文案
            current_state: 当前会话状态

        Returns:
            推荐结果
        """
        # R: 检索成功案例
        cases = self._retrieve_success_cases(text)

        # A: 增强模式分析
        patterns = self._augment_with_patterns(cases, current_state)

        # G: 生成最优路径
        result = self._generate_optimal_path(text, patterns, current_state)

        # 添加检索到的案例供用户参考
        result["reference_cases"] = [
            {
                "text": case.get("text", ""),
                "tags": case.get("tags", ""),
                "score": case.get("evaluation_score", 0),
                "likes": case.get("real_likes", 0)
            }
            for case in cases[:3]
        ]

        return result

    def _retrieve_success_cases(self, text: str, limit: int = 10) -> List[Dict]:
        """检索成功案例（委托 MemoryManager）"""
        all_cases = self.memory.get_successful_publishes(limit * 2)
        similar_cases = self._calculate_similarity(text, all_cases)
        return similar_cases[:limit]

    def _calculate_similarity(self, text: str, cases: List[Dict]) -> List[Dict]:
        """计算文案相似度"""
        similar_cases = []

        for case in cases:
            case_text = case.get("text", "")

            # 简化相似度计算：关键词匹配
            text_keywords = self._extract_keywords(text)
            case_keywords = self._extract_keywords(case_text)

            overlap = len(set(text_keywords) & set(case_keywords))
            similarity = overlap / max(len(text_keywords), len(case_keywords), 1)

            if similarity > 0.3:
                case["similarity"] = similarity
                similar_cases.append(case)

        similar_cases.sort(key=lambda x: x.get("similarity", 0), reverse=True)

        return similar_cases

    def _extract_keywords(self, text: str) -> List[str]:
        """提取关键词（委托共享 extract_keywords）"""
        return extract_keywords(text)

    def _augment_with_patterns(self, cases: List[Dict], current_state: dict) -> Dict:
        """增强模式分析"""
        patterns = {
            "tag_patterns": [],
            "music_patterns": [],
            "score_distribution": []
        }

        for case in cases:
            if case.get("tags"):
                tags = case["tags"].split(",")
                patterns["tag_patterns"].append(tags)

            if case.get("music"):
                music_info = json.loads(case["music"])
                patterns["music_patterns"].append({
                    "name": music_info.get("name"),
                    "style": music_info.get("style")
                })

            patterns["score_distribution"].append(case.get("evaluation_score", 0))

        # 分析高频标签
        tag_frequency = {}
        for tag_list in patterns["tag_patterns"]:
            for tag in tag_list:
                tag_frequency[tag] = tag_frequency.get(tag, 0) + 1

        patterns["top_tags"] = sorted(tag_frequency.items(), key=lambda x: x[1], reverse=True)[:5]

        # 分析高频配乐风格
        style_frequency = {}
        for music in patterns["music_patterns"]:
            style = music.get("style", "未知")
            style_frequency[style] = style_frequency.get(style, 0) + 1

        patterns["top_styles"] = sorted(style_frequency.items(), key=lambda x: x[1], reverse=True)[:3]

        return patterns

    def _generate_optimal_path(self, text: str, patterns: Dict, current_state: dict) -> Dict:
        """生成最优路径"""
        # 简化实现：推荐所有Skill
        recommended_path = ["Skill1", "Skill2", "Skill3", "Skill4"]

        # 生成优化建议
        optimization_suggestions = []

        if patterns.get("top_tags"):
            suggested_tags = [tag[0] for tag in patterns["top_tags"][:3]]
            optimization_suggestions.append(f"建议使用高频成功标签: {', '.join(suggested_tags)}")

        if patterns.get("top_styles"):
            suggested_style = patterns["top_styles"][0][0]
            optimization_suggestions.append(f"建议使用 {suggested_style} 风格配乐")

        return {
            "recommended_path": recommended_path,
            "optimization_suggestions": optimization_suggestions,
            "confidence_score": self._calculate_confidence(patterns),
            "similar_cases_count": len(patterns.get("tag_patterns", []))
        }

    def _calculate_confidence(self, patterns: Dict) -> float:
        """计算推荐置信度"""
        case_count = len(patterns.get("tag_patterns", []))

        if case_count >= 10:
            return 0.9
        elif case_count >= 5:
            return 0.7
        elif case_count >= 3:
            return 0.5
        else:
            return 0.3