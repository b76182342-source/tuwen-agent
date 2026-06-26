"""
轻量级调度器：根据决策结果执行Skill组合

功能：
1. 执行Skill组合
2. 管理执行状态
3. 区分创作者内容和Agent建议
"""
from typing import List, Dict

from skills.hashtag_recommender import HashtagRecommender
from skills.image_recommender import recommend_images
from skills.music_recommender import recommend_music
from skills.content_evaluator import evaluate
# Skill5（发布）已注释 — from skills.douyin_publisher import publish
from utils.memory import MemoryManager


class LightweightScheduler:
    """轻量级调度器：根据决策结果执行Skill组合"""

    def __init__(self, memory: MemoryManager = None):
        self.memory = memory or MemoryManager()
        self.skill_registry = {
            "Skill1": HashtagRecommender(),
            "Skill2": recommend_images,
            "Skill3": recommend_music,
            "Skill4": None,  # 评估是函数，不是类
            # Skill5（发布）已注释 — 创作顾问 Agent 不自动发布
            # "Skill5": None
        }

    def execute_plan(
        self,
        plan: List[str],
        user_input: dict,
        session_state: dict,
        context: dict = None
    ) -> Dict:
        """
        执行计划

        Args:
            plan: Skill组合
            user_input: 用户输入
            session_state: 会话状态
            context: 对话上下文（可选）

        Returns:
            执行结果
        """
        # 初始化执行结果
        result = {
            "creator_content": {
                "text": user_input.get("text", ""),
                "tags": user_input.get("tags", []),
                "images": user_input.get("images", []),
                "music": user_input.get("music", [])
            },
            "agent_suggestions": {},
            "execution_log": []
        }

        # 更新会话状态
        session_state.update(user_input)

        # 如果有上下文，考虑历史执行
        if context and context.get("agent_responses"):
            print(f"[Scheduler] 考虑历史执行: {len(context['agent_responses'])} 条Agent回复")
            # 可以在这里添加基于上下文的执行逻辑
            # 例如：如果之前推荐过某些标签，可以避免重复推荐

        # 执行每个Skill
        for skill_name in plan:
            skill_result = self._execute_skill(skill_name, session_state, context)

            # 区分创作者内容和Agent建议
            if skill_name in ["Skill2", "Skill3"]:
                # 可选Skill的结果作为建议
                result["agent_suggestions"][skill_name] = skill_result
            else:
                # 必须执行的Skill直接更新状态
                if skill_name == "Skill1":
                    session_state["tags"] = skill_result
                elif skill_name == "Skill4":
                    session_state["evaluation"] = skill_result

            result["execution_log"].append({
                "skill": skill_name,
                "status": "success" if skill_result else "failed"
            })

        # 保存会话状态
        self.memory.save_session(session_state)

        result["session_state"] = session_state

        return result

    def _execute_skill(self, skill_name: str, session_state: dict, context: dict = None) -> any:
        """执行单个Skill"""
        text = session_state.get("text", "")
        tags = session_state.get("tags", [])
        images = session_state.get("images", [])
        music = session_state.get("music", [])

        if skill_name == "Skill1":
            # 标签推荐
            recommender = self.skill_registry["Skill1"]
            result = recommender.recommend(text)
            return [item["tag"] for item in result]

        elif skill_name == "Skill2":
            # 图片推荐
            result = recommend_images(text)
            return result

        elif skill_name == "Skill3":
            # 配乐推荐（默认获取可播放 URL 用于前端试听）
            result = recommend_music(tags, text, fetch_urls=True)
            return result

        elif skill_name == "Skill4":
            # 内容评估
            result = evaluate(text, tags, images, music)
            return result

        # Skill5（发布）已注释 — 创作顾问 Agent 不自动发布
        # 发布操作由用户手动完成
        # elif skill_name == "Skill5":
        #     image_paths = [img.get("local_path") for img in images if img.get("local_path")]
        #     tag_names = [tag.replace("#", "") for tag in tags]
        #     result = publish(text, image_paths, tag_names)
        #     return result

        return None

    def execute_single_skill(self, skill_name: str, session_state: dict, iteration: int = 0) -> dict:
        """公开方法：执行单个 Skill 并返回更新后的 session_state

        Args:
            skill_name: 'Skill1' / 'Skill2' / 'Skill3' / 'Skill4'
            session_state: 当前会话状态
            iteration: 当前循环轮次（用于参数变化）

        Returns:
            更新后的 session_state
        """
        text = session_state.get("text", "")
        tags = session_state.get("tags", [])
        images = session_state.get("images", [])

        if skill_name == "Skill1":
            # 每轮变化推荐策略，增加多样性
            strategies = ["balanced", "aggressive", "hot_only", "super_only"]
            strategy = strategies[iteration % len(strategies)]
            count = min(10 + iteration * 2, 20)
            recommender = self.skill_registry["Skill1"]
            result = recommender.recommend(text, count=count, strategy=strategy)
            new_tags = [item["tag"] for item in result]
            session_state["tags"] = new_tags
            print(f"[AutoLoop] Skill1 重新执行 (strategy={strategy}, count={count}) → {len(new_tags)} 个标签")

        elif skill_name == "Skill2":
            count = 4 + iteration  # 每轮多要一张图
            result = recommend_images(text, count=count)
            session_state["images"] = result
            print(f"[AutoLoop] Skill2 重新执行 (count={count}) → {len(result) if result else 0} 张图片")

        elif skill_name == "Skill3":
            all_tags = session_state.get("tags", [])
            result = recommend_music(all_tags[:15], text, fetch_urls=True)
            session_state["music"] = result
            print(f"[AutoLoop] Skill3 重新执行 → {len(result) if result else 0} 首配乐")

        elif skill_name == "Skill4":
            result = evaluate(
                session_state.get("text", ""),
                session_state.get("tags", []),
                session_state.get("images", []),
                session_state.get("music", [])
            )
            session_state["evaluation"] = result
            print(f"[AutoLoop] Skill4 重新评估 → {result.get('score', 'N/A')}/5.0")

        return session_state