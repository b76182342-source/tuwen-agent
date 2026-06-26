"""
抖音创作顾问 Agent — 后端 API 服务器

启动：python backend/server.py
端口：8000

TODO: [架构] 当前文件超过 1000 行，包含路由、Pydantic 模型、业务逻辑，呈 God Object 状态。
      待三库架构落地后，按职责拆分为 routers/（对话、Agent、素材、分析）、schemas.py、services/ 等模块。
      拆分需同步修改前端 API 路径、测试脚本、nginx 配置，当前阶段收益 < 风险。
"""
import os
import json
import re
import time
import sqlite3
import requests
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

# 预编译正则表达式（提升性能）
_RE_REMOVE_BGM = re.compile(r'[配bg][乐m].*?[：:]\s*[《「].*?[》」].*?(?:[版节]).*?(?:[。，]|$)', re.IGNORECASE)
_RE_REMOVE_TAGS = re.compile(r'(?:\s*#\S+){2,}\s*$')

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent

os.chdir(str(PROJECT_ROOT))

from fastapi import FastAPI, Request, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import uvicorn
import logging

logger = logging.getLogger("douyin-agent")

# 导入技能模块
from skills.hashtag_recommender import HashtagRecommender
from skills.image_recommender import recommend_images
from skills.music_recommender import recommend_music
from skills.content_evaluator import evaluate
from utils.config import PROJECT_ROOT as CFG_ROOT, PROXY, call_deepseek_json, call_deepseek, get_deepseek_api_key, get_api_key, is_safe_url
from utils.memory import MemoryManager
from utils.cache import cache as redis_cache
from utils.vector_store import vector_store

# =====================================================
# 常量定义（消除 magic numbers）
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

# 意图类型常量
INTENT_TOPIC = "topic"
INTENT_CREATE = "create"
INTENT_OPTIMIZE = "optimize"
INTENT_MODIFY = "modify"
INTENT_QUESTION = "question"
VALID_INTENTS = {INTENT_TOPIC, INTENT_CREATE, INTENT_OPTIMIZE, INTENT_MODIFY, INTENT_QUESTION}

memory = MemoryManager()

# =====================================================
# Pydantic 输入验证模型
# =====================================================

class CreateConversationRequest(BaseModel):
    title: str = Field(default="新对话", min_length=1, max_length=200)
    user_id: str = Field(default="default_user", min_length=1, max_length=100)

class AddMessageRequest(BaseModel):
    conversation_id: str = Field(..., min_length=1, max_length=200)
    role: str = Field(..., min_length=1, max_length=50)
    content: str = Field(..., min_length=1, max_length=10000)
    metadata: Optional[dict] = None

class PublishDataUpdate(BaseModel):
    likes: int = Field(default=0, ge=0)
    comments: int = Field(default=0, ge=0)
    views: int = Field(default=0, ge=0)

class DouyinSyncRequest(BaseModel):
    records: List[dict] = Field(..., min_items=1, max_items=100)

# 通用错误响应：不暴露内部细节
def _api_error(detail: str = "操作失败，请稍后重试", status_code: int = 500):
    raise HTTPException(status_code=status_code, detail=detail)

app = FastAPI(title="抖音创作顾问 Agent API")

_cors_origins = os.environ.get("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173,http://127.0.0.1:3000,http://127.0.0.1:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _cors_origins if o.strip()],
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", "Authorization", "X-Request-Id"],
    allow_credentials=True,
)

DB_PATH = PROJECT_ROOT / "memory.db"

# =====================================================
# API 认证中间件
# =====================================================

# 无需认证的公开端点
_PUBLIC_PATHS = {"/api/health", "/docs", "/openapi.json", "/redoc"}


@app.middleware("http")
async def api_key_middleware(request: Request, call_next):
    """API Key 认证中间件 — 保护所有 /api/* 端点"""
    path = request.url.path
    # 跳过公开端点
    if path in _PUBLIC_PATHS or path.startswith("/personal/") or path.startswith("/public/"):
        return await call_next(request)

    # 仅保护 /api/ 前缀的端点
    if path.startswith("/api/"):
        expected_key = get_api_key()
        if expected_key:
            # 从 Authorization header 或 X-API-Key header 读取
            auth_header = request.headers.get("Authorization", "")
            api_key_header = request.headers.get("X-API-Key", "")

            provided_key = ""
            if auth_header.startswith("Bearer "):
                provided_key = auth_header[7:]
            elif api_key_header:
                provided_key = api_key_header

            if provided_key != expected_key:
                return JSONResponse(
                    status_code=403,
                    content={"detail": "无效的 API 密钥。请在请求头中提供有效的 X-API-Key 或 Bearer token。"}
                )

    return await call_next(request)


from fastapi.responses import JSONResponse

# =====================================================
# 图片识别（DeepSeek Vision）
# =====================================================

def analyze_images(image_urls: list) -> str:
    """分析图片内容：提取图片信息并通过 DeepSeek Chat 推理出文案方向

    由于 deepseek-chat 不直接支持多模态 Vision，
    使用图片 URL、文件名等元信息让模型推理内容。

    安全措施：
    - 仅允许白名单域名（pexels.com, unsplash.com, localhost）
    - 仅支持 http/https 协议
    - 响应体大小限制为 5MB
    - 连接超时 5 秒
    """
    api_key = get_deepseek_api_key()
    if not api_key:
        return ""

    # 收集图片信息
    img_infos = []
    MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5MB

    for img_url in image_urls[:3]:
        info = {"url": img_url[:120]}
        try:
            if img_url.startswith("http"):
                if not is_safe_url(img_url):
                    info["error"] = "域名不在白名单内"
                    img_infos.append(info)
                    continue
                # 尝试下载获取基本信息（限制大小和超时）
                resp = requests.get(
                    img_url,
                    timeout=5,
                    proxies=PROXY if PROXY else None,
                    stream=True,
                )
                content = b""
                for chunk in resp.iter_content(chunk_size=1024):
                    content += chunk
                    if len(content) > MAX_IMAGE_SIZE:
                        info["error"] = "图片超过大小限制"
                        break
                else:
                    info["size"] = len(content)
                    info["type"] = resp.headers.get("Content-Type", "unknown")
                    # 从 URL 提取可能的描述词
                    path_parts = img_url.split("/")
                    keywords = [p for p in path_parts if len(p) > 2 and not p.startswith("?")]
                    info["url_keywords"] = keywords[-3:] if keywords else []
            elif img_url.startswith("data:"):
                info["type"] = "data:image"
                info["size"] = len(img_url)
            else:
                local_path = PROJECT_ROOT / img_url.lstrip("/")
                if local_path.exists():
                    info["size"] = local_path.stat().st_size
                    info["filename"] = local_path.name
                    info["type"] = "local_image"
        except Exception as e:
            info["error"] = str(e)[:50]
        img_infos.append(info)

    if not img_infos:
        return ""

    # 构建文本 prompt
    info_text = "\n".join(
        f"图片{i+1}: {json.dumps(info, ensure_ascii=False)}"
        for i, info in enumerate(img_infos)
    )

    prompt = f"""你是一个视觉内容分析专家。根据以下图片的元信息，推理图片可能的画面内容和氛围，生成一句适合抖音发布的文案（不超过40字）。

{info_text}

要求：
1. 根据 URL 关键词、文件名等线索推理内容
2. 文案要简短有感染力，适合抖音
3. 直接输出文案，不要其他内容"""

    result = call_deepseek(
        system_prompt="你是图片分析专家，根据元信息推理图片内容。只输出文案，不输出其他。",
        user_prompt=prompt,
        temperature=0.7,
        max_tokens=100,
    )

    if result and isinstance(result, str):
        print(f"[图片识别] 推理结果: {result[:60]}")
        return result.strip()

    return ""


# call_deepseek_json 和 call_deepseek 已从 utils.config 统一导入，无本地副本


# =====================================================
# 会话管理（短期记忆）
# =====================================================

SESSION_FILE = PROJECT_ROOT / "state" / "current_session.json"


def _load_session() -> dict:
    if SESSION_FILE.exists():
        try:
            return json.loads(open(SESSION_FILE, "r", encoding="utf-8").read())
        except Exception:
            pass
    return {
        "session_id": f"{time.strftime('%Y%m%d_%H%M%S')}",
        "messages": [],
        "iteration": 0,
        "iteration_history": [],
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


def _save_session(session: dict):
    SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    session["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(SESSION_FILE, "w", encoding="utf-8") as f:
        json.dump(session, f, ensure_ascii=False, indent=2)


@app.get("/api/session")
def get_session():
    """获取当前会话"""
    return _load_session()


@app.post("/api/session/save")
async def save_session(request: Request):
    """保存会话"""
    data = await request.json()
    session = _load_session()
    session.update(data)
    _save_session(session)
    return {"success": True}


@app.post("/api/session/reset")
def reset_session():
    """重置会话"""
    SESSION_FILE.unlink(missing_ok=True)
    return {"success": True, "session": _load_session()}


# =====================================================
# 对话管理API
# =====================================================

@app.post("/api/conversations")
async def create_conversation(request: CreateConversationRequest):
    """创建新的对话会话"""
    try:
        conversation_id = memory.create_conversation(title=request.title, user_id=request.user_id)
        return {"conversation_id": conversation_id}
    except Exception as e:
        logger.error(f"创建对话失败: {e}")
        _api_error("创建对话失败，请稍后重试")


@app.get("/api/conversations/{conversation_id}")
def get_conversation(conversation_id: str):
    """获取对话会话信息"""
    try:
        conversation = memory.get_conversation(conversation_id)
        if not conversation:
            _api_error("对话不存在", 404)
        return conversation
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取对话失败: {e}")
        _api_error("获取对话失败")


@app.get("/api/conversations")
def list_conversations(user_id: Optional[str] = None, limit: int = 50):
    """列出对话会话"""
    try:
        return memory.list_conversations(user_id=user_id, limit=limit)
    except Exception as e:
        logger.error(f"列出对话失败: {e}")
        _api_error("列出对话失败")


@app.delete("/api/conversations/{conversation_id}")
def delete_conversation(conversation_id: str):
    """删除对话会话"""
    try:
        success = memory.delete_conversation(conversation_id)
        if not success:
            _api_error("对话不存在", 404)
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除对话失败: {e}")
        _api_error("删除对话失败")


@app.post("/api/conversations/batch-delete")
async def batch_delete_conversations(request: Request):
    """批量删除对话会话"""
    try:
        body = await request.body()
        try:
            data = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError):
            data = json.loads(body.decode("gbk", errors="replace"))
    except Exception:
        return {"error": "invalid_body", "deleted_count": 0}

    conversation_ids = data.get("conversation_ids", [])
    if not conversation_ids:
        return {"deleted_count": 0}

    deleted_count = 0
    for conv_id in conversation_ids:
        try:
            if memory.delete_conversation(conv_id):
                deleted_count += 1
        except Exception as e:
            logger.error(f"删除对话 {conv_id} 失败: {e}")

    print(f"[后端] 批量删除完成: 请求 {len(conversation_ids)} 个, 成功 {deleted_count} 个")
    return {"deleted_count": deleted_count, "total": len(conversation_ids)}


@app.put("/api/conversations/{conversation_id}")
async def update_conversation(conversation_id: str, request: Request):
    """更新对话会话（如标题）"""
    try:
        body = json.loads(await request.body())
        title = body.get("title")
        if title:
            memory.update_conversation_title(conversation_id, title)
            print(f"[后端] 更新对话标题: {conversation_id} → {title}")
        return {"success": True}
    except Exception as e:
        logger.error(f"更新对话失败: {e}")
        _api_error("更新对话失败")


@app.post("/api/conversations/messages")
async def add_message(request: AddMessageRequest):
    """添加消息到对话历史"""
    try:
        message_id = memory.add_message(
            conversation_id=request.conversation_id,
            role=request.role,
            content=request.content,
            metadata=request.metadata
        )
        return {"message_id": message_id}
    except Exception as e:
        logger.error(f"添加消息失败: {e}")
        _api_error("添加消息失败")


@app.get("/api/conversations/{conversation_id}/messages")
def get_conversation_history(conversation_id: str, limit: Optional[int] = None):
    """获取对话历史"""
    try:
        return memory.get_conversation_history(conversation_id, limit=limit or 100)
    except Exception as e:
        logger.error(f"获取对话历史失败: {e}")
        _api_error("获取对话历史失败")


@app.get("/api/conversations/{conversation_id}/context")
def get_conversation_context(conversation_id: str, max_messages: int = 20):
    """获取对话上下文（用于Agent执行）"""
    try:
        return memory.get_context_for_agent(conversation_id, max_messages=max_messages)
    except Exception as e:
        logger.error(f"获取对话上下文失败: {e}")
        _api_error("获取对话上下文失败")


@app.get("/api/conversations/{conversation_id}/stats")
def get_conversation_stats(conversation_id: str):
    """获取对话统计信息"""
    try:
        return memory.get_conversation_stats(conversation_id)
    except Exception as e:
        logger.error(f"获取对话统计失败: {e}")
        _api_error("获取对话统计失败")


@app.get("/api/conversations/search")
def search_conversations(keyword: str, user_id: Optional[str] = None, limit: int = 20):
    """搜索对话"""
    try:
        return memory.search_conversations(keyword, user_id=user_id, limit=limit)
    except Exception as e:
        logger.error(f"搜索对话失败: {e}")
        _api_error("搜索对话失败")


# =====================================================
# Agent 执行
# =====================================================

# =====================================================
# Agent 辅助函数（从 god 函数中提取）
# =====================================================

def _classify_intent_with_llm(text: str, prev_text: str, prev_score: float, has_context: bool) -> str:
    """通过 LLM 分类用户意图 → topic/create/optimize/modify/question"""
    intent_prompt = f"""分析用户输入，判断意图类型。只输出一个词。

## 当前状态
{'- 上一轮文案: ' + prev_text[:80] if has_context else '- 全新会话，无历史'}
{'- 上一轮评分: ' + str(prev_score) + '/5.0' if has_context else ''}

## 用户输入
"{text}"

## 意图类型
topic: 用户提出了一个主题/想法/需求，需要先生成文案（如"我想做浴室用品图文"、"帮我写一段关于春天的文案"）
create: 用户已经提供了完整的文案内容，直接使用即可（如"夕阳把影子拉得很长"）
optimize: 用户希望改进上一轮结果（需有上下文）
modify: 用户想修改上一轮的某部分
question: 用户提问或闲聊

只输出 topic / create / optimize / modify / question 中的一个词。"""

    intent_result = call_deepseek(
        system_prompt="你是一个严格的分类器，只输出一个词。",
        user_prompt=intent_prompt,
        temperature=0.1,
        max_tokens=INTENT_CLASSIFY_MAX_TOKENS,
        timeout=10,
    )

    if intent_result and isinstance(intent_result, str):
        user_intent = intent_result.strip().lower()
        if user_intent not in VALID_INTENTS:
            user_intent = INTENT_TOPIC if len(text) > MIN_TEXT_LENGTH_FOR_TOPIC and not has_context else INTENT_CREATE
    else:
        user_intent = INTENT_TOPIC if len(text) > MIN_TEXT_LENGTH_FOR_TOPIC and not has_context else INTENT_CREATE

    print(f"[后端] LLM 意图: '{text[:30]}' → {user_intent}")
    return user_intent


def _clean_copy(text: str) -> str:
    """清洗 LLM 输出的文案：移除混入的配乐名、标签、多余 emoji 噪声"""
    # 移除 "配乐：《...》" 或 "BGM：..." 等混入的配乐推荐
    text = _RE_REMOVE_BGM.sub('', text)
    # 移除末尾的 #标签 堆（标签不应在文案正文中）
    text = _RE_REMOVE_TAGS.sub('', text)
    # 如果清洗后太短，保留原文
    if len(text.strip()) < 10:
        return text
    return text.strip()


def _generate_copy_from_topic(user_idea: str) -> str:
    """根据用户主题/想法生成抖音文案"""
    gen_prompt = f"""你是一个抖音文案写手。根据用户的主题/想法，生成一段适合抖音图文的文案。

规则（严格遵守）：
1. 30-100字，简短有力
2. 只输出文案正文，不要输出配乐名、标签、BGM、歌手名
3. 不要输出 #标签，标签由单独的系统生成
4. 如果用户提到了具体产品/场景，围绕它展开
5. 可以包含问句或悬念增加互动

用户想法：{user_idea}

直接输出文案正文，不要其他内容。"""

    generated = call_deepseek(
        system_prompt="你是专业抖音文案写手，只输出文案正文，绝不输出配乐名或标签。",
        user_prompt=gen_prompt,
        temperature=0.8,
        max_tokens=COPY_GENERATE_MAX_TOKENS,
        timeout=15,
    )
    if generated and isinstance(generated, str) and len(generated) > MIN_GENERATED_COPY_LENGTH:
        copy_text = _clean_copy(generated.strip())
        print(f"[后端] 文案生成: {copy_text[:TEXT_PREVIEW_LENGTH]}...")
        return copy_text
    return ""


def _optimize_copy(user_feedback: str, prev_text: str, prev_suggestions: list) -> str:
    """根据用户反馈和评估建议优化文案"""
    opt_suggestions = "; ".join(prev_suggestions) if prev_suggestions else "提升整体质量"
    rewrite_prompt = f"""优化以下抖音文案。

用户反馈：{user_feedback}
上一轮评估建议：{opt_suggestions}

原文案：{prev_text[:200]}

规则（严格遵守）：
1. 保持核心主题不变，针对用户反馈和评估建议改进
2. 30-120字，适合抖音图文，有感染力
3. 只输出文案正文，不要输出配乐名、标签、BGM、歌手名
4. 不要输出 #标签

直接输出文案正文，不要其他内容。"""

    rewritten = call_deepseek(
        system_prompt="你是专业文案优化师，只输出文案正文，绝不输出配乐名或标签。",
        user_prompt=rewrite_prompt,
        temperature=0.8,
        max_tokens=COPY_GENERATE_MAX_TOKENS,
        timeout=15,
    )
    if rewritten and isinstance(rewritten, str) and len(rewritten) > MIN_GENERATED_COPY_LENGTH:
        new_text = _clean_copy(rewritten.strip())
        print(f"[后端] Optimize 文案优化: {new_text[:TEXT_PREVIEW_LENGTH]}...")
        return new_text
    return ""


def _parse_user_intent_semantic(user_feedback: str) -> dict:
    """通过 LLM 语义理解解析用户想修改/保留哪些组件

    Returns:
        {"change_copy": bool, "change_tags": bool, "change_images": bool, "change_music": bool,
         "keep_copy": bool, "keep_tags": bool, "keep_images": bool, "keep_music": bool}
    失败返回 None，由关键词回退处理
    """
    prompt = f"""分析用户对当前图文内容的反馈，判断想修改和保留哪些组件。

## 用户反馈
"{user_feedback}"

## 输出格式（严格 JSON）
{{
  "change_copy": false,
  "change_tags": false,
  "change_images": false,
  "change_music": false,
  "keep_copy": false,
  "keep_tags": false,
  "keep_images": false,
  "keep_music": false
}}

## 判断规则
- change_* = true: 用户想修改/更换/优化这个组件
- keep_* = true: 用户明确表示保留/不变/继续用
- 没提到的组件默认为 false
- "优化一下"/"再改改" = change_copy: true（默认重写文案）
- "换个风格" = change_copy: true
- "照片不太好看"/"图不搭"/"换张图" = change_images: true
- "背景音乐太吵"/"换首歌"/"BGM不合适" = change_music: true
- "标签挺好的"/"保留标签" = keep_tags: true
- "原图不变"/"图片保留"/"继续用原来的" = keep_images: true

只输出 JSON，不要其他内容。"""

    result = call_deepseek_json(
        system_prompt="你是一个严格的 JSON 输出器，只输出 JSON。",
        user_prompt=prompt,
        temperature=0.0,
        max_tokens=200,
        timeout=5,
    )
    if isinstance(result, dict) and any(k in result for k in ["change_copy", "change_tags", "change_images", "change_music"]):
        print(f"[语义解析] {result}")
        return result
    return None


def _rewrite_copy(user_feedback: str, prev_text: str) -> str:
    """根据用户反馈改写文案"""
    rewrite_prompt = f"""重写以下抖音文案。

用户的改写要求：{user_feedback}

原文案：{prev_text[:200]}

规则（严格遵守）：
1. 保持核心主题不变，根据用户的改写要求调整风格
2. 30-120字，适合抖音图文，有感染力
3. 只输出文案正文，不要输出配乐名、标签、BGM、歌手名
4. 不要输出 #标签

直接输出文案正文，不要其他内容。"""

    rewritten = call_deepseek(
        system_prompt="你是专业文案改写师，只输出文案正文，绝不输出配乐名或标签。",
        user_prompt=rewrite_prompt,
        temperature=0.8,
        max_tokens=REWRITE_MAX_TOKENS,
        timeout=15,
    )
    if rewritten and isinstance(rewritten, str) and len(rewritten) > MIN_GENERATED_COPY_LENGTH:
        new_text = _clean_copy(rewritten.strip())
        print(f"[后端] 文案改写: {new_text[:TEXT_PREVIEW_LENGTH]}...")
        return new_text
    return ""


@app.post("/api/agent/run")
async def agent_run(request: Request):
    """智能补全：根据用户提供的素材，自动推理并补全缺失内容"""
    try:
        body = await request.body()
        try:
            data = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError):
            data = json.loads(body.decode("gbk", errors="replace"))
    except Exception:
        return {"error": "invalid_body", "evaluation": None, "agent_suggestions": {}, "execution_log": []}

    text = data.get("text", "").strip()
    tags_input = data.get("tags", [])
    images_input = data.get("images", [])
    music_input = data.get("music", [])
    session_id = data.get("session_id", "")
    conversation_id = data.get("conversation_id") or request.query_params.get("conversation_id") or ""

    # 加载会话（优先从 conversation_id 重建，否则使用 session_id）
    session = {}
    if conversation_id:
        # 优先从对话历史重建会话上下文
        try:
            ctx = memory.get_context_for_agent(conversation_id, max_messages=MAX_CONTEXT_MSGS)
            msgs = ctx.get("messages", [])
            # 找最近一条 assistant 消息，恢复完整会话状态
            for msg in reversed(msgs):
                if msg.get("role") == "assistant":
                    meta = msg.get("metadata")
                    if isinstance(meta, str):
                        meta = json.loads(meta) if meta else {}
                    if isinstance(meta, dict):
                        if meta.get("evaluation"):
                            session["evaluation"] = meta["evaluation"]
                        # 从 evaluation.showcase 恢复上次的图片/标签/配乐
                        showcase = meta["evaluation"].get("showcase", {})
                        if showcase.get("images"):
                            session["images"] = showcase["images"]
                        if showcase.get("tags"):
                            session["tags"] = [f"#{t}" if not t.startswith('#') else t for t in showcase["tags"]]
                        if showcase.get("music"):
                            session["music"] = showcase["music"]
                        # 恢复用户素材标记
                        if meta.get("user_provided"):
                            session["user_provided"] = meta["user_provided"]
                        if meta.get("user_original_images"):
                            session["user_original_images"] = meta["user_original_images"]
                    break
            # 找最近一条 user 消息作为上轮文案
            for msg in reversed(msgs):
                if msg.get("role") == "user" and msg.get("content") and msg["content"] not in ("优化一下", "换标签", "换个配乐", "重试"):
                    session["text"] = msg["content"]
                    # 从 user 消息 metadata 恢复用户原始素材
                    user_meta = msg.get("metadata")
                    if isinstance(user_meta, str):
                        user_meta = json.loads(user_meta) if user_meta else {}
                    if isinstance(user_meta, dict):
                        if user_meta.get("images") and not session.get("user_original_images"):
                            session["user_original_images"] = user_meta["images"]
                    break
            print(f"[后端] 从对话历史重建会话: text={bool(session.get('text'))} images={len(session.get('images',[]))} tags={len(session.get('tags',[]))} eval={bool(session.get('evaluation'))}")
        except Exception as e:
            print(f"[后端] 重建会话失败: {e}")
    elif session_id:
        # 没有 conversation_id 时，使用本地会话文件
        session = _load_session()

    # 加载对话上下文
    context = {}
    if conversation_id:
        try:
            context = memory.get_context_for_agent(conversation_id, max_messages=MAX_CONTEXT_MSGS)
            print(f"[后端] 加载对话上下文: {len(context.get('messages', []))} 条历史消息")
        except Exception as e:
            print(f"[后端] 加载对话上下文失败: {e}")

    # 初始化变量
    need_tags = need_images = need_music = False
    prev_eval = None
    user_intent = "create"  # topic | create | optimize | modify | question
    generated_copy = ""     # LLM 生成的文案（topic 模式）

    # ================================================================
    # LLM 意图分类：对所有文本输入判断用户想干什么
    # ================================================================
    if text:
        prev_tags = session.get("tags", []) if session else []
        prev_eval = session.get("evaluation", {}) if session else {}
        prev_text = session.get("text", "") if session else ""
        prev_score = prev_eval.get("score", 0) if isinstance(prev_eval, dict) else 0
        prev_suggestions = prev_eval.get("suggestions", []) if isinstance(prev_eval, dict) else []

        # 构建 LLM 意图分类 prompt
        has_context = bool(prev_text)

        # LLM 意图分类
        user_intent = _classify_intent_with_llm(text, prev_text, prev_score, has_context)

        # ---- 意图路由 ----
        if user_intent == INTENT_TOPIC:
            # 用户给了一个主题 → 先生成文案
            generated_copy = _generate_copy_from_topic(text)
            if generated_copy:
                text = generated_copy
            # 标记需要全流程
            need_tags = True
            need_images = True
            need_music = True

        elif user_intent in ("optimize", "modify") and has_context:
            # ================================================================
            # 统一会话延续处理：从 session 恢复全部状态，用户素材默认保留
            # ================================================================
            user_feedback = text
            text = prev_text
            tags_input = prev_tags
            images_input = session.get("images", []) or []
            music_input = session.get("music", []) or []
            user_provided = session.get("user_provided", {})
            session["iteration"] = session.get("iteration", 0) + 1

            # --- 默认值 ---
            need_copy = False
            need_tags = False
            need_images = False
            need_music = False

            # ================================================================
            # 混合意图解析：LLM 语义理解（优先）→ 关键词匹配（回退）
            # ================================================================
            parsed = _parse_user_intent_semantic(user_feedback)
            if parsed:
                want_copy = parsed.get("change_copy", False)
                want_tags = parsed.get("change_tags", False)
                want_images = parsed.get("change_images", False)
                want_music = parsed.get("change_music", False)
                keep_images = parsed.get("keep_images", False)
                keep_tags = parsed.get("keep_tags", False)
                keep_music = parsed.get("keep_music", False)
            else:
                # LLM 不可用 → 关键词回退
                want_copy = any(kw in user_feedback for kw in ["文案", "文字", "风格", "改写", "改一下", "不满意", "换种", "重写", "优化"])
                want_tags = any(kw in user_feedback for kw in ["标签", "tag", "话题"])
                want_music = any(kw in user_feedback for kw in ["配乐", "音乐", "bgm", "歌曲", "BGM"])
                want_images = any(kw in user_feedback for kw in ["图片", "图", "照片"])
                keep_any = any(kw in user_feedback for kw in ["不变", "保留", "原来的", "继续用", "别动", "别改"])
                keep_images = keep_any and want_images
                keep_tags = keep_any and want_tags
                keep_music = keep_any and want_music

            if user_intent == "optimize":
                need_copy = True
                if not user_provided.get("tags", True): need_tags = True
                if not user_provided.get("images", True): need_images = True
                if not user_provided.get("music", True): need_music = True

            # --- 语义/关键词结果覆盖默认值 ---
            if want_copy: need_copy = True
            if want_tags and not keep_tags: need_tags = True
            if want_images and not keep_images: need_images = True
            if want_music and not keep_music: need_music = True
            
            # --- 默认保留已有图片（除非用户明确要求更换）---
            # 当用户没有提到图片时，默认保留上一轮的图片
            if not want_images and not keep_images and session.get("images"):
                images_input = session["images"]
                print(f"[后端] 默认保留上一轮图片 {len(images_input)} 张")

            # --- 恢复用户原始素材 ---
            if keep_images and session.get("user_original_images"):
                images_input = session["user_original_images"]
                print(f"[后端] 恢复用户原始图片 {len(images_input)} 张")

            # --- 执行文案重写 ---
            if need_copy:
                if user_intent == "optimize":
                    rewritten = _optimize_copy(user_feedback, prev_text, prev_suggestions)
                else:
                    rewritten = _rewrite_copy(user_feedback, prev_text)
                if rewritten:
                    text = rewritten
                # 新文案需匹配新标签+配乐（除非用户自己提供了这些组件）
                if not user_provided.get("tags", False): need_tags = True
                if not user_provided.get("music", False): need_music = True

            print(f"[后端] {user_intent}: copy={need_copy} tags={need_tags} images={need_images} music={need_music} | 用户提供: tags={user_provided.get('tags')} images={user_provided.get('images')} music={user_provided.get('music')} | 保留: images={keep_images} tags={keep_tags} music={keep_music}")

        elif user_intent == "question":
            need_tags = need_images = need_music = False
            need_eval = False

    # 智能识别：无文案但有图片 → 图片生成文案
    if not text and images_input:
        img_urls = [img.get("url", img.get("path", "")) for img in images_input if img.get("url") or img.get("path")]
        if img_urls:
            print(f"[后端] 检测到 {len(img_urls)} 张图片，启动图片识别...")
            recognized_text = analyze_images(img_urls)
            if recognized_text:
                text = recognized_text
                print(f"[后端] 图片识别生成文案: {text[:TEXT_PREVIEW_LENGTH]}...")

    # 智能判断：哪些 Skill 需要执行（followup 模式已在上面设置）
    if user_intent in ("topic", "create"):
        need_tags = not tags_input and bool(text)
        need_images = not images_input and bool(text)
        need_music = not music_input and bool(text)
        # 记录用户自行提供了哪些组件（后续 optimize/modify 默认保留）
        session["user_provided"] = {
            "tags": bool(tags_input),
            "images": bool(images_input),
            "music": bool(music_input),
        }
        # 保存用户原始提供的素材，后续轮次可恢复
        if images_input and not session.get("user_original_images"):
            session["user_original_images"] = list(images_input)
        if tags_input and not session.get("user_original_tags"):
            session["user_original_tags"] = list(tags_input)
    need_eval = bool(text)  # 只要有文案就评估

    print(f"[后端] 智能分析: text={bool(text)} need_tags={need_tags} need_images={need_images} need_music={need_music}")

    result = {
        "creator_content": {
            "text": text,
            "tags": tags_input,
            "images": images_input,
            "music": music_input,
        },
        "agent_suggestions": {"Skill1": [], "Skill2": [], "Skill3": []},
        "execution_log": [],
        "session_state": {"text": text, "tags": tags_input, "images": images_input, "music": music_input, "evaluation": None},
        "evaluation": None,
    }

    # ================================================================
    # Skill 1/2/3 并发执行（互不依赖，显著减少总耗时）
    # ================================================================
    from concurrent.futures import ThreadPoolExecutor, as_completed
    t_skills_start = time.time()

    def _run_skill1():
        if not need_tags:
            return ("Skill1", "skipped", tags_input)
        try:
            tr = HashtagRecommender.recommend(text, count=10)
            tags = [t["tag"] for t in tr] if tr else []
            return ("Skill1", "completed", tags)
        except Exception as e:
            return ("Skill1", "failed", str(e))

    def _run_skill2():
        if not need_images:
            return ("Skill2", "skipped", images_input)
        try:
            ir = recommend_images(text, count=4)
            return ("Skill2", "completed", ir if ir else [])
        except Exception as e:
            return ("Skill2", "failed", str(e))

    def _run_skill3(tags_for_music):
        if not need_music:
            return ("Skill3", "skipped", music_input)
        try:
            mr = recommend_music(tags_for_music[:15], text, use_api=True, fetch_urls=True)
            return ("Skill3", "completed", mr if mr else [])
        except Exception as e:
            return ("Skill3", "failed", str(e))

    skill1_tags = tags_input
    with ThreadPoolExecutor(max_workers=3) as executor:
        f1 = executor.submit(_run_skill1)
        f2 = executor.submit(_run_skill2)

        # 等 Skill1 完成 → 拿到标签 → 立即启动 Skill3（与 Skill2 并行）
        name, status, data = f1.result()
        if name == "Skill1" and status == "completed":
            skill1_tags = data
        result["execution_log"].append({
            "skill": "标签推荐", "status": status, "timestamp": time.strftime("%H:%M:%S")
        })
        if status != "failed":
            result["agent_suggestions"]["Skill1"] = data
        else:
            result["agent_suggestions"]["Skill1"] = []
            result["execution_log"][-1]["error"] = str(data)

        # Skill3 现在可以启动（Skill1 结果已就绪）
        f3 = executor.submit(_run_skill3, skill1_tags)

        # 等 Skill2 完成
        name, status, data = f2.result()
        result["execution_log"].append({
            "skill": "图片推荐", "status": status, "timestamp": time.strftime("%H:%M:%S")
        })
        if status != "failed":
            result["agent_suggestions"]["Skill2"] = data
        else:
            result["agent_suggestions"]["Skill2"] = []
            result["execution_log"][-1]["error"] = str(data)

        # 等 Skill3 完成
        name, status, data = f3.result()
        result["execution_log"].append({
            "skill": "配乐推荐", "status": status, "timestamp": time.strftime("%H:%M:%S")
        })
        if status != "failed":
            result["agent_suggestions"]["Skill3"] = data
        else:
            result["agent_suggestions"]["Skill3"] = []
            result["execution_log"][-1]["error"] = str(data)

    print(f"[后端] Skill1/2/3 并发完成 ({time.time()-t_skills_start:.1f}s)")

    # ================================================================
    # 构建最终合并状态（新推荐优先 + 已有素材补充，去重）
    # 在 Skill 4 评估和 showcase 之前统一计算，确保评估的是完整补全后的结果
    # ================================================================
    new_tags = result["agent_suggestions"]["Skill1"] if isinstance(result["agent_suggestions"]["Skill1"], list) else []
    new_images = result["agent_suggestions"]["Skill2"] if isinstance(result["agent_suggestions"]["Skill2"], list) else []
    new_music = result["agent_suggestions"]["Skill3"] if isinstance(result["agent_suggestions"]["Skill3"], list) else []

    # tags 去重合并
    seen_tags = set()
    final_tags = []
    for t in (new_tags + tags_input):
        tag_str = t.replace("#", "") if isinstance(t, str) else str(t)
        if tag_str and tag_str not in seen_tags:
            seen_tags.add(tag_str)
            final_tags.append(tag_str)

    # images 去重合并（按 URL）
    seen_urls = set()
    final_images = []
    for img in (new_images + images_input):
        if not isinstance(img, dict): continue
        url = img.get("original_url") or img.get("url") or img.get("local_path", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            final_images.append({"url": url, "desc": img.get("description", ""), "local_path": img.get("local_path", ""), "source": img.get("source", "")})

    # music 去重合并（按名称）
    seen_names = set()
    final_music = []
    for m in (new_music + music_input):
        if not isinstance(m, dict): continue
        name = m.get("name", "")
        if name and name not in seen_names:
            seen_names.add(name)
            final_music.append({"name": name, "artist": m.get("artist", ""), "style": m.get("style", ""), "mood": m.get("mood", ""), "reason": m.get("reason", ""), "preview_url": m.get("preview_url") or m.get("url"), "can_preview": bool(m.get("preview_url") or m.get("url"))})

    # Skill 4：用去重后的最终状态评估
    if need_eval:
        t0 = time.time()
        try:
            # 评估使用最终合并后的完整组件（不是 raw_tags_input + raw_skill_result 的暴力拼接）
            eval_result = evaluate(
                text,
                final_tags[:10],
                images=final_images[:6],
                music=final_music[:5]
            )

            report = eval_result.get("report", "")
            if user_intent in ("optimize", "modify"):
                prev_score_val = prev_eval.get("score", 0) if isinstance(prev_eval, dict) else 0
                new_score = eval_result.get("score", 0)
                delta = new_score - prev_score_val
                delta_str = f"+{delta:.1f}" if delta > 0 else f"{delta:.1f}"
                report = (
                    f"> 第 {session.get('iteration', 1)} 轮优化 (上轮 {prev_score_val:.1f} → 本轮 {new_score:.1f} {delta_str})\n\n"
                    f"{report}"
                )
                result["agent_suggestions"]["_conversational"] = {
                    "type": "optimization",
                    "iteration": session.get("iteration", 1),
                    "previous_score": prev_score_val,
                    "delta": delta,
                }

            # 构建对话上下文注释
            ctx_text = ""
            if context.get("messages"):
                ctx_lines = ["\n\n## 对话历史（供参考）"]
                for m in context["messages"][-6:]:
                    role = "用户" if m.get("role") == "user" else "Agent"
                    content = str(m.get("content", ""))[:100]
                    ctx_lines.append(f"- {role}: {content}")
                ctx_text = "\n".join(ctx_lines)
            if ctx_text:
                report += f"\n{ctx_text}"

            showcase = {
                "text": text[:200],
                "tags": final_tags,
                "images": final_images,
                "music": final_music,
                "score": eval_result.get("score", 0),
                "tip": "按这个组合发布，效果更好哦 ✨",
            }

            result["evaluation"] = {
                "score": eval_result.get("score", 0),
                "level": eval_result.get("level", "未知"),
                "report": report,
                "suggestions": eval_result.get("suggestions", [])[:3],
                "showcase": showcase,
            }
            result["session_state"]["evaluation"] = result["evaluation"]
            result["execution_log"].append({"skill": "内容评估", "status": "completed", "timestamp": time.strftime("%H:%M:%S")})
        except Exception as e:
            result["execution_log"].append({"skill": "内容评估", "status": "failed", "error": str(e)})
        print(f"[后端] Skill4 内容评估 完成 ({time.time()-t0:.1f}s)")

    # ---- 处理 question 意图：用 LLM 生成对话式回答 ----
    if user_intent == "question":
        prev_tags = session.get("tags", []) if session else []
        prev_text = session.get("text", "") if session else ""
        prev_eval = session.get("evaluation", {}) if session else {}
        prev_score = prev_eval.get("score", 0) if isinstance(prev_eval, dict) else 0

        q_prompt = f"""用户在上一轮获得了创作推荐，现在问了一个问题。请用友好、有帮助的语气回答。

## 上一轮创作结果
- 文案: {prev_text[:100]}
- 标签: {', '.join(prev_tags[:8])}
- 评分: {prev_score}/5.0
- 建议: {'; '.join(prev_eval.get('suggestions', [])) if isinstance(prev_eval, dict) else '无'}

## 用户问题
{text}

请用简洁的中文回答，2-4句话即可。如果用户要求优化，告诉他可以输入"优化"来自动改进。"""

        answer = call_deepseek(
            system_prompt="你是一个创作顾问，回答用户关于内容创作的问题。",
            user_prompt=q_prompt,
            temperature=0.7,
            max_tokens=200,
            timeout=15,
        )
        answer_text = answer if (answer and isinstance(answer, str)) else "你可以输入'优化'来改进当前内容，或输入'换标签'来更换推荐。"
        result["evaluation"] = {
            "score": prev_score,
            "level": "对话回复",
            "report": answer_text,
            "suggestions": [],
        }

    # 首次创作完成 → 附加提示引导用户确认或优化
    if user_intent in ("topic", "create") and result.get("evaluation"):
        score = result["evaluation"]["score"]
        level = result["evaluation"]["level"]
        if score >= 4.0:
            result["evaluation"]["report"] += "\n\n---\n> ✅ 评分达标，可以发布。如有需要，输入\"优化一下\"继续改进。"
        else:
            result["evaluation"]["report"] += "\n\n---\n> ⚠️ 评分未达 4.0。输入\"优化\"我会根据建议自动改进。"

    print(f"[后端] 全流程完成 — 意图:{user_intent} 评分: {result['evaluation']['score'] if result['evaluation'] else 'N/A'}")

    # 自动保存到会话
    if session_id:
        session["session_id"] = session_id
        session["text"] = text
        session["tags"] = final_tags[:10] if final_tags else tags_input[:10]
        session["images"] = final_images[:6] if final_images else images_input[:6]
        session["music"] = final_music[:5] if final_music else music_input[:5]
        session["evaluation"] = result["evaluation"]
        _save_session(session)

    # 保存到对话历史（如果有 conversation_id）
    if conversation_id:
        try:
            memory.add_message(
                conversation_id=conversation_id,
                role="user",
                content=text,
                metadata={"tags": tags_input, "images": images_input, "music": music_input}
            )
            memory.add_message(
                conversation_id=conversation_id,
                role="assistant",
                content=json.dumps(result, ensure_ascii=False),
                metadata={
                    "evaluation": result.get("evaluation"),
                    "suggestions": result.get("agent_suggestions"),
                    "user_provided": session.get("user_provided", {}),
                    "user_original_images": session.get("user_original_images", []),
                }
            )
            print(f"[后端] 消息已保存到对话历史 conversation_id={conversation_id}")
            
            # 自动保存到发布记录表（用于数据分析）
            evaluation = result.get("evaluation", {})
            if evaluation and evaluation.get("score"):
                try:
                    memory.save_conversation_to_publish_history(
                        conversation_id=conversation_id,
                        text=text,
                        tags=final_tags,
                        images=final_images,
                        music=final_music,
                        evaluation_score=evaluation.get("score", 0),
                        evaluation_level=evaluation.get("level", "未知")
                    )
                    print(f"[后端] 已保存到发布记录表 conversation_id={conversation_id}")
                except Exception as e:
                    print(f"[后端] 保存发布记录失败: {e}")
        except Exception as e:
            print(f"[后端] 保存对话历史失败: {e}")

    return result


# =====================================================
# =====================================================
# 素材管理（委托 MemoryManager）
# =====================================================

@app.get("/api/materials")
def get_materials(type: Optional[str] = None):
    """获取素材列表"""
    return memory.list_materials(material_type=type)


@app.post("/api/materials")
def add_material(data: dict):
    """添加素材"""
    mat_type = data.get("material_type", "text")
    if mat_type == "text":
        content = data.get("original_content", "")
        mid = memory.add_text_material(content)
    elif mat_type == "image":
        content = data.get("image_path", data.get("original_content", ""))
        mid = memory.add_image_material(content)
    else:
        content = data.get("music_name", data.get("original_content", ""))
        mid = memory.add_music(content)
    return {"id": mid}


@app.put("/api/materials/{material_id}")
def update_material(material_id: int, data: dict):
    """更新素材"""
    mat_type = data.get("material_type", "text")
    if mat_type == "text":
        content = data.get("original_content", "")
    elif mat_type == "image":
        content = data.get("image_path", data.get("original_content", ""))
    else:
        content = data.get("music_name", data.get("original_content", ""))
    success = memory.update_material(material_id, content)
    return {"success": success}


@app.delete("/api/materials/{material_id}")
def delete_material(material_id: int):
    """删除素材"""
    success = memory.delete_material(material_id)
    return {"success": success}


@app.get("/api/materials/by-tags")
def get_materials_by_tags(tags: str):
    """根据标签获取素材"""
    tag_list = tags.split(",") if tags else []
    return memory.get_materials_by_tags(tag_list)


@app.get("/api/materials/top")
def get_top_materials(type: str, limit: int = 10):
    """获取热门素材"""
    return memory.get_top_materials(type, limit)


# =====================================================
# 发布历史（委托 MemoryManager）
# =====================================================

@app.get("/api/publish/history")
def get_publish_history():
    """获取发布历史"""
    return memory.get_publish_history(limit=50)


@app.put("/api/publish/{publish_id}/data")
def update_publish_data(publish_id: int, data: PublishDataUpdate):
    """更新发布数据"""
    try:
        memory.update_publish_data(publish_id, data.likes, data.comments, data.views)
        return {"success": True}
    except Exception as e:
        logger.error(f"更新发布数据失败: {e}")
        _api_error("更新发布数据失败")


# =====================================================
# 数据分析（委托 MemoryManager）
# =====================================================

@app.get("/api/analytics/overview")
def get_analytics_overview():
    """获取分析概览"""
    return memory.analyze_personal_data()


@app.get("/api/analytics/traffic-trend")
def get_traffic_trend(content_id: int = None, limit: int = 30):
    """获取流量日趋势"""
    return memory.get_traffic_trend(content_id=content_id, limit=limit)


@app.get("/api/analytics/follower-trend")
def get_follower_trend(content_id: int = None, limit: int = 30):
    """获取粉丝日趋势"""
    return memory.get_follower_trend(content_id=content_id, limit=limit)


@app.get("/api/content/{post_id}")
def get_content_detail(post_id: int):
    """获取单条内容详情（含日趋势）"""
    detail = memory.get_content_detail(post_id)
    if not detail:
        raise HTTPException(status_code=404, detail="内容不存在")
    return detail


# =====================================================
# 抖音数据同步
# =====================================================

STATE_FILE = PROJECT_ROOT / "douyin_state.json"


@app.post("/api/douyin/login")
def douyin_login():
    """
    [已禁用] 触发浏览器扫码登录（Playwright 有头模式）

    发布 Skill 已永久禁用。此端点保留但不再工作。
    """
    return {"success": False, "message": "发布功能已禁用。本产品为创作顾问，不提供自动发布。"}


@app.get("/api/douyin/status")
def douyin_status():
    """检查抖音登录状态"""
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)
            cookies = state.get("cookies", [])
            # 找关键 Cookie 判断登录状态
            session_cookie = next((c for c in cookies if c.get("name") == "sessionid"), None)
            is_logged_in = bool(session_cookie and session_cookie.get("value"))
            return {
                "logged_in": is_logged_in,
                "cookie_count": len(cookies),
                "state_file": str(STATE_FILE),
                "message": "已登录" if is_logged_in else "Cookie 已过期",
            }
        except Exception as e:
            return {"logged_in": False, "error": str(e)}
    return {"logged_in": False, "cookie_count": 0, "message": "未找到登录状态文件"}


@app.post("/api/douyin/sync")
def douyin_sync(data: dict = None):
    """
    录入个人发布数据到 memory.db
    接受前端提交的发布记录数组，写入 publish_history 表。
    """
    if not data or "records" not in data:
        return {"success": False, "message": "缺少 records 字段"}

    count = memory.batch_sync_records(data["records"])
    return {"success": True, "synced": count, "message": f"成功同步 {count} 条记录"}


@app.post("/api/douyin/sync-auto")
def douyin_sync_auto():
    """
    [已禁用] 自动拉取创作者数据（需有效 Cookie）
    发布 Skill 已禁用，此端点仅返回提示。
    """
    return {"success": False, "message": "发布 Skill 已禁用。请使用 /api/douyin/sync 手动录入数据。"}


@app.get("/api/douyin/sync-history")
def get_sync_history():
    """获取同步历史记录"""
    return memory.get_publish_history(limit=50)


# =====================================================
# 健康检查
# =====================================================

# =====================================================
# 图片上传 + 静态文件服务
# =====================================================
# 个人素材库目录（用户上传的图片）
PERSONAL_DIR = PROJECT_ROOT / "personal_materials"
PERSONAL_DIR.mkdir(parents=True, exist_ok=True)
# 公共通用库目录（Agent 推荐的图片）
PUBLIC_DIR = PROJECT_ROOT / "approved_images"
PUBLIC_DIR.mkdir(parents=True, exist_ok=True)

# 静态挂载在文件末尾（必须在所有路由注册之后）


# 允许上传的图片文件扩展名
_ALLOWED_UPLOAD_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "webp", "bmp"}

@app.post("/api/upload")
async def upload_image(file: UploadFile = File(...)):
    """上传用户图片到个人素材库，返回持久化 URL 并记录到 personal_material_library"""
    import uuid
    ext = file.filename.rsplit(".", 1)[-1] if file.filename and "." in file.filename else "jpg"
    # 验证文件扩展名（防止上传恶意文件类型）
    if ext.lower() not in _ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型 .{ext}，仅允许: {', '.join(sorted(_ALLOWED_UPLOAD_EXTENSIONS))}"
        )
    safe_name = f"user_{uuid.uuid4().hex[:8]}_{file.filename or 'image'}"
    safe_name = "".join(c for c in safe_name if c.isalnum() or c in "._-") + f".{ext}"
    file_path = PERSONAL_DIR / safe_name
    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)
    url = f"/personal/{safe_name}"
    # 记录到个人素材库
    try:
        tags = ["用户上传"]
        memory.record_material(str(file_path), "image", tags)
    except Exception as e:
        print(f"[上传] 素材库记录失败: {e}")
    print(f"[上传] {file.filename} → {url} ({len(content)} bytes)")
    return {"url": url, "original_name": file.filename, "size": len(content)}


# =====================================================
# Redis 短期记忆 + Qdrant 公共库端点
# =====================================================

@app.get("/api/stats/daily")
def get_daily_stats():
    """获取今日实时统计（Redis）"""
    stats = redis_cache.get_daily_stats()
    return {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "stats": stats,
        "redis_available": redis_cache._ok(),
    }


@app.get("/api/qdrant/hot-topics")
def get_qdrant_hot_topics(limit: int = 10):
    """获取热门话题（Qdrant topic_trends）"""
    topics = vector_store.get_hot_topics(limit)
    return {
        "topics": topics,
        "qdrant_available": vector_store._ok,
        "source": "qdrant" if vector_store._ok else "fallback",
    }


@app.get("/api/qdrant/similar-texts")
def search_similar_texts(text: str, limit: int = 5):
    """搜索相似文案 + 质量参考（Qdrant public_texts）"""
    if not text:
        return {"results": [], "message": "缺少 text 参数"}
    results = vector_store.search_similar_texts(text, limit)
    return {"results": results, "count": len(results)}


@app.get("/api/qdrant/search-tags")
def search_tags_qdrant(text: str, limit: int = 10):
    """语义搜索公共标签（Qdrant public_tags）"""
    if not text:
        return {"results": [], "message": "缺少 text 参数"}
    results = vector_store.search_tags(text, limit)
    return {"results": results, "count": len(results)}


@app.post("/api/qdrant/index-text")
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


@app.get("/api/health")
def health():
    """健康检查接口（用于浏览器扩展检测后端状态）"""
    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
    }


# =====================================================
# 静态文件挂载（必须在所有路由之后）
# =====================================================
app.mount("/personal", StaticFiles(directory=str(PERSONAL_DIR)), name="personal")
app.mount("/public", StaticFiles(directory=str(PUBLIC_DIR)), name="public")

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=9000)
