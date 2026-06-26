"""
Qdrant 公共数据库层

四个 Collection：
  public_tags    — 公共标签库（语义搜索标签推荐）
  public_texts   — 热门文案参考库（相似文案搜索 + 质量预测）
  public_images  — 图片描述向量库（图文匹配）
  topic_trends   — 话题趋势（热点检测）

降级: Qdrant 不可用时所有查询返回空，主流程回退到原有逻辑。
"""
import os
import json
import threading
from typing import List, Dict, Optional

try:
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, VectorParams, PointStruct, Filter
    _QDRANT_AVAILABLE = True
except ImportError:
    _QDRANT_AVAILABLE = False
    QdrantClient = None
    Distance = None
    VectorParams = None
    PointStruct = None
    Filter = None

from utils.embeddings import embed, embed_batch, get_dim

_QDRANT_URL = os.environ.get("QDRANT_URL", "http://127.0.0.1:6333")

COLLECTIONS = {
    "public_tags": {
        "desc": "公共标签库",
        "schema": {
            "tag": str, "category": str, "usage_count": int,
            "avg_engagement": float, "trending_score": float,
        },
    },
    "public_texts": {
        "desc": "热门文案参考库",
        "schema": {
            "text": str, "tags": list, "quality_score": float,
            "real_views": int, "real_likes": int, "real_engagement": float,
        },
    },
    "public_images": {
        "desc": "图片描述向量库",
        "schema": {
            "url": str, "description": str, "tags": list,
            "style": str, "usage_count": int, "source": str,
        },
    },
    "topic_trends": {
        "desc": "话题趋势",
        "schema": {
            "topic": str, "keywords": list, "hot_score": float,
            "related_tags": list, "valid_from": str, "valid_until": str,
        },
    },
}

DIM = get_dim()


class VectorStore:
    """Qdrant 向量库管理器 — 单例"""

    _instance: Optional["VectorStore"] = None
    _lock = threading.Lock()

    def __init__(self):
        self.client: Optional[QdrantClient] = None
        self._ok = False
        if not _QDRANT_AVAILABLE:
            print("[Qdrant] qdrant-client 未安装，降级运行")
            return
        try:
            self.client = QdrantClient(url=_QDRANT_URL, timeout=5, check_compatibility=False)
            self.client.get_collections()
            self._ok = True
            self._init_collections()
            print(f"[Qdrant] 连接成功 ({_QDRANT_URL})")
        except Exception as e:
            print(f"[Qdrant] 不可用 (降级运行): {e}")
            self.client = None

    @classmethod
    def get(cls) -> "VectorStore":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def _init_collections(self):
        """确保 4 个 Collection 存在"""
        if not self._ok:
            return
        for name, info in COLLECTIONS.items():
            try:
                self.client.get_collection(name)
            except Exception:
                self.client.create_collection(
                    collection_name=name,
                    vectors_config=VectorParams(size=DIM, distance=Distance.COSINE),
                )
                print(f"[Qdrant] 创建 Collection: {name} ({info['desc']})")

    # ==================== public_tags ====================

    def search_tags(self, text: str, limit: int = 20) -> List[Dict]:
        """根据文案语义搜索最匹配的公共标签"""
        if not self._ok:
            return []
        try:
            vector = embed(text)
            results = self.client.search(
                collection_name="public_tags",
                query_vector=vector,
                limit=limit,
            )
            return [
                {
                    "tag": r.payload.get("tag", ""),
                    "category": r.payload.get("category", ""),
                    "usage_count": r.payload.get("usage_count", 0),
                    "avg_engagement": r.payload.get("avg_engagement", 0.0),
                    "trending_score": r.payload.get("trending_score", 0.0),
                    "similarity": round(r.score, 4),
                }
                for r in results
            ]
        except Exception as e:
            print(f"[Qdrant] search_tags 失败: {e}")
            return []

    def upsert_tags(self, tags: List[Dict]) -> int:
        """批量写入/更新公共标签"""
        if not self._ok or not tags:
            return 0
        try:
            texts = [t["tag"] for t in tags]
            vectors = embed_batch(texts)
            points = [
                PointStruct(
                    id=abs(hash(t["tag"])) % (10 ** 12),
                    vector=vectors[i],
                    payload={
                        "tag": t["tag"],
                        "category": t.get("category", "通用"),
                        "usage_count": t.get("usage_count", 1),
                        "avg_engagement": t.get("avg_engagement", 0.0),
                        "trending_score": t.get("trending_score", 0.0),
                    },
                )
                for i, t in enumerate(tags)
            ]
            self.client.upsert(collection_name="public_tags", points=points)
            return len(points)
        except Exception as e:
            print(f"[Qdrant] upsert_tags 失败: {e}")
            return 0

    # ==================== public_texts ====================

    def search_similar_texts(self, text: str, limit: int = 5) -> List[Dict]:
        """搜索相似文案 + 返回真实表现数据"""
        if not self._ok:
            return []
        try:
            vector = embed(text)
            results = self.client.search(
                collection_name="public_texts",
                query_vector=vector,
                limit=limit,
            )
            return [
                {
                    "text": r.payload.get("text", ""),
                    "tags": r.payload.get("tags", []),
                    "quality_score": r.payload.get("quality_score", 0.0),
                    "real_views": r.payload.get("real_views", 0),
                    "real_likes": r.payload.get("real_likes", 0),
                    "real_engagement": r.payload.get("real_engagement", 0.0),
                    "similarity": round(r.score, 4),
                }
                for r in results
            ]
        except Exception as e:
            print(f"[Qdrant] search_similar_texts 失败: {e}")
            return []

    def add_text(self, text: str, tags: List[str] = None,
                 quality_score: float = 0.0, views: int = 0,
                 likes: int = 0, engagement: float = 0.0) -> int:
        """写入一条高质量文案到公共库（仅评分 ≥ 4.0）"""
        if not self._ok:
            return 0
        if quality_score < 4.0:
            return 0
        try:
            vector = embed(text)
            point_id = abs(hash(text)) % (10 ** 12)
            self.client.upsert(
                collection_name="public_texts",
                points=[PointStruct(
                    id=point_id,
                    vector=vector,
                    payload={
                        "text": text,
                        "tags": tags or [],
                        "quality_score": quality_score,
                        "real_views": views,
                        "real_likes": likes,
                        "real_engagement": engagement,
                    },
                )],
            )
            return 1
        except Exception as e:
            print(f"[Qdrant] add_text 失败: {e}")
            return 0

    # ==================== public_images ====================

    def search_images(self, text: str, limit: int = 6) -> List[Dict]:
        """根据文案语义搜索匹配图片"""
        if not self._ok:
            return []
        try:
            vector = embed(text)
            results = self.client.search(
                collection_name="public_images",
                query_vector=vector,
                limit=limit,
            )
            return [
                {
                    "url": r.payload.get("url", ""),
                    "description": r.payload.get("description", ""),
                    "tags": r.payload.get("tags", []),
                    "style": r.payload.get("style", ""),
                    "usage_count": r.payload.get("usage_count", 0),
                    "source": r.payload.get("source", ""),
                    "similarity": round(r.score, 4),
                }
                for r in results
            ]
        except Exception as e:
            print(f"[Qdrant] search_images 失败: {e}")
            return []

    def add_image(self, url: str, description: str, tags: List[str] = None,
                  style: str = "", source: str = "") -> int:
        if not self._ok:
            return 0
        try:
            vector = embed(description or tags[0] if tags else "通用")
            point_id = abs(hash(url)) % (10 ** 12)
            self.client.upsert(
                collection_name="public_images",
                points=[PointStruct(
                    id=point_id,
                    vector=vector,
                    payload={
                        "url": url, "description": description,
                        "tags": tags or [], "style": style,
                        "usage_count": 1, "source": source,
                    },
                )],
            )
            return 1
        except Exception as e:
            print(f"[Qdrant] add_image 失败: {e}")
            return 0

    # ==================== topic_trends ====================

    def get_hot_topics(self, limit: int = 10) -> List[Dict]:
        """获取当前热门话题（按 hot_score 降序）"""
        if not self._ok:
            return []
        try:
            results = self.client.scroll(
                collection_name="topic_trends",
                limit=limit,
                with_payload=True,
                with_vectors=False,
            )[0]
            topics = [
                {
                    "topic": r.payload.get("topic", ""),
                    "keywords": r.payload.get("keywords", []),
                    "hot_score": r.payload.get("hot_score", 0.0),
                    "related_tags": r.payload.get("related_tags", []),
                }
                for r in results
            ]
            return sorted(topics, key=lambda t: t["hot_score"], reverse=True)
        except Exception as e:
            print(f"[Qdrant] get_hot_topics 失败: {e}")
            return []

    def upsert_topic(self, topic: str, keywords: List[str],
                     hot_score: float, related_tags: List[str] = None) -> int:
        if not self._ok:
            return 0
        try:
            vector = embed(topic)
            point_id = abs(hash(topic)) % (10 ** 12)
            self.client.upsert(
                collection_name="topic_trends",
                points=[PointStruct(
                    id=point_id,
                    vector=vector,
                    payload={
                        "topic": topic, "keywords": keywords,
                        "hot_score": hot_score,
                        "related_tags": related_tags or [],
                        "valid_from": "",
                        "valid_until": "",
                    },
                )],
            )
            return 1
        except Exception as e:
            print(f"[Qdrant] upsert_topic 失败: {e}")
            return 0


# 全局单例
vector_store = VectorStore()
