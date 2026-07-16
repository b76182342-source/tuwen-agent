"""
LangGraph 节点函数 — 18 个节点

每个节点接收 AgentState，返回 AgentState 的部分更新。
"""
import json
import time
from typing import Dict, Any

from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, SystemMessage

from backend.graph.state import AgentState
from backend.graph.tools import ALL_TOOLS, TOOL_BY_NAME
from backend.constants import (
    MIN_TEXT_LENGTH_FOR_TOPIC, VALID_INTENTS,
    INTENT_TOPIC, INTENT_CREATE, INTENT_OPTIMIZE, INTENT_MODIFY, INTENT_QUESTION,
    MAX_CONTEXT_MSGS,
)
from backend.schemas import (
    IntentOutput, CopyOutput, ModifyFlags, QuestionAnswer,
)
from utils.config import get_chat_model
from utils.memory import MemoryManager

memory = MemoryManager()

# Agent 对话最大 ReAct 迭代次数
MAX_AGENT_ITERATIONS = 5


# ============================================================
# Node 1: initialize — 双层记忆恢复 (DB1 Redis + DB2 SQLite)
# ============================================================

def initialize(state: AgentState) -> Dict[str, Any]:
    """从 DB1 (Redis 摘要) + DB2 (SQLite 完整消息) 恢复会话上下文

    双层设计:
      DB1 摘要 — 供所有节点使用: topic, last_score, user_style, last_tags...
      DB2 消息 — 仅供 agent_dialogue 使用: 完整 LangChain Message 对象列表

    两层独立读、独立写，互不依赖。
    """
    user_input = state.get("user_input", {})
    conversation_id = state.get("conversation_id", "")
    session = {}
    has_context = False
    prev_copy_text = ""
    prev_evaluation = {}
    prev_tags = []
    prev_images = []
    prev_music = []
    dialogue_messages = []
    summary = {}

    if conversation_id:
        # ── DB1: 加载摘要 ──
        try:
            summary = memory.load_session_summary(conversation_id) or {}
            if summary:
                print(f"[Graph:init] DB1 摘要命中: topic={summary.get('topic','?')[:30]} "
                      f"score={summary.get('last_score','?')} rounds={summary.get('total_rounds','?')}")
        except Exception as e:
            print(f"[Graph:init] DB1 摘要加载失败: {e}")
            summary = {}

        # ── 从摘要恢复 Workflow 上下文 ──
        if summary:
            prev_copy_text = summary.get("topic", "")
            prev_evaluation = summary.get("last_evaluation", {})
            prev_tags = summary.get("last_tags", [])
            prev_images = summary.get("last_images", [])
            prev_music = summary.get("last_music", [])
            has_context = bool(prev_copy_text)

        # ── DB2: 加载完整对话消息 ──
        try:
            dialogue_messages = memory.load_dialogue_messages(conversation_id, limit=50)
            if dialogue_messages:
                print(f"[Graph:init] DB2 消息恢复: {len(dialogue_messages)} 条")
        except Exception as e:
            print(f"[Graph:init] DB2 消息加载失败: {e}")
            dialogue_messages = []

        # ── 兜底: 如果 DB1 无摘要，尝试从 DB2 的消息中提取上下文 ──
        if not has_context and dialogue_messages:
            # 从最近的消息中找用户文案
            for msg in reversed(dialogue_messages):
                from langchain_core.messages import HumanMessage
                if isinstance(msg, HumanMessage) and msg.content and \
                   msg.content not in ("优化一下", "换标签", "换个配乐", "重试"):
                    prev_copy_text = msg.content[:120]
                    has_context = True
                    break

        # ── 再兜底: 旧版 add_message 格式 ──
        if not has_context and conversation_id:
            try:
                ctx = memory.get_context_for_agent(conversation_id, max_messages=MAX_CONTEXT_MSGS)
                msgs = ctx.get("messages", [])
                for msg in reversed(msgs):
                    meta = msg.get("metadata")
                    if isinstance(meta, str):
                        meta = json.loads(meta) if meta else {}
                    if isinstance(meta, dict) and meta.get("evaluation"):
                        prev_evaluation = prev_evaluation or meta["evaluation"]
                    if not prev_copy_text and msg.get("role") == "user" and msg.get("content"):
                        prev_copy_text = msg["content"]
                has_context = bool(prev_copy_text)
            except Exception:
                pass

    # ── 构建 session 对象（供旧代码兼容） ──
    session = {
        "summary": summary,
        "has_context": has_context,
    }

    return {
        "session": session,
        "has_context": has_context,
        "prev_copy_text": prev_copy_text,
        "prev_evaluation": prev_evaluation,
        "prev_tags": prev_tags,
        "prev_images": prev_images,
        "prev_music": prev_music,
        "dialogue_messages": dialogue_messages,  # ← Agent 对话直接复用，不需重新加载
        "copy_text": user_input.get("text", ""),
        "iteration": 0,  # 每次请求独立计数，不从 DB1 继承
        "loop_history": summary.get("loop_history", []),
        "execution_log": [],
    }


# ============================================================
# Node 2: classify_intent — LLM 意图分类
# ============================================================

def classify_intent(state: AgentState) -> Dict[str, Any]:
    """LLM 五分类: topic/create/optimize/modify/question"""
    text = state.get("copy_text", "")
    prev_text = state.get("prev_copy_text", "")
    has_context = state.get("has_context", False)
    prev_score = state.get("prev_evaluation", {}).get("score", 0)

    if not text:
        return {"intent": INTENT_CREATE}

    intent_prompt = f"""分析用户输入，判断意图类型。

## 当前状态
{'- 上一轮文案: ' + prev_text[:80] if has_context else '- 全新会话，无历史'}
{'- 上一轮评分: ' + str(prev_score) + '/5.0' if has_context else ''}

## 用户输入
"{text}"

## 意图类型
topic: 用户提出了主题/想法/需求（如"帮我写一段关于春天的文案"）
create: 用户已提供完整文案（如"夕阳把影子拉得很长"）
optimize: 用户希望改进（需有上下文）
modify: 用户想修改特定部分
question: 用户提问或闲聊

只输出 topic / create / optimize / modify / question 中的一个词。"""

    try:
        llm = get_chat_model(temperature=0.1, max_tokens=100, timeout=10)
        structured = llm.with_structured_output(IntentOutput, method="function_calling")
        result = structured.invoke([
            {"role": "system", "content": "你是一个严格的分类器。"},
            {"role": "user", "content": intent_prompt},
        ])
        intent = result.intent.strip().lower()
        if intent not in VALID_INTENTS:
            intent = INTENT_TOPIC if len(text) > MIN_TEXT_LENGTH_FOR_TOPIC and not has_context else INTENT_CREATE
    except Exception as e:
        print(f"[Graph:intent] 失败: {e}")
        intent = INTENT_TOPIC if len(text) > MIN_TEXT_LENGTH_FOR_TOPIC and not has_context else INTENT_CREATE

    print(f"[Graph:intent] '{text[:30]}' → {intent}")
    return {"intent": intent}


# ============================================================
# Node 3: generate_copy — LLM 文案生成
# ============================================================

def generate_copy(state: AgentState) -> Dict[str, Any]:
    """topic 意图：根据用户想法生成抖音文案"""
    text = state.get("copy_text", "")  # 用户的原始想法

    gen_prompt = f"""你是一个抖音文案写手。根据用户的主题/想法，生成一段适合抖音图文的文案。

规则：
1. 30-100字，简短有力
2. 只输出文案正文，不要输出配乐名、标签、BGM、歌手名
3. 不要输出 #标签
4. 可以包含问句或悬念增加互动

用户想法：{text}

直接输出文案正文。"""

    try:
        llm = get_chat_model(temperature=0.8, max_tokens=150, timeout=15)
        structured = llm.with_structured_output(CopyOutput, method="function_calling")
        result = structured.invoke([
            {"role": "system", "content": "你是专业抖音文案写手，只输出文案正文。"},
            {"role": "user", "content": gen_prompt},
        ])
        if result and len(result.copy_text) > 5:
            print(f"[Graph:gen] 生成: {result.copy_text[:40]}...")
            return {
                "copy_text": result.copy_text.strip(),
                "need_tags": True,
                "need_images": True,
                "need_music": True,
            }
    except Exception as e:
        print(f"[Graph:gen] 失败: {e}")

    return {"copy_text": text, "need_tags": True, "need_images": True, "need_music": True}


# ============================================================
# Node 4: optimize_copy — LLM 文案优化/改写
# ============================================================

def optimize_copy(state: AgentState) -> Dict[str, Any]:
    """optimize/modify 意图：优化文案"""
    user_feedback = state.get("copy_text", "")
    prev_text = state.get("prev_copy_text", "")
    prev_eval = state.get("prev_evaluation", {})
    prev_suggestions = prev_eval.get("suggestions", []) if isinstance(prev_eval, dict) else []

    opt_suggestions = "; ".join(prev_suggestions) if prev_suggestions else "提升整体质量"
    rewrite_prompt = f"""优化以下抖音文案。

用户反馈：{user_feedback}
上一轮评估建议：{opt_suggestions}
原文案：{prev_text[:200]}

规则：保持核心主题不变，30-120字。只输出文案正文。"""

    try:
        llm = get_chat_model(temperature=0.8, max_tokens=150, timeout=15)
        structured = llm.with_structured_output(CopyOutput, method="function_calling")
        result = structured.invoke([
            {"role": "system", "content": "你是专业文案优化师，只输出文案正文。"},
            {"role": "user", "content": rewrite_prompt},
        ])
        if result and len(result.copy_text) > 5:
            print(f"[Graph:opt] 优化: {result.copy_text[:40]}...")
            return {"copy_text": result.copy_text.strip()}
    except Exception as e:
        print(f"[Graph:opt] 失败: {e}")

    return {}


# ============================================================
# Node 5: parse_modify_intent — LLM 解析修改意图
# ============================================================

def parse_modify_intent(state: AgentState) -> Dict[str, Any]:
    """modify 意图：LLM 解析用户想改什么"""
    user_feedback = state.get("copy_text", "")

    prompt = f"""分析用户反馈，判断想修改/保留哪些组件。
用户反馈: "{user_feedback}"

输出 JSON: {{change_copy, change_tags, change_images, change_music, keep_copy, keep_tags, keep_images, keep_music}}
- change_*=true: 想修改/更换/优化
- keep_*=true: 明确保留
- "优化一下"=change_copy:true
- "换标签"=change_tags:true
- "换图"=change_images:true
- "换配乐"=change_music:true"""

    try:
        llm = get_chat_model(temperature=0.0, max_tokens=200, timeout=5)
        structured = llm.with_structured_output(ModifyFlags, method="function_calling")
        result = structured.invoke([
            {"role": "system", "content": "JSON 输出器。"},
            {"role": "user", "content": prompt},
        ])
        flags = {
            "change_copy": result.change_copy,
            "change_tags": result.change_tags,
            "change_images": result.change_images,
            "change_music": result.change_music,
            "keep_tags": result.keep_tags,
            "keep_images": result.keep_images,
            "keep_music": result.keep_music,
        }
        print(f"[Graph:modify] {flags}")
        update = {"modify_flags": flags}
        # 不修改文案时，用上一轮文案替换用户的指令文本
        if not flags.get("change_copy"):
            prev = state.get("prev_copy_text", "")
            if prev:
                update["copy_text"] = prev
        return update
    except Exception as e:
        print(f"[Graph:modify] 失败: {e}")

    # 关键词回退
    fb = user_feedback
    flags = {
        "change_copy": any(kw in fb for kw in ["文案", "文字", "风格", "改写", "优化"]),
        "change_tags": any(kw in fb for kw in ["标签", "tag"]),
        "change_images": any(kw in fb for kw in ["图片", "图", "照片"]),
        "change_music": any(kw in fb for kw in ["配乐", "音乐", "bgm"]),
        "keep_tags": False, "keep_images": False, "keep_music": False,
    }
    update = {"modify_flags": flags}
    if not flags["change_copy"]:
        prev = state.get("prev_copy_text", "")
        if prev:
            update["copy_text"] = prev
    return update


# ============================================================
# Node 6: agent_dialogue — ReAct Agent 对话（替代 question_response）
# ============================================================

def agent_dialogue(state: AgentState) -> Dict[str, Any]:
    """Agent 对话节点：LLM + tools 自由交互

    两阶段设计：
      阶段1 — ReAct 循环：LLM 自由调用工具（推荐标签/评估/情绪分析...）
      阶段2 — 路由判断：如果 LLM 调用了 enter_creation_workflow →
              设置 should_enter_workflow=True，走主流程管线

    否则返回对话结果，走到 END。
    """
    text = state.get("copy_text", "")
    prev_text = state.get("prev_copy_text", "")
    prev_tags = state.get("prev_tags", [])
    prev_images = state.get("prev_images", [])
    prev_music = state.get("prev_music", [])
    prev_eval = state.get("prev_evaluation", {})
    conversation_id = state.get("conversation_id", "")

    # ── 构建系统提示 ──
    context_blocks = []
    if prev_text:
        context_blocks.append(f"上一轮文案：{prev_text[:120]}")
    if prev_tags:
        context_blocks.append(f"上一轮标签：{', '.join(prev_tags[:8])}")
    if prev_eval.get("score"):
        context_blocks.append(f"上一轮评分：{prev_eval['score']}/5.0")

    context_str = "\n".join(context_blocks) if context_blocks else "全新会话，无历史记录。"

    system_prompt = f"""你是抖音创作顾问，帮助用户完成图文创作。

## 当前会话状态
{context_str}

## 工作方式
1. 回答用户的创作问题，给出专业建议
2. 如果用户想分析内容，使用 evaluate_content 工具评估
3. 如果用户想了解情绪基调，使用 analyze_emotion_tool 分析
4. 如果用户想看标签/图片/配乐建议，分别调用对应工具
5. **关键**：当用户明确想要一整套完整的创作素材（文案+标签+图片+配乐），
   调用 enter_creation_workflow 进入自动化创作管线。
   - 用户只给主题/想法 → workflow_intent="topic"
   - 用户已有文案 → workflow_intent="create"

## 重要规则
- 不要编造标签或推荐结果，必须通过工具获取
- 每次回复简洁专业，2-5句话
- 如果只是普通问题或闲聊，直接回答，不要调用工具"""

    # ── 加载/初始化对话消息 ──
    dialogue_messages = list(state.get("dialogue_messages", []))

    # 从 SQLite 恢复历史（仅在首次对话时）
    if not dialogue_messages and conversation_id:
        try:
            ctx = memory.get_context_for_agent(conversation_id, max_messages=MAX_CONTEXT_MSGS)
            for msg in ctx.get("messages", []):
                role = msg.get("role", "")
                content = msg.get("content", "")
                if role == "user":
                    dialogue_messages.append(HumanMessage(content=content))
                elif role == "assistant":
                    dialogue_messages.append(AIMessage(content=content))
            if dialogue_messages:
                print(f"[Graph:agent] 从 SQLite 恢复 {len(dialogue_messages)} 条历史消息")
        except Exception as e:
            print(f"[Graph:agent] 加载历史失败: {e}")

    # 追加当前用户消息
    dialogue_messages.append(HumanMessage(content=text))

    # ── ReAct 循环 ──
    llm = get_chat_model(temperature=0.7, max_tokens=600, timeout=30)
    llm_with_tools = llm.bind_tools(ALL_TOOLS)

    should_enter = False
    workflow_intent_override = "topic"
    final_answer = ""
    tool_log = []

    for iteration in range(MAX_AGENT_ITERATIONS):
        try:
            response = llm_with_tools.invoke(
                [SystemMessage(content=system_prompt)] + dialogue_messages
            )
        except Exception as e:
            print(f"[Graph:agent] LLM 调用失败 (iter {iteration}): {e}")
            final_answer = "抱歉，我暂时无法处理你的请求，请稍后重试。"
            break

        dialogue_messages.append(response)

        # 没有工具调用 → Agent 认为对话结束
        if not response.tool_calls:
            final_answer = response.content or ""
            break

        # 处理工具调用
        for tool_call in response.tool_calls:
            tool_name = tool_call.get("name", "")
            tool_args = tool_call.get("args", {})
            tool_id = tool_call.get("id", "")

            print(f"[Graph:agent] 调用工具: {tool_name}({json.dumps(tool_args, ensure_ascii=False)[:80]})")

            tool_func = TOOL_BY_NAME.get(tool_name)
            if tool_func is None:
                result_str = f"未知工具: {tool_name}"
            else:
                try:
                    result_str = tool_func.invoke(tool_args)
                except Exception as e:
                    result_str = f"工具调用失败: {e}"

            # 检测是否触发了 enter_creation_workflow
            if tool_name == "enter_creation_workflow":
                should_enter = True
                workflow_intent_override = tool_args.get("workflow_intent", "topic")
                # 解析工具返回的 JSON
                try:
                    parsed = json.loads(result_str)
                    tool_log.append({
                        "skill": "Agent → Workflow",
                        "status": "triggered",
                        "reason": parsed.get("reason", ""),
                        "timestamp": time.strftime("%H:%M:%S"),
                    })
                except Exception:
                    pass

            dialogue_messages.append(
                ToolMessage(content=str(result_str), tool_call_id=tool_id)
            )
            tool_log.append({
                "skill": tool_name,
                "status": "completed",
                "timestamp": time.strftime("%H:%M:%S"),
            })

        # 如果触发了 enter_creation_workflow，立刻结束循环
        if should_enter:
            final_answer = response.content or "正在为你生成完整的创作素材包..."
            break

    # ── 如果没有显式 final_answer（所有迭代都是工具调用），取最后一次 LLM 回复 ──
    if not final_answer and dialogue_messages:
        for msg in reversed(dialogue_messages):
            if isinstance(msg, AIMessage) and msg.content:
                final_answer = msg.content
                break
    if not final_answer:
        final_answer = "你可以输入'优化'来改进当前内容，或输入'换标签'来更换推荐。"

    # ── 持久化: DB1 摘要 + DB2 完整消息 ──
    if conversation_id:
        # DB2: 全量保存 dialogue_messages（含 ToolMessage、tool_calls）
        try:
            memory.save_dialogue_messages(conversation_id, dialogue_messages)
        except Exception as e:
            print(f"[Graph:agent] DB2 保存失败: {e}")

        # DB1: 更新摘要（从对话中提取关键信息）
        try:
            existing = memory.load_session_summary(conversation_id) or {}
            # 合并已有摘要 + 本轮新信息
            existing["total_rounds"] = existing.get("total_rounds", 0) + 1
            existing["last_updated"] = ""
            # 保留已有偏好，本轮对话如果发现新偏好会追加
            if not existing.get("topic") and text:
                existing["topic"] = text[:80]

            # 从工具调用结果中提取有用信息
            for entry in tool_log:
                if entry.get("skill") == "evaluate_content":
                    existing["last_score"] = entry.get("score", existing.get("last_score", 0))

            memory.save_session_summary(conversation_id, existing)
        except Exception as e:
            print(f"[Graph:agent] DB1 摘要更新失败: {e}")

    # ── 返回状态更新 ──
    result = {
        "dialogue_messages": dialogue_messages,
        "should_enter_workflow": should_enter,
        "execution_log": tool_log,
    }

    if should_enter:
        # 进入管线：覆盖 intent，让后续 analyze_content 正确判断组件需求
        result["intent"] = workflow_intent_override
        result["workflow_intent_override"] = workflow_intent_override
        # 保留 copy_text（用户原始输入），管线中的 generate_copy 节点会处理
        result["evaluation"] = {
            "score": 0,
            "level": "进入创作管线",
            "report": "Agent 已判断需要完整的图文创作流程，正在进入自动化管线...",
            "suggestions": [],
        }
    else:
        # 纯对话：构造兼容旧 API 的 evaluation 结构
        result["evaluation"] = {
            "score": prev_eval.get("score", 0) if prev_eval else 0,
            "level": "对话回复",
            "report": final_answer,
            "suggestions": [],
        }

    print(f"[Graph:agent] {'→ 进入管线' if should_enter else '→ 对话结束'} (工具调用: {len(tool_log)}次)")
    return result


# ============================================================
# Node 7: analyze_emotion — LLM 情绪分析
# ============================================================

def analyze_emotion_node(state: AgentState) -> Dict[str, Any]:
    """分析文案情绪（供 Skill1/Skill3 使用）"""
    from skills.hashtag_recommender import analyze_emotion

    text = state.get("copy_text", "")
    emotion = analyze_emotion(text)
    print(f"[Graph:emotion] mood={emotion.get('mood', '?')} energy={emotion.get('energy', '?')}")
    return {"emotion": emotion}


# ============================================================
# Node 8: analyze_content — Python: 组件需求分析
# ============================================================

def analyze_content(state: AgentState) -> Dict[str, Any]:
    """分析当前状态，决定需要补全哪些组件"""
    intent = state.get("intent", INTENT_CREATE)
    user_input = state.get("user_input", {})
    copy_text = state.get("copy_text", "")
    modify_flags = state.get("modify_flags", {})

    need_tags = False
    need_images = False
    need_music = False

    if intent == INTENT_TOPIC:
        need_tags = need_images = need_music = True

    elif intent == INTENT_CREATE:
        need_tags = not user_input.get("tags")
        need_images = not user_input.get("images")
        need_music = not user_input.get("music")

    elif intent in (INTENT_OPTIMIZE, INTENT_MODIFY):
        if modify_flags.get("change_copy"):
            need_tags = not modify_flags.get("keep_tags")
            need_music = not modify_flags.get("keep_music")
        need_tags = need_tags or modify_flags.get("change_tags", False)
        need_images = modify_flags.get("change_images", False)
        need_music = need_music or modify_flags.get("change_music", False)

    if not copy_text:
        need_tags = need_images = need_music = False

    print(f"[Graph:analyze] tags={need_tags} images={need_images} music={need_music}")
    return {"need_tags": need_tags, "need_images": need_images, "need_music": need_music}


# ============================================================
# Node 9: decide_skills — Python: 决定执行哪些 Skill
# ============================================================

def decide_skills(state: AgentState) -> Dict[str, Any]:
    """根据 need_* 标记决定要执行的 Skill 列表"""
    return {}


# ============================================================
# Node 10: execute_all_skills — 内部并行 Skill1/2/3 + merge
# ============================================================

def execute_all_skills(state: AgentState) -> Dict[str, Any]:
    """并行执行 Skill1/2/3（ThreadPoolExecutor），合并去重

    跳过时优先用 prev_*（上轮保留的数据），回退到 user_input。
    这样 optimize/modify 路径不会丢失上一轮的标签/图片/配乐。
    """
    text = state.get("copy_text", "")
    user_input = state.get("user_input", {})
    need_tags = state.get("need_tags", False)
    need_images = state.get("need_images", False)
    need_music = state.get("need_music", False)
    emotion = state.get("emotion", {})

    # 跳过时的默认值：prev_* > user_input
    fallback_tags = state.get("prev_tags", []) or user_input.get("tags", [])
    fallback_images = state.get("prev_images", []) or user_input.get("images", [])
    fallback_music = state.get("prev_music", []) or user_input.get("music", [])

    new_log = []
    from concurrent.futures import ThreadPoolExecutor

    def _run_skill1():
        if not need_tags:
            return ("Skill1", "skipped", fallback_tags)
        try:
            from skills.hashtag_recommender import HashtagRecommender
            tr = HashtagRecommender.recommend(text, count=10)
            tags = [t["tag"] for t in tr] if tr else []
            return ("Skill1", "completed", tags)
        except Exception as e:
            return ("Skill1", "failed", str(e))

    def _run_skill2():
        if not need_images:
            return ("Skill2", "skipped", fallback_images)
        try:
            from skills.image_recommender import recommend_images
            ir = recommend_images(text, count=4)
            return ("Skill2", "completed", ir if ir else [])
        except Exception as e:
            return ("Skill2", "failed", str(e))

    def _run_skill3():
        if not need_music:
            return ("Skill3", "skipped", fallback_music)
        try:
            from skills.music_recommender import recommend_music
            emotion_tags = [f"#{kw}" for kw in emotion.get("keywords", [])]
            mr = recommend_music(emotion_tags, text, use_api=True, fetch_urls=True, emotion=emotion)
            return ("Skill3", "completed", mr if mr else [])
        except Exception as e:
            return ("Skill3", "failed", str(e))

    results = {}
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(_run_skill1): "Skill1",
            executor.submit(_run_skill2): "Skill2",
            executor.submit(_run_skill3): "Skill3",
        }
        for f, name in futures.items():
            try:
                skill_name, status, data = f.result()
                results[name] = (status, data)
                new_log.append({"skill": {"Skill1": "标签推荐", "Skill2": "图片推荐", "Skill3": "配乐推荐"}[name],
                            "status": status, "timestamp": time.strftime("%H:%M:%S")})
            except Exception as e:
                results[name] = ("failed", str(e))

    new_tags = results.get("Skill1", ("skipped", []))[1] if results.get("Skill1", ("skipped", []))[0] in ("completed", "skipped") else []
    new_images = results.get("Skill2", ("skipped", []))[1] if results.get("Skill2", ("skipped", []))[0] in ("completed", "skipped") else []
    new_music = results.get("Skill3", ("skipped", []))[1] if results.get("Skill3", ("skipped", []))[0] in ("completed", "skipped") else []

    # merge
    seen_tags = set()
    final_tags = []
    for t in (new_tags + user_input.get("tags", [])):
        tag_str = t.replace("#", "") if isinstance(t, str) else str(t)
        if tag_str and tag_str not in seen_tags:
            seen_tags.add(tag_str)
            final_tags.append(tag_str)

    seen_urls = set()
    final_images = []
    for img in (new_images + user_input.get("images", [])):
        if not isinstance(img, dict): continue
        url = img.get("original_url") or img.get("url") or img.get("local_path", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            final_images.append({"url": url, "desc": img.get("description", ""),
                                 "local_path": img.get("local_path", ""), "source": img.get("source", "")})

    seen_names = set()
    final_music = []
    for m in (new_music + user_input.get("music", [])):
        if not isinstance(m, dict): continue
        name = m.get("name", "")
        if name and name not in seen_names:
            seen_names.add(name)
            final_music.append({"name": name, "artist": m.get("artist", ""),
                                "style": m.get("style", ""), "mood": m.get("mood", ""),
                                "reason": m.get("reason", ""),
                                "preview_url": m.get("preview_url") or m.get("url"),
                                "can_preview": bool(m.get("preview_url") or m.get("url"))})

    print(f"[Graph:skills] tags={len(final_tags)} images={len(final_images)} music={len(final_music)}")
    return {
        "final_tags": final_tags,
        "final_images": final_images,
        "final_music": final_music,
        "execution_log": new_log,
    }


# ============================================================
# Node (保留旧独立 Skill 节点供 retry loop 使用)
# ============================================================

def execute_skill1(state: AgentState) -> Dict[str, Any]:
    """Skill 1: 标签推荐"""
    from skills.hashtag_recommender import HashtagRecommender

    text = state.get("copy_text", "")
    if not state.get("need_tags"):
        return {"final_tags": state.get("user_input", {}).get("tags", [])}

    try:
        tr = HashtagRecommender.recommend(text, count=10)
        tags = [t["tag"] for t in tr] if tr else []
        log = state.get("execution_log", [])
        log.append({"skill": "标签推荐", "status": "completed", "timestamp": time.strftime("%H:%M:%S")})
        print(f"[Graph:skill1] {len(tags)} 标签")
        return {"final_tags": tags, "execution_log": log}
    except Exception as e:
        print(f"[Graph:skill1] 失败: {e}")
        return {"final_tags": []}


def execute_skill2(state: AgentState) -> Dict[str, Any]:
    """Skill 2: 图片推荐"""
    from skills.image_recommender import recommend_images

    text = state.get("copy_text", "")
    if not state.get("need_images"):
        return {"final_images": state.get("user_input", {}).get("images", [])}

    try:
        ir = recommend_images(text, count=4)
        log = state.get("execution_log", [])
        log.append({"skill": "图片推荐", "status": "completed", "timestamp": time.strftime("%H:%M:%S")})
        print(f"[Graph:skill2] {len(ir) if ir else 0} 图片")
        return {"final_images": ir if ir else [], "execution_log": log}
    except Exception as e:
        print(f"[Graph:skill2] 失败: {e}")
        return {"final_images": []}


def execute_skill3(state: AgentState) -> Dict[str, Any]:
    """Skill 3: 配乐推荐"""
    from skills.music_recommender import recommend_music

    text = state.get("copy_text", "")
    emotion = state.get("emotion", {})
    if not state.get("need_music"):
        return {"final_music": state.get("user_input", {}).get("music", [])}

    try:
        emotion_tags = [f"#{kw}" for kw in emotion.get("keywords", [])]
        mr = recommend_music(emotion_tags, text, use_api=True, fetch_urls=True, emotion=emotion)
        log = state.get("execution_log", [])
        log.append({"skill": "配乐推荐", "status": "completed", "timestamp": time.strftime("%H:%M:%S")})
        print(f"[Graph:skill3] {len(mr) if mr else 0} 配乐")
        return {"final_music": mr if mr else [], "execution_log": log}
    except Exception as e:
        print(f"[Graph:skill3] 失败: {e}")
        return {"final_music": []}


# ============================================================
# Node 13: merge_state — Python: 合并去重
# ============================================================

def merge_state(state: AgentState) -> Dict[str, Any]:
    """合并 Skill 输出与用户原始输入，去重"""
    user_input = state.get("user_input", {})
    new_tags = state.get("final_tags", [])
    new_images = state.get("final_images", [])
    new_music = state.get("final_music", [])

    # tags 去重
    seen_tags = set()
    final_tags = []
    for t in (new_tags + user_input.get("tags", [])):
        tag_str = t.replace("#", "") if isinstance(t, str) else str(t)
        if tag_str and tag_str not in seen_tags:
            seen_tags.add(tag_str)
            final_tags.append(tag_str)

    # images 去重
    seen_urls = set()
    final_images = []
    for img in (new_images + user_input.get("images", [])):
        if not isinstance(img, dict):
            continue
        url = img.get("original_url") or img.get("url") or img.get("local_path", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            final_images.append({"url": url, "desc": img.get("description", ""),
                                 "local_path": img.get("local_path", ""), "source": img.get("source", "")})

    # music 去重
    seen_names = set()
    final_music = []
    for m in (new_music + user_input.get("music", [])):
        if not isinstance(m, dict):
            continue
        name = m.get("name", "")
        if name and name not in seen_names:
            seen_names.add(name)
            final_music.append({"name": name, "artist": m.get("artist", ""),
                                "style": m.get("style", ""), "mood": m.get("mood", ""),
                                "reason": m.get("reason", ""),
                                "preview_url": m.get("preview_url") or m.get("url"),
                                "can_preview": bool(m.get("preview_url") or m.get("url"))})

    print(f"[Graph:merge] tags={len(final_tags)} images={len(final_images)} music={len(final_music)}")
    return {"final_tags": final_tags, "final_images": final_images, "final_music": final_music}


# ============================================================
# Node 14: evaluate — Tool: Skill 4 内容评估
# ============================================================

def evaluate_node(state: AgentState) -> Dict[str, Any]:
    """Skill 4: 综合评估"""
    from skills.content_evaluator import evaluate

    text = state.get("copy_text", "")
    tags = state.get("final_tags", [])[:10]
    images = state.get("final_images", [])[:6]
    music = state.get("final_music", [])[:5]

    try:
        eval_result = evaluate(text, tags, images=images, music=music)
        new_entry = [{"skill": "内容评估", "status": "completed", "timestamp": time.strftime("%H:%M:%S")}]
        print(f"[Graph:eval] score={eval_result.get('score', 'N/A')}")
        return {"evaluation": eval_result, "execution_log": new_entry}
    except Exception as e:
        print(f"[Graph:eval] 失败: {e}")
        return {"evaluation": {"score": 0, "level": "评估失败", "report": str(e), "suggestions": [], "dimensions": {}}}


# ============================================================
# Node 15: check_threshold — Python: 评分判断 + best_result 追踪
# ============================================================

def check_threshold(state: AgentState) -> Dict[str, Any]:
    """判断评分是否达标，追踪最佳结果"""
    evaluation = state.get("evaluation", {})
    score = evaluation.get("score", 0)
    iteration = state.get("iteration", 0) + 1  # 递增迭代计数器

    # 追踪 best
    best_score = state.get("best_score", 0)
    update = {"iteration": iteration}

    if score > best_score:
        update["best_score"] = score
        update["best_evaluation"] = evaluation
        update["best_final_tags"] = state.get("final_tags", [])
        update["best_final_images"] = state.get("final_images", [])
        update["best_final_music"] = state.get("final_music", [])

    loop_history = state.get("loop_history", [])
    loop_history.append({"iteration": iteration, "score": score})
    update["loop_history"] = loop_history

    print(f"[Graph:check] score={score} best={max(score, best_score)} iter={iteration}")
    return update


# ============================================================
# Node 16: identify_weak_dimension — Python: 找最低分维度
# ============================================================

def identify_weak_dimension(state: AgentState) -> Dict[str, Any]:
    """根据 evaluation.dimensions 找到最低分维度"""
    evaluation = state.get("evaluation", {})
    dimensions = evaluation.get("dimensions", {})

    if not dimensions:
        return {"error": "no_dimensions"}

    # 找最低分维度
    dim_map = {
        "text_quality": "Skill1",       # 文案差 → 重写文案会触发新标签
        "tag_match": "Skill1",          # 标签不匹配 → 重跑 Skill1
        "image_richness": "Skill2",     # 素材不足 → 重跑 Skill2
        "music_harmony": "Skill3",      # 配乐不协调 → 重跑 Skill3
        "completeness": "Skill1",       # 结构不完整 → 重跑全部基础 Skill
    }

    weakest = min(dimensions.items(), key=lambda x: x[1])
    dim_name, dim_score = weakest
    skill = dim_map.get(dim_name, "Skill1")

    print(f"[Graph:weak] 最低分维度: {dim_name}={dim_score} → 重跑 {skill}")
    return {"execution_log": [{"skill": f"自动重试 ({skill})", "status": "started",
            "reason": f"{dim_name}={dim_score}", "timestamp": time.strftime("%H:%M:%S")}]}


# ============================================================
# Node 17: rerun_skill — Tool: 重跑最弱 Skill
# ============================================================

def rerun_skill(state: AgentState) -> Dict[str, Any]:
    """根据 identify_weak_dimension 重跑单个 Skill"""
    evaluation = state.get("evaluation", {})
    dimensions = evaluation.get("dimensions", {})

    if not dimensions:
        return {}

    weakest = min(dimensions.items(), key=lambda x: x[1])
    dim_name = weakest[0]
    text = state.get("copy_text", "")
    emotion = state.get("emotion", {})

    if dim_name in ("tag_match", "completeness"):
        from skills.hashtag_recommender import HashtagRecommender
        try:
            tr = HashtagRecommender.recommend(text, count=10, strategy="aggressive")
            tags = [t["tag"] for t in tr] if tr else []
            return {"final_tags": tags}
        except Exception as e:
            print(f"[Graph:rerun1] 失败: {e}")

    elif dim_name == "image_richness":
        from skills.image_recommender import recommend_images
        try:
            ir = recommend_images(text, count=4)
            return {"final_images": ir if ir else []}
        except Exception as e:
            print(f"[Graph:rerun2] 失败: {e}")

    elif dim_name == "music_harmony":
        from skills.music_recommender import recommend_music
        try:
            emotion_tags = [f"#{kw}" for kw in emotion.get("keywords", [])]
            mr = recommend_music(emotion_tags, text, use_api=True, fetch_urls=True, emotion=emotion)
            return {"final_music": mr if mr else []}
        except Exception as e:
            print(f"[Graph:rerun3] 失败: {e}")

    return {}


# ============================================================
# Node 18: rerun_evaluate — Tool: 重评估
# ============================================================

def rerun_evaluate(state: AgentState) -> Dict[str, Any]:
    """重跑 Skill 4 评估（与 evaluate_node 相同，但计入 loop_history）"""
    return evaluate_node(state)
