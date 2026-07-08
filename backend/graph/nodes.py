"""
LangGraph 节点函数 — 18 个节点

每个节点接收 AgentState，返回 AgentState 的部分更新。
"""
import json
import time
from typing import Dict, Any

from backend.graph.state import AgentState
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


# ============================================================
# Node 1: initialize — 加载 session + context
# ============================================================

def initialize(state: AgentState) -> Dict[str, Any]:
    """从 conversation_id 或 session_id 恢复会话上下文"""
    user_input = state.get("user_input", {})
    conversation_id = state.get("conversation_id", "")
    session = {}
    context = {}
    has_context = False
    prev_copy_text = ""
    prev_evaluation = {}
    prev_tags = []
    prev_images = []
    prev_music = []

    if conversation_id:
        try:
            ctx = memory.get_context_for_agent(conversation_id, max_messages=MAX_CONTEXT_MSGS)
            msgs = ctx.get("messages", [])
            context = ctx

            for msg in reversed(msgs):
                if msg.get("role") == "assistant":
                    meta = msg.get("metadata")
                    if isinstance(meta, str):
                        meta = json.loads(meta) if meta else {}
                    if isinstance(meta, dict):
                        if meta.get("evaluation"):
                            session["evaluation"] = meta["evaluation"]
                            prev_evaluation = meta["evaluation"]
                        showcase = meta["evaluation"].get("showcase", {})
                        if showcase.get("images"):
                            prev_images = showcase["images"]
                        if showcase.get("tags"):
                            prev_tags = [f"#{t}" if not t.startswith('#') else t for t in showcase["tags"]]
                        if showcase.get("music"):
                            prev_music = showcase["music"]
                    break

            for msg in reversed(msgs):
                if msg.get("role") == "user" and msg.get("content") and \
                   msg["content"] not in ("优化一下", "换标签", "换个配乐", "重试"):
                    prev_copy_text = msg["content"]
                    break

            has_context = bool(prev_copy_text)
            print(f"[Graph:init] 重建会话: text={has_context} images={len(prev_images)} eval={bool(prev_evaluation)}")
        except Exception as e:
            print(f"[Graph:init] 失败: {e}")

    return {
        "session": session,
        "has_context": has_context,
        "prev_copy_text": prev_copy_text,
        "prev_evaluation": prev_evaluation,
        "prev_tags": prev_tags,
        "prev_images": prev_images,
        "prev_music": prev_music,
        "copy_text": user_input.get("text", ""),
        "iteration": session.get("iteration", 0),
        "loop_history": session.get("loop_history", []),
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
        return {"modify_flags": flags}
    except Exception as e:
        print(f"[Graph:modify] 失败: {e}")

    # 关键词回退
    fb = user_feedback
    return {"modify_flags": {
        "change_copy": any(kw in fb for kw in ["文案", "文字", "风格", "改写", "优化"]),
        "change_tags": any(kw in fb for kw in ["标签", "tag"]),
        "change_images": any(kw in fb for kw in ["图片", "图", "照片"]),
        "change_music": any(kw in fb for kw in ["配乐", "音乐", "bgm"]),
        "keep_tags": False, "keep_images": False, "keep_music": False,
    }}


# ============================================================
# Node 6: question_response — LLM 问答
# ============================================================

def question_response(state: AgentState) -> Dict[str, Any]:
    """question 意图：对话式回答"""
    text = state.get("copy_text", "")
    prev_tags = state.get("prev_tags", [])
    prev_text = state.get("prev_copy_text", "")
    prev_score = state.get("prev_evaluation", {}).get("score", 0)

    q_prompt = f"""用户在上一轮获得了创作推荐，现在问了一个问题。
上一轮: 文案={prev_text[:100]} 标签={', '.join(prev_tags[:8])} 评分={prev_score}/5.0

用户问题: {text}
请用简洁中文回答，2-4句话。"""

    try:
        llm = get_chat_model(temperature=0.7, max_tokens=200, timeout=15)
        structured = llm.with_structured_output(QuestionAnswer, method="function_calling")
        result = structured.invoke([
            {"role": "system", "content": "你是创作顾问。"},
            {"role": "user", "content": q_prompt},
        ])
        answer = result.answer
    except Exception:
        answer = "你可以输入'优化'来改进当前内容，或输入'换标签'来更换推荐。"

    return {
        "evaluation": {"score": prev_score, "level": "对话回复", "report": answer, "suggestions": []},
    }


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
    """并行执行 Skill1/2/3（ThreadPoolExecutor），合并去重"""
    text = state.get("copy_text", "")
    user_input = state.get("user_input", {})
    need_tags = state.get("need_tags", False)
    need_images = state.get("need_images", False)
    need_music = state.get("need_music", False)
    emotion = state.get("emotion", {})
    new_log = []  # 增量日志，Annotated reducer 自动合并
    from concurrent.futures import ThreadPoolExecutor

    def _run_skill1():
        if not need_tags:
            return ("Skill1", "skipped", user_input.get("tags", []))
        try:
            from skills.hashtag_recommender import HashtagRecommender
            tr = HashtagRecommender.recommend(text, count=10)
            tags = [t["tag"] for t in tr] if tr else []
            return ("Skill1", "completed", tags)
        except Exception as e:
            return ("Skill1", "failed", str(e))

    def _run_skill2():
        if not need_images:
            return ("Skill2", "skipped", user_input.get("images", []))
        try:
            from skills.image_recommender import recommend_images
            ir = recommend_images(text, count=4)
            return ("Skill2", "completed", ir if ir else [])
        except Exception as e:
            return ("Skill2", "failed", str(e))

    def _run_skill3():
        if not need_music:
            return ("Skill3", "skipped", user_input.get("music", []))
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

    new_tags = results.get("Skill1", ("skipped", []))[1] if results.get("Skill1", ("skipped", []))[0] == "completed" else []
    new_images = results.get("Skill2", ("skipped", []))[1] if results.get("Skill2", ("skipped", []))[0] == "completed" else []
    new_music = results.get("Skill3", ("skipped", []))[1] if results.get("Skill3", ("skipped", []))[0] == "completed" else []

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
