"""
抖音数据同步路由
"""
import json

from fastapi import APIRouter, HTTPException, Request, Query
from pydantic import BaseModel, Field
from typing import List

from backend.constants import STATE_FILE
from utils.memory import MemoryManager

router = APIRouter()
memory = MemoryManager()

# =====================================================
# Pydantic 模型
# =====================================================

class DouyinSyncRequest(BaseModel):
    records: List[dict] = Field(..., min_items=1, max_items=100)


# =====================================================
# 抖音数据同步
# =====================================================


@router.post("/api/douyin/login")
def douyin_login():
    """
    [已禁用] 触发浏览器扫码登录（Playwright 有头模式）

    发布 Skill 已永久禁用。此端点保留但不再工作。
    """
    return {"success": False, "message": "发布功能已禁用。本产品为创作顾问，不提供自动发布。"}


@router.get("/api/douyin/status")
def douyin_status():
    """检查抖音登录状态"""
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)
            cookies = state.get("cookies", [])
            # 找关键 Cookie 判断登录状态
            session_cookie = next((c for c in cookies if c.get("name") == "sessionid"), None)
            is_logged_in = bool(session_cookie and session_cookie.get("value"))
            return {
                "logged_in": is_logged_in,
                "cookie_count": len(cookies),
                "state_file": str(STATE_FILE),
                "message": "已登录" if is_logged_in else "Cookie 已过期",
            }
        except Exception as e:
            return {"logged_in": False, "error": str(e)}
    return {"logged_in": False, "cookie_count": 0, "message": "未找到登录状态文件"}


@router.post("/api/douyin/sync")
def douyin_sync(data: dict = None):
    """
    录入个人发布数据到 memory.db
    接受前端提交的发布记录数组，写入 publish_history 表。
    """
    if not data or "records" not in data:
        return {"success": False, "message": "缺少 records 字段"}

    count = memory.batch_sync_records(data["records"])
    return {"success": True, "synced": count, "message": f"成功同步 {count} 条记录"}


@router.post("/api/douyin/sync-auto")
def douyin_sync_auto():
    """
    [已禁用] 自动拉取创作者数据（需有效 Cookie）
    发布 Skill 已禁用，此端点仅返回提示。
    """
    return {"success": False, "message": "发布 Skill 已禁用。请使用 /api/douyin/sync 手动录入数据。"}


@router.get("/api/douyin/sync-history")
def get_sync_history():
    """获取同步历史记录"""
    return memory.get_publish_history(limit=50)
