"""
抖音标签推荐 Skill
基于 DeepSeek API 语义理解和关键词规则匹配生成抖音标签推荐
"""
import os
import json
from pathlib import Path
from typing import List, Dict, Tuple, Optional

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


def recommend_via_api(text: str, count: int = 10) -> List[Dict[str, str]]:
    """
    通过 DeepSeek API 理解文案并生成标签（优先使用）

    Args:
        text: 文案内容
        count: 推荐标签数量

    Returns:
        标签列表，每个元素包含 tag 和 reason
        如果 API 调用失败，返回空列表
    """
    prompt = f"""你是一个抖音运营专家。根据以下文案，推荐{count}个最合适的抖音标签。

要求：
1. 每个标签以 # 开头，不要带空格
2. 为每个标签写一句简短的推荐理由（10字以内）
3. 输出格式必须是严格的 JSON 数组，每个元素包含 "tag" 和 "reason" 两个字段
4. 不要输出任何其他内容，只输出 JSON 数组

文案：{text}

示例输出：
[{{"tag": "#猫咪日常", "reason": "萌宠类热门话题"}}, {{"tag": "#拆家", "reason": "与文案行为相关"}}]"""

    result = call_deepseek_json(
        system_prompt="你是一个严格的 JSON 输出器，只输出 JSON，不输出其他内容。",
        user_prompt=prompt,
        temperature=0.7,
        max_tokens=500,
    )

    if result is None:
        return []

    if isinstance(result, list) and all("tag" in t and "reason" in t for t in result):
        print(f"[API] DeepSeek 返回 {len(result)} 个标签")
        return result[:count]
    else:
        print("[API] 返回格式不正确")
        return []


class HashtagRecommender:
    """
    抖音标签推荐器 - 实用版
    
    功能特性：
    1. 基于 DeepSeek API 语义理解生成标签（优先）
    2. 关键词智能匹配标签（回退）
    3. 标签热度分级（超级热门/热门/潜力）
    4. 支持自定义标签数量
    5. 生成推荐理由
    6. 集成记忆层，优先推荐历史效果好的标签
    """
    
    HOT_TAGS = _TAG_RULES.get("hot_tags", {}) or {
        "生活": {"super": ["#生活", "#日常"], "hot": ["#生活分享"], "potential": ["#生活碎片"]},
        "美食": {"super": ["#美食"], "hot": ["#美食分享"], "potential": ["#美食教程"]},
        "旅行": {"super": ["#旅行"], "hot": ["#旅行日记"], "potential": ["#旅行攻略"]},
    }

    KEYWORD_PATTERNS = KEYWORD_PATTERNS

    @classmethod
    def extract_keywords(cls, text: str) -> List[str]:
        """从文案中提取关键词类别（使用共享 extract_keywords + 去重逻辑）"""
        matched_categories = extract_keywords(text, cls.KEYWORD_PATTERNS)

        _DEDUP_CATEGORIES = [
            "穿搭", "健身", "美食", "学习", "情感", "职场",
            "文学", "哲思", "书评", "毕业", "情感语录"
        ]
        if "生活" in matched_categories:
            if any(cat in matched_categories for cat in _DEDUP_CATEGORIES):
                matched_categories.remove("生活")

        return matched_categories

    REASON_TEMPLATES = _TAG_RULES.get("reason_templates", []) or [
        "相关话题近期热度上升",
        "与文案内容高度相关",
        "该话题流量表现优秀",
        "适合目标受众群体",
        "推荐用于增加曝光",
    ]

    @classmethod
    def recommend(
        cls, 
        text: str, 
        count: int = 10,
        strategy: str = "balanced",
        use_memory: bool = True,
        use_api: bool = True
    ) -> List[Dict[str, str]]:
        """
        推荐标签
        
        Args:
            text: 文案内容
            count: 推荐标签数量（1-20）
            strategy: 推荐策略
                - balanced: 平衡策略（超级热门+热门+潜力）
                - super_only: 仅超级热门标签
                - hot_only: 仅热门标签
                - potential_only: 仅潜力标签
                - aggressive: 激进策略（更多超级热门）
            use_memory: 是否使用记忆层数据优化推荐
            use_api: 是否优先使用 DeepSeek API
        
        Returns:
            推荐标签列表，包含标签名和推荐理由
        """
        count = max(1, min(count, 20))

        # 1. 优先尝试 DeepSeek API 语义理解（带 Redis 缓存）
        if use_api:
            cache_key = f"hashtag:{text[:80]}"
            cached = redis_cache.get_cached("deepseek", cache_key)
            if cached:
                return cached[:count]
            api_result = recommend_via_api(text, count)
            if api_result:
                redis_cache.set_cached("deepseek", cache_key, api_result, ttl=86400)
                if use_memory:
                    try:
                        mm = MemoryManager()
                        for tag_info in api_result:
                            mm.increment_tag_usage(tag_info["tag"])
                    except Exception:
                        pass
                return api_result

        # 2. 回退到 Qdrant 语义标签搜索（本地向量检索，零 API 成本）
        qdrant_tags = vector_store.search_tags(text, limit=count)
        if qdrant_tags:
            result = [
                {"tag": t["tag"], "reason": f"语义匹配 (相似度{t['similarity']:.0%})"}
                for t in qdrant_tags[:count]
            ]
            return result

        # 3. 回退到关键词匹配 + 硬编码标签库
        keywords = cls.extract_keywords(text)
        recommended_tags = []
        
        if not keywords:
            keywords = ["生活"]
        
        for keyword in keywords:
            if keyword in cls.HOT_TAGS:
                tag_group = cls.HOT_TAGS[keyword]
                
                if strategy == "super_only":
                    recommended_tags.extend(tag_group["super"])
                elif strategy == "hot_only":
                    recommended_tags.extend(tag_group["hot"])
                elif strategy == "potential_only":
                    recommended_tags.extend(tag_group["potential"])
                elif strategy == "aggressive":
                    recommended_tags.extend(tag_group["super"] * 2)
                    recommended_tags.extend(tag_group["hot"])
                else:
                    recommended_tags.extend(tag_group["super"])
                    recommended_tags.extend(tag_group["hot"])
                    recommended_tags.extend(tag_group["potential"])
        
        recommended_tags = list(dict.fromkeys(recommended_tags))
        
        if use_memory:
            recommended_tags = cls._apply_memory_weighting(recommended_tags)
        
        recommended_tags = recommended_tags[:count]
        
        results = []
        for i, tag in enumerate(recommended_tags):
            reason = cls.REASON_TEMPLATES[i % len(cls.REASON_TEMPLATES)]
            
            if use_memory:
                performance = cls._get_tag_performance(tag)
                if performance:
                    reason = cls._generate_performance_reason(tag, performance)
            
            results.append({
                "tag": tag,
                "reason": reason
            })
        
        return results
    
    @classmethod
    def _apply_memory_weighting(cls, tags: List[str]) -> List[str]:
        """
        根据记忆层数据对标签进行加权排序
        
        Args:
            tags: 候选标签列表
        
        Returns:
            加权排序后的标签列表
        """
        try:
            mm = MemoryManager()
            top_tags = mm.get_top_tags(50)
            
            performance_map = {}
            for tp in top_tags:
                performance_map[tp["tag"]] = {
                    "avg_likes": tp["avg_likes"],
                    "avg_views": tp["avg_views"],
                    "last_effectiveness": tp["last_effectiveness"],
                    "usage_count": tp["usage_count"]
                }
            
            def tag_weight(tag):
                if tag in performance_map:
                    perf = performance_map[tag]
                    weight = perf["avg_likes"] * 0.5 + perf["usage_count"] * 10
                    if perf["last_effectiveness"] == "优秀":
                        weight *= 1.5
                    elif perf["last_effectiveness"] == "良好":
                        weight *= 1.2
                    return weight
                return 0
            
            sorted_tags = sorted(tags, key=tag_weight, reverse=True)
            return sorted_tags
        
        except Exception as e:
            print(f"[记忆层] 加权排序失败，使用原始顺序: {e}")
            return tags
    
    @classmethod
    def _get_tag_performance(cls, tag: str) -> Optional[Dict]:
        """
        获取标签的历史表现数据
        
        Args:
            tag: 标签名称
        
        Returns:
            表现数据（如果存在）
        """
        try:
            mm = MemoryManager()
            return mm.get_tag_performance(tag)
        except Exception:
            return None
    
    @classmethod
    def _generate_performance_reason(cls, tag: str, performance: Dict) -> str:
        """
        根据历史表现生成推荐理由
        
        Args:
            tag: 标签名称
            performance: 表现数据
        
        Returns:
            推荐理由
        """
        effectiveness = performance.get("last_effectiveness", "未知")
        avg_likes = performance.get("avg_likes", 0)
        usage_count = performance.get("usage_count", 0)
        
        if effectiveness == "优秀":
            return f"历史表现优秀，平均点赞 {int(avg_likes)}+"
        elif effectiveness == "良好":
            return f"历史表现良好，使用 {usage_count} 次"
        elif usage_count >= 3:
            return f"常用标签，使用 {usage_count} 次"
        else:
            return cls.REASON_TEMPLATES[0]

    @classmethod
    def get_tags_by_category(cls, category: str) -> Dict[str, List[str]]:
        """
        获取指定类别的标签
        
        Args:
            category: 类别名称
        
        Returns:
            标签分组字典
        """
        if category in cls.HOT_TAGS:
            return cls.HOT_TAGS[category]
        return {"super": [], "hot": [], "potential": []}

    @classmethod
    def get_all_categories(cls) -> List[str]:
        """获取所有可用类别"""
        return list(cls.HOT_TAGS.keys())


def recommend(text: str, count: int = 10, strategy: str = "balanced", use_memory: bool = True, use_api: bool = True) -> List[Dict[str, str]]:
    """
    便捷函数：推荐标签
    
    Args:
        text: 文案内容
        count: 推荐标签数量
        strategy: 推荐策略
        use_memory: 是否使用记忆层数据优化推荐
        use_api: 是否优先使用 DeepSeek API
    
    Returns:
        推荐标签列表
    """
    return HashtagRecommender.recommend(text, count, strategy, use_memory, use_api)


if __name__ == "__main__":
    import argparse
    import json
    
    parser = argparse.ArgumentParser(description="抖音标签推荐器")
    parser.add_argument("text", nargs="?", help="文案内容")
    parser.add_argument("--count", type=int, default=10, help="推荐标签数量")
    parser.add_argument("--strategy", default="balanced", 
                        choices=["balanced", "super_only", "hot_only", "potential_only", "aggressive"],
                        help="推荐策略")
    parser.add_argument("--no-memory", action="store_true", help="不使用记忆层数据")
    parser.add_argument("--no-api", action="store_true", help="不使用 DeepSeek API（仅用关键词匹配）")
    parser.add_argument("--json", action="store_true", help="输出 JSON 格式")
    parser.add_argument("--test", action="store_true", help="运行测试模式")
    
    args = parser.parse_args()
    
    if args.test or not args.text:
        # 测试模式
        test_cases = [
            "我家猫今天又把花瓶推倒了，真是个调皮鬼！",
            "今天做了一道超级好吃的红烧肉，做法简单又美味",
            "周末和朋友一起去海边玩，风景太美了",
            "分享一下我的日常穿搭，显瘦又好看",
            "刚刚完成了今天的健身打卡，感觉很棒",
            "最近在准备考研，每天都要学习很多东西",
        ]
        
        print("="*60)
        print("抖音标签推荐器 - 实用版测试")
        print("="*60)
        print()
        
        for case in test_cases:
            print(f"文案: {case}")
            print()
            
            print("  [API + 记忆层] 默认推荐:")
            tags = HashtagRecommender.recommend(case, count=8, use_api=True, use_memory=True)
            for i, tag in enumerate(tags):
                print(f"    {i+1}. {tag['tag']} - {tag['reason']}")
            print()
            
            print("  [仅关键词匹配] 不使用 API:")
            tags_no_api = HashtagRecommender.recommend(case, count=8, use_api=False, use_memory=True)
            for i, tag in enumerate(tags_no_api):
                print(f"    {i+1}. {tag['tag']} - {tag['reason']}")
            print()
            
            print("-"*60)
            print()

        print("="*60)
        print("可用类别列表:")
        print("="*60)
        categories = HashtagRecommender.get_all_categories()
        for i, cat in enumerate(categories, 1):
            print(f"  {i}. {cat}")
    
    else:
        # 正常模式
        use_memory = not args.no_memory
        use_api = not args.no_api
        tags = HashtagRecommender.recommend(
            args.text, 
            count=args.count, 
            strategy=args.strategy,
            use_memory=use_memory,
            use_api=use_api
        )
        
        if args.json:
            # JSON 输出
            print(json.dumps(tags, ensure_ascii=False))
        else:
            # 友好输出
            print("="*60)
            print(f"文案: {args.text}")
            print("="*60)
            print()
            print(f"推荐标签 (API: {'启用' if use_api else '禁用'}, 记忆层: {'启用' if use_memory else '禁用'}):")
            print()
            for i, tag in enumerate(tags):
                print(f"  {i+1}. {tag['tag']} - {tag['reason']}")