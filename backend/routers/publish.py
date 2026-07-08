"""
发布历史路由
"""
from fastapi import APIRouter, HTTPException, Request, Query
from pydantic import BaseModel, Field
from typing import Optional
import logging

from utils.memory import MemoryManager

router = APIRouter()
memory = MemoryManager()
logger = logging.getLogger("douyin-agent")

# =====================================================
# Pydantic 模型
# =====================================================

class PublishDataUpdate(BaseModel):
    likes: int = Field(default=0, ge=0)
    comments: int = Field(default=0, ge=0)
    views: int = Field(default=0, ge=0)


@router.get("/api/publish/history")
def get_publish_history():
    """获取发布历史"""
    return memory.get_publish_history(limit=50)


@router.put("/api/publish/{publish_id}/data")
def update_publish_data(publish_id: int, data: PublishDataUpdate):
    """更新发布数据"""
    try:
        memory.update_publish_data(publish_id, data.likes, data.comments, data.views)
        return {"success": True}
    except Exception as e:
        logger.error(f"更新发布数据失败: {e}")
        raise HTTPException(status_code=500, detail=f"更新发布数据失败: {e}")


@router.get("/api/content/{post_id}")
def get_content_detail(post_id: int):
    """获取单条内容详情（含日趋势）"""
    detail = memory.get_content_detail(post_id)
    if not detail:
        raise HTTPException(status_code=404, detail="内容不存在")
    return detail


@router.get("/api/publish/{publish_id}")
def get_publish_detail(publish_id: str):
    """获取单条发布详情"""
    try:
        detail = memory.get_publish_detail(publish_id)
        if not detail:
            raise HTTPException(status_code=404, detail="发布记录不存在")
        return detail
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取发布详情失败: {e}")


@router.delete("/api/publish/{publish_id}")
def delete_publish_record(publish_id: str):
    """删除发布记录"""
    try:
        success = memory.delete_content(publish_id)
        if not success:
            raise HTTPException(status_code=404, detail="发布记录不存在")
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除失败: {e}")
