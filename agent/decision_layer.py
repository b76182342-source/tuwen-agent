"""
决策层：基于分析结果推理最优Skill组合

功能：
1. 基于分析结果推理Skill组合
2. 生成执行计划
3. 提供决策依据
"""
from typing import List, Dict


class DecisionLayer:
    """决策层：基于分析结果推理最优Skill组合"""

    def __init__(self):
        self.skill_registry = {
            "Skill1": "标签推荐",
            "Skill2": "图片推荐",
            "Skill3": "配乐推荐",
            "Skill4": "内容评估",
            # Skill5（发布）已注释 — 创作顾问 Agent 不自动发布
            # "Skill5": "图文发布"
        }

    def decide_skill_combination(
        self,
        analysis_result: dict,
        user_input: dict,
        context: dict = None
    ) -> Dict:
        """
        推理最优Skill组合

        Args:
            analysis_result: 分析层的结果
            user_input: 用户输入
            context: 对话上下文（可选）

        Returns:
            决策结果
        """
        combination = []
        reasons = []

        # 如果有上下文，考虑历史决策
        if context and context.get("agent_responses"):
            print(f"[DecisionLayer] 考虑历史决策: {len(context['agent_responses'])} 条Agent回复")
            # 可以在这里添加基于上下文的决策逻辑
            # 例如：如果之前推荐过标签但用户不满意，可以调整推荐策略

        # 决策1：是否需要标签推荐
        if self._need_tag_recommendation(user_input, analysis_result):
            combination.append("Skill1")
            reasons.append(self._get_tag_recommendation_reason(user_input, analysis_result))

        # 决策2：是否需要图片推荐
        if self._need_image_recommendation(user_input, analysis_result):
            combination.append("Skill2")
            reasons.append(self._get_image_recommendation_reason(user_input, analysis_result))

        # 决策3：是否需要配乐推荐
        if self._need_music_recommendation(user_input, analysis_result):
            combination.append("Skill3")
            reasons.append(self._get_music_recommendation_reason(user_input, analysis_result))

        # 决策4：是否需要内容评估
        if self._need_content_evaluation(user_input, analysis_result):
            combination.append("Skill4")
            reasons.append("内容评估是质量把关的必要环节")

        # Skill5（发布）已注释 — 创作顾问 Agent 不自动发布
        # # 决策5：是否需要发布
        # if self._ready_to_publish(user_input, analysis_result):
        #     combination.append("Skill5")
        #     reasons.append("内容完整，可以发布")

        return {
            "recommended_combination": combination,
            "reasons": reasons,
            "confidence": self._calculate_confidence(analysis_result)
        }

    def _need_tag_recommendation(self, user_input: dict, analysis: dict) -> bool:
        """决策：是否需要标签推荐"""
        tags = user_input.get("tags", [])

        # 情况1：用户没有提供标签
        if not tags:
            return True

        # 情况2：标签与文案相似度低
        text_tag_sim = analysis["tag_similarity"]["text_tag_similarity"]
        if text_tag_sim < 0.5:
            return True

        # 情况3：标签不是热点
        tag_hot_sim = analysis["tag_similarity"]["tag_hot_similarity"]
        if tag_hot_sim == 0:
            return True

        return False

    def _need_image_recommendation(self, user_input: dict, analysis: dict) -> bool:
        """决策：是否需要图片推荐"""
        images = user_input.get("images", [])

        # 情况1：用户没有提供图片
        if not images:
            return True

        # 情况2：图片数量不足
        if len(images) < 2:
            return True

        return False

    def _need_music_recommendation(self, user_input: dict, analysis: dict) -> bool:
        """决策：是否需要配乐推荐"""
        music = user_input.get("music", [])

        # 情况1：用户没有提供配乐
        if not music:
            return True

        # 情况2：配乐风格与文案基调不匹配
        tone = analysis["nlp_features"]["tone"]
        if music and music[0].get("style", ""):
            music_style = music[0]["style"]
            if not self._is_music_style_matched(music_style, tone):
                return True

        return False

    def _need_content_evaluation(self, user_input: dict, analysis: dict) -> bool:
        """决策：是否需要内容评估"""
        # 内容评估是质量把关的必要环节，始终需要
        return True

    def _ready_to_publish(self, user_input: dict, analysis: dict) -> bool:
        """决策：是否可以发布"""
        # 检查是否有必要的内容
        has_text = bool(user_input.get("text"))
        has_images = bool(user_input.get("images"))
        has_tags = bool(user_input.get("tags"))

        # 至少需要文案和图片
        return has_text and has_images and has_tags

    def _get_tag_recommendation_reason(self, user_input: dict, analysis: dict) -> str:
        """获取标签推荐的原因"""
        tags = user_input.get("tags", [])

        if not tags:
            return "用户未提供标签，需要推荐"

        text_tag_sim = analysis["tag_similarity"]["text_tag_similarity"]
        if text_tag_sim < 0.5:
            return f"标签与文案相似度较低（{text_tag_sim:.0%}），建议优化"

        tag_hot_sim = analysis["tag_similarity"]["tag_hot_similarity"]
        if tag_hot_sim == 0:
            return "当前标签不是热点，建议添加热点标签"

        return ""

    def _get_image_recommendation_reason(self, user_input: dict, analysis: dict) -> str:
        """获取图片推荐的原因"""
        images = user_input.get("images", [])

        if not images:
            return "用户未提供图片，需要推荐"

        if len(images) < 2:
            return f"图片数量不足（{len(images)}张），建议补充至2-3张"

        return ""

    def _get_music_recommendation_reason(self, user_input: dict, analysis: dict) -> str:
        """获取配乐推荐的原因"""
        music = user_input.get("music", [])

        if not music:
            return "用户未提供配乐，需要推荐"

        tone = analysis["nlp_features"]["tone"]
        music_style = music[0].get("style", "")

        if not self._is_music_style_matched(music_style, tone):
            return f"配乐风格（{music_style}）与文案基调（{tone}）不匹配，建议调整"

        return ""

    def _is_music_style_matched(self, music_style: str, tone: str) -> bool:
        """判断配乐风格是否匹配文案基调"""
        # 简化实现：基于关键词匹配
        if tone == "轻松搞笑":
            return "欢快" in music_style or "搞笑" in music_style
        elif tone == "情感治愈":
            return "抒情" in music_style or "治愈" in music_style
        elif tone == "生活分享":
            return "轻松" in music_style or "生活" in music_style
        else:
            return True

    def _calculate_confidence(self, analysis: dict) -> float:
        """计算决策置信度"""
        # 基于相似案例数量计算置信度
        similar_cases_count = len(analysis["collected_data"].get("similar_cases", []))

        if similar_cases_count >= 10:
            return 0.9
        elif similar_cases_count >= 5:
            return 0.7
        elif similar_cases_count >= 3:
            return 0.5
        else:
            return 0.3