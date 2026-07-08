"""
全局常量 — 消除 server.py 中的 magic numbers
"""
import re
from pathlib import Path

# =====================================================
# 项目根目录
# =====================================================
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# =====================================================
# 预编译正则表达式
# =====================================================
_RE_REMOVE_BGM = re.compile(r'[配bg][乐m].*?[：:]\s*[《「].*?[》」].*?(?:[版节]).*?(?:[。，]|$)', re.IGNORECASE)
_RE_REMOVE_TAGS = re.compile(r'(?:\s*#\S+){2,}\s*$')

# =====================================================
# Agent 管线常量
# =====================================================
MIN_TEXT_LENGTH_FOR_TOPIC = 10     # 判断 topic 意图的最小文案长度
TEXT_PREVIEW_LENGTH = 60           # 日志中文案预览截断长度
MIN_GENERATED_COPY_LENGTH = 5      # LLM 生成文案的最小有效长度
INTENT_CLASSIFY_MAX_TOKENS = 10    # 意图分类 token 上限
COPY_GENERATE_MAX_TOKENS = 150     # 文案生成 token 上限
REWRITE_MAX_TOKENS = 150           # 文案改写 token 上限
QA_MAX_TOKENS = 200               # 问答回复 token 上限
FOLLOWUP_MAX_TEXT_LENGTH = 10      # followup 检测的最大输入长度
MAX_CONTEXT_MSGS = 20              # 上下文加载最大消息数

# =====================================================
# 意图类型
# =====================================================
INTENT_TOPIC = "topic"
INTENT_CREATE = "create"
INTENT_OPTIMIZE = "optimize"
INTENT_MODIFY = "modify"
INTENT_QUESTION = "question"
VALID_INTENTS = {INTENT_TOPIC, INTENT_CREATE, INTENT_OPTIMIZE, INTENT_MODIFY, INTENT_QUESTION}

# =====================================================
# 会话状态文件
# =====================================================
SESSION_FILE = PROJECT_ROOT / "state" / "current_session.json"
STATE_FILE = PROJECT_ROOT / "douyin_state.json"

# =====================================================
# 素材库目录
# =====================================================
PERSONAL_DIR = PROJECT_ROOT / "personal_materials"
PUBLIC_DIR = PROJECT_ROOT / "approved_images"

# =====================================================
# 允许上传的图片格式
# =====================================================
_ALLOWED_UPLOAD_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "webp", "bmp"}
