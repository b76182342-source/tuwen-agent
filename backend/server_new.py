"""
抖音创作顾问 Agent — 后端 API 服务器（模块化版本）

启动：python backend/server.py
端口：9000

路由拆分:
  routers/health.py        — 健康检查
  routers/conversations.py — 会话 + 对话管理（11 路由）
  routers/agent.py         — Agent 执行管线（1 路由 + 2 新增）
  routers/materials.py     — 素材管理（6 路由）
  routers/publish.py       — 发布记录（4 路由）
  routers/analytics.py     — 数据分析（4 路由）
  routers/douyin.py        — 抖音同步（5 路由）
  routers/upload.py        — 图片上传（1 路由）
  routers/stats.py         — Redis/Qdrant 统计（6 路由）
"""
import os
import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import uvicorn

from backend.constants import PERSONAL_DIR, PUBLIC_DIR
from utils.config import get_api_key

logger = logging.getLogger("douyin-agent")

# =====================================================
# App 工厂
# =====================================================
app = FastAPI(title="抖音创作顾问 Agent API")

# =====================================================
# CORS
# =====================================================
_cors_origins = os.environ.get(
    "CORS_ORIGINS",
    "http://localhost:3000,http://localhost:5173,http://127.0.0.1:3000,http://127.0.0.1:5173"
).split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _cors_origins if o.strip()],
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", "Authorization", "X-Request-Id"],
    allow_credentials=True,
)

# =====================================================
# API 认证中间件
# =====================================================
_PUBLIC_PATHS = {"/api/health", "/docs", "/openapi.json", "/redoc"}


@app.middleware("http")
async def api_key_middleware(request: Request, call_next):
    """API Key 认证中间件 — 保护所有 /api/* 端点"""
    path = request.url.path
    if path in _PUBLIC_PATHS or path.startswith("/personal/") or path.startswith("/public/"):
        return await call_next(request)

    if path.startswith("/api/"):
        expected_key = get_api_key()
        if expected_key:
            auth_header = request.headers.get("Authorization", "")
            api_key_header = request.headers.get("X-API-Key", "")

            provided_key = ""
            if auth_header.startswith("Bearer "):
                provided_key = auth_header[7:]
            elif api_key_header:
                provided_key = api_key_header

            if provided_key != expected_key:
                from fastapi.responses import JSONResponse
                return JSONResponse(
                    status_code=401,
                    content={"error": "unauthorized", "message": "无效的 API Key"}
                )

    return await call_next(request)


# =====================================================
# 注册路由模块
# =====================================================

from backend.routers.health import router as health_router
from backend.routers.conversations import router as conversations_router
from backend.routers.agent import router as agent_router
from backend.routers.materials import router as materials_router
from backend.routers.publish import router as publish_router
from backend.routers.analytics import router as analytics_router
from backend.routers.douyin import router as douyin_router
from backend.routers.upload import router as upload_router
from backend.routers.stats import router as stats_router

app.include_router(health_router)
app.include_router(conversations_router)
app.include_router(agent_router)
app.include_router(materials_router)
app.include_router(publish_router)
app.include_router(analytics_router)
app.include_router(douyin_router)
app.include_router(upload_router)
app.include_router(stats_router)

# =====================================================
# 静态文件挂载（必须在所有路由之后）
# =====================================================
PERSONAL_DIR.mkdir(parents=True, exist_ok=True)
PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/personal", StaticFiles(directory=str(PERSONAL_DIR)), name="personal")
app.mount("/public", StaticFiles(directory=str(PUBLIC_DIR)), name="public")

# =====================================================
# 启动入口
# =====================================================
if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=9000)
