"""
统一配置模块 — douyin-agent

功能：
- 自动加载项目根目录 .env
- 提供类型化配置访问器（API key、代理等）
- 动态计算项目根目录
- 共享 DeepSeek API 调用 helper
- 共享关键词提取（extract_keywords）
"""
import os
import re
import json as _json
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

# ============================================================================
# 项目根目录 — 从本文件位置动态计算
# ============================================================================
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent

# ============================================================================
# .env 加载 — import 时自动执行一次
# ============================================================================

def _load_dotenv() -> None:
    """只加载一次，写入 os.environ（不覆盖已有值）"""
    env_file = PROJECT_ROOT / ".env"
    if not env_file.exists():
        return
    with open(env_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key, value = key.strip(), value.strip()
            if key and value and not os.environ.get(key):
                os.environ[key] = value


_load_dotenv()

# ============================================================================
# 类型化配置访问器
# ============================================================================

def get_deepseek_api_key() -> str:
    """DeepSeek API key — 优先读 DEEPSEEK_API_KEY，回退兼容旧变量 ANTHROPIC_AUTH_TOKEN"""
    return os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN", "")


def get_deepseek_base_url() -> str:
    return os.environ.get("ANTHROPIC_BASE_URL", "https://api.deepseek.com/anthropic")


def get_unsplash_access_key() -> str:
    return os.environ.get("UNSPLASH_ACCESS_KEY", "")


def get_pexels_api_key() -> str:
    return os.environ.get("PEXELS_API_KEY", "")


def get_douyin_client_key() -> str:
    return os.environ.get("DOUYIN_CLIENT_KEY", "")


def get_douyin_client_secret() -> str:
    return os.environ.get("DOUYIN_CLIENT_SECRET", "")

# ============================================================================
# 代理 — 从 .env 读取，为空时自动禁用
# ============================================================================

def _build_proxy() -> Optional[Dict[str, str]]:
    """从 PROXY_URL 环境变量构建代理字典，未设置时返回 None"""
    proxy_url = os.environ.get("PROXY_URL", "").strip()
    if not proxy_url:
        return None
    return {"http": proxy_url, "https": proxy_url}


PROXY: Optional[Dict[str, str]] = _build_proxy()

# ============================================================================
# 浏览器模式
# ============================================================================

def get_headless() -> bool:
    """是否以无头模式运行 Playwright（HEADLESS 环境变量，默认 False）"""
    return os.environ.get("HEADLESS", "").lower() in ("1", "true", "yes")


# ============================================================================
# 共享关键词提取（项目唯一实现点）
# ============================================================================

KEYWORD_PATTERNS: Dict[str, str] = {
    "猫": r"猫|猫咪|喵|铲屎官|猫主子|吸猫|猫奴|橘猫|英短|布偶|蓝猫|暹罗",
    "狗": r"狗|狗狗|汪|汪星人|狗主子|遛狗|金毛|泰迪|哈士奇|柴犬|萨摩耶|柯基",
    "宠物": r"宠物|萌宠|养宠|宠|仓鼠|兔子|鹦鹉|金鱼|乌龟|爬宠",
    "搞笑": r"搞笑|沙雕|哈哈|笑死|逗比|幽默|笑死我了|太逗了|爆笑",
    "生活": r"生活|日常|碎片|vlog|记录|日常vlog|生活vlog|独居|租房",
    "美食": r"美食|吃|做饭|吃货|干饭|餐厅|探店|外卖|食谱|红烧肉|火锅",
    "旅行": r"旅行|旅游|打卡|景点|攻略|游玩|海边|爬山|自驾|出发",
    "穿搭": r"穿搭|衣服|搭配|ootd|显瘦|时尚|服装|衬衫|裤子|裙子",
    "美妆": r"美妆|化妆|护肤|口红|粉底|眼影|面膜|洗面奶|爽肤水|精华",
    "健身": r"健身|运动|减肥|跑步|瑜伽|自律|减脂|增肌|锻炼|健身房",
    "情感": r"情感|恋爱|单身|分手|爱情|情侣|暧昧|表白|求婚|结婚",
    "职场": r"职场|上班|打工|办公室|工作|同事|老板|薪资|加班|面试",
    "学习": r"学习|学生|考研|考试|自律|看书|刷题|笔记|复习|作业",
    "科技": r"科技|数码|手机|电脑|测评|产品|芯片|软件|硬件|互联网",
    "汽车": r"汽车|开车|新车|自驾|买车|加油|保养|改装|驾照|高速",
    "游戏": r"游戏|手游|电竞|王者|吃鸡|原神|LOL|CS|手游|端游",
    "音乐": r"音乐|唱歌|翻唱|热门音乐|歌曲|歌词|乐器|吉他|钢琴|唱歌",
    "影视": r"影视|电影|电视剧|影评|追剧|演员|导演|票房|上映|热播",
    "母婴": r"母婴|育儿|宝宝|孕期|待产|母乳|辅食|早教|亲子|幼儿园",
    "家居": r"家居|装修|软装|收纳|家具|设计|改造|小户型|北欧|日式",
    "文学": r"文学|小说|散文|诗歌|文字控|文案|语录|作家|作品|创作",
    "哲思": r"人生|哲理|思考|感悟|成长|智慧|心灵|意义|认知|反思",
    "书评": r"读书|书评|阅读|书单|读后感|书籍|好书|书|阅读打卡",
    "毕业": r"毕业|毕业季|青春|校园|大学生|毕业典礼|毕业照|离校",
    "情感语录": r"情感语录|治愈|温暖|晚安|心情|正能量|文案馆|心灵鸡汤",
    "自然": r"风景|自然|山水|森林|草原|日出|日落|星空",
    "城市": r"城市|街头|夜景|霓虹|建筑|地铁|咖啡厅",
    "人物": r"人物|人像|自拍|闺蜜|情侣|朋友|家人",
}


def extract_keywords(text: str, patterns: Dict[str, str] = None) -> List[str]:
    """从文案中提取关键词类别（项目唯一实现点）

    Args:
        text: 文案内容
        patterns: 可选的自定义模式字典，默认使用 KEYWORD_PATTERNS

    Returns:
        匹配到的类别列表（按匹配顺序）
    """
    if patterns is None:
        patterns = KEYWORD_PATTERNS

    matched = []
    for category, pattern in patterns.items():
        if re.search(pattern, text):
            matched.append(category)
    return matched


# ============================================================================
# 中文→英文关键词翻译映射（用于图片搜索）
# ============================================================================

KEYWORD_TRANSLATION: Dict[str, str] = {
    "猫": "cat", "狗": "dog", "宠物": "pet",
    "美食": "food", "吃": "food", "做饭": "cooking",
    "旅行": "travel", "旅游": "travel", "海边": "beach",
    "穿搭": "fashion", "美妆": "makeup", "健身": "fitness",
    "生活": "lifestyle", "家居": "home decor", "自然": "nature",
    "城市": "city", "人物": "portrait",
}

# ============================================================================
# 项目路径（全部基于 PROJECT_ROOT）
# ============================================================================

def get_state_dir() -> Path:
    return PROJECT_ROOT / "state"


def get_db_path() -> Path:
    return PROJECT_ROOT / "memory.db"


def get_approved_images_dir() -> Path:
    return PROJECT_ROOT / "approved_images"


# ============================================================================
# API 认证
# ============================================================================

def get_api_key() -> str:
    """后端 API 认证密钥（用于保护 API 端点）"""
    return os.environ.get("API_KEY", "")


# ============================================================================
# SSRF 防护 — URL 安全验证
# ============================================================================

# 允许的图片域名白名单（用于防止 SSRF 攻击）
ALLOWED_IMAGE_DOMAINS = {
    "localhost", "127.0.0.1",
    "pexels.com", "images.pexels.com",
    "unsplash.com", "images.unsplash.com",
    "picsum.photos", "i.picsum.photos",
}


def is_safe_url(url: str) -> bool:
    """检查 URL 是否在安全白名单内，防止 SSRF 攻击

    Args:
        url: 待验证的 URL

    Returns:
        True 表示 URL 安全可访问
    """
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        domain = parsed.netloc.lower().split(":")[0]
        # 检查域名是否在白名单中，或是否为白名单域名的子域名
        return domain in ALLOWED_IMAGE_DOMAINS or any(
            domain.endswith("." + allowed) for allowed in ALLOWED_IMAGE_DOMAINS
        )
    except Exception:
        return False


# ============================================================================
# DeepSeek API 共享调用 helper
# ============================================================================

def call_deepseek(
    system_prompt: str,
    user_prompt: str,
    *,
    temperature: float = 0.7,
    max_tokens: int = 500,
    timeout: int = 15,
    model: str = "deepseek-chat",
) -> Optional[str]:
    """调用 DeepSeek Chat API 并返回助手原始消息文本

    失败（无 key、HTTP 错误、超时等）时返回 None。
    """
    api_key = get_deepseek_api_key()
    if not api_key:
        print("[API] 未设置 DEEPSEEK_API_KEY")
        return None

    base_url = get_deepseek_base_url()
    url = base_url.replace("/anthropic", "/v1/chat/completions")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    try:
        resp = requests.post(
            url, headers=headers, json=payload,
            timeout=timeout, proxies=PROXY if PROXY else None
        )
        if resp.status_code == 200:
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        else:
            print(f"[API] HTTP 错误 {resp.status_code}: {resp.text[:100]}")
    except requests.exceptions.Timeout:
        print("[API] 请求超时")
    except requests.exceptions.RequestException as e:
        print(f"[API] 网络错误: {e}")
    except Exception as e:
        print(f"[API] 异常: {e}")

    return None


def call_deepseek_json(
    system_prompt: str,
    user_prompt: str,
    *,
    temperature: float = 0.7,
    max_tokens: int = 500,
    timeout: int = 15,
    model: str = "deepseek-chat",
) -> Optional[Any]:
    """调用 DeepSeek 并返回解析后的 JSON

    自动清理 Markdown 代码块标记，返回 dict/list 或 None。
    """
    content = call_deepseek(
        system_prompt, user_prompt,
        temperature=temperature, max_tokens=max_tokens,
        timeout=timeout, model=model,
    )
    if content is None:
        return None

    content = content.strip()
    if content.startswith("```"):
        parts = content.split("\n", 1)
        if len(parts) > 1:
            content = parts[1]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

    try:
        return _json.loads(content)
    except _json.JSONDecodeError as e:
        print(f"[API] JSON 解析失败: {e}")
        return None
