"""
通用图文协助 Agent - 主入口

功能：
1. 接收用户输入，语义理解意图
2. 执行分析层 → 决策层 → 调度器 → 评测层
3. 内部自动循环：评分 < 4.0 自动重新推理（最多 3 轮）
4. 输出最佳结果 + 发布预测
"""
from typing import Dict, List, Tuple

from agent.analysis_layer import AnalysisLayer
from agent.decision_layer import DecisionLayer
from agent.lightweight_scheduler import LightweightScheduler
from skills.content_evaluator import evaluate_with_blackbox_option, SCORE_THRESHOLD, _recommend_rollback
from utils.memory import MemoryManager

# 内部自动循环最大次数
MAX_AUTO_ITERATIONS = 3

# 维度 → Skill 映射
_DIM_TO_SKILL = {
    "标签推荐": "Skill1",
    "图片推荐": "Skill2",
    "配乐推荐": "Skill3",
}


class DouyinAgent:
    """通用图文协助 Agent — 带内部自动循环

    所有依赖支持注入，便于测试和替换实现：
        agent = DouyinAgent(
            memory=MockMemoryManager(),
            scheduler=CustomScheduler(),
        )
    """

    def __init__(
        self,
        memory: MemoryManager = None,
        analysis_layer: AnalysisLayer = None,
        decision_layer: DecisionLayer = None,
        scheduler: LightweightScheduler = None,
    ):
        self.memory = memory or MemoryManager()
        self.analysis_layer = analysis_layer or AnalysisLayer()
        self.decision_layer = decision_layer or DecisionLayer()
        self.scheduler = scheduler or LightweightScheduler()

    def run(self, user_input: dict, enable_blackbox: bool = False, conversation_id: str = None) -> Dict:
        """
        运行 Agent（含内部自动循环）

        Args:
            user_input: {"text", "tags", "images", "music"}
            enable_blackbox: 是否启用智能黑箱
            conversation_id: 对话ID

        Returns:
            执行结果（包含循环历史）
        """
        session = self.memory.new_session(user_input.get("text", ""))

        # 加载对话上下文
        context = None
        if conversation_id:
            print(f"[Agent] 加载对话上下文: {conversation_id}")
            context = self.memory.get_context_for_agent(conversation_id)
            print(f"[Agent] 上下文加载完成: {context['message_count']} 条消息")
            self.memory.add_message(
                conversation_id, "user", user_input.get("text", ""),
                {"tags": user_input.get("tags", []), "images": user_input.get("images", []), "music": user_input.get("music", [])}
            )

        # Step 1-2: 分析 + 决策（固定执行一次）
        analysis_result = self.analysis_layer.analyze(user_input, context=context)
        print(f"[Agent] 分析完成: 主题={analysis_result['nlp_features']['topic']}, 基调={analysis_result['nlp_features']['tone']}")

        decision_result = self.decision_layer.decide_skill_combination(analysis_result, user_input, context=context)
        print(f"[Agent] 决策完成: 推荐组合={decision_result['recommended_combination']}, 置信度={decision_result['confidence']:.0%}")

        # Step 3-4: 执行 + 评测（含自动循环）
        execution_result, evaluation_result, loop_history = self._auto_loop(
            decision_result["recommended_combination"],
            user_input,
            session,
            enable_blackbox=enable_blackbox,
            context=context
        )

        # 保存 Agent 回复到对话历史
        if conversation_id:
            response_summary = self._generate_response_summary(execution_result, evaluation_result)
            self.memory.add_message(
                conversation_id, "assistant", response_summary,
                {"evaluation_score": evaluation_result["score"],
                 "evaluation_level": evaluation_result["level"],
                 "agent_suggestions": execution_result["agent_suggestions"],
                 "loop_history": loop_history}
            )

        return {
            "creator_content": execution_result["creator_content"],
            "agent_suggestions": execution_result["agent_suggestions"],
            "evaluation": evaluation_result,
            "decision": decision_result,
            "analysis": analysis_result,
            "session_state": execution_result["session_state"],
            "conversation_id": conversation_id,
            "context": context,
            "loop_history": loop_history,
        }

    # ================================================================
    # 内部自动循环
    # ================================================================

    def _auto_loop(
        self,
        plan: List[str],
        user_input: dict,
        session: dict,
        enable_blackbox: bool = False,
        context: dict = None
    ) -> Tuple[dict, dict, list]:
        """执行 Skill 组合并自动循环直到评分 ≥ 4.0 或达到最大轮次

        Returns:
            (execution_result, evaluation_result, loop_history)
        """
        loop_history = []
        best_execution = None
        best_evaluation = None
        best_score = 0.0

        # 确保 plan 中有 Skill4（评估）
        if "Skill4" not in plan:
            plan = plan + ["Skill4"]

        # 首轮执行
        print("[Agent] === 第 1 轮执行 ===")
        execution_result = self.scheduler.execute_plan(plan, user_input, session, context=context)

        evaluation_result = evaluate_with_blackbox_option(
            user_input.get("text", ""),
            execution_result["session_state"].get("tags", []),
            execution_result["session_state"].get("images", []),
            execution_result["session_state"].get("music", []),
            enable_blackbox=enable_blackbox,
            context=context
        )
        current_score = evaluation_result["score"]
        print(f"[Agent] 第 1 轮评分: {current_score}/5.0 ({evaluation_result['level']})")

        best_execution = execution_result
        best_evaluation = evaluation_result
        best_score = current_score

        loop_history.append({
            "round": 1,
            "score": current_score,
            "level": evaluation_result["level"],
            "action": "初始执行",
            "dimensions": evaluation_result.get("dimensions", {}),
        })

        # 自动循环
        iteration = 0
        while current_score < SCORE_THRESHOLD and iteration < MAX_AUTO_ITERATIONS:
            iteration += 1
            round_num = iteration + 1

            # 定位最低分维度 → 对应 Skill
            dimensions = evaluation_result.get("dimensions", {})
            skill_to_rerun_name = _recommend_rollback(dimensions)

            if not skill_to_rerun_name:
                print(f"[Agent] 无法定位需要优化的维度，停止循环")
                break

            skill_key = _DIM_TO_SKILL.get(skill_to_rerun_name)
            if not skill_key:
                print(f"[Agent] 维度 {skill_to_rerun_name} 无对应 Skill，停止循环")
                break

            print(f"[Agent] === 第 {round_num} 轮执行（自动优化: {skill_to_rerun_name} → {skill_key}）===")

            # 重新执行指定 Skill（参数随轮次变化）
            current_state = execution_result["session_state"]
            updated_state = self.scheduler.execute_single_skill(
                skill_key, current_state, iteration
            )

            # 必须重新评估
            updated_state = self.scheduler.execute_single_skill(
                "Skill4", updated_state, iteration
            )
            evaluation_result = updated_state.get("evaluation", {})
            current_score = evaluation_result.get("score", 0) if isinstance(evaluation_result, dict) else 0

            print(f"[Agent] 第 {round_num} 轮评分: {current_score}/5.0 ({evaluation_result.get('level', '?')})")

            # 更新 execution_result 中的 session_state
            execution_result["session_state"] = updated_state
            execution_result["execution_log"].append({
                "skill": skill_key,
                "status": "auto_rerun",
                "iteration": iteration
            })

            loop_history.append({
                "round": round_num,
                "score": current_score,
                "level": evaluation_result.get("level", "?") if isinstance(evaluation_result, dict) else "?",
                "action": f"自动优化: {skill_to_rerun_name}",
                "skill_rerun": skill_key,
            })

            # 保留最佳结果
            if current_score > best_score:
                best_execution = execution_result
                best_evaluation = evaluation_result
                best_score = current_score

            # 记录到记忆层
            self.memory.record_iteration(
                score=current_score,
                rollback_to=skill_to_rerun_name if current_score < SCORE_THRESHOLD else None,
                reason=f"自动循环第 {iteration} 轮",
                retained_skills=[s for s in plan if s != skill_key]
            )

        # 循环结束：输出结果
        if iteration >= MAX_AUTO_ITERATIONS and best_score < SCORE_THRESHOLD:
            print(f"[Agent] 自动循环 {MAX_AUTO_ITERATIONS} 轮后仍未达标（最佳: {best_score}/5.0），输出当前最优结果")
            best_evaluation["_auto_loop_exhausted"] = True
            best_evaluation["_auto_loop_message"] = (
                f"已自动优化 {MAX_AUTO_ITERATIONS} 轮，当前最佳评分 {best_score}/5.0。"
                + "你可以指定不满意的部分让我重新优化（如'换标签'、'换个配乐'）。"
            )

        if best_score >= SCORE_THRESHOLD:
            print(f"[Agent] ✅ 评分达标 ({best_score}/5.0)，循环结束")

        return best_execution, best_evaluation, loop_history

    # ================================================================
    # 辅助方法
    # ================================================================

    def _generate_response_summary(self, execution_result: dict, evaluation_result: dict) -> str:
        """生成Agent回复摘要"""
        summary_parts = [f"评分: {evaluation_result['score']}/5.0 ({evaluation_result['level']})"]

        suggestions = []
        if execution_result["agent_suggestions"].get("Skill1"):
            suggestions.append(f"推荐标签: {', '.join(execution_result['agent_suggestions']['Skill1'][:5])}")
        if execution_result["agent_suggestions"].get("Skill3"):
            music_list = execution_result["agent_suggestions"]["Skill3"]
            if music_list and isinstance(music_list, list) and len(music_list) > 0:
                suggestions.append(f"推荐配乐: {music_list[0].get('name', '无') if isinstance(music_list[0], dict) else music_list[0]}")
        if suggestions:
            summary_parts.append(" | ".join(suggestions))
        if evaluation_result["suggestions"]:
            summary_parts.append(f"优化建议: {'; '.join(evaluation_result['suggestions'][:2])}")

        return " | ".join(summary_parts)


# 命令行入口
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="通用图文协助 Agent")
    parser.add_argument("--text", type=str, help="文案内容")
    parser.add_argument("--tags", type=str, help="标签（逗号分隔）")
    parser.add_argument("--enable-blackbox", action="store_true", help="启用智能黑箱")

    args = parser.parse_args()

    user_input = {
        "text": args.text or "我家猫今天又把花瓶推倒了，太调皮了！",
        "tags": args.tags.split(",") if args.tags else [],
        "images": [],
        "music": []
    }

    agent = DouyinAgent()
    result = agent.run(user_input, enable_blackbox=args.enable_blackbox)

    print("\n" + "="*60)
    print("执行结果")
    print("="*60)
    print(f"最终评分: {result['evaluation']['score']}/5.0 ({result['evaluation']['level']})")

    # 展示循环历史
    loop_history = result.get("loop_history", [])
    if len(loop_history) > 1:
        print(f"\n自动优化了 {len(loop_history) - 1} 轮:")
        for entry in loop_history:
            action = entry.get("action", "")
            print(f"  第{entry['round']}轮: {entry['score']}/5.0 — {action}")
    elif len(loop_history) == 1:
        print(f"  一轮通过，无需自动优化")

    if result["evaluation"].get("_auto_loop_exhausted"):
        print(f"\n⚠️  {result['evaluation'].get('_auto_loop_message', '')}")

    print(f"\n推荐标签: {result['agent_suggestions'].get('Skill1', [])[:5]}")
    print(f"推荐图片: {len(result['agent_suggestions'].get('Skill2', []))} 张")
    print(f"推荐配乐: {len(result['agent_suggestions'].get('Skill3', []))} 首")