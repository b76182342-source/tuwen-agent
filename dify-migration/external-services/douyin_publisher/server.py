"""
抖音图文发布微服务
独立于 Dify 运行，通过 HTTP API 接收发布请求
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional
import json
import os
from pathlib import Path
from datetime import datetime

app = FastAPI(title="抖音发布微服务", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 状态文件路径
STATE_FILE = Path(__file__).parent / "douyin_state.json"
PUBLISH_LOG = Path(__file__).parent / "publish_log.jsonl"


class PublishRequest(BaseModel):
    text: str = Field(..., description="文案内容", max_length=500)
    image_paths: List[str] = Field(..., description="图片本地路径", max_items=6)
    tags: List[str] = Field(default=[], description="标签列表")
    schedule_time: Optional[str] = Field(default=None, description="定时发布时间 ISO格式")


class PublishResponse(BaseModel):
    status: str
    message: str
    publish_id: Optional[str] = None
    publish_time: Optional[str] = None


@app.post("/publish", response_model=PublishResponse)
async def publish(req: PublishRequest):
    """
    执行图文发布

    发布流程:
    1. 参数验证
    2. 调用 Playwright 自动化脚本
    3. 记录发布日志
    """
    # 参数验证
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="文案不能为空")
    if not req.image_paths:
        raise HTTPException(status_code=400, detail="至少需要1张图片")
    if len(req.image_paths) > 6:
        raise HTTPException(status_code=400, detail="最多6张图片")

    # 验证图片文件存在
    for path in req.image_paths:
        if not Path(path).exists():
            raise HTTPException(status_code=400, detail=f"图片不存在: {path}")

    publish_id = datetime.now().strftime("%Y%m%d%H%M%S")

    try:
        # 这里调用实际的 Playwright 发布脚本
        # 当前返回模拟结果（需要接入真实 Playwright 时取消注释）

        # import subprocess
        # result = subprocess.run(
        #     ["python", str(Path(__file__).parent.parent.parent / "skills" / "douyin_publisher.py"),
        #      req.text,
        #      ",".join(req.image_paths),
        #      ",".join(req.tags)],
        #     capture_output=True, text=True, timeout=120
        # )
        # if result.returncode != 0:
        #     raise Exception(result.stderr)

        # 记录发布日志
        log_entry = {
            "publish_id": publish_id,
            "time": datetime.now().isoformat(),
            "text": req.text,
            "image_count": len(req.image_paths),
            "tag_count": len(req.tags),
        }
        with open(PUBLISH_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

        return PublishResponse(
            status="success",
            message="发布成功",
            publish_id=publish_id,
            publish_time=datetime.now().isoformat(),
        )

    except Exception as e:
        return PublishResponse(
            status="failed",
            message=f"发布失败: {str(e)}",
            publish_id=publish_id,
        )


@app.post("/publish/schedule")
async def schedule_publish(req: PublishRequest):
    """定时发布（预留接口）"""
    if not req.schedule_time:
        raise HTTPException(status_code=400, detail="schedule_time 不能为空")
    # TODO: 实现定时发布逻辑
    return {"status": "scheduled", "schedule_time": req.schedule_time}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "douyin-publisher"}


@app.get("/history")
async def publish_history(limit: int = 20):
    """获取发布历史"""
    if not PUBLISH_LOG.exists():
        return {"history": [], "total": 0}

    entries = []
    with open(PUBLISH_LOG, "r", encoding="utf-8") as f:
        for line in f:
            try:
                entries.append(json.loads(line.strip()))
            except json.JSONDecodeError:
                continue

    entries.reverse()
    return {"history": entries[:limit], "total": len(entries)}


if __name__ == "__main__":
    import uvicorn
    print("[发布服务] 启动中...")
    print("[发布服务] API 文档: http://localhost:9001/docs")
    uvicorn.run(app, host="0.0.0.0", port=9001)
