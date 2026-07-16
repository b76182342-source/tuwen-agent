"""
Agent 执行管线路由 — v2.0 快车道

核心路由:
  POST /api/agent/run          — 智能补全主流程（委托 LangGraph）
  GET  /api/agent/status/{id}  — 查询 session 状态
  POST /api/agent/rollback     — Skill 回滚

v2.0 变化：
  路由从 400 行重复逻辑 → 简化为请求解析 + 委托 builder.run_agent()
  图中的节点统一处理：意图分类、文案生成、Skill 执行、评估、循环优化、持久化
"""
import json
import time
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Request, HTTPException

from backend.constants import PROJECT_ROOT, SESSION_FILE
from utils.config import get_chat_model
from utils.memory import MemoryManager

router = APIRouter()
memory = MemoryManager()


# =====================================================
# 图片 URL → 文案（图尚未覆盖的功能，暂时留在路由层）
# =====================================================

def _analyze_images(img_urls: list) -> str:
    """从图片 URL 元信息推理文案"""
    from backend.schemas import CopyOutput

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
            {"role": "system", "content": "你是图片分析专家，根据元信息推理图片内容。只输出文案。"},
            {"role": "user", "content": prompt},
        ])
        if result and isinstance(result, CopyOutput):
            print(f"[路由] 图片识别: {result.copy_text[:60]}")
            return result.copy_text.strip()
    except Exception as e:
        print(f"[路由] 图片识别失败: {e}")
    return ""


# =====================================================
# 主流程: POST /api/agent/run
# =====================================================

@router.post("/api/agent/run")
async def agent_run(request: Request):
    """智能补全：委托 LangGraph 图执行全流程

    图负责：意图分类 → 文案生成/优化 → Skill1/2/3 并行 → Skill4 评估
           → 质量闭环（最多3轮）→ Agent 对话 → DB1/DB2 持久化
    路由只做：解析请求 → 图片→文案（图暂未覆盖）→ 委托图 → 返回
    """
    # ── 1. 解析请求 ──
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
    conversation_id = data.get("conversation_id") or request.query_params.get("conversation_id") or ""

    # ── 2. 图片 → 文案（图尚未覆盖，路由层处理）──
    if not text and images_input:
        img_urls = [img.get("url", img.get("path", "")) for img in images_input
                    if img.get("url") or img.get("path")]
        if img_urls:
            recognized = _analyze_images(img_urls)
            if recognized:
                text = recognized

    if not text and not images_input:
        return {
            "error": "empty_input",
            "evaluation": {"score": 0, "level": "无输入", "report": "请输入文案或主题，或上传图片。", "suggestions": []},
            "agent_suggestions": {},
            "execution_log": [],
        }

    # ── 3. 委托图 ──
    from backend.graph.builder import run_agent

    user_input = {
        "text": text,
        "tags": tags_input,
        "images": images_input,
        "music": music_input,
    }

    t0 = time.time()
    result = run_agent(user_input, conversation_id)
    elapsed = time.time() - t0
    print(f"[路由] 图执行完成 ({elapsed:.1f}s)")

    return result


# =====================================================
# GET /api/agent/status/{session_id}
# =====================================================

@router.get("/api/agent/status/{session_id}")
def get_agent_status(session_id: str):
    """查询 session 运行状态"""
    try:
        conversations = memory.list_conversations(limit=100)
        for conv in conversations:
            conv_id = conv.get("id", conv.get("conversation_id", ""))
            if conv_id == session_id:
                return {"session_id": session_id, "status": "completed", "conversation": conv}

        if SESSION_FILE.exists():
            try:
                session = json.loads(open(SESSION_FILE, "r", encoding="utf-8").read())
                return {
                    "session_id": session_id,
                    "status": "running" if session.get("evaluation") is None else "completed",
                    "iteration": session.get("iteration", 0),
                    "last_updated": session.get("updated_at", ""),
                }
            except Exception:
                pass

        return {"session_id": session_id, "status": "not_found"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询状态失败: {e}")


# =====================================================
# POST /api/agent/rollback
# =====================================================

@router.post("/api/agent/rollback")
async def agent_rollback(request: Request):
    """回滚 Skill 结果到上一轮"""
    try:
        data = json.loads(await request.body())
    except Exception:
        return {"success": False, "message": "无法解析请求体"}

    conversation_id = data.get("conversation_id", "")
    skill_name = data.get("skill", "")

    if not conversation_id:
        return {"success": False, "message": "缺少 conversation_id"}

    try:
        msgs = memory.get_conversation_history(conversation_id, limit=10)
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
