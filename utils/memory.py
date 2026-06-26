"""
记忆层管理器 v2 — 对齐抖音数据导出格式

表结构:
  content_posts        核心发布表（播放量/点赞/评论/分享/收藏/划走率/文案展开率/涨粉/脱粉...）
  traffic_daily        流量日趋势
  follower_daily       粉丝日趋势
  tags                 标签库
  conversations        对话会话
  conversation_messages 对话历史
"""
import json
import secrets
import sqlite3
import threading
import contextlib
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

from utils.config import PROJECT_ROOT
from utils.cache import cache as redis_cache  # Redis 短期记忆


class MemoryManager:
    """记忆层管理器 v2"""

    STAGES = ["标签推荐", "图片推荐", "配乐推荐", "内容评估"]
    SKILL_MAP = {
        "Skill1": "标签推荐", "Skill2": "图片推荐",
        "Skill3": "配乐推荐", "Skill4": "内容评估",
    }

    def __init__(self, project_root: str = None):
        self.root = Path(project_root) if project_root else PROJECT_ROOT
        self.state_dir = self.root / "state"
        self.db_path = self.root / "memory.db"
        self._lock = threading.Lock()
        self._init_db()

    @contextlib.contextmanager
    def _get_conn(self):
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            with self._lock:
                yield conn
        finally:
            conn.close()

    # ==================== 数据库初始化 ====================

    def _init_db(self) -> None:
        """仅在新表不存在时创建（不影响已迁移的数据）"""
        with self._get_conn() as conn:
            c = conn.cursor()

            c.execute("""
                CREATE TABLE IF NOT EXISTS content_posts (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    text            TEXT    NOT NULL,
                    publish_time    TEXT,
                    views           INTEGER DEFAULT 0,
                    likes           INTEGER DEFAULT 0,
                    comments        INTEGER DEFAULT 0,
                    shares          INTEGER DEFAULT 0,
                    favorites       INTEGER DEFAULT 0,
                    swipe_away_rate REAL    DEFAULT 0.0,
                    copy_expand_rate REAL   DEFAULT 0.0,
                    avg_images_viewed REAL  DEFAULT 0.0,
                    fan_gain        INTEGER DEFAULT 0,
                    fan_loss        INTEGER DEFAULT 0,
                    fan_play_ratio  REAL    DEFAULT 0.0,
                    source          TEXT    DEFAULT 'manual',
                    evaluation_score REAL   DEFAULT 0.0,
                    evaluation_level TEXT   DEFAULT '未评估',
                    tags_json       TEXT,
                    images_json     TEXT,
                    music_json      TEXT,
                    created_at      TEXT    DEFAULT (datetime('now','localtime')),
                    updated_at      TEXT
                )
            """)

            c.execute("""
                CREATE TABLE IF NOT EXISTS traffic_daily (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    content_id  INTEGER REFERENCES content_posts(id),
                    date        TEXT    NOT NULL,
                    views       INTEGER DEFAULT 0,
                    source      TEXT    DEFAULT '抖音',
                    UNIQUE(content_id, date, source)
                )
            """)

            c.execute("""
                CREATE TABLE IF NOT EXISTS follower_daily (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    content_id  INTEGER REFERENCES content_posts(id),
                    date        TEXT    NOT NULL,
                    fan_gain    INTEGER DEFAULT 0,
                    fan_loss    INTEGER DEFAULT 0,
                    source      TEXT    DEFAULT '抖音',
                    UNIQUE(content_id, date, source)
                )
            """)

            c.execute("""
                CREATE TABLE IF NOT EXISTS tags (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    name        TEXT    UNIQUE NOT NULL,
                    usage_count INTEGER DEFAULT 1,
                    total_likes INTEGER DEFAULT 0,
                    total_views INTEGER DEFAULT 0,
                    created_at  TEXT    DEFAULT (datetime('now','localtime'))
                )
            """)

            c.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id          TEXT    PRIMARY KEY,
                    title       TEXT    DEFAULT '新对话',
                    user_id     TEXT    DEFAULT 'default_user',
                    created_at  TEXT    DEFAULT (datetime('now','localtime')),
                    updated_at  TEXT
                )
            """)

            c.execute("""
                CREATE TABLE IF NOT EXISTS conversation_messages (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    conv_id     TEXT    REFERENCES conversations(id),
                    role        TEXT    NOT NULL,
                    content     TEXT    NOT NULL,
                    metadata    TEXT,
                    created_at  TEXT    DEFAULT (datetime('now','localtime'))
                )
            """)

            conn.commit()

    # ==================== 短期记忆：会话状态 ====================

    def _default_session(self) -> dict:
        return {
            "session_id": self._generate_session_id(),
            "stage": "标签推荐",
            "text": "", "tags": [], "images": [], "music": {},
            "evaluation": None, "publish_status": "未发布",
            "rollback_history": [],
            "iteration": 0, "iteration_history": [],
            "score_threshold": 4.0,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }

    def _generate_session_id(self) -> str:
        return f"sess_{secrets.token_urlsafe(12)}"

    def load_session(self) -> dict:
        return self._default_session()

    def save_session(self, state: dict) -> None:
        """持久化会话状态 → Redis (热) + SQLite (冷)"""
        conv_id = state.get("session_id") or state.get("conversation_id")
        if not conv_id:
            return
        # Redis 热缓存（TTL 7天）
        redis_cache.save_session(conv_id, state)
        # SQLite 持久化
        evaluation = state.get("evaluation")
        try:
            with self._get_conn() as conn:
                conn.execute(
                    """INSERT INTO conversation_messages (conv_id, role, content, metadata)
                       VALUES (?, 'assistant', ?, ?)""",
                    (conv_id, json.dumps(state, ensure_ascii=False, default=str),
                     json.dumps({"evaluation": evaluation}, ensure_ascii=False))
                )
                conn.execute(
                    "UPDATE conversations SET updated_at = datetime('now','localtime') WHERE id = ?",
                    (conv_id,)
                )
                conn.commit()
        except Exception as e:
            print(f"[save_session] SQLite 保存失败: {e}")

    def new_session(self, text: str = "") -> dict:
        s = self._default_session()
        if text:
            s["text"] = text
        return s

    # ==================== 内容发布 CRUD ====================

    def batch_sync_records(self, records: List[Dict]) -> int:
        """批量同步发布记录 — 对齐抖音导出字段，返回成功条数"""
        with self._get_conn() as conn:
            c = conn.cursor()
            count = 0
            for rec in records:
                try:
                    text = (rec.get("text") or "").strip()
                    if not text:
                        continue

                    # 去重：同文案不重复录入
                    existing = c.execute(
                        "SELECT id FROM content_posts WHERE text = ?", (text,)
                    ).fetchone()
                    if existing:
                        continue

                    c.execute("""
                        INSERT INTO content_posts
                        (text, publish_time, views, likes, comments, shares, favorites,
                         swipe_away_rate, copy_expand_rate, avg_images_viewed,
                         fan_gain, fan_loss, fan_play_ratio,
                         source, evaluation_score, evaluation_level, tags_json, images_json)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        text,
                        rec.get("publish_time", datetime.now().isoformat()),
                        int(rec.get("views", 0)),
                        int(rec.get("likes", 0)),
                        int(rec.get("comments", 0)),
                        int(rec.get("shares", 0)),
                        int(rec.get("favorites", 0)),
                        float(rec.get("swipe_away_rate", 0)),
                        float(rec.get("copy_expand_rate", 0)),
                        float(rec.get("avg_images_viewed", 0)),
                        int(rec.get("fan_gain", 0)),
                        int(rec.get("fan_loss", 0)),
                        float(rec.get("fan_play_ratio", 0)),
                        rec.get("source", "manual"),
                        float(rec.get("evaluation_score", 0)),
                        rec.get("evaluation_level", "未评估"),
                        json.dumps(rec.get("tags", []), ensure_ascii=False) if rec.get("tags") else None,
                        json.dumps(rec.get("images", []), ensure_ascii=False) if rec.get("images") else None,
                    ))
                    post_id = c.lastrowid

                    # 同步标签
                    for tag in (rec.get("tags") or []):
                        tag_name = tag.strip().lstrip("#") if isinstance(tag, str) else str(tag)
                        if tag_name:
                            self._upsert_tag(c, tag_name, int(rec.get("likes", 0)), int(rec.get("views", 0)))

                    # 流量日趋势
                    for td in (rec.get("traffic_daily") or []):
                        if isinstance(td, dict):
                            c.execute(
                                "INSERT OR IGNORE INTO traffic_daily (content_id, date, views, source) VALUES (?, ?, ?, ?)",
                                (post_id, td.get("date", ""), int(td.get("views", 0)), td.get("source", "抖音"))
                            )

                    # 粉丝日趋势
                    for fd in (rec.get("follower_daily") or []):
                        if isinstance(fd, dict):
                            c.execute(
                                "INSERT OR IGNORE INTO follower_daily (content_id, date, fan_gain, fan_loss, source) VALUES (?, ?, ?, ?, ?)",
                                (post_id, fd.get("date", ""), int(fd.get("fan_gain", 0)), int(fd.get("fan_loss", 0)), fd.get("source", "抖音"))
                            )

                    count += 1
                except Exception as e:
                    print(f"[同步] 记录失败: {e}")
                    continue

            conn.commit()
            print(f"[同步] 完成: 成功 {count} 条")
            return count

    def get_publish_history(self, limit: int = 50, source: str = None) -> List[Dict]:
        """获取发布历史"""
        with self._get_conn() as conn:
            query = "SELECT * FROM content_posts"
            params = []
            if source:
                query += " WHERE source = ?"
                params.append(source)
            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)
            return [dict(r) for r in conn.execute(query, params).fetchall()]

    def get_content_detail(self, post_id: int) -> Optional[Dict]:
        """获取单条内容详情含日趋势数据"""
        with self._get_conn() as conn:
            post = conn.execute("SELECT * FROM content_posts WHERE id = ?", (post_id,)).fetchone()
            if not post:
                return None
            result = dict(post)
            result["traffic_daily"] = [
                dict(r) for r in conn.execute(
                    "SELECT * FROM traffic_daily WHERE content_id = ? ORDER BY date", (post_id,)
                ).fetchall()
            ]
            result["follower_daily"] = [
                dict(r) for r in conn.execute(
                    "SELECT * FROM follower_daily WHERE content_id = ? ORDER BY date", (post_id,)
                ).fetchall()
            ]
            return result

    def update_content_stats(self, post_id: int, **kwargs) -> bool:
        """更新内容统计"""
        allowed = {"views", "likes", "comments", "shares", "favorites",
                   "swipe_away_rate", "copy_expand_rate", "avg_images_viewed",
                   "fan_gain", "fan_loss", "fan_play_ratio",
                   "evaluation_score", "evaluation_level"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return False
        sets = ", ".join(f"{k} = ?" for k in updates)
        vals = list(updates.values()) + [post_id]
        with self._get_conn() as conn:
            conn.execute(f"UPDATE content_posts SET {sets}, updated_at = datetime('now','localtime') WHERE id = ?", vals)
            conn.commit()
        return True

    def delete_content(self, post_id: int) -> bool:
        """删除内容及关联日趋势"""
        with self._get_conn() as conn:
            conn.execute("DELETE FROM traffic_daily WHERE content_id = ?", (post_id,))
            conn.execute("DELETE FROM follower_daily WHERE content_id = ?", (post_id,))
            conn.execute("DELETE FROM content_posts WHERE id = ?", (post_id,))
            conn.commit()
        return True

    # ==================== 数据分析 ====================

    def analyze_personal_data(self) -> Dict:
        """数据分析 — 对齐抖音数据维度"""
        with self._get_conn() as conn:
            c = conn.cursor()

            total = c.execute("SELECT COUNT(*) FROM content_posts").fetchone()[0]
            if total == 0:
                return {
                    "total_publishes": 0,
                    "avg_views": 0, "avg_likes": 0, "avg_comments": 0,
                    "avg_shares": 0, "avg_favorites": 0,
                    "avg_swipe_away_rate": 0, "avg_copy_expand_rate": 0,
                    "avg_images_viewed": 0,
                    "total_fan_gain": 0, "total_fan_loss": 0,
                    "avg_fan_play_ratio": 0,
                    "total_views": 0, "total_likes": 0, "total_comments": 0,
                    "best_content": None, "top_tags": [],
                    "source_breakdown": {"manual": 0, "extension": 0, "agent": 0},
                }

            row = c.execute("""
                SELECT AVG(views), AVG(likes), AVG(comments), AVG(shares), AVG(favorites),
                       AVG(swipe_away_rate), AVG(copy_expand_rate), AVG(avg_images_viewed),
                       SUM(fan_gain), SUM(fan_loss), AVG(fan_play_ratio),
                       SUM(views), SUM(likes), SUM(comments)
                FROM content_posts
            """).fetchone()

            # 最佳内容
            best = c.execute("""
                SELECT * FROM content_posts
                WHERE views > 0
                ORDER BY (likes + comments * 2.0) / views DESC LIMIT 1
            """).fetchone()

            # Top 标签
            top_tags = []
            tag_rows = c.execute("""
                SELECT name, usage_count, total_likes, total_views
                FROM tags ORDER BY usage_count DESC LIMIT 10
            """).fetchall()
            for t in tag_rows:
                top_tags.append({
                    "tag": t["name"],
                    "usage_count": t["usage_count"] or 0,
                    "avg_likes": round(t["total_likes"] / max(t["usage_count"], 1), 1),
                    "avg_views": round(t["total_views"] / max(t["usage_count"], 1), 1),
                    "avg_engagement_rate": round(t["total_likes"] / max(t["total_views"], 1), 4),
                })

            source_rows = c.execute(
                "SELECT source, COUNT(*) FROM content_posts GROUP BY source"
            ).fetchall()
            source_breakdown = {r["source"]: r[1] for r in source_rows}

            return {
                "total_publishes": total,
                "avg_views": round(row[0] or 0, 1),
                "avg_likes": round(row[1] or 0, 1),
                "avg_comments": round(row[2] or 0, 1),
                "avg_shares": round(row[3] or 0, 1),
                "avg_favorites": round(row[4] or 0, 1),
                "avg_swipe_away_rate": round(row[5] or 0, 4),
                "avg_copy_expand_rate": round(row[6] or 0, 4),
                "avg_images_viewed": round(row[7] or 0, 1),
                "total_fan_gain": int(row[8] or 0),
                "total_fan_loss": int(row[9] or 0),
                "avg_fan_play_ratio": round(row[10] or 0, 4),
                "total_views": int(row[11] or 0),
                "total_likes": int(row[12] or 0),
                "total_comments": int(row[13] or 0),
                "best_content": dict(best) if best else None,
                "top_tags": top_tags,
                "source_breakdown": source_breakdown,
            }

    def get_traffic_trend(self, content_id: int = None, limit: int = 30) -> List[Dict]:
        """获取流量日趋势"""
        with self._get_conn() as conn:
            if content_id:
                rows = conn.execute(
                    "SELECT * FROM traffic_daily WHERE content_id = ? ORDER BY date LIMIT ?",
                    (content_id, limit)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT date, SUM(views) as views FROM traffic_daily GROUP BY date ORDER BY date LIMIT ?",
                    (limit,)
                ).fetchall()
            return [dict(r) for r in rows]

    def get_follower_trend(self, content_id: int = None, limit: int = 30) -> List[Dict]:
        """获取粉丝日趋势"""
        with self._get_conn() as conn:
            if content_id:
                rows = conn.execute(
                    "SELECT * FROM follower_daily WHERE content_id = ? ORDER BY date LIMIT ?",
                    (content_id, limit)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT date, SUM(fan_gain) as fan_gain, SUM(fan_loss) as fan_loss FROM follower_daily GROUP BY date ORDER BY date LIMIT ?",
                    (limit,)
                ).fetchall()
            return [dict(r) for r in rows]

    # ==================== 标签管理 ====================

    def _upsert_tag(self, cursor, name: str, likes: int = 0, views: int = 0):
        cursor.execute("""
            INSERT INTO tags (name, usage_count, total_likes, total_views)
            VALUES (?, 1, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                usage_count = usage_count + 1,
                total_likes = total_likes + ?,
                total_views = total_views + ?
        """, (name, likes, views, likes, views))

    def get_top_tags(self, limit: int = 10) -> List[Dict]:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM tags ORDER BY usage_count DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]

    def get_tag_performance(self, tag: str) -> Optional[Dict]:
        with self._get_conn() as conn:
            row = conn.execute("SELECT * FROM tags WHERE name = ?", (tag,)).fetchone()
            return dict(row) if row else None

    # ==================== 对话管理 ====================

    def create_conversation(self, title: str = None, user_id: str = None) -> str:
        conv_id = f"conv_{secrets.token_urlsafe(16)}"
        with self._get_conn() as conn:
            conn.execute(
                "INSERT INTO conversations (id, title, user_id) VALUES (?, ?, ?)",
                (conv_id, title or "新对话", user_id or "default_user")
            )
            conn.commit()
        return conv_id

    def get_conversation(self, conv_id: str) -> Optional[Dict]:
        with self._get_conn() as conn:
            row = conn.execute("SELECT * FROM conversations WHERE id = ?", (conv_id,)).fetchone()
            return dict(row) if row else None

    def list_conversations(self, user_id: str = None, limit: int = 50) -> List[Dict]:
        with self._get_conn() as conn:
            if user_id:
                rows = conn.execute(
                    "SELECT * FROM conversations WHERE user_id = ? ORDER BY updated_at DESC LIMIT ?",
                    (user_id, limit)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM conversations ORDER BY updated_at DESC LIMIT ?", (limit,)
                ).fetchall()
            return [dict(r) for r in rows]

    def delete_conversation(self, conv_id: str) -> bool:
        with self._get_conn() as conn:
            conn.execute("DELETE FROM conversation_messages WHERE conv_id = ?", (conv_id,))
            conn.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
            conn.commit()
        return True

    def update_conversation_title(self, conv_id: str, title: str) -> bool:
        with self._get_conn() as conn:
            conn.execute(
                "UPDATE conversations SET title = ?, updated_at = datetime('now','localtime') WHERE id = ?",
                (title, conv_id)
            )
            conn.commit()
        return True

    def add_message(self, conversation_id: str, role: str, content: str, metadata: dict = None) -> int:
        with self._get_conn() as conn:
            c = conn.cursor()
            c.execute(
                "INSERT INTO conversation_messages (conv_id, role, content, metadata) VALUES (?, ?, ?, ?)",
                (conversation_id, role, content, json.dumps(metadata, ensure_ascii=False) if metadata else None)
            )
            conn.execute(
                "UPDATE conversations SET updated_at = datetime('now','localtime') WHERE id = ?",
                (conversation_id,)
            )
            conn.commit()
            return c.lastrowid

    def get_conversation_history(self, conv_id: str, limit: int = 100) -> List[Dict]:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM conversation_messages WHERE conv_id = ? ORDER BY created_at ASC LIMIT ?",
                (conv_id, limit)
            ).fetchall()
            return [dict(r) for r in rows]

    def get_context_for_agent(self, conv_id: str, max_messages: int = 20) -> Dict:
        history = self.get_conversation_history(conv_id, max_messages)
        conv = self.get_conversation(conv_id)
        return {
            "conversation_id": conv_id,
            "title": conv.get("title") if conv else "",
            "messages": history,
        }

    def search_conversations(self, keyword: str, user_id: str = None, limit: int = 20) -> List[Dict]:
        with self._get_conn() as conn:
            kw = f"%{keyword}%"
            if user_id:
                rows = conn.execute(
                    "SELECT * FROM conversations WHERE user_id = ? AND title LIKE ? ORDER BY updated_at DESC LIMIT ?",
                    (user_id, kw, limit)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM conversations WHERE title LIKE ? ORDER BY updated_at DESC LIMIT ?",
                    (kw, limit)
                ).fetchall()
            return [dict(r) for r in rows]

    def get_conversation_stats(self, conv_id: str) -> Dict:
        with self._get_conn() as conn:
            msg_count = conn.execute(
                "SELECT COUNT(*) FROM conversation_messages WHERE conv_id = ?", (conv_id,)
            ).fetchone()[0]
            conv = self.get_conversation(conv_id)
            return {
                "conversation_id": conv_id,
                "title": conv.get("title") if conv else "",
                "message_count": msg_count,
                "created_at": conv.get("created_at") if conv else "",
            }

    # ==================== 同步兼容方法 ====================

    def save_conversation_to_publish_history(
        self, conversation_id: str, text: str, tags: list = None,
        images: list = None, music: list = None,
        evaluation_score: float = 0, evaluation_level: str = "未评估"
    ):
        """Agent 全流程完成后自动保存到内容表"""
        with self._get_conn() as conn:
            c = conn.cursor()
            # 去重
            existing = c.execute(
                "SELECT id FROM content_posts WHERE text = ? AND source = 'agent'", (text,)
            ).fetchone()
            if existing:
                return

            c.execute("""
                INSERT INTO content_posts
                (text, source, evaluation_score, evaluation_level,
                 tags_json, images_json, music_json)
                VALUES (?, 'agent', ?, ?, ?, ?, ?)
            """, (
                text,
                evaluation_score,
                evaluation_level,
                json.dumps(tags or [], ensure_ascii=False),
                json.dumps(images or [], ensure_ascii=False),
                json.dumps(music or [], ensure_ascii=False),
            ))

            if tags:
                for tag in tags:
                    tag_name = tag.strip().lstrip("#") if isinstance(tag, str) else str(tag)
                    if tag_name:
                        self._upsert_tag(c, tag_name)

            conn.commit()

    # ==================== 旧 API 兼容（委托到新方法） ====================

    def record_publish(self, *args, **kwargs):
        """旧 API → 不再需要单独调用，数据直接写入 content_posts"""
        pass

    def update_publish_data(self, post_id: int, likes: int = 0, comments: int = 0, views: int = 0):
        return self.update_content_stats(post_id, likes=likes, comments=comments, views=views)

    def update_publish_results(self, post_id: int, likes: int = 0, comments: int = 0,
                               views: int = 0, shares: int = 0):
        return self.update_content_stats(post_id, likes=likes, comments=comments,
                                         views=views, shares=shares)

    def get_top_performing_content(self, limit: int = 10) -> List[Dict]:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM content_posts WHERE views > 0 ORDER BY likes DESC LIMIT ?",
                (limit,)
            ).fetchall()
            return [dict(r) for r in rows]

    # 素材相关旧 API — 兼容空返回
    def add_text_material(self, text: str, **kw) -> int: return 0
    def add_image_material(self, image_path: str, **kw) -> int: return 0
    def add_music(self, music_name: str, **kw) -> int: return 0
    def list_materials(self, material_type: str = None, limit: int = 50) -> List: return []
    def update_material(self, material_id: int, content: str) -> bool: return False
    def delete_material(self, material_id: int) -> bool: return False
    def get_materials_by_type(self, type_: str, limit: int = 10) -> List: return []
    def get_materials_by_tags(self, tags: list, type_: str = "image", limit: int = 10) -> List: return []
    def record_material(self, file_path: str, type_: str, tags: list = None) -> None: pass
    def update_material_performance(self, file_path: str, views: int) -> None: pass
    def increment_material_usage(self, file_path: str) -> None: pass
    def increment_tag_usage(self, tag: str) -> None: pass
    def get_top_materials(self, material_type: str, limit: int = 10) -> List: return []
    def get_material_by_tags(self, material_type: str, tags: list, limit: int = 10) -> List: return []

    # Skill 执行追踪
    def start_skill_execution(self, *args, **kwargs) -> int: return 0
    def complete_skill_execution(self, *args, **kwargs): pass
    def interrupt_skill_execution(self, *args, **kwargs): pass
    def get_skill_execution_history(self, *args, **kwargs) -> List: return []
    def get_last_confirmed_skill(self, *args, **kwargs) -> Optional[str]: return None

    # 回滚
    def record_rollback(self, *args, **kwargs): pass
    def get_rollback_history(self, session_id: str) -> List: return []
    def rollback_to_skill(self, *args, **kwargs) -> bool: return False

    # Session
    def update_stage(self, stage_name: str) -> None: pass
    def clear_stage_from(self, stage_name: str) -> None: pass
    def start_new_iteration(self) -> int: return 1
    def record_iteration(self, *args, **kwargs): pass
    def get_iteration_history(self) -> list: return []
    def should_loop(self, score: float) -> bool: return score < 4.0
    def set_threshold(self, value: float) -> None: pass
    def get_threshold(self) -> float: return 4.0
    def get_retained_skills(self) -> list: return []
    def get_iteration_count(self) -> int: return 0
    def get_latest_passed_iteration(self) -> Optional[Dict]: return None

    # Preferences
    def set_preference(self, key: str, value: str, category: str = "") -> None: pass
    def get_preference(self, key: str) -> Optional[str]: return None
    def get_preferences_by_category(self, category: str) -> Dict: return {}
