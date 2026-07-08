"""
LangGraph StateGraph 构建器

14 节点 + 6 条件边 + 重试循环
"""
from typing import Literal, Dict, Any

from langgraph.graph import StateGraph, END

from backend.graph.state import AgentState
from backend.graph.nodes import (
    initialize, classify_intent, generate_copy, optimize_copy,
    parse_modify_intent, question_response, analyze_emotion_node,
    analyze_content, decide_skills,
    execute_all_skills,
    evaluate_node, check_threshold,
    identify_weak_dimension, rerun_skill, rerun_evaluate,
)

MAX_ITERATIONS = 3
SCORE_THRESHOLD = 4.0


# ============================================================
# 条件路由函数（7 条边）
# ============================================================

def route_by_intent(state: AgentState) -> Literal[
    "generate_copy", "optimize_copy", "parse_modify_intent",
    "question_response", "analyze_emotion"
]:
    """classify_intent 后的路由"""
    intent = state.get("intent", "create")
    has_context = state.get("has_context", False)

    if intent == "topic":
        return "generate_copy"
    elif intent == "create":
        return "analyze_emotion"
    elif intent == "optimize" and has_context:
        return "optimize_copy"
    elif intent == "modify" and has_context:
        return "parse_modify_intent"
    elif intent == "question":
        return "question_response"
    # fallback
    return "analyze_emotion"


def route_after_modify(state: AgentState) -> Literal["optimize_copy", "analyze_emotion"]:
    """parse_modify_intent 后的路由"""
    flags = state.get("modify_flags", {})
    if flags.get("change_copy"):
        return "optimize_copy"
    return "analyze_emotion"


def route_by_score(state: AgentState) -> Literal["finalize", "identify_weak", "finalize"]:
    """check_threshold 后按评分和迭代次数路由"""
    evaluation = state.get("evaluation", {})
    score = evaluation.get("score", 0)
    iteration = state.get("iteration", 0)

    if score >= SCORE_THRESHOLD:
        return "finalize"
    elif iteration < MAX_ITERATIONS:
        return "identify_weak"
    else:
        return "finalize"


def route_after_weak(state: AgentState) -> Literal["rerun_skill", "finalize"]:
    """identify_weak_dimension 后路由"""
    error = state.get("error")
    if error == "no_dimensions":
        return "finalize"
    return "rerun_skill"


# ============================================================
# Graph 构建
# ============================================================

def build_graph() -> StateGraph:
    """构建 LangGraph StateGraph，编译并返回"""

    builder = StateGraph(AgentState)

    # ---- 注册节点 ----
    builder.add_node("initialize", initialize)
    builder.add_node("classify_intent", classify_intent)
    builder.add_node("generate_copy", generate_copy)
    builder.add_node("optimize_copy", optimize_copy)
    builder.add_node("parse_modify_intent", parse_modify_intent)
    builder.add_node("question_response", question_response)
    builder.add_node("analyze_emotion", analyze_emotion_node)
    builder.add_node("analyze_content", analyze_content)
    builder.add_node("decide_skills", decide_skills)
    builder.add_node("execute_all_skills", execute_all_skills)
    builder.add_node("evaluate", evaluate_node)
    builder.add_node("check_threshold", check_threshold)
    builder.add_node("identify_weak", identify_weak_dimension)
    builder.add_node("rerun_skill", rerun_skill)
    builder.add_node("rerun_evaluate", rerun_evaluate)

    # ---- 入口 ----
    builder.set_entry_point("initialize")

    # ---- 顺序边 ----
    builder.add_edge("initialize", "classify_intent")

    # 条件路由: intent → 5 路分支
    builder.add_conditional_edges(
        "classify_intent",
        route_by_intent,
        {
            "generate_copy": "generate_copy",
            "optimize_copy": "optimize_copy",
            "parse_modify_intent": "parse_modify_intent",
            "question_response": "question_response",
            "analyze_emotion": "analyze_emotion",
        }
    )

    builder.add_edge("generate_copy", "analyze_emotion")
    builder.add_edge("optimize_copy", "analyze_emotion")

    builder.add_conditional_edges(
        "parse_modify_intent",
        route_after_modify,
        {"optimize_copy": "optimize_copy", "analyze_emotion": "analyze_emotion"}
    )

    builder.add_edge("question_response", END)

    builder.add_edge("analyze_emotion", "analyze_content")
    builder.add_edge("analyze_content", "decide_skills")

    # decide_skills → execute_all_skills（单节点内部并行 Skill1/2/3）
    builder.add_edge("decide_skills", "execute_all_skills")

    # execute_all_skills → evaluate
    builder.add_edge("execute_all_skills", "evaluate")

    builder.add_edge("evaluate", "check_threshold")

    builder.add_conditional_edges(
        "check_threshold",
        route_by_score,
        {"finalize": END, "identify_weak": "identify_weak"}
    )

    builder.add_conditional_edges(
        "identify_weak",
        route_after_weak,
        {"rerun_skill": "rerun_skill", "finalize": END}
    )

    builder.add_edge("rerun_skill", "rerun_evaluate")
    builder.add_edge("rerun_evaluate", "check_threshold")  # 循环边

    return builder


def compile_graph():
    """编译状态图（可缓存复用）"""
    builder = build_graph()
    return builder.compile()


# ============================================================
# 便捷入口
# ============================================================

def run_agent(user_input: dict, conversation_id: str = "") -> Dict[str, Any]:
    """运行 Agent 全流程，返回与旧 /api/agent/run 兼容的 JSON

    Args:
        user_input: {"text": str, "tags": list, "images": list, "music": list}
        conversation_id: 对话 ID

    Returns:
        {"creator_content": ..., "agent_suggestions": ..., "evaluation": ..., "execution_log": ...}
    """
    graph = compile_graph()

    initial_state: AgentState = {
        "user_input": user_input,
        "conversation_id": conversation_id,
        "enable_blackbox": False,
        "intent": "create",
        "session": {},
        "has_context": False,
        "prev_copy_text": "",
        "prev_evaluation": {},
        "prev_tags": [],
        "prev_images": [],
        "prev_music": [],
        "copy_text": user_input.get("text", ""),
        "need_tags": False,
        "need_images": False,
        "need_music": False,
        "modify_flags": {},
        "emotion": {},
        "final_tags": [],
        "final_images": [],
        "final_music": [],
        "evaluation": {},
        "iteration": 0,
        "best_score": 0,
        "best_evaluation": {},
        "best_final_tags": [],
        "best_final_images": [],
        "best_final_music": [],
        "loop_history": [],
        "result": {},
        "execution_log": [],
        "error": None,
    }

    final_state = graph.invoke(initial_state)

    # 构建与旧 API 兼容的响应
    evaluation = final_state.get("evaluation", {})
    best_eval = final_state.get("best_evaluation", {})
    best_score = final_state.get("best_score", 0)
    current_score = evaluation.get("score", 0)

    # 使用最佳结果
    if best_score > current_score and best_eval:
        eval_out = best_eval
    else:
        eval_out = evaluation

    tags = final_state.get("final_tags", [])
    images = final_state.get("final_images", [])
    music = final_state.get("final_music", [])

    showcase = {
        "text": final_state.get("copy_text", "")[:200],
        "tags": tags,
        "images": images,
        "music": music,
        "score": eval_out.get("score", 0),
        "tip": "按这个组合发布，效果更好哦 ✨",
    }

    report = eval_out.get("report", "")
    iteration = final_state.get("iteration", 0)
    if iteration > 0:
        report = f"> 第 {iteration} 轮优化 (最佳评分 {max(best_score, current_score):.1f})\n\n{report}"

    if eval_out.get("score", 0) >= SCORE_THRESHOLD:
        report += "\n\n---\n> ✅ 评分达标，可以发布。"
    elif iteration >= MAX_ITERATIONS:
        report += "\n\n---\n> ⚠️ 已达最大优化次数，输出当前最佳结果。"
    else:
        report += "\n\n---\n> ⚠️ 评分未达 4.0。输入\"优化\"我会自动改进。"

    return {
        "creator_content": {
            "text": final_state.get("copy_text", ""),
            "tags": user_input.get("tags", []),
            "images": user_input.get("images", []),
            "music": user_input.get("music", []),
        },
        "agent_suggestions": {
            "Skill1": tags,
            "Skill2": images,
            "Skill3": music,
        },
        "execution_log": final_state.get("execution_log", []),
        "session_state": {
            "text": final_state.get("copy_text", ""),
            "tags": tags,
            "images": images,
            "music": music,
            "evaluation": eval_out,
        },
        "evaluation": {
            "score": eval_out.get("score", 0),
            "level": eval_out.get("level", "未知"),
            "report": report,
            "suggestions": eval_out.get("suggestions", [])[:3],
            "showcase": showcase,
        },
    }
