"""
Redis 短期记忆层

职责：
  · 会话上下文 (替代 state/current_session.json)
  · API 响应缓存 (DeepSeek 降本)
  · Skill 流水线状态
  · 限流保护
  · 实时统计
  · 创作草稿暂存

所有 Redis 操作失败时静默降级，不影响主流程。
"""
import json
import hashlib
import functools
import os
from typing import Optional, Dict, Any

try:
    import redis
    _REDIS_AVAILABLE = True
except ImportError:
    _REDIS_AVAILABLE = False
    redis = None


def _get_redis_url() -> str:
    return os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")


class CacheManager:
    """Redis 缓存管理器 — 单例"""

    _instance: Optional["CacheManager"] = None

    def __init__(self):
        self.client: Optional["redis.Redis"] = None
        if _REDIS_AVAILABLE:
            try:
                self.client = redis.Redis.from_url(
                    _get_redis_url(),
                    decode_responses=True,
                    socket_connect_timeout=2,
                    socket_timeout=2,
                    retry_on_timeout=False,
                )
                self.client.ping()
                print("[Redis] 连接成功")
            except Exception as e:
                print(f"[Redis] 不可用 (降级运行): {e}")
                self.client = None

    @classmethod
    def get(cls) -> "CacheManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _ok(self) -> bool:
        return self.client is not None

    # ==================== 会话上下文 ====================

    def save_session(self, conv_id: str, state: dict) -> bool:
        """保存会话状态，TTL 7天"""
        if not self._ok():
            return False
        try:
            key = f"session:{conv_id}"
            self.client.setex(key, 7 * 86400, json.dumps(state, ensure_ascii=False, default=str))
            return True
        except Exception:
            return False

    def load_session(self, conv_id: str) -> Optional[dict]:
        if not self._ok():
            return None
        try:
            data = self.client.get(f"session:{conv_id}")
            return json.loads(data) if data else None
        except Exception:
            return None

    def delete_session(self, conv_id: str) -> bool:
        if not self._ok():
            return False
        try:
            self.client.delete(f"session:{conv_id}")
            return True
        except Exception:
            return False

    # ==================== API 响应缓存 ====================

    def cached(self, ttl: int = 3600):
        """装饰器: 缓存函数返回值到 Redis

        用法:
            @cache.cached(ttl=86400)
            def recommend_tags(text): ...
        """
        def decorator(func):
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                if not self._ok():
                    return func(*args, **kwargs)
                # 构建缓存 key
                payload = json.dumps({"args": args, "kwargs": kwargs}, ensure_ascii=False, sort_keys=True)
                key = f"llm:cache:{func.__name__}:{hashlib.md5(payload.encode()).hexdigest()[:16]}"
                try:
                    cached = self.client.get(key)
                    if cached:
                        return json.loads(cached)
                except Exception:
                    pass
                result = func(*args, **kwargs)
                try:
                    self.client.setex(key, ttl, json.dumps(result, ensure_ascii=False, default=str))
                except Exception:
                    pass
                return result
            return wrapper
        return decorator

    def get_cached(self, namespace: str, cache_key: str) -> Optional[Any]:
        """手动获取缓存"""
        if not self._ok():
            return None
        try:
            data = self.client.get(f"{namespace}:{cache_key}")
            return json.loads(data) if data else None
        except Exception:
            return None

    def set_cached(self, namespace: str, cache_key: str, value: Any, ttl: int = 3600) -> bool:
        """手动设置缓存"""
        if not self._ok():
            return False
        try:
            self.client.setex(
                f"{namespace}:{cache_key}",
                ttl,
                json.dumps(value, ensure_ascii=False, default=str),
            )
            return True
        except Exception:
            return False

    # ==================== Skill 流水线状态 ====================

    def save_pipeline(self, conv_id: str, stage: str, status: str, data: dict = None) -> bool:
        """保存 Skill 执行中间状态"""
        if not self._ok():
            return False
        try:
            key = f"skill:pipe:{conv_id}"
            self.client.hset(key, stage, json.dumps({"status": status, "data": data}, ensure_ascii=False))
            self.client.expire(key, 3600)
            return True
        except Exception:
            return False

    def get_pipeline(self, conv_id: str) -> dict:
        """获取 Skill 流水线完整状态"""
        if not self._ok():
            return {}
        try:
            raw = self.client.hgetall(f"skill:pipe:{conv_id}")
            return {k: json.loads(v) for k, v in raw.items()}
        except Exception:
            return {}

    # ==================== 限流 ====================

    def check_rate_limit(self, namespace: str, max_calls: int, window: int = 86400) -> bool:
        """检查是否超限。返回 True 表示允许调用"""
        if not self._ok():
            return True  # Redis 不可用时不做限流
        try:
            from datetime import datetime
            today = datetime.now().strftime("%Y-%m-%d")
            key = f"ratelimit:{namespace}:{today}"
            count = self.client.incr(key)
            if count == 1:
                self.client.expire(key, window)
            return count <= max_calls
        except Exception:
            return True

    def get_rate_limit_remaining(self, namespace: str, max_calls: int) -> int:
        """获取剩余调用次数"""
        if not self._ok():
            return max_calls
        try:
            from datetime import datetime
            today = datetime.now().strftime("%Y-%m-%d")
            key = f"ratelimit:{namespace}:{today}"
            count = int(self.client.get(key) or 0)
            return max(0, max_calls - count)
        except Exception:
            return max_calls

    # ==================== 实时统计 ====================

    def incr_stat(self, field: str, amount: int = 1) -> bool:
        """递增实时统计计数器"""
        if not self._ok():
            return False
        try:
            from datetime import datetime
            today = datetime.now().strftime("%Y-%m-%d")
            self.client.hincrby(f"stats:daily:{today}", field, amount)
            self.client.expire(f"stats:daily:{today}", 30 * 86400)
            return True
        except Exception:
            return False

    def get_daily_stats(self) -> dict:
        """获取今日实时统计"""
        if not self._ok():
            return {}
        try:
            from datetime import datetime
            today = datetime.now().strftime("%Y-%m-%d")
            return self.client.hgetall(f"stats:daily:{today}")
        except Exception:
            return {}

    # ==================== 创作草稿 ====================

    def save_draft(self, conv_id: str, draft: dict) -> bool:
        if not self._ok():
            return False
        try:
            self.client.setex(f"draft:{conv_id}", 86400, json.dumps(draft, ensure_ascii=False))
            return True
        except Exception:
            return False

    def load_draft(self, conv_id: str) -> Optional[dict]:
        if not self._ok():
            return None
        try:
            data = self.client.get(f"draft:{conv_id}")
            return json.loads(data) if data else None
        except Exception:
            return None


# 全局单例
cache = CacheManager()
