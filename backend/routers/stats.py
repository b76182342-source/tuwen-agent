"""
统计 & Qdrant 公共库路由
"""
import json
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request, Query

from utils.cache import cache as redis_cache
from utils.vector_store import vector_store

router = APIRouter()


@router.get("/api/stats/daily")
def get_daily_stats():
    """获取今日实时统计（Redis）"""
    stats = redis_cache.get_daily_stats()
    return {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "stats": stats,
        "redis_available": redis_cache._ok(),
    }


@router.get("/api/qdrant/hot-topics")
def get_qdrant_hot_topics(limit: int = 10):
    """获取热门话题（Qdrant topic_trends）"""
    topics = vector_store.get_hot_topics(limit)
    return {
        "topics": topics,
        "qdrant_available": vector_store._ok,
        "source": "qdrant" if vector_store._ok else "fallback",
    }


@router.get("/api/qdrant/similar-texts")
def search_similar_texts(text: str, limit: int = 5):
    """搜索相似文案 + 质量参考（Qdrant public_texts）"""
    if not text:
        return {"results": [], "message": "缺少 text 参数"}
    results = vector_store.search_similar_texts(text, limit)
    return {"results": results, "count": len(results)}


@router.get("/api/qdrant/search-tags")
def search_tags_qdrant(text: str, limit: int = 10):
    """语义搜索公共标签（Qdrant public_tags）"""
    if not text:
        return {"results": [], "message": "缺少 text 参数"}
    results = vector_store.search_tags(text, limit)
    return {"results": results, "count": len(results)}


@router.post("/api/qdrant/index-text")
async def index_text_to_qdrant(request: Request):
    """将高质量文案写入 Qdrant 公共库（评分 ≥ 4.0）"""
    try:
        body = json.loads(await request.body())
    except Exception:
        return {"success": False, "message": "无法解析请求体"}
    text = body.get("text", "").strip()
    if not text:
        return {"success": False, "message": "缺少 text"}
    score = body.get("quality_score", 0)
    if score < 4.0:
        return {"success": False, "message": f"评分 {score} < 4.0，未达到索引门槛"}
    count = vector_store.add_text(
        text=text,
        tags=body.get("tags", []),
        quality_score=score,
        views=body.get("views", 0),
        likes=body.get("likes", 0),
        engagement=body.get("real_engagement", 0),
    )
    return {"success": count > 0, "indexed": count}
