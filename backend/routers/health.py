"""
健康检查路由
"""
from datetime import datetime

from fastapi import APIRouter

router = APIRouter()


@router.get("/api/health")
def health():
    """健康检查接口（用于浏览器扩展检测后端状态）"""
    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
    }
