"""
抖音标签推荐 Skill v2 — 三阶段流水线
Stage 1: 规则关键词提取（快，永远可用）
Stage 2: Qdrant 向量泛化（语义扩展，需 embedding 模型）
Stage 3: DeepSeek LLM 重排序（精准，需 API）
"""
import os
import json
import sys
from pathlib import Path
from typing import List, Dict, Optional

# 确保项目根目录在 sys.path 中（支持独立运行）
_project_root = Path(__file__).parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from utils.memory import MemoryManager
from utils.config import call_deepseek_json, extract_keywords, KEYWORD_PATTERNS
from utils.cache import cache as redis_cache
from utils.vector_store import vector_store

_CONFIG_PATH = Path(__file__).parent.parent / "config" / "tag_rules.json"


def _load_tag_rules() -> Dict:
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


_TAG_RULES = _load_tag_rules()


# ============================================================
# Stage 1: 规则关键词提取
# ============================================================

def _stage1_keywords(text: str) -> List[str]:
    """从文案提取关键词类别（规则匹配，零成本）"""
    keywords = extract_keywords(text, KEYWORD_PATTERNS)
    if not keywords:
        keywords = ["生活"]  # 兜底
    return keywords


# ============================================================
# Stage 2: Qdrant 向量泛化（语义扩展）
# ============================================================

def _stage2_qdrant_expand(keywords: List[str], text: str, limit: int = 20) -> List[Dict]:
    """
    每个关键词 → embedding → Qdrant 检索 → 合并去重
    返回: [{"tag": "#xxx", "similarity": 0.92, "category": "宠物", "tier": "super"}, ...]
    """
    candidates = {}  # tag → 最佳匹配信息

    # 用完整文案做一次向量检索（语义最准）
    try:
        results = vector_store.search_tags(text, limit=15)
        for r in results:
            tag = r["tag"]
            if tag not in candidates or r.get("similarity", 0) > candidates[tag].get("similarity", 0):
                candidates[tag] = r
    except Exception as e:
        print(f"[Stage2] 全文向量检索失败: {e}")

    # 每个关键词独立检索（补充覆盖面）
    for kw in keywords[:3]:
        try:
            results = vector_store.search_tags(kw, limit=8)
            for r in results:
                tag = r["tag"]
                if tag not in candidates or r.get("similarity", 0) > candidates[tag].get("similarity", 0):
                    candidates[tag] = r
        except Exception as e:
            print(f"[Stage2] 关键词 '{kw}' 向量检索失败: {e}")

    return sorted(candidates.values(), key=lambda x: x.get("similarity", 0), reverse=True)[:limit]


# ============================================================
# Stage 3: DeepSeek LLM 重排序
# ============================================================

def _stage3_llm_rerank(text: str, candidates: List[Dict], top_k: int = 8) -> List[Dict]:
    """
    将候选标签交给 DeepSeek，让它精选并给出理由
    """
    if not candidates:
        return []

    candidate_tags = [c["tag"] for c in candidates]
    prompt = f"""你是抖音运营专家。根据以下文案，从候选标签中选择 {top_k} 个最合适的标签。

文案：{text}

候选标签列表：
{json.dumps(candidate_tags, ensure_ascii=False)}

要求：
1. 挑选 {top_k} 个与文案内容最相关的标签
2. 为每个选中的标签写一句简短推荐理由（10字以内）
3. 按相关度从高到低排序
4. 输出格式必须是严格的 JSON 数组：[{{"tag": "#标签名", "reason": "理由"}}]
5. 不要输出任何其他内容"""

    result = call_deepseek_json(
        system_prompt="你是严格的 JSON 输出器，只输出 JSON 数组。",
        user_prompt=prompt,
        temperature=0.5,
        max_tokens=400,
    )

    if result and isinstance(result, list):
        return [r for r in result if isinstance(r, dict) and "tag" in r][:top_k]
    return []


# ============================================================
# 情绪分析（共享给标签 + 配乐）
# ============================================================

_EMOTION_CACHE = {}

def analyze_emotion(text: str) -> Dict:
    """
    分析文案情绪/基调，返回 dict：
    {"mood": "搞笑", "intensity": 0.8, "keywords": ["猫", "搞笑", "意外"], "energy": "high"}
    """
    cache_key = text[:60]
    if cache_key in _EMOTION_CACHE:
        return _EMOTION_CACHE[cache_key]

    prompt = f"""分析以下文案的情绪和基调。返回严格的 JSON：
文案：{text}

格式：{{"mood": "描述情绪(如搞笑/温馨/伤感/励志/日常/吐槽)", "intensity": 0.0-1.0, "energy": "high/medium/low", "keywords": ["关键情绪词1", "关键情绪词2"]}}
只输出 JSON，不要其他。"""

    result = call_deepseek_json(
        system_prompt="你是严格的 JSON 输出器。",
        user_prompt=prompt,
        temperature=0.3,
        max_tokens=150,
    )

    if result and isinstance(result, dict):
        _EMOTION_CACHE[cache_key] = result
        return result

    # 回退：规则情绪判断
    fallback = _rule_emotion(text)
    _EMOTION_CACHE[cache_key] = fallback
    return fallback


def _rule_emotion(text: str) -> Dict:
    """规则情绪判断回退"""
    patterns = {
        "搞笑": r"搞笑|哈哈|笑死|沙雕|逗比|幽默|笑死我了|太逗了|爆笑|调皮",
        "温馨": r"温馨|温暖|治愈|感动|陪伴|幸福|美好|甜蜜|浪漫",
        "伤感": r"伤心|难过|哭|孤独|失去|想念|遗憾|分手|怀念",
        "励志": r"加油|努力|坚持|奋斗|自律|成长|进步|挑战|梦想|成功",
        "日常": r"日常|记录|碎片|vlog|日记|今天|分享|打卡",
        "吐槽": r"吐槽|无语|离谱|气死|踩雷|翻车|居然|什么鬼|毁",
    }
    max_score = 0
    best_mood = "日常"
    for mood, pat in patterns.items():
        import re
        matches = len(re.findall(pat, text))
        if matches > max_score:
            max_score = matches
            best_mood = mood

    intensity = min(0.9, 0.3 + max_score * 0.2)
    energy = "high" if best_mood in ("搞笑", "励志", "吐槽") else ("low" if best_mood == "伤感" else "medium")

    # 规则提取情绪关键词
    import re
    emotion_keywords = list(set(re.findall(r"[一-鿿]{2,4}", text)))[:3]

    return {"mood": best_mood, "intensity": intensity, "energy": energy, "keywords": emotion_keywords}


# ============================================================
# HashtagRecommender v2 — 三阶段流水线
# ============================================================

class HashtagRecommender:
    """抖音标签推荐器 v2"""

    HOT_TAGS = _TAG_RULES.get("hot_tags", {})
    REASON_TEMPLATES = _TAG_RULES.get("reason_templates", [])

    @classmethod
    def extract_keywords(cls, text: str) -> List[str]:
        return _stage1_keywords(text)

    @classmethod
    def recommend(
        cls,
        text: str,
        count: int = 10,
        use_api: bool = True,
        use_memory: bool = True,
    ) -> List[Dict[str, str]]:
        """
        三阶段流水线推荐标签

        Stage 1: 规则提取关键词（始终执行）
        Stage 2: Qdrant 向量泛化扩展候选（有 Qdrant 时执行）
        Stage 3: DeepSeek LLM 精选重排序（有 API Key 时执行）
        """
        count = max(1, min(count, 20))

        # Redis 缓存
        cache_key = f"hashtag_v2:{text[:80]}"
        if use_api:
            cached = redis_cache.get_cached("deepseek", cache_key)
            if cached:
                return cached[:count]

        # ── Stage 1: 关键词提取 ──
        keywords = _stage1_keywords(text)
        print(f"[Stage1] 关键词: {keywords}")

        # 规则库直接匹配（兜底候选）
        rule_candidates = []
        for kw in keywords:
            if kw in cls.HOT_TAGS:
                for tier in ("super", "hot", "potential"):
                    for tag in cls.HOT_TAGS[kw][tier]:
                        rule_candidates.append({"tag": tag, "similarity": 1.0, "category": kw, "tier": tier})

        # ── Stage 2: Qdrant 向量泛化 ──
        qdrant_candidates = _stage2_qdrant_expand(keywords, text, limit=30)
        print(f"[Stage2] Qdrant 扩展: {len(qdrant_candidates)} 个候选")

        # 合并候选（Qdrant 优先 + 规则补充）
        seen = set()
        merged_candidates = []
        for c in qdrant_candidates + rule_candidates:
            if c["tag"] not in seen:
                seen.add(c["tag"])
                merged_candidates.append(c)

        # ── Stage 3: LLM 重排序 ──
        if use_api and merged_candidates:
            result = _stage3_llm_rerank(text, merged_candidates[:30], top_k=count)
            if result:
                print(f"[Stage3] LLM 精选: {len(result)} 个标签")
                redis_cache.set_cached("deepseek", cache_key, result, ttl=86400)
                if use_memory:
                    cls._increment_tags(result)
                return result

        # ── Fallback: Qdrant 结果直接输出 ──
        if qdrant_candidates:
            result = [
                {"tag": c["tag"], "reason": f"语义匹配 ({int(c.get('similarity', 0) * 100)}%)"}
                for c in qdrant_candidates[:count]
            ]
            return result

        # ── 最终兜底: 规则结果 ──
        result = []
        for i, c in enumerate(merged_candidates[:count]):
            reason = cls.REASON_TEMPLATES[i % len(cls.REASON_TEMPLATES)] if cls.REASON_TEMPLATES else "相关话题推荐"
            result.append({"tag": c["tag"], "reason": reason})
        return result

    @classmethod
    def _increment_tags(cls, tags: List[Dict]):
        try:
            mm = MemoryManager()
            for t in tags:
                mm.increment_tag_usage(t["tag"])
        except Exception:
            pass


def recommend(text: str, count: int = 10, use_memory: bool = True, use_api: bool = True) -> List[Dict[str, str]]:
    return HashtagRecommender.recommend(text, count=count, use_api=use_api, use_memory=use_memory)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="抖音标签推荐器 v2")
    parser.add_argument("text", nargs="?", help="文案内容")
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--no-api", action="store_true", help="不使用 DeepSeek API")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--test", action="store_true")
    args = parser.parse_args()

    if args.test or not args.text:
        test_cases = [
            "我家猫今天又把花瓶推倒了，真是个调皮鬼！",
            "今天做了一道超级好吃的红烧肉，做法简单又美味",
            "周末和朋友一起去海边玩，风景太美了",
            "分享一下我的日常穿搭，显瘦又好看",
        ]
        for case in test_cases:
            print(f"\n{'='*50}")
            print(f"文案: {case}")
            print(f"{'='*50}")
            tags = HashtagRecommender.recommend(case, count=8, use_api=not args.no_api)
            for i, tag in enumerate(tags):
                print(f"  {i+1}. {tag['tag']} — {tag['reason']}")
    else:
        tags = HashtagRecommender.recommend(args.text, count=args.count, use_api=not args.no_api)
        if args.json:
            print(json.dumps(tags, ensure_ascii=False))
        else:
            for i, tag in enumerate(tags):
                print(f"{i+1}. {tag['tag']} — {tag['reason']}")
