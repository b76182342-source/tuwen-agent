# 抖音创作顾问 Agent — 前后端接口审计报告

> 审计日期：2026-07-10  
> 版本：v2.0  
> 审计范围：全部 8 个路由模块 (35 个端点) + LangGraph 14 节点工作流 + 前端 6 页面数据流

---

## 一、系统架构总览

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Frontend (React + Vite :3000)                    │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌─────────────┐  │
│  │Workspace │ │Materials │ │ Publish  │ │Analytics │ │DouyinSync/  │  │
│  │ (核心)   │ │ Library  │ │ History  │ │          │ │Settings     │  │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ └──────┬──────┘  │
│       │             │            │            │               │         │
│  ┌────┴─────────────┴────────────┴────────────┴───────────────┴──────┐  │
│  │              services/api.ts  (axios, baseURL='/api')              │  │
│  │              services/websocket.ts (ws://localhost:8000)           │  │
│  │              stores/appStore.ts  (Zustand)                         │  │
│  └────────────────────────────────┬───────────────────────────────────┘  │
│                                   │ Vite Proxy                          │
│                    /api → :9000   /ws → :8000                           │
└───────────────────────────────────┼─────────────────────────────────────┘
                                    │
┌───────────────────────────────────┼─────────────────────────────────────┐
│                         Backend (FastAPI :9000)                          │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                    server.py (App Factory)                        │   │
│  │  • CORS Middleware    • API Key Auth Middleware                   │   │
│  │  • Static Mounts: /personal, /public                             │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                    │                                     │
│  ┌─────────┐ ┌─────────┐ ┌────────┐ ┌─────────┐ ┌────────┐            │
│  │ health  │ │conversa-│ │ agent  │ │materials│ │publish │            │
│  │ (1)     │ │tions(14)│ │  (3)   │ │  (6)    │ │  (5)   │            │
│  └─────────┘ └─────────┘ └───┬────┘ └─────────┘ └────────┘            │
│                              │                                          │
│              ┌───────────────┼───────────────┐                          │
│              │ analytics(3)  │ douyin(5)     │                          │
│              └───────────────┴───────────────┘                          │
│                              │                                          │
│              ┌───────────────┼───────────────┐                          │
│              │  upload(1)    │  stats(5)      │                         │
│              └───────────────┴───────────────┘                          │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │               LangGraph 工作流 (14 节点 + 6 条件边)              │   │
│  │                                                                  │   │
│  │  initialize → classify_intent ─┬→ generate_copy                  │   │
│  │                                ├→ optimize_copy                  │   │
│  │                                ├→ parse_modify_intent            │   │
│  │                                ├→ agent_dialogue → END/管线      │   │
│  │                                └→ analyze_emotion                │   │
│  │                                       ↓                          │   │
│  │  analyze_content → decide_skills → execute_all_skills            │   │
│  │       (Skill1║Skill2║Skill3 并行)                                │   │
│  │              ↓                                                   │   │
│  │  evaluate → check_threshold ─┬→ END (≥4.0 or iter≥3)            │   │
│  │                              └→ identify_weak → rerun_skill      │   │
│  │                                    └→ rerun_evaluate ↩           │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │              持久化层                                             │   │
│  │  • Redis (Cache) — DB1: 会话摘要, 每日统计                       │   │
│  │  • SQLite (memory.db) — DB2: 对话消息, 发布数据, 素材库          │   │
│  │  • Qdrant (Vector Store) — 公共文案/标签语义搜索                 │   │
│  └──────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 二、后端接口清单（35 个端点）

### 2.1 健康检查 — `routers/health.py`

| # | 方法 | 路径 | 认证 | 请求体 | 响应 | 说明 |
|---|------|------|------|--------|------|------|
| 1 | GET | `/api/health` | 无 | — | `{status, timestamp}` | 健康检查，免 API Key 认证 |

**审计发现**：✅ 正常。`server.py` 中 `_PUBLIC_PATHS` 已豁免此路径认证。

---

### 2.2 会话 & 对话管理 — `routers/conversations.py` (14 端点)

| # | 方法 | 路径 | 认证 | 请求体/参数 | 响应 | 说明 |
|---|------|------|------|-------------|------|------|
| 2 | GET | `/api/session` | API Key | — | `{session_id, messages[], ...}` | 获取当前会话（从 `state/current_session.json`） |
| 3 | POST | `/api/session/save` | API Key | `dict` (合并到 session) | `{success: true}` | 保存会话状态到 JSON 文件 |
| 4 | POST | `/api/session/reset` | API Key | — | `{success, session}` | 重置会话（删除 JSON 文件） |
| 5 | POST | `/api/conversations` | API Key | `{title, user_id}` | `{conversation_id}` | 创建对话（生成 `conv_xxx` ID） |
| 6 | GET | `/api/conversations/{id}` | API Key | — | `Conversation` | 获取单个对话信息 |
| 7 | GET | `/api/conversations` | API Key | `?user_id&limit` | `Conversation[]` | 列出对话列表 |
| 8 | DELETE | `/api/conversations/{id}` | API Key | — | `{success}` | 删除对话（级联删除消息） |
| 9 | POST | `/api/conversations/batch-delete` | API Key | `{conversation_ids: []}` | `{deleted_count, total}` | 批量删除对话 |
| 10 | PUT | `/api/conversations/{id}` | API Key | `{title}` | `{success}` | 更新对话标题 |
| 11 | POST | `/api/conversations/messages` | API Key | `{conversation_id, role, content, metadata?}` | `{message_id}` | 添加消息到对话历史 |
| 12 | GET | `/api/conversations/{id}/messages` | API Key | `?limit` | `Message[]` | 获取对话消息历史 |
| 13 | GET | `/api/conversations/{id}/context` | API Key | `?max_messages` | `{conversation_id, messages[]}` | 获取对话上下文（供 Agent 使用） |
| 14 | GET | `/api/conversations/{id}/stats` | API Key | — | `{message_count, ...}` | 获取对话统计信息 |
| 15 | GET | `/api/conversations/search` | API Key | `?keyword&user_id&limit` | `Conversation[]` | 搜索对话（标题模糊匹配） |

**审计发现**：

| 问题编号 | 严重度 | 问题描述 |
|----------|--------|----------|
| **B-01** | 🟡 中 | `POST /api/session/save` 无输入验证 — 直接 `session.update(data)` 可造成 JSON 文件被任意键值覆盖 |
| **B-02** | 🟡 中 | `GET /api/session` 与 `GET /api/conversations/{id}` 数据源不一致 — 前者读 JSON 文件，后者读 SQLite，两者互不同步 |
| **B-03** | 🟢 低 | `POST /api/conversations/batch-delete` 对 JSON 解析有两层回退（UTF-8→GBK），但删除失败静默忽略，不报告具体哪些 ID 失败 |
| **B-04** | 🟢 低 | `GET /api/conversations/search` 仅搜索标题而非消息内容，实用性有限 |

---

### 2.3 Agent 执行管线 — `routers/agent.py` (3 端点)

| # | 方法 | 路径 | 认证 | 请求体 | 响应 | 说明 |
|---|------|------|------|--------|------|------|
| 16 | POST | `/api/agent/run` | API Key | `{text, tags[], images[], music[], conversation_id?}` | `{creator_content, agent_suggestions, evaluation, execution_log, session_state}` | **核心端点**：委托 LangGraph 全流程执行 |
| 17 | GET | `/api/agent/status/{session_id}` | API Key | — | `{session_id, status, iteration}` | 查询 session 运行状态 |
| 18 | POST | `/api/agent/rollback` | API Key | `{conversation_id, skill}` | `{success, restored[]}` | 回滚 Skill 结果到上一轮 |

**审计发现**：

| 问题编号 | 严重度 | 问题描述 |
|----------|--------|----------|
| **B-05** | 🔴 高 | `POST /api/agent/run` 请求体解析有两层编码回退 (`json.loads` → `gbk`)，在极端情况下可能解析出乱码数据进入管线 |
| **B-06** | 🟡 中 | `GET /api/agent/status/{session_id}` 数据源优先级混乱：先查 `memory.list_conversations()` → 再查 JSON 文件 → 最后返回 `not_found`。两个数据源结构不同，返回字段不一致 |
| **B-07** | 🟡 中 | `POST /api/agent/rollback` 实现简陋 — 仅找回上一条 assistant 消息的 JSON，不区分 Skill 类型，`skill_name` 参数未实际使用 |
| **B-08** | 🟡 中 | `_analyze_images()` 函数仅从 URL 文件名推理文案，实际图片内容未读取，且 LLM 超时仅 10 秒 |
| **B-09** | 🟢 低 | 空输入返回 `error: "empty_input"` 但 HTTP 状态码为 200，前端无法通过 HTTP 状态码区分错误 |

---

### 2.4 素材管理 — `routers/materials.py` (6 端点)

| # | 方法 | 路径 | 认证 | 请求体/参数 | 响应 | 说明 |
|---|------|------|------|-------------|------|------|
| 19 | GET | `/api/materials` | API Key | `?type` | `Material[]` | 获取素材列表（全部/按类型筛选） |
| 20 | POST | `/api/materials` | API Key | `{material_type, original_content/image_path/music_name, music_url?}` | `{id}` | 添加素材 |
| 21 | PUT | `/api/materials/{material_id}` | API Key | `{material_type, original_content/image_path/music_name}` | `{success}` | 更新素材 |
| 22 | DELETE | `/api/materials/{material_id}` | API Key | — | `{success}` | 删除素材 |
| 23 | GET | `/api/materials/by-tags` | API Key | `?tags` (逗号分隔) | `Material[]` | 按标签搜索素材 |
| 24 | GET | `/api/materials/top` | API Key | `?type&limit` | `Material[]` | 获取热门素材 |

**审计发现**：

| 问题编号 | 严重度 | 问题描述 |
|----------|--------|----------|
| **B-10** | 🔴 高 | `POST /api/materials` 和 `PUT /api/materials/{id}` 无 Pydantic 验证模型 — 直接接收 `dict`，无字段校验、无类型检查、无必填验证 |
| **B-11** | 🟡 中 | `PUT /api/materials/{id}` 中 `material_id` 声明为 `int` 但未做错误处理，非法 ID 会直接抛 FastAPI 异常 |
| **B-12** | 🟢 低 | `GET /api/materials/by-tags` 要求 tags 为逗号分隔字符串，但前端 `materialApi.getMaterialsByTags` 传的是 `string[]`（axios 会转成 `?tags[]=a&tags[]=b`），**前后端参数格式不匹配** |

---

### 2.5 发布历史 — `routers/publish.py` (5 端点)

| # | 方法 | 路径 | 认证 | 请求体/参数 | 响应 | 说明 |
|---|------|------|------|-------------|------|------|
| 25 | GET | `/api/publish/history` | API Key | — | `PublishHistory[]` | 获取发布历史 |
| 26 | PUT | `/api/publish/{publish_id}/data` | API Key | `{likes, comments, views}` | `{success}` | 更新发布数据（有 Pydantic 校验） |
| 27 | GET | `/api/content/{post_id}` | API Key | — | `ContentDetail` (含日趋势) | 获取单条内容详情 |
| 28 | GET | `/api/publish/{publish_id}` | API Key | — | `PublishDetail` | 获取单条发布详情 |
| 29 | DELETE | `/api/publish/{publish_id}` | API Key | — | `{success}` | 删除发布记录 |

**审计发现**：

| 问题编号 | 严重度 | 问题描述 |
|----------|--------|----------|
| **B-13** | 🟡 中 | 路径参数类型不一致 — `publish_id` 在 `PUT /api/publish/{publish_id}/data` 中为 `int`，但在 `GET /api/publish/{publish_id}` 中为 `str`，在 `DELETE /api/publish/{publish_id}` 中也为 `str` |
| **B-14** | 🟡 中 | `GET /api/content/{post_id}` 和 `GET /api/publish/{publish_id}` 功能重叠 — 两者返回相同的 `content_posts` 表数据，但路径不同 (`/content/` vs `/publish/`) |
| **B-15** | 🟢 低 | 前端 `publishApi.getPublish(id: number)` 传 number，但后端路径参数类型为 `str` — FastAPI 可自动转换，但语义不一致 |

---

### 2.6 数据分析 — `routers/analytics.py` (3 端点)

| # | 方法 | 路径 | 认证 | 请求体/参数 | 响应 | 说明 |
|---|------|------|------|-------------|------|------|
| 30 | GET | `/api/analytics/overview` | API Key | — | `PersonalDataAnalysis` | 数据分析总览 |
| 31 | GET | `/api/analytics/traffic-trend` | API Key | `?content_id&limit` | `TrafficDailyItem[]` | 流量日趋势 |
| 32 | GET | `/api/analytics/follower-trend` | API Key | `?content_id&limit` | `FollowerDailyItem[]` | 粉丝日趋势 |

**审计发现**：

| 问题编号 | 严重度 | 问题描述 |
|----------|--------|----------|
| **B-16** | 🟢 低 | `content_id` 参数在路由函数签名中类型为 `int = None`，但前端可能传 `undefined`；FastAPI 会将 `None` 默认值正确处理，但类型注解不精确 |

---

### 2.7 抖音同步 — `routers/douyin.py` (5 端点)

| # | 方法 | 路径 | 认证 | 请求体/参数 | 响应 | 说明 |
|---|------|------|------|-------------|------|------|
| 33 | POST | `/api/douyin/login` | API Key | — | `{success: false}` | **[已禁用]** 触发浏览器登录 |
| 34 | GET | `/api/douyin/status` | API Key | — | `{logged_in, cookie_count}` | 检查登录状态（从 `douyin_state.json`） |
| 35 | POST | `/api/douyin/sync` | API Key | `{records: []}` | `{success, synced}` | 手动录入发布数据 |
| 36 | POST | `/api/douyin/sync-auto` | API Key | — | `{success: false}` | **[已禁用]** 自动拉取数据 |
| 37 | GET | `/api/douyin/sync-history` | API Key | — | `PublishHistory[]` | 获取同步历史 |

**审计发现**：

| 问题编号 | 严重度 | 问题描述 |
|----------|--------|----------|
| **B-17** | 🔴 高 | `POST /api/douyin/sync` 的 Pydantic 模型 `DouyinSyncRequest` 定义了 `records: List[dict]` 带 `min_items=1`，但路由函数签名使用 `data: dict = None` 而非 Pydantic 模型，**Pydantic 校验完全被绕过** |
| **B-18** | 🟡 中 | `POST /api/douyin/login` 和 `POST /api/douyin/sync-auto` 已禁用但端点仍暴露，应返回 410 Gone 或直接删除 |
| **B-19** | 🟢 低 | `GET /api/douyin/sync-history` 与 `GET /api/publish/history` 返回相同数据，属于冗余端点 |

---

### 2.8 图片上传 — `routers/upload.py` (1 端点)

| # | 方法 | 路径 | 认证 | 请求体/参数 | 响应 | 说明 |
|---|------|------|------|-------------|------|------|
| 38 | POST | `/api/upload` | API Key | `multipart/form-data` (file) | `{url, original_name, size}` | 上传图片到 `personal_materials/` |

**审计发现**：

| 问题编号 | 严重度 | 问题描述 |
|----------|--------|----------|
| **B-20** | 🟡 中 | 文件名清理 `"".join(c for c in safe_name if c.isalnum() or c in "._-")` 会删除中文字符，用户上传中文文件名会变成纯英文数字 |
| **B-21** | 🟢 低 | 文件大小无限制，可能被上传大文件耗尽磁盘 |

---

### 2.9 统计 & Qdrant — `routers/stats.py` (5 端点)

| # | 方法 | 路径 | 认证 | 请求体/参数 | 响应 | 说明 |
|---|------|------|------|-------------|------|------|
| 39 | GET | `/api/stats/daily` | API Key | — | `{date, stats, redis_available}` | 今日实时统计（Redis） |
| 40 | GET | `/api/qdrant/hot-topics` | API Key | `?limit` | `{topics[], qdrant_available}` | 热门话题（Qdrant） |
| 41 | GET | `/api/qdrant/similar-texts` | API Key | `?text&limit` | `{results[], count}` | 相似文案语义搜索 |
| 42 | GET | `/api/qdrant/search-tags` | API Key | `?text&limit` | `{results[], count}` | 标签语义搜索 |
| 43 | POST | `/api/qdrant/index-text` | API Key | `{text, quality_score, tags[], ...}` | `{success, indexed}` | 高质量文案写入 Qdrant |

**审计发现**：

| 问题编号 | 严重度 | 问题描述 |
|----------|--------|----------|
| **B-22** | 🟡 中 | `POST /api/qdrant/index-text` 无 Pydantic 验证，手动解析 JSON 且只有 `score < 4.0` 校验 |
| **B-23** | 🟢 低 | `GET /api/qdrant/similar-texts` 和 `GET /api/qdrant/search-tags` 中 `text` 参数通过 query string 传递，长文案可能超出 URL 长度限制 |

---

## 三、前端 API 调用与数据流

### 3.1 API Service 层 ([frontend/src/services/api.ts](frontend/src/services/api.ts))

**axios 实例配置**：
- `baseURL: '/api'`
- `timeout: 180000` (3 分钟)
- 请求拦截器：附加 `X-Request-Id` + `X-API-Key`
- 响应拦截器：统一错误提示 (500→error, 400→warning, 网络断连→error)

**前端 API 模块与实际后端路由映射**：

| 前端模块 | 前端方法 | 实际请求路径 | 后端路由 |
|----------|----------|-------------|----------|
| `agentApi.run` | POST | `/api/agent/run` | `routers/agent.py` |
| `agentApi.getStatus` | GET | `/api/agent/status/{id}` | `routers/agent.py` |
| `agentApi.rollback` | POST | `/api/agent/rollback` | `routers/agent.py` |
| `conversationApi.create` | POST | `/api/conversations` | `routers/conversations.py` |
| `conversationApi.get` | GET | `/api/conversations/{id}` | `routers/conversations.py` |
| `conversationApi.list` | GET | `/api/conversations` | `routers/conversations.py` |
| `conversationApi.delete` | DELETE | `/api/conversations/{id}` | `routers/conversations.py` |
| `conversationApi.batchDelete` | POST | `/api/conversations/batch-delete` | `routers/conversations.py` |
| `conversationApi.updateTitle` | PUT | `/api/conversations/{id}` | `routers/conversations.py` |
| `conversationApi.addMessage` | POST | `/api/conversations/messages` | `routers/conversations.py` |
| `conversationApi.getHistory` | GET | `/api/conversations/{id}/messages` | `routers/conversations.py` |
| `conversationApi.getContext` | GET | `/api/conversations/{id}/context` | `routers/conversations.py` |
| `conversationApi.getStats` | GET | `/api/conversations/{id}/stats` | `routers/conversations.py` |
| `conversationApi.search` | GET | `/api/conversations/search` | `routers/conversations.py` |
| `materialApi.getMaterials` | GET | `/api/materials` | `routers/materials.py` |
| `materialApi.addMaterial` | POST | `/api/materials` | `routers/materials.py` |
| `materialApi.updateMaterial` | PUT | `/api/materials/{id}` | `routers/materials.py` |
| `materialApi.deleteMaterial` | DELETE | `/api/materials/{id}` | `routers/materials.py` |
| `materialApi.getMaterialsByTags` | GET | `/api/materials/by-tags` | `routers/materials.py` |
| `materialApi.getTopMaterials` | GET | `/api/materials/top` | `routers/materials.py` |
| `publishApi.getHistory` | GET | `/api/publish/history` | `routers/publish.py` |
| `publishApi.getPublish` | GET | `/api/publish/{id}` | `routers/publish.py` |
| `publishApi.updatePublishData` | PUT | `/api/publish/{id}/data` | `routers/publish.py` |
| `publishApi.delete` | DELETE | `/api/publish/{id}` | `routers/publish.py` |
| `analyticsApi.getOverview` | GET | `/api/analytics/overview` | `routers/analytics.py` |
| `analyticsApi.getTrafficTrend` | GET | `/api/analytics/traffic-trend` | `routers/analytics.py` |
| `analyticsApi.getFollowerTrend` | GET | `/api/analytics/follower-trend` | `routers/analytics.py` |
| `analyticsApi.getContentDetail` | GET | `/api/content/{post_id}` | `routers/publish.py` |
| `douyinSyncApi.sync` | POST | `/api/douyin/sync` | `routers/douyin.py` |
| `douyinSyncApi.healthCheck` | GET | `/api/health` | `routers/health.py` |
| `douyinSyncApi.getSyncHistory` | GET | `/api/douyin/sync-history` | `routers/douyin.py` |

**审计发现**：

| 问题编号 | 严重度 | 问题描述 |
|----------|--------|----------|
| **F-01** | 🔴 高 | **API Key 硬编码**：`api.ts:30` 中 `X-API-Key: 'your-api-key-here'`，这是一个占位符值，不会被后端验证通过（除非后端恰好也配置了这个值），导致所有 API 调用 401 |
| **F-02** | 🔴 高 | **rollback 请求体字段名不匹配**：前端 `agentApi.rollback` 发送 `{session_id, target_skill}`，但后端 `POST /api/agent/rollback` 期望 `{conversation_id, skill}` — **完全不匹配** |
| **F-03** | 🟡 中 | **Mock 模式依赖 localStorage**：每次调用 `isMockMode()` 读 localStorage，在 Settings 页切换后需刷新才能影响已在运行的请求 |
| **F-04** | 🟡 中 | **materialApi.getMaterialsByTags** 传 `string[]` 给 `params: { tags }`，axios 默认序列化为 `?tags[]=a&tags[]=b`，但后端期望 `?tags=a,b`（逗号分隔字符串） |
| **F-05** | 🟡 中 | **analyticsApi.getContentDetail** 调用 `/api/content/{postId}` 归于 publish 路由模块，但定义在 analyticsApi 中，归类混乱 |
| **F-06** | 🟡 中 | **douyinSyncApi.healthCheck** 调用 `/api/health`，与 douyin 同步无关，应归属独立 healthApi |
| **F-07** | 🟡 中 | **前端未使用 `/api/upload` 端点** — 图片上传功能在前端 `Workspace.tsx` 使用 Ant Design Upload 组件，但图片直接通过 `FileReader` 转 base64 放在 `userInput.images` 中随 `/api/agent/run` 一起提交，绕过了独立上传端点 |
| **F-08** | 🟢 低 | **WebSocket 连接到 `ws://localhost:8000`** 但后端 `server.py` 运行在 `:9000` 且无 WebSocket 端点定义 — WebSocket service 定义了完整的消息类型和重连逻辑，但**后端未实现 WebSocket 端点** |

---

### 3.2 State 管理 ([frontend/src/stores/appStore.ts](frontend/src/stores/appStore.ts))

**Zustand Store 数据流**：

```
useAppStore
├── conversationId  ← localStorage('current_conversation_id')
├── messages[]      ← localStorage('msg_cache_{convId}')
├── inputText       ← localStorage('workspace_draft')
├── executionStages[]
├── executionResult
├── userInput {text, tags[], images[], music[], enable_blackbox}
├── materials[]
├── publishHistory[]
└── analytics
```

**持久化策略**：
| 数据 | 存储位置 | 生命周期 |
|------|----------|----------|
| conversationId | localStorage | 永久 |
| messages (缓存) | localStorage (`msg_cache_{id}`) | 永久 (最多 50 条) |
| inputText (草稿) | localStorage (`workspace_draft`) | 永久 |
| conversation 数据 | SQLite (via API) | 永久 |
| session 摘要 | Redis (via API) | 30 天 TTL |
| executionStages/Result | Zustand (内存) | 会话级别 |

---

### 3.3 页面级数据流详情

**Workspace 页（核心页面）**：
```
用户输入文本
    ↓
agentApi.run({text, tags, images, music, conversation_id})
    ↓
后端 LangGraph 14节点工作流
    ↓
返回 {creator_content, agent_suggestions, evaluation, execution_log, session_state}
    ↓
前端解析为 ChatMessageData 展示
    ↓
保存到 messages[] + localStorage 缓存
```

**MaterialLibrary 页**：
```
materialApi.getMaterials(type?)  → 展示素材列表
materialApi.deleteMaterial(id)   → 删除素材
materialApi.addMaterial(data)    → 添加素材
```

**PublishHistory 页**：
```
publishApi.getHistory()          → 展示发布历史列表
publishApi.getPublish(id)        → 查看单条详情
analyticsApi.getContentDetail(id)→ 查看含日趋势的详情
publishApi.delete(id)            → 删除记录
```

**Analytics 页**：
```
analyticsApi.getOverview()       → 数据总览
analyticsApi.getTrafficTrend()   → 流量趋势图
analyticsApi.getFollowerTrend()  → 粉丝趋势图
```

**DouyinSync 页**：
```
douyinSyncApi.sync(records)      → 手动录入数据
douyinSyncApi.getSyncHistory()   → 查看同步历史
douyinSyncApi.healthCheck()      → 检查后端健康
```

---

## 四、LangGraph 工作流数据流

### 4.1 State 定义 ([backend/graph/state.py](backend/graph/state.py))

`AgentState` 包含 26 个字段，覆盖全流程：

```
输入层:   user_input, conversation_id, enable_blackbox
意图层:   intent (topic|create|optimize|modify|question)
上下文:   session, has_context, prev_copy_text, prev_evaluation,
         prev_tags, prev_images, prev_music
文案层:   copy_text
组件层:   need_tags, need_images, need_music, modify_flags
情绪层:   emotion {mood, intensity, energy, keywords}
Skill层:  final_tags, final_images, final_music
评估层:   evaluation, iteration, best_score, best_evaluation,
         best_final_*, loop_history
对话层:   dialogue_messages, should_enter_workflow, workflow_intent_override
输出层:   result, execution_log, error
```

### 4.2 节点数据流图

```
                         ┌──────────────┐
                         │  initialize  │  ← DB1(Redis摘要) + DB2(SQLite消息)
                         └──────┬───────┘
                                │
                         ┌──────▼───────┐
                         │classify_intent│  ← LLM 五分类
                         └──────┬───────┘
                                │
          ┌─────────┬───────────┼───────────┬──────────┐
          ▼         ▼           ▼           ▼          ▼
   generate_copy optimize_copy parse_modify agent_dialogue analyze_emotion
   (topic→文案)  (optimize→改写) (modify→标记) (ReAct循环)  (已create→情绪)
          │         │           │           │          │
          └────┬────┘           │      ┌────┴────┐     │
               │                │      │ END     │     │
               ▼                ▼      │ 管线入口 │     │
          analyze_emotion◄──────┘      └─────────┘     │
               │                                        │
               ▼                                        │
         analyze_content  ← Python: 判断需要哪些组件      │
               │                                        │
               ▼                                        │
         decide_skills    ← Python: 决定执行哪些Skill     │
               │                                        │
               ▼                                        │
      execute_all_skills ← ThreadPoolExecutor并行3 Skill  │
               │                                        │
               ▼                                        │
           evaluate      ← Skill4 综合评估                │
               │                                        │
               ▼                                        │
        check_threshold  ← 评分≥4.0? iter≥3?             │
          │          │                                   │
     ┌────▼──┐  ┌───▼──────────┐                        │
     │  END   │  │identify_weak │ ← 找最低分维度          │
     └────────┘  └───┬──────────┘                        │
                     │                                    │
                ┌────▼─────┐                              │
                │rerun_skill│ ← 重跑最弱Skill              │
                └────┬─────┘                              │
                     │                                    │
                ┌────▼──────┐                             │
                │rerun_evaluate│ ← 重新评估               │
                └────┬──────┘                             │
                     │                                    │
                     └──→ check_threshold (循环)          │
```

### 4.3 条件边路由表

| 条件边 | 源节点 | 条件 | 目标 |
|--------|--------|------|------|
| `route_by_intent` | classify_intent | `topic` | generate_copy |
| | | `create` | analyze_emotion |
| | | `optimize` + has_context | optimize_copy |
| | | `modify` + has_context | parse_modify_intent |
| | | `question` | agent_dialogue |
| `route_after_modify` | parse_modify_intent | `change_copy=true` | optimize_copy |
| | | `change_copy=false` | analyze_emotion |
| `route_after_dialogue` | agent_dialogue | `should_enter_workflow` | analyze_emotion |
| | | 否则 | END |
| `route_by_score` | check_threshold | `score ≥ 4.0` | END |
| | | `score < 4.0 AND iter < 3` | identify_weak |
| | | `iter ≥ 3` | END |
| `route_after_weak` | identify_weak | `error == "no_dimensions"` | END |
| | | 否则 | rerun_skill |

---

## 五、数据持久化层

### 5.1 三层存储架构

```
┌────────────────────────────────────────────────────┐
│                    Redis (Cache)                    │
│  • 会话摘要 (DB1): summary:{conv_id} (TTL 30天)    │
│  • 每日统计: daily_stats                            │
│  • Qdrant 代理缓存                                  │
└────────────────────┬───────────────────────────────┘
                     │
┌────────────────────┴───────────────────────────────┐
│                 SQLite (memory.db)                  │
│  表:                                                │
│  • content_posts        — 发布内容                  │
│  • traffic_daily        — 流量日趋势                │
│  • follower_daily       — 粉丝日趋势                │
│  • tags                 — 标签库                    │
│  • conversations        — 对话会话                  │
│  • conversation_messages — 对话消息 (DB2)           │
│  • personal_material_library — 个人素材库           │
└────────────────────┬───────────────────────────────┘
                     │
┌────────────────────┴───────────────────────────────┐
│               Qdrant (Vector Store)                 │
│  • public_texts        — 公共文案向量               │
│  • public_tags         — 公共标签向量               │
│  • topic_trends        — 热门话题                   │
└────────────────────────────────────────────────────┘
```

### 5.2 双层记忆（DB1 + DB2）数据流

```
请求进入 →
  initialize 节点:
    ├── DB1 (Redis) 加载摘要 → prev_copy_text, prev_tags, prev_evaluation
    ├── DB2 (SQLite) 加载消息 → dialogue_messages (仅 agent_dialogue 用)
    └── 兜底: SQLite add_message 旧格式

管线完成 / Agent对话结束 →
  builder.run_agent():
    ├── DB1 (Redis) 保存摘要 ← save_session_summary()
    └── DB2 (SQLite) 保存消息 ← save_dialogue_messages()

  agent_dialogue 节点:
    ├── DB1 更新摘要（合并已有 + 新偏好）
    └── DB2 全量保存 ReAct 消息（先清空 agent 消息 → 批量插入）
```

---

## 六、关键问题汇总

### 🔴 高危 (需立即修复)

| 编号 | 位置 | 问题 |
|------|------|------|
| **F-01** | [api.ts:30](frontend/src/services/api.ts#L30) | API Key 硬编码为 `'your-api-key-here'`，所有请求 401 |
| **F-02** | [api.ts:171-174](frontend/src/services/api.ts#L171-L174) | rollback 请求体字段名与后端不匹配 (`session_id` vs `conversation_id`) |
| **B-10** | [materials.py:19-32](backend/routers/materials.py#L19-L32) | POST/PUT materials 无 Pydantic 验证 |
| **B-17** | [douyin.py:61-71](backend/routers/douyin.py#L61-L71) | douyin sync Pydantic 模型定义但未使用 |

### 🟡 中危 (建议近期修复)

| 编号 | 位置 | 问题 |
|------|------|------|
| **F-04** | [api.ts:290-293](frontend/src/services/api.ts#L290-L293) | getMaterialsByTags 参数格式前后端不匹配 |
| **F-08** | [websocket.ts:15](frontend/src/services/websocket.ts#L15) | WebSocket 连接到 8000 但后端无 WS 端点 |
| **B-01** | [conversations.py:78-85](backend/routers/conversations.py#L78-L85) | session/save 无输入验证 |
| **B-06** | [agent.py:129-151](backend/routers/agent.py#L129-L151) | status 端点数据源混乱 |
| **B-07** | [agent.py:160-195](backend/routers/agent.py#L160-L195) | rollback 未使用 skill_name |
| **B-12** | [materials.py:60-64](backend/routers/materials.py#L60-L64) | tags 参数格式与前端不兼容 |
| **B-13** | [publish.py](backend/routers/publish.py) | publish_id 类型不一致 (int vs str) |
| **B-14** | [publish.py](backend/routers/publish.py) | `/content/{id}` 与 `/publish/{id}` 功能重叠 |

### 🟢 低危 (可择机处理)

| 编号 | 位置 | 问题 |
|------|------|------|
| **B-03** | [conversations.py:150-175](backend/routers/conversations.py#L150-L175) | 批量删除失败静默忽略 |
| **B-04** | [conversations.py:239-246](backend/routers/conversations.py#L239-L246) | 搜索仅限标题 |
| **B-20** | [upload.py:25](backend/routers/upload.py#L25) | 中文文件名被删除 |
| **B-21** | [upload.py:16](backend/routers/upload.py#L16) | 无文件大小限制 |
| **B-23** | [stats.py:38-43](backend/routers/stats.py#L38-L43) | 长文本通过 query string 传递 |
| **F-06** | [api.ts:367-384](frontend/src/services/api.ts#L367-L384) | healthCheck 归错 API 模块 |

---

## 七、数据流一致性检查

### 7.1 请求 → 响应链路完整性

| 功能 | 前端调用 | 后端路由 | Graph 节点 | 持久化 | 状态 |
|------|----------|----------|-----------|--------|------|
| 智能创作 | Workspace → agentApi.run | POST /api/agent/run | 14节点完整链路 | DB1+DB2 | ✅ 完整 |
| 对话管理 | Workspace → conversationApi.* | CRUD 14端点 | initialize (读) | SQLite | ✅ 完整 |
| 素材浏览 | MaterialLibrary → materialApi.* | CRUD 6端点 | — | SQLite | ⚠️ 参数不匹配 |
| 发布历史 | PublishHistory → publishApi.* | CRUD 5端点 | — | SQLite | ⚠️ 类型不一致 |
| 数据分析 | Analytics → analyticsApi.* | 查询 3端点 | — | SQLite | ✅ 完整 |
| 数据同步 | DouyinSync → douyinSyncApi.* | 同步 5端点 | — | SQLite | ⚠️ 校验被绕过 |
| 图片上传 | — | POST /api/upload | — | 文件系统+SQLite | ⚠️ 前端未使用 |
| 实时推送 | websocket.ts | — | — | — | ❌ 后端未实现 |

### 7.2 前后端字段名对照

| 数据流 | 前端字段名 | 后端期望字段名 | 匹配 |
|--------|-----------|---------------|------|
| agent/run 请求 | `text, tags, images, music, enable_blackbox` | `text, tags, images, music, conversation_id` | ✅ (enable_blackbox 被后端忽略) |
| agent/run 响应 | `ExecutionResult` | `{creator_content, agent_suggestions, evaluation, execution_log, session_state}` | ✅ |
| agent/rollback 请求 | `session_id, target_skill` | `conversation_id, skill` | ❌ 不匹配 |
| conversations/create 请求 | `title, user_id` | `CreateConversationRequest(title, user_id)` | ✅ |
| materials 请求 | `{material_type, original_content, ...}` | 直接取 dict key | ⚠️ 无验证 |
| douyin/sync 请求 | `{records: DouyinSyncRecord[]}` | `{records: List[dict]}` (Pydantic 未使用) | ⚠️ 无验证 |

### 7.3 Vite 代理配置检查

| 代理前缀 | 目标 | 状态 |
|----------|------|------|
| `/api` | `http://localhost:9000` | ✅ 正常 |
| `/personal` | `http://localhost:9000` | ✅ 正常 (静态文件) |
| `/public` | `http://localhost:9000` | ✅ 正常 (静态文件) |
| `/ws` | `ws://localhost:8000` | ❌ 后端无 WS (server.py 运行在 9000) |

---

## 八、安全审计

### 8.1 API Key 认证

- ✅ 中间件正确豁免 `/api/health`, `/docs`, `/openapi.json`, `/redoc`
- ✅ 支持 `Authorization: Bearer <key>` 和 `X-API-Key: <key>` 两种方式
- ✅ 静态文件路径 `/personal/*`, `/public/*` 免认证
- ❌ 前端硬编码 API Key (F-01)
- ⚠️ API Key 从环境变量 `DEEPSEEK_API_KEY` 获取 (命名存在误导 — 实际复用 DeepSeek 的 Key 作为 API Key)

### 8.2 CORS

- ✅ 允许 localhost:3000, localhost:5173 (开发环境)
- ✅ 限制 Methods: GET, POST, PUT, DELETE
- ✅ 限制 Headers: Content-Type, Authorization, X-Request-Id
- ⚠️ 生产环境需更新 `CORS_ORIGINS` 环境变量

### 8.3 输入校验

- ✅ `conversations.py` 使用了 Pydantic 模型
- ✅ `publish.py` 的 `PublishDataUpdate` 使用了 Pydantic 模型
- ⚠️ `materials.py` 无 Pydantic 验证
- ⚠️ `douyin.py` 定义了模型但路由函数未使用
- ⚠️ `agent.py` 手动解析 JSON + GBK 回退

---

## 九、建议修复优先级

### P0 (立即)
1. 修复 API Key 硬编码 (F-01)
2. 修复 rollback 字段名不匹配 (F-02)

### P1 (本周)
3. 为 materials 路由添加 Pydantic 验证 (B-10)
4. 修复 douyin sync Pydantic 校验绕过 (B-17)
5. 统一 materials/by-tags 参数格式 (F-04, B-12)
6. 统一 publish_id 类型 (B-13)

### P2 (本月)
7. 实现或移除 WebSocket 端点 (F-08)
8. 修复 status 端点数据源混乱 (B-06)
9. 清理已禁用端点 (B-18)
10. 添加文件上传大小限制 (B-21)

---

*报告由全栈接口审计自动生成 · 2026-07-10*
