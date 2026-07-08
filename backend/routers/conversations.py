"""
会话管理和对话管理路由
"""
import json
import time
import logging
from typing import Optional, List, Dict

from fastapi import APIRouter, Request, HTTPException, Query
from pydantic import BaseModel, Field

from utils.memory import MemoryManager
from backend.constants import SESSION_FILE, STATE_FILE

logger = logging.getLogger("douyin-agent")

memory = MemoryManager()

router = APIRouter()


# =====================================================
# Pydantic 输入验证模型
# =====================================================

class CreateConversationRequest(BaseModel):
    title: str = Field(default="新对话", min_length=1, max_length=200)
    user_id: str = Field(default="default_user", min_length=1, max_length=100)


class AddMessageRequest(BaseModel):
    conversation_id: str = Field(..., min_length=1, max_length=200)
    role: str = Field(..., min_length=1, max_length=50)
    content: str = Field(..., min_length=1, max_length=10000)
    metadata: Optional[dict] = None


# =====================================================
# 通用错误响应
# =====================================================

def _api_error(detail: str = "操作失败，请稍后重试", status_code: int = 500):
    raise HTTPException(status_code=status_code, detail=detail)


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


@router.get("/api/session")
def get_session():
    """获取当前会话"""
    return _load_session()


@router.post("/api/session/save")
async def save_session(request: Request):
    """保存会话"""
    data = await request.json()
    session = _load_session()
    session.update(data)
    _save_session(session)
    return {"success": True}


@router.post("/api/session/reset")
def reset_session():
    """重置会话"""
    SESSION_FILE.unlink(missing_ok=True)
    return {"success": True, "session": _load_session()}


# =====================================================
# 对话管理API
# =====================================================

@router.post("/api/conversations")
async def create_conversation(request: CreateConversationRequest):
    """创建新的对话会话"""
    try:
        conversation_id = memory.create_conversation(title=request.title, user_id=request.user_id)
        return {"conversation_id": conversation_id}
    except Exception as e:
        logger.error(f"创建对话失败: {e}")
        _api_error("创建对话失败，请稍后重试")


@router.get("/api/conversations/{conversation_id}")
def get_conversation(conversation_id: str):
    """获取对话会话信息"""
    try:
        conversation = memory.get_conversation(conversation_id)
        if not conversation:
            _api_error("对话不存在", 404)
        return conversation
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取对话失败: {e}")
        _api_error("获取对话失败")


@router.get("/api/conversations")
def list_conversations(user_id: Optional[str] = None, limit: int = 50):
    """列出对话会话"""
    try:
        return memory.list_conversations(user_id=user_id, limit=limit)
    except Exception as e:
        logger.error(f"列出对话失败: {e}")
        _api_error("列出对话失败")


@router.delete("/api/conversations/{conversation_id}")
def delete_conversation(conversation_id: str):
    """删除对话会话"""
    try:
        success = memory.delete_conversation(conversation_id)
        if not success:
            _api_error("对话不存在", 404)
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除对话失败: {e}")
        _api_error("删除对话失败")


@router.post("/api/conversations/batch-delete")
async def batch_delete_conversations(request: Request):
    """批量删除对话会话"""
    try:
        body = await request.body()
        try:
            data = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError):
            data = json.loads(body.decode("gbk", errors="replace"))
    except Exception:
        return {"error": "invalid_body", "deleted_count": 0}

    conversation_ids = data.get("conversation_ids", [])
    if not conversation_ids:
        return {"deleted_count": 0}

    deleted_count = 0
    for conv_id in conversation_ids:
        try:
            if memory.delete_conversation(conv_id):
                deleted_count += 1
        except Exception as e:
            logger.error(f"删除对话 {conv_id} 失败: {e}")

    print(f"[后端] 批量删除完成: 请求 {len(conversation_ids)} 个, 成功 {deleted_count} 个")
    return {"deleted_count": deleted_count, "total": len(conversation_ids)}


@router.put("/api/conversations/{conversation_id}")
async def update_conversation(conversation_id: str, request: Request):
    """更新对话会话（如标题）"""
    try:
        body = json.loads(await request.body())
        title = body.get("title")
        if title:
            memory.update_conversation_title(conversation_id, title)
            print(f"[后端] 更新对话标题: {conversation_id} → {title}")
        return {"success": True}
    except Exception as e:
        logger.error(f"更新对话失败: {e}")
        _api_error("更新对话失败")


@router.post("/api/conversations/messages")
async def add_message(request: AddMessageRequest):
    """添加消息到对话历史"""
    try:
        message_id = memory.add_message(
            conversation_id=request.conversation_id,
            role=request.role,
            content=request.content,
            metadata=request.metadata
        )
        return {"message_id": message_id}
    except Exception as e:
        logger.error(f"添加消息失败: {e}")
        _api_error("添加消息失败")


@router.get("/api/conversations/{conversation_id}/messages")
def get_conversation_history(conversation_id: str, limit: Optional[int] = None):
    """获取对话历史"""
    try:
        return memory.get_conversation_history(conversation_id, limit=limit or 100)
    except Exception as e:
        logger.error(f"获取对话历史失败: {e}")
        _api_error("获取对话历史失败")


@router.get("/api/conversations/{conversation_id}/context")
def get_conversation_context(conversation_id: str, max_messages: int = 20):
    """获取对话上下文（用于Agent执行）"""
    try:
        return memory.get_context_for_agent(conversation_id, max_messages=max_messages)
    except Exception as e:
        logger.error(f"获取对话上下文失败: {e}")
        _api_error("获取对话上下文失败")


@router.get("/api/conversations/{conversation_id}/stats")
def get_conversation_stats(conversation_id: str):
    """获取对话统计信息"""
    try:
        return memory.get_conversation_stats(conversation_id)
    except Exception as e:
        logger.error(f"获取对话统计失败: {e}")
        _api_error("获取对话统计失败")


@router.get("/api/conversations/search")
def search_conversations(keyword: str, user_id: Optional[str] = None, limit: int = 20):
    """搜索对话"""
    try:
        return memory.search_conversations(keyword, user_id=user_id, limit=limit)
    except Exception as e:
        logger.error(f"搜索对话失败: {e}")
        _api_error("搜索对话失败")
