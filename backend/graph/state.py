"""
LangGraph AgentState — 18 字段 TypedDict

覆盖输入→推理→Skill→评估→循环→输出全流程
"""
from typing import TypedDict, List, Dict, Optional, Any, Annotated
import operator


def _merge_lists(a: list, b: list) -> list:
    """Reducer: 合并两个列表（用于 execution_log 等并行更新）"""
    return (a or []) + (b or [])


def _keep_latest(a: Any, b: Any) -> Any:
    """Reducer: 保留最新值"""
    return b if b else a


class AgentState(TypedDict, total=False):
    # ======== 输入 ========
    user_input: dict          # {text, tags, images, music}
    conversation_id: str
    enable_blackbox: bool

    # ======== 意图 ========
    intent: str               # topic|create|optimize|modify|question

    # ======== 上下文 ========
    session: dict             # 从 MemoryManager 恢复的会话状态
    has_context: bool         # 是否有上轮文案
    prev_copy_text: str       # 上轮文案
    prev_evaluation: dict     # 上轮评估
    prev_tags: list           # 上轮标签
    prev_images: list         # 上轮图片
    prev_music: list          # 上轮配乐

    # ======== 当前文案 ========
    copy_text: str

    # ======== 组件标记 ========
    need_tags: bool
    need_images: bool
    need_music: bool
    modify_flags: dict        # {change_copy, change_tags, change_images, change_music,
                              #  keep_tags, keep_images, keep_music}

    # ======== 情绪 ========
    emotion: dict             # {mood, intensity, energy, keywords}

    # ======== Skill 输出 ========
    final_tags: list
    final_images: list
    final_music: list

    # ======== 评估 + 循环 ========
    evaluation: dict          # {score, level, dimensions, suggestions, report}
    iteration: int
    best_score: float
    best_evaluation: dict
    best_final_tags: list
    best_final_images: list
    best_final_music: list
    loop_history: Annotated[list, _merge_lists]

    # ======== Agent 对话 ========
    dialogue_messages: Annotated[list, _merge_lists]  # ReAct 消息历史
    should_enter_workflow: bool                        # LLM 是否决定进入管线
    workflow_intent_override: str                      # 从 Agent 进入管线时的意图覆盖

    # ======== 终端 ========
    result: dict
    execution_log: Annotated[list, _merge_lists]
    error: Optional[str]
