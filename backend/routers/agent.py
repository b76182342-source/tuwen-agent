"""
Agent 执行管线路由

核心路由:
  POST /api/agent/run          — 智能补全主流程
  GET  /api/agent/status/{id}  — 查询 session 状态 [NEW]
  POST /api/agent/rollback     — Skill 回滚 [NEW]
"""
import json
import time
from pathlib import Path
from typing import Optional, List, Dict

from fastapi import APIRouter, Request, HTTPException

from backend.constants import (
    PROJECT_ROOT, _RE_REMOVE_BGM, _RE_REMOVE_TAGS,
    MIN_TEXT_LENGTH_FOR_TOPIC, TEXT_PREVIEW_LENGTH,
    MIN_GENERATED_COPY_LENGTH, INTENT_CLASSIFY_MAX_TOKENS,
    COPY_GENERATE_MAX_TOKENS, REWRITE_MAX_TOKENS, QA_MAX_TOKENS,
    FOLLOWUP_MAX_TEXT_LENGTH, MAX_CONTEXT_MSGS,
    INTENT_TOPIC, INTENT_CREATE, INTENT_OPTIMIZE, INTENT_MODIFY, INTENT_QUESTION,
    VALID_INTENTS, SESSION_FILE,
)
from backend.schemas import (
    IntentOutput, CopyOutput, ModifyFlags, QuestionAnswer,
)
from utils.config import get_chat_model
from utils.memory import MemoryManager

router = APIRouter()
memory = MemoryManager()

# ---- 技能模块 ----
from skills.hashtag_recommender import HashtagRecommender, analyze_emotion
from skills.image_recommender import recommend_images
from skills.music_recommender import recommend_music
from skills.content_evaluator import evaluate


# =====================================================
# 会话管理（短期记忆）
# =====================================================

def _load_session() -> dict:
    if SESSION_FILE.exists():
        try:
            return json.loads(open(SESSION_FILE, "r", encoding="utf-8").read())
        except Exception:
            pass
    return {
        "session_id": f"{time.strftime('%Y%m%d_%H%M%S')}",
        "messages": [],
        "iteration": 0,
        "iteration_history": [],
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


def _save_session(session: dict):
    SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    session["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(SESSION_FILE, "w", encoding="utf-8") as f:
        json.dump(session, f, ensure_ascii=False, indent=2)


# =====================================================
# Agent 辅助函数
# =====================================================

def _classify_intent_with_llm(text: str, prev_text: str, prev_score: float, has_context: bool) -> str:
    """通过 LLM 分类用户意图 → topic/create/optimize/modify/question"""
    intent_prompt = f"""分析用户输入，判断意图类型。只输出一个词。

## 当前状态
{'- 上一轮文案: ' + prev_text[:80] if has_context else '- 全新会话，无历史'}
{'- 上一轮评分: ' + str(prev_score) + '/5.0' if has_context else ''}

## 用户输入
"{text}"

## 意图类型
topic: 用户提出了一个主题/想法/需求，需要先生成文案（如"我想做浴室用品图文"、"帮我写一段关于春天的文案"）
create: 用户已经提供了完整的文案内容，直接使用即可（如"夕阳把影子拉得很长"）
optimize: 用户希望改进上一轮结果（需有上下文）
modify: 用户想修改上一轮的某部分
question: 用户提问或闲聊

只输出 topic / create / optimize / modify / question 中的一个词。"""

    try:
        llm = get_chat_model(temperature=0.1, max_tokens=100, timeout=10)
        structured = llm.with_structured_output(IntentOutput, method="function_calling")
        intent_result = structured.invoke([
            {"role": "system", "content": "你是一个严格的分类器。"},
            {"role": "user", "content": intent_prompt},
        ])
        user_intent = intent_result.intent.strip().lower()
        if user_intent not in VALID_INTENTS:
            user_intent = INTENT_TOPIC if len(text) > MIN_TEXT_LENGTH_FOR_TOPIC and not has_context else INTENT_CREATE
    except Exception as e:
        print(f"[后端] 意图分类失败: {e}")
        user_intent = INTENT_TOPIC if len(text) > MIN_TEXT_LENGTH_FOR_TOPIC and not has_context else INTENT_CREATE

    print(f"[后端] LLM 意图: '{text[:30]}' → {user_intent}")
    return user_intent


def _clean_copy(text: str) -> str:
    """清洗 LLM 输出的文案：移除混入的配乐名、标签、多余 emoji 噪声"""
    text = _RE_REMOVE_BGM.sub('', text)
    text = _RE_REMOVE_TAGS.sub('', text)
    if len(text.strip()) < 10:
        return text
    return text.strip()


def _generate_copy_from_topic(user_idea: str) -> str:
    """根据用户主题/想法生成抖音文案"""
    gen_prompt = f"""你是一个抖音文案写手。根据用户的主题/想法，生成一段适合抖音图文的文案。

规则（严格遵守）：
1. 30-100字，简短有力
2. 只输出文案正文，不要输出配乐名、标签、BGM、歌手名
3. 不要输出 #标签，标签由单独的系统生成
4. 如果用户提到了具体产品/场景，围绕它展开
5. 可以包含问句或悬念增加互动

用户想法：{user_idea}

直接输出文案正文，不要其他内容。"""

    llm = get_chat_model(temperature=0.8, max_tokens=COPY_GENERATE_MAX_TOKENS, timeout=15)
    structured = llm.with_structured_output(CopyOutput, method="function_calling")
    try:
        generated = structured.invoke([
            {"role": "system", "content": "你是专业抖音文案写手，只输出文案正文，绝不输出配乐名或标签。"},
            {"role": "user", "content": gen_prompt},
        ])
        if generated and isinstance(generated, CopyOutput) and len(generated.copy_text) > MIN_GENERATED_COPY_LENGTH:
            copy_text = _clean_copy(generated.copy_text.strip())
            print(f"[后端] 文案生成: {copy_text[:TEXT_PREVIEW_LENGTH]}...")
            return copy_text
    except Exception as e:
        print(f"[后端] 文案生成失败: {e}")
    return ""


def _optimize_copy(user_feedback: str, prev_text: str, prev_suggestions: list) -> str:
    """根据用户反馈和评估建议优化文案"""
    opt_suggestions = "; ".join(prev_suggestions) if prev_suggestions else "提升整体质量"
    rewrite_prompt = f"""优化以下抖音文案。

用户反馈：{user_feedback}
上一轮评估建议：{opt_suggestions}

原文案：{prev_text[:200]}

规则（严格遵守）：
1. 保持核心主题不变，针对用户反馈和评估建议改进
2. 30-120字，适合抖音图文，有感染力
3. 只输出文案正文，不要输出配乐名、标签、BGM、歌手名
4. 不要输出 #标签

直接输出文案正文，不要其他内容。"""

    llm = get_chat_model(temperature=0.8, max_tokens=COPY_GENERATE_MAX_TOKENS, timeout=15)
    structured = llm.with_structured_output(CopyOutput, method="function_calling")
    try:
        rewritten = structured.invoke([
            {"role": "system", "content": "你是专业文案优化师，只输出文案正文，绝不输出配乐名或标签。"},
            {"role": "user", "content": rewrite_prompt},
        ])
        if rewritten and isinstance(rewritten, CopyOutput) and len(rewritten.copy_text) > MIN_GENERATED_COPY_LENGTH:
            new_text = _clean_copy(rewritten.copy_text.strip())
            print(f"[后端] Optimize 文案优化: {new_text[:TEXT_PREVIEW_LENGTH]}...")
            return new_text
    except Exception as e:
        print(f"[后端] 文案优化失败: {e}")
    return ""


def _parse_user_intent_semantic(user_feedback: str) -> dict:
    """通过 LLM 语义理解解析用户想修改/保留哪些组件"""
    prompt = f"""分析用户对当前图文内容的反馈，判断想修改和保留哪些组件。

## 用户反馈
"{user_feedback}"

## 输出格式（严格 JSON）
{{
  "change_copy": false,
  "change_tags": false,
  "change_images": false,
  "change_music": false,
  "keep_copy": false,
  "keep_tags": false,
  "keep_images": false,
  "keep_music": false
}}

## 判断规则
- change_* = true: 用户想修改/更换/优化这个组件
- keep_* = true: 用户明确表示保留/不变/继续用
- 没提到的组件默认为 false
- "优化一下"/"再改改" = change_copy: true（默认重写文案）
- "换个风格" = change_copy: true
- "照片不太好看"/"图不搭"/"换张图" = change_images: true
- "背景音乐太吵"/"换首歌"/"BGM不合适" = change_music: true
- "标签挺好的"/"保留标签" = keep_tags: true
- "原图不变"/"图片保留"/"继续用原来的" = keep_images: true

只输出 JSON，不要其他内容。"""

    llm = get_chat_model(temperature=0.0, max_tokens=200, timeout=5)
    structured = llm.with_structured_output(ModifyFlags, method="function_calling")
    try:
        result = structured.invoke([
            {"role": "system", "content": "你是一个严格的 JSON 输出器，只输出 JSON。"},
            {"role": "user", "content": prompt},
        ])
    except Exception as e:
        print(f"[语义解析] 失败: {e}")
        return None

    if isinstance(result, ModifyFlags):
        parsed = {
            "change_copy": result.change_copy,
            "change_tags": result.change_tags,
            "change_images": result.change_images,
            "change_music": result.change_music,
            "keep_copy": result.keep_copy,
            "keep_tags": result.keep_tags,
            "keep_images": result.keep_images,
            "keep_music": result.keep_music,
        }
        print(f"[语义解析] {parsed}")
        return parsed
    return None


def _rewrite_copy(user_feedback: str, prev_text: str) -> str:
    """根据用户反馈改写文案"""
    rewrite_prompt = f"""重写以下抖音文案。

用户的改写要求：{user_feedback}

原文案：{prev_text[:200]}

规则（严格遵守）：
1. 保持核心主题不变，根据用户的改写要求调整风格
2. 30-120字，适合抖音图文，有感染力
3. 只输出文案正文，不要输出配乐名、标签、BGM、歌手名
4. 不要输出 #标签

直接输出文案正文，不要其他内容。"""

    llm = get_chat_model(temperature=0.8, max_tokens=REWRITE_MAX_TOKENS, timeout=15)
    structured = llm.with_structured_output(CopyOutput, method="function_calling")
    try:
        rewritten = structured.invoke([
            {"role": "system", "content": "你是专业文案改写师，只输出文案正文，绝不输出配乐名或标签。"},
            {"role": "user", "content": rewrite_prompt},
        ])
        if rewritten and isinstance(rewritten, CopyOutput) and len(rewritten.copy_text) > MIN_GENERATED_COPY_LENGTH:
            new_text = _clean_copy(rewritten.copy_text.strip())
            print(f"[后端] 文案改写: {new_text[:TEXT_PREVIEW_LENGTH]}...")
            return new_text
    except Exception as e:
        print(f"[后端] 文案改写失败: {e}")
    return ""


# =====================================================
# 图片 URL 分析（图片 → 文案）
# =====================================================

def _analyze_images(img_urls: list) -> str:
    """从图片元信息推理文案"""
    import requests as req
    from utils.config import PROXY

    prompt_parts = ["以下是几张图片的 URL。请根据 URL 中的关键词、文件名等线索，推断图片内容并生成一段简短文案。"]
    for i, url in enumerate(img_urls[:3], 1):
        prompt_parts.append(f"\n图片 {i}: {url}")

    prompt_parts.append("""
要求：
1. 根据 URL 关键词、文件名等线索推理内容
2. 文案要简短有感染力，适合抖音
3. 直接输出文案，不要其他内容""")
    prompt = "\n".join(prompt_parts)

    llm = get_chat_model(temperature=0.7, max_tokens=100, timeout=10)
    structured = llm.with_structured_output(CopyOutput, method="function_calling")
    try:
        result = structured.invoke([
            {"role": "system", "content": "你是图片分析专家，根据元信息推理图片内容。只输出文案，不输出其他。"},
            {"role": "user", "content": prompt},
        ])
        if result and isinstance(result, CopyOutput):
            print(f"[图片识别] 推理结果: {result.copy_text[:60]}")
            return result.copy_text.strip()
    except Exception as e:
        print(f"[图片识别] 失败: {e}")
    return ""


# =====================================================
# 主流程: POST /api/agent/run
# =====================================================

@router.post("/api/agent/run")
async def agent_run(request: Request):
    """智能补全：根据用户提供的素材，自动推理并补全缺失内容"""
    try:
        body = await request.body()
        try:
            data = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError):
            data = json.loads(body.decode("gbk", errors="replace"))
    except Exception:
        return {"error": "invalid_body", "evaluation": None, "agent_suggestions": {}, "execution_log": []}

    text = data.get("text", "").strip()
    tags_input = data.get("tags", [])
    images_input = data.get("images", [])
    music_input = data.get("music", [])
    session_id = data.get("session_id", "")
    conversation_id = data.get("conversation_id") or request.query_params.get("conversation_id") or ""

    # 加载会话
    session = {}
    if conversation_id:
        try:
            ctx = memory.get_context_for_agent(conversation_id, max_messages=MAX_CONTEXT_MSGS)
            msgs = ctx.get("messages", [])
            for msg in reversed(msgs):
                if msg.get("role") == "assistant":
                    meta = msg.get("metadata")
                    if isinstance(meta, str):
                        meta = json.loads(meta) if meta else {}
                    if isinstance(meta, dict):
                        if meta.get("evaluation"):
                            session["evaluation"] = meta["evaluation"]
                        showcase = meta["evaluation"].get("showcase", {})
                        if showcase.get("images"):
                            session["images"] = showcase["images"]
                        if showcase.get("tags"):
                            session["tags"] = [f"#{t}" if not t.startswith('#') else t for t in showcase["tags"]]
                        if showcase.get("music"):
                            session["music"] = showcase["music"]
                        if meta.get("user_provided"):
                            session["user_provided"] = meta["user_provided"]
                        if meta.get("user_original_images"):
                            session["user_original_images"] = meta["user_original_images"]
                    break
            for msg in reversed(msgs):
                if msg.get("role") == "user" and msg.get("content") and msg["content"] not in ("优化一下", "换标签", "换个配乐", "重试"):
                    session["text"] = msg["content"]
                    user_meta = msg.get("metadata")
                    if isinstance(user_meta, str):
                        user_meta = json.loads(user_meta) if user_meta else {}
                    if isinstance(user_meta, dict):
                        if user_meta.get("images") and not session.get("user_original_images"):
                            session["user_original_images"] = user_meta["images"]
                    break
            print(f"[后端] 从对话历史重建会话: text={bool(session.get('text'))} images={len(session.get('images',[]))} tags={len(session.get('tags',[]))} eval={bool(session.get('evaluation'))}")
        except Exception as e:
            print(f"[后端] 重建会话失败: {e}")
    elif session_id:
        session = _load_session()

    # 加载对话上下文
    context = {}
    if conversation_id:
        try:
            context = memory.get_context_for_agent(conversation_id, max_messages=MAX_CONTEXT_MSGS)
            print(f"[后端] 加载对话上下文: {len(context.get('messages', []))} 条历史消息")
        except Exception as e:
            print(f"[后端] 加载对话上下文失败: {e}")

    need_tags = need_images = need_music = False
    prev_eval = None
    user_intent = "create"
    generated_copy = ""

    # LLM 意图分类
    if text:
        prev_tags = session.get("tags", []) if session else []
        prev_eval = session.get("evaluation", {}) if session else {}
        prev_text = session.get("text", "") if session else ""
        prev_score = prev_eval.get("score", 0) if isinstance(prev_eval, dict) else 0
        prev_suggestions = prev_eval.get("suggestions", []) if isinstance(prev_eval, dict) else []
        has_context = bool(prev_text)

        user_intent = _classify_intent_with_llm(text, prev_text, prev_score, has_context)

        if user_intent == INTENT_TOPIC:
            generated_copy = _generate_copy_from_topic(text)
            if generated_copy:
                text = generated_copy
            need_tags = True
            need_images = True
            need_music = True

        elif user_intent in ("optimize", "modify") and has_context:
            user_feedback = text
            text = prev_text
            tags_input = prev_tags
            images_input = session.get("images", []) or []
            music_input = session.get("music", []) or []
            user_provided = session.get("user_provided", {})
            session["iteration"] = session.get("iteration", 0) + 1

            need_copy = False
            need_tags = False
            need_images = False
            need_music = False

            parsed = _parse_user_intent_semantic(user_feedback)
            if parsed:
                want_copy = parsed.get("change_copy", False)
                want_tags = parsed.get("change_tags", False)
                want_images = parsed.get("change_images", False)
                want_music = parsed.get("change_music", False)
                keep_images = parsed.get("keep_images", False)
                keep_tags = parsed.get("keep_tags", False)
                keep_music = parsed.get("keep_music", False)
            else:
                want_copy = any(kw in user_feedback for kw in ["文案", "文字", "风格", "改写", "改一下", "不满意", "换种", "重写", "优化"])
                want_tags = any(kw in user_feedback for kw in ["标签", "tag", "话题"])
                want_music = any(kw in user_feedback for kw in ["配乐", "音乐", "bgm", "歌曲", "BGM"])
                want_images = any(kw in user_feedback for kw in ["图片", "图", "照片"])
                keep_any = any(kw in user_feedback for kw in ["不变", "保留", "原来的", "继续用", "别动", "别改"])
                keep_images = keep_any and want_images
                keep_tags = keep_any and want_tags
                keep_music = keep_any and want_music

            if user_intent == "optimize":
                need_copy = True
                if not user_provided.get("tags", True): need_tags = True
                if not user_provided.get("images", True): need_images = True
                if not user_provided.get("music", True): need_music = True

            if want_copy: need_copy = True
            if want_tags and not keep_tags: need_tags = True
            if want_images and not keep_images: need_images = True
            if want_music and not keep_music: need_music = True

            if not want_images and not keep_images and session.get("images"):
                images_input = session["images"]
                print(f"[后端] 默认保留上一轮图片 {len(images_input)} 张")

            if keep_images and session.get("user_original_images"):
                images_input = session["user_original_images"]
                print(f"[后端] 恢复用户原始图片 {len(images_input)} 张")

            if need_copy:
                if user_intent == "optimize":
                    rewritten = _optimize_copy(user_feedback, prev_text, prev_suggestions)
                else:
                    rewritten = _rewrite_copy(user_feedback, prev_text)
                if rewritten:
                    text = rewritten
                if not user_provided.get("tags", False): need_tags = True
                if not user_provided.get("music", False): need_music = True

            print(f"[后端] {user_intent}: copy={need_copy} tags={need_tags} images={need_images} music={need_music} | 用户提供: tags={user_provided.get('tags')} images={user_provided.get('images')} music={user_provided.get('music')} | 保留: images={keep_images} tags={keep_tags} music={keep_music}")

        elif user_intent == "question":
            need_tags = need_images = need_music = False

    # 图片 → 文案
    if not text and images_input:
        img_urls = [img.get("url", img.get("path", "")) for img in images_input if img.get("url") or img.get("path")]
        if img_urls:
            print(f"[后端] 检测到 {len(img_urls)} 张图片，启动图片识别...")
            recognized_text = _analyze_images(img_urls)
            if recognized_text:
                text = recognized_text
                print(f"[后端] 图片识别生成文案: {text[:TEXT_PREVIEW_LENGTH]}...")

    # 智能判断需要哪些 Skill
    if user_intent in ("topic", "create"):
        need_tags = not tags_input and bool(text)
        need_images = not images_input and bool(text)
        need_music = not music_input and bool(text)
        session["user_provided"] = {
            "tags": bool(tags_input),
            "images": bool(images_input),
            "music": bool(music_input),
        }
        if images_input and not session.get("user_original_images"):
            session["user_original_images"] = list(images_input)
        if tags_input and not session.get("user_original_tags"):
            session["user_original_tags"] = list(tags_input)
    need_eval = bool(text)

    print(f"[后端] 智能分析: text={bool(text)} need_tags={need_tags} need_images={need_images} need_music={need_music}")

    result = {
        "creator_content": {
            "text": text,
            "tags": tags_input,
            "images": images_input,
            "music": music_input,
        },
        "agent_suggestions": {"Skill1": [], "Skill2": [], "Skill3": []},
        "execution_log": [],
        "session_state": {"text": text, "tags": tags_input, "images": images_input, "music": music_input, "evaluation": None},
        "evaluation": None,
    }

    # Skill 1/2/3 并行执行
    from concurrent.futures import ThreadPoolExecutor

    t_skills_start = time.time()

    t_emotion = time.time()
    emotion = analyze_emotion(text)
    print(f"[后端] 情绪分析完成 ({time.time()-t_emotion:.1f}s): mood={emotion.get('mood', '?')} energy={emotion.get('energy', '?')}")

    def _run_skill1():
        if not need_tags:
            return ("Skill1", "skipped", tags_input)
        try:
            tr = HashtagRecommender.recommend(text, count=10)
            tags = [t["tag"] for t in tr] if tr else []
            return ("Skill1", "completed", tags)
        except Exception as e:
            return ("Skill1", "failed", str(e))

    def _run_skill2():
        if not need_images:
            return ("Skill2", "skipped", images_input)
        try:
            ir = recommend_images(text, count=4)
            return ("Skill2", "completed", ir if ir else [])
        except Exception as e:
            return ("Skill2", "failed", str(e))

    def _run_skill3():
        if not need_music:
            return ("Skill3", "skipped", music_input)
        try:
            emotion_tags = [f"#{kw}" for kw in emotion.get("keywords", [])]
            mr = recommend_music(emotion_tags, text, use_api=True, fetch_urls=True, emotion=emotion)
            return ("Skill3", "completed", mr if mr else [])
        except Exception as e:
            return ("Skill3", "failed", str(e))

    with ThreadPoolExecutor(max_workers=3) as executor:
        f1 = executor.submit(_run_skill1)
        f2 = executor.submit(_run_skill2)
        f3 = executor.submit(_run_skill3)

        for f, skill_name in [(f1, "标签推荐"), (f2, "图片推荐"), (f3, "配乐推荐")]:
            try:
                name, status, data = f.result()
            except Exception as e:
                name, status, data = skill_name, "failed", str(e)
            result["execution_log"].append({
                "skill": skill_name, "status": status, "timestamp": time.strftime("%H:%M:%S")
            })
            key = {"标签推荐": "Skill1", "图片推荐": "Skill2", "配乐推荐": "Skill3"}[skill_name]
            if status == "completed":
                result["agent_suggestions"][key] = data
            elif status == "skipped":
                result["agent_suggestions"][key] = data
            else:
                result["agent_suggestions"][key] = []
                result["execution_log"][-1]["error"] = str(data)

    print(f"[后端] Skill1/2/3 并行完成 ({time.time()-t_skills_start:.1f}s)")

    # 去重合并
    new_tags = result["agent_suggestions"]["Skill1"] if isinstance(result["agent_suggestions"]["Skill1"], list) else []
    new_images = result["agent_suggestions"]["Skill2"] if isinstance(result["agent_suggestions"]["Skill2"], list) else []
    new_music = result["agent_suggestions"]["Skill3"] if isinstance(result["agent_suggestions"]["Skill3"], list) else []

    seen_tags = set()
    final_tags = []
    for t in (new_tags + tags_input):
        tag_str = t.replace("#", "") if isinstance(t, str) else str(t)
        if tag_str and tag_str not in seen_tags:
            seen_tags.add(tag_str)
            final_tags.append(tag_str)

    seen_urls = set()
    final_images = []
    for img in (new_images + images_input):
        if not isinstance(img, dict): continue
        url = img.get("original_url") or img.get("url") or img.get("local_path", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            final_images.append({"url": url, "desc": img.get("description", ""), "local_path": img.get("local_path", ""), "source": img.get("source", "")})

    seen_names = set()
    final_music = []
    for m in (new_music + music_input):
        if not isinstance(m, dict): continue
        name = m.get("name", "")
        if name and name not in seen_names:
            seen_names.add(name)
            final_music.append({"name": name, "artist": m.get("artist", ""), "style": m.get("style", ""), "mood": m.get("mood", ""), "reason": m.get("reason", ""), "preview_url": m.get("preview_url") or m.get("url"), "can_preview": bool(m.get("preview_url") or m.get("url"))})

    # Skill 4: 内容评估
    if need_eval:
        t0 = time.time()
        try:
            eval_result = evaluate(
                text,
                final_tags[:10],
                images=final_images[:6],
                music=final_music[:5]
            )

            report = eval_result.get("report", "")
            if user_intent in ("optimize", "modify"):
                prev_score_val = prev_eval.get("score", 0) if isinstance(prev_eval, dict) else 0
                new_score = eval_result.get("score", 0)
                delta = new_score - prev_score_val
                delta_str = f"+{delta:.1f}" if delta > 0 else f"{delta:.1f}"
                report = (
                    f"> 第 {session.get('iteration', 1)} 轮优化 (上轮 {prev_score_val:.1f} → 本轮 {new_score:.1f} {delta_str})\n\n"
                    f"{report}"
                )
                result["agent_suggestions"]["_conversational"] = {
                    "type": "optimization",
                    "iteration": session.get("iteration", 1),
                    "previous_score": prev_score_val,
                    "delta": delta,
                }

            ctx_text = ""
            if context.get("messages"):
                ctx_lines = ["\n\n## 对话历史（供参考）"]
                for m in context["messages"][-6:]:
                    role = "用户" if m.get("role") == "user" else "Agent"
                    content = str(m.get("content", ""))[:100]
                    ctx_lines.append(f"- {role}: {content}")
                ctx_text = "\n".join(ctx_lines)
            if ctx_text:
                report += f"\n{ctx_text}"

            showcase = {
                "text": text[:200],
                "tags": final_tags,
                "images": final_images,
                "music": final_music,
                "score": eval_result.get("score", 0),
                "tip": "按这个组合发布，效果更好哦 ✨",
            }

            result["evaluation"] = {
                "score": eval_result.get("score", 0),
                "level": eval_result.get("level", "未知"),
                "report": report,
                "suggestions": eval_result.get("suggestions", [])[:3],
                "showcase": showcase,
            }
            result["session_state"]["evaluation"] = result["evaluation"]
            result["execution_log"].append({"skill": "内容评估", "status": "completed", "timestamp": time.strftime("%H:%M:%S")})
        except Exception as e:
            result["execution_log"].append({"skill": "内容评估", "status": "failed", "error": str(e)})
        print(f"[后端] Skill4 内容评估 完成 ({time.time()-t0:.1f}s)")

    # question 意图
    if user_intent == "question":
        prev_tags = session.get("tags", []) if session else []
        prev_text = session.get("text", "") if session else ""
        prev_eval = session.get("evaluation", {}) if session else {}
        prev_score = prev_eval.get("score", 0) if isinstance(prev_eval, dict) else 0

        q_prompt = f"""用户在上一轮获得了创作推荐，现在问了一个问题。请用友好、有帮助的语气回答。

## 上一轮创作结果
- 文案: {prev_text[:100]}
- 标签: {', '.join(prev_tags[:8])}
- 评分: {prev_score}/5.0
- 建议: {'; '.join(prev_eval.get('suggestions', [])) if isinstance(prev_eval, dict) else '无'}

## 用户问题
{text}

请用简洁的中文回答，2-4句话即可。如果用户要求优化，告诉他可以输入"优化"来自动改进。"""

        llm = get_chat_model(temperature=0.7, max_tokens=200, timeout=15)
        structured = llm.with_structured_output(QuestionAnswer, method="function_calling")
        try:
            answer = structured.invoke([
                {"role": "system", "content": "你是一个创作顾问，回答用户关于内容创作的问题。"},
                {"role": "user", "content": q_prompt},
            ])
            answer_text = answer.answer if isinstance(answer, QuestionAnswer) else ""
        except Exception as e:
            print(f"[后端] 问答失败: {e}")
            answer_text = ""
        if not answer_text:
            answer_text = "你可以输入'优化'来改进当前内容，或输入'换标签'来更换推荐。"
        result["evaluation"] = {
            "score": prev_score,
            "level": "对话回复",
            "report": answer_text,
            "suggestions": [],
        }

    # 首次创作完成提示
    if user_intent in ("topic", "create") and result.get("evaluation"):
        score = result["evaluation"]["score"]
        if score >= 4.0:
            result["evaluation"]["report"] += "\n\n---\n> ✅ 评分达标，可以发布。如有需要，输入\"优化一下\"继续改进。"
        else:
            result["evaluation"]["report"] += "\n\n---\n> ⚠️ 评分未达 4.0。输入\"优化\"我会根据建议自动改进。"

    print(f"[后端] 全流程完成 — 意图:{user_intent} 评分: {result['evaluation']['score'] if result['evaluation'] else 'N/A'}")

    # 自动保存
    if session_id:
        session["session_id"] = session_id
        session["text"] = text
        session["tags"] = final_tags[:10] if final_tags else tags_input[:10]
        session["images"] = final_images[:6] if final_images else images_input[:6]
        session["music"] = final_music[:5] if final_music else music_input[:5]
        session["evaluation"] = result["evaluation"]
        _save_session(session)

    if conversation_id:
        try:
            memory.add_message(
                conversation_id=conversation_id, role="user", content=text,
                metadata={"tags": tags_input, "images": images_input, "music": music_input}
            )
            memory.add_message(
                conversation_id=conversation_id, role="assistant",
                content=json.dumps(result, ensure_ascii=False),
                metadata={
                    "evaluation": result.get("evaluation"),
                    "suggestions": result.get("agent_suggestions"),
                    "user_provided": session.get("user_provided", {}),
                    "user_original_images": session.get("user_original_images", []),
                }
            )
            print(f"[后端] 消息已保存到对话历史 conversation_id={conversation_id}")

            evaluation = result.get("evaluation", {})
            if evaluation and evaluation.get("score"):
                try:
                    memory.save_conversation_to_publish_history(
                        conversation_id=conversation_id, text=text,
                        tags=final_tags, images=final_images, music=final_music,
                        evaluation_score=evaluation.get("score", 0),
                        evaluation_level=evaluation.get("level", "未知")
                    )
                    print(f"[后端] 已保存到发布记录表 conversation_id={conversation_id}")
                except Exception as e:
                    print(f"[后端] 保存发布记录失败: {e}")
        except Exception as e:
            print(f"[后端] 保存对话历史失败: {e}")

    return result


# =====================================================
# NEW: GET /api/agent/status/{session_id}
# =====================================================

@router.get("/api/agent/status/{session_id}")
def get_agent_status(session_id: str):
    """查询 session 运行状态（配合前端轮询）"""
    try:
        # 尝试从对话历史查找
        conversations = memory.list_conversations(limit=100)
        for conv in conversations:
            conv_id = conv.get("id", conv.get("conversation_id", ""))
            if conv_id == session_id:
                return {
                    "session_id": session_id,
                    "status": "completed",
                    "conversation": conv,
                }
        # 检查本地会话文件
        if SESSION_FILE.exists():
            session = _load_session()
            return {
                "session_id": session_id,
                "status": "running" if session.get("evaluation") is None else "completed",
                "iteration": session.get("iteration", 0),
                "last_updated": session.get("updated_at", ""),
            }
        return {"session_id": session_id, "status": "not_found"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询状态失败: {e}")


# =====================================================
# NEW: POST /api/agent/rollback
# =====================================================

@router.post("/api/agent/rollback")
async def agent_rollback(request: Request):
    """回滚 Skill 结果到上一轮（保留 best_result 逻辑）"""
    try:
        data = json.loads(await request.body())
    except Exception:
        return {"success": False, "message": "无法解析请求体"}

    conversation_id = data.get("conversation_id", "")
    skill_name = data.get("skill", "")  # Skill1/Skill2/Skill3

    if not conversation_id:
        return {"success": False, "message": "缺少 conversation_id"}

    # 从对话历史恢复上一轮结果
    try:
        msgs = memory.get_conversation_history(conversation_id, limit=10)
        # 找最近一条 assistant 消息作为回滚目标
        prev_result = None
        for msg in reversed(msgs):
            if msg.get("role") == "assistant":
                content = msg.get("content", "")
                if isinstance(content, str):
                    try:
                        prev_result = json.loads(content)
                    except Exception:
                        pass
                break

        if prev_result:
            return {
                "success": True,
                "message": f"已回滚 {skill_name} 到上一轮结果",
                "restored": prev_result.get("agent_suggestions", {}).get(skill_name, []),
            }
        return {"success": False, "message": "未找到上一轮结果"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"回滚失败: {e}")
