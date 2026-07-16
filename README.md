# 通用图文协助助手 — 产品说明书

**版本**：1.0.0-alpha | **日期**：2026-06-23 | **定位**：AI 驱动的图文内容创作顾问

---

## 目录

1. [产品概述](#一产品概述)
2. [系统架构](#二系统架构)
3. [核心工作流](#三核心工作流)
4. [Skill 规范](#四skill-规范)
5. [智能循环机制](#五智能循环机制)
6. [数据模型](#六数据模型)
7. [API 参考](#七api-参考)
8. [前端页面指南](#八前端页面指南)
9. [配置手册](#九配置手册)
10. [部署指南](#十部署指南)

---

## 一、产品概述

### 1.1 产品定位

通用图文协助助手是一个 **Task-Oriented Creative Advisory Agent**。用户输入任意形式的创作意图（主题、草稿文案、图片、想法），Agent 自动完成：

- **文案**：主题 → 文案生成 / 文案优化改写
- **标签**：语义分析 → 热门标签推荐（含推荐理由）
- **图片**：关键词提取 → 多源图片搜索 → 本地下载
- **配乐**：风格匹配 → 音乐推荐
- **评估**：5 维度综合评分 + 发布预测 + 优化建议

### 1.2 核心设计原则

| 原则 | 说明 |
|------|------|
| **顾问而非发布者** | Agent 推荐素材但不自动发布，发布由用户手动完成 |
| **双轨降级** | DeepSeek API（优先） → 本地规则（回退），保证离线可用 |
| **质量闭环** | 评分 < 4.0 自动重新推理，最多 3 轮 |
| **用户主导迭代** | 评分通过后用户可指定不满意的组件重新生成 |
| **持续记忆** | SQLite 持久化对话历史、素材表现、标签效果 |

### 1.3 技术栈

| 层 | 技术 |
|----|------|
| **前端** | React 18 + TypeScript + Vite 5 + Ant Design 5 + Zustand 4 |
| **后端** | Python 3.10+ / FastAPI / WebSocket |
| **AI** | DeepSeek Chat API（语义理解 + 内容生成） |
| **数据** | SQLite 9 表（对话/素材/发布/评估/标签） |
| **图片** | Pexels API + Unsplash API |
| **配乐** | 抖音官方音乐榜单 API + 规则映射 |
| **浏览器自动化** | Playwright（发布辅助，可选） |

---

## 二、系统架构

### 2.1 分层架构图

```
┌──────────────────────────────────────────────────────────────┐
│                    Frontend (port 3000)                       │
│  Workspace │ MaterialLibrary │ PublishHistory │ Analytics    │
│  DouyinSync │ Settings                                        │
│  Zustand store ──── axios ──── /api/*                        │
└──────────────────────────┬───────────────────────────────────┘
                           │ HTTP
┌──────────────────────────▼───────────────────────────────────┐
│                   Backend (port 9000)                         │
│  FastAPI + CORS + WebSocket                                   │
│  /api/agent/run  /api/conversations  /api/materials          │
│  /api/publish    /api/analytics      /api/douyin             │
└──────────────────────────┬───────────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────────┐
│                     Agent Layer                               │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────────┐    │
│  │AnalysisLayer│→│DecisionLayer │→│LightweightSched  │    │
│  │ NLP + 意图  │  │ Skill 组合   │  │ 执行编排 + 循环  │    │
│  └─────────────┘  └──────────────┘  └──────────────────┘    │
│  ┌──────────────────────────────────────────────────────┐    │
│  │  IntelligentBlackbox  RAG 案例检索 + 路径推荐         │    │
│  └──────────────────────────────────────────────────────┘    │
└──────────────────────────┬───────────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────────┐
│                     Skill Layer                               │
│  Skill1: 标签推荐  │ Skill2: 图片推荐  │ Skill3: 配乐推荐    │
│  DeepSeek API →     │ Pexels → Unsplash  │ 抖音榜单 → 规则    │
│  关键词规则回退     │ → 本地模拟回退     │ 映射回退           │
│                     │                    │                    │
│  Skill4: 内容评估                                           │
│  5 维度评分(1-5) → 综合加权 → 发布预测                       │
└──────────────────────────┬───────────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────────┐
│                    Memory Layer                               │
│  ┌─────────────────────┐  ┌─────────────────────────────┐    │
│  │ 长期记忆 (memory.db) │  │ 短期记忆 (current_session)   │    │
│  │ • personal_material  │  │ • session_id                 │    │
│  │ • semantic_tags      │  │ • stage / text / tags        │    │
│  │ • music_library      │  │ • iteration / history        │    │
│  │ • publish_history    │  │ • preferences                │    │
│  │ • material_perform   │  └─────────────────────────────┘    │
│  │ • skill_execution    │                                     │
│  │ • rollback_history   │                                     │
│  │ • conversations      │                                     │
│  │ • conversation_history│                                    │
│  └─────────────────────┘                                     │
└──────────────────────────────────────────────────────────────┘
```

### 2.2 数据流

```
用户输入 "我想发浴室用品的图文"
  │
  ├─ 1. 语义理解 (AnalysisLayer)
  │     意图: topic │ 主题: 家居 │ 基调: 生活分享
  │
  ├─ 2. 决策推理 (DecisionLayer)
  │     缺文案 → 生成文案 │ 缺标签/图片/配乐 → 执行 Skill1-3
  │
  ├─ 3. 执行编排 (LightweightScheduler)
  │     文案生成 → Skill1 → Skill2 → Skill3 → Skill4
  │
  ├─ 4. 评估 (Skill4)
  │     score ≥ 4.0? ──是──→ 输出完整素材包 + 发布预测
  │     score < 4.0? ──否──→ 定位最低分维度 → 重新执行 → 最多 3 轮
  │
  └─ 5. 持久化 (MemoryManager)
        对话历史 + 素材记录 + 迭代历史 → memory.db
```

---

## 三、核心工作流

### 3.1 意图分类与路由

Agent 将用户输入分为 5 种意图，每种意图触发不同的处理流程：

| 意图 | 说明 | 触发条件（LLM 判断） | 处理流程 |
|------|------|---------------------|----------|
| `topic` | 用户给出主题/想法 | "帮我写一段关于..." | 生成文案 → Skill1→2→3→4 |
| `create` | 用户提供完整文案 | "夕阳把影子拉得很长" | Skill1→2→3→4 |
| `optimize` | 用户想整体改进 | "优化一下" | 重新生成文案 + Skill1→3→4 |
| `modify` | 用户指定修改目标 | "换个标签"、"配乐不合适" | 仅重跑指定 Skill → Skill4 |
| `question` | 用户提问/闲聊 | "为什么推荐这个？" | LLM 生成对话式回答 |

### 3.2 组件补全判断

| 组件 | 缺失判定 | 补全方式 |
|------|----------|----------|
| 文案 | `text` 为空或意图为 `topic` | DeepSeek 生成（30-100字） |
| 标签 | `tags` 为空 | Skill1 推荐 |
| 图片 | `images` 为空 | Skill2 搜索 + 下载 |
| 配乐 | `music` 为空 | Skill3 推荐 |
| 评估 | 任一组件更新 | Skill4 重评 |

### 3.3 用户旅行地图

```
第一轮：初次创作
  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
  │ 输入想法  │ → │ Agent 推荐│ → │ 查看结果  │ → │ 评分 4.2 │
  │          │    │ 全套素材  │    │ 素材包    │    │ ✅ 可发布 │
  └──────────┘    └──────────┘    └──────────┘    └──────────┘

第二轮：不满意标签
  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
  │ "换标签"  │ → │ 仅重跑   │ → │ 新标签    │ → │ 评分 4.5 │
  │          │    │ Skill1   │    │ 替换旧标签 │    │ ✅       │
  └──────────┘    └──────────┘    └──────────┘    └──────────┘

第三轮：换个主题
  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
  │ 新想法    │ → │ 新对话   │ → │ 全套新    │ → │ 独立对话  │
  │          │    │          │    │ 素材包    │    │ 历史保留  │
  └──────────┘    └──────────┘    └──────────┘    └──────────┘
```

---

## 四、Skill 规范

### 4.1 Skill 1：标签推荐

| 属性 | 值 |
|------|-----|
| **CLI 命令** | `python skills/hashtag_recommender.py "<文案>" [--json] [--count N] [--strategy S] [--no-api]` |
| **输入** | 中文文案（任意长度） |
| **输出** | `[{"tag": "#标签", "reason": "推荐理由"}, ...]` |
| **推荐策略** | `balanced`（默认）/ `aggressive` / `hot_only` / `super_only` / `potential_only` |
| **API 依赖** | DeepSeek Chat API（优先） |
| **回退** | 24 类关键词规则匹配 → 600+ 预定义标签词库 |
| **记忆集成** | 历史高表现标签加权排序 |

**评分逻辑**（被 Skill 4 引用）：
- 标签数量 3-8 个：+0.2 分
- 标签与文案关联度 > 60%：+0.3 分
- 包含抖音热点标签：每个 +0.15（最多 +0.5）

### 4.2 Skill 2：图片推荐

| 属性 | 值 |
|------|-----|
| **CLI 命令** | `python skills/image_recommender.py "<文案>" --count 4 [--no-api]` |
| **输入** | 中文文案 |
| **输出** | `[{"local_path", "original_url", "description", "record_tags", "source"}, ...]` |
| **搜索优先级** | ① Pexels 中文搜索 → ② DeepSeek 英文关键词 + Unsplash → ③ 本地模拟数据 |
| **下载路径** | `approved_images/img_<timestamp>_<seq>.jpg` |
| **API 依赖** | Pexels API + Unsplash API + DeepSeek（关键词翻译） |

### 4.3 Skill 3：配乐推荐

| 属性 | 值 |
|------|-----|
| **CLI 命令** | `python skills/music_recommender.py "<标签1,标签2>" "<文案>" [--json] [--no-api]` |
| **输入** | 标签列表 + 文案 |
| **输出** | `[{"name", "style", "mood", "reason"}, ...]` |
| **搜索优先级** | ① 抖音官方音乐榜单 API → ② GD Studio Music API → ③ TAG_TO_STYLE 规则映射 |
| **风格映射** | 27 类标签 → 3 种风格 → 150+ 预置配乐 |
| **API 依赖** | 抖音音乐榜单（需 token）|

### 4.4 Skill 4：内容评估

| 属性 | 值 |
|------|-----|
| **CLI 命令** | `python skills/content_evaluator.py "<文案>" "<标签>" [图片路径] [配乐名称] [--no-api]` |
| **输入** | 文案 + 标签 + (可选)图片路径 + (可选)配乐名称 |
| **输出** | `{"score": 4.2, "level": "较好", "report": "## Markdown报告", "suggestions": [...], "dimensions": {...}}` |

**评分维度与权重**：

| 维度 | 权重 | 评分要素 |
|------|:---:|------|
| 文案质量 | 30% | 长度(30-100字最佳)、问句/悬念(+0.3)、情绪词(+0.2)、无标签符号(-0.3) |
| 标签匹配 | 25% | 数量(3-8最佳,+0.2)、关联度(>60%,+0.3)、抖音热点(+0.15/个,上限+0.5) |
| 素材丰富度 | 20% | 图片数量(≥2,+0.3)、描述完整度、Unsplash来源(+0.2) |
| 音乐协调性 | 15% | 风格-情绪匹配(+0.3)、抖音热门(+0.4)、超千万使用(+0.2) |
| 结构完整性 | 10% | 四组件齐全(基础5分,缺×-1.0,缺配乐-1.5,缺图片-2.0) |

**评分等级映射**：

| 分数 | 等级 | 发布建议 |
|------|------|------|
| ≥ 4.5 | 很好 | ✅ 预计曝光 5000-20000 |
| ≥ 4.0 | 较好 | ✅ 预计曝光 2000-8000 |
| ≥ 3.5 | 中等偏上 | ⚠️ 预计曝光 1000-3000 |
| ≥ 3.0 | 中等 | ⚠️ 预计曝光 500-1500 |
| < 3.0 | 中等偏下 | ❌ 建议优化后再发布 |

**发布时段建议**：

| 内容类型 | 推荐时段 |
|----------|----------|
| 美食 | 11:00-13:00 / 17:00-19:00 |
| 萌宠/搞笑/日常 | 12:00-13:00 / 21:00-23:00 |
| 时尚/穿搭/美妆 | 10:00-12:00 / 20:00-22:00 |
| 励志/成长/职场 | 08:00-09:00 / 22:00-23:00 |
| 其他 | 12:00-13:00 / 18:00-20:00 |

---

## 五、智能循环机制

### 5.1 第一层：内部自动循环

```
┌──────────────────────────────────────────────────────┐
│                 DouyinAgent._auto_loop()               │
│                                                      │
│  第 1 轮: Skill1→2→3→4 → score = 3.2 ❌              │
│           ↓ _recommend_rollback()                     │
│           最低分维度: tag_match (2.5)                  │
│           ↓ _DIM_TO_SKILL["标签推荐"] = "Skill1"       │
│                                                      │
│  第 2 轮: Skill1(strategy=aggressive) → Skill4        │
│           → score = 3.8 ❌                             │
│           ↓ 最低分维度: image_richness (3.0)          │
│                                                      │
│  第 3 轮: Skill2(count=6) → Skill4                    │
│           → score = 4.1 ✅ 达标，输出结果              │
│                                                      │
│  终止条件: score ≥ 4.0 OR 循环次数 ≥ 3               │
└──────────────────────────────────────────────────────┘
```

**参数变化策略**：

| 循环轮次 | Skill1 策略 | Skill1 count | Skill2 count | Skill3 |
|:---:|------|:---:|:---:|------|
| 1 | balanced | 10 | 4 | 默认 |
| 2 | aggressive | 12 | 5 | 重新调用 |
| 3 | hot_only | 14 | 6 | 重新调用 |

### 5.2 第二层：用户指定重推理

评分 ≥ 4.0 后，用户可以针对不满意的部分触发定向重生成：

| 用户输入 | 重执行 | 不计入自动循环 |
|----------|:---:|:---:|
| "换标签" / "换一批标签" | Skill1 | ✅ |
| "换图片" / "换一批图" | Skill2 | ✅ |
| "换个配乐" / "换 BGM" | Skill3 | ✅ |
| "改写文案" / "换种风格" | 文案生成 + Skill1→4 | ✅ |
| "优化一下" | 全流程 | ✅ |

---

## 六、数据模型

### 6.1 数据库：memory.db（SQLite）

#### 6.1.1 personal_material_library（个人素材库）

| 列 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| material_type | TEXT | 'text' / 'image' / 'tag' |
| original_content | TEXT | 原始内容/路径 |
| created_at | DATETIME | 创建时间 |
| updated_at | DATETIME | 更新时间 |

索引：`idx_material_type ON (material_type)`

#### 6.1.2 semantic_tags（语义标签关联）

| 列 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| material_id | INTEGER FK | 关联素材 |
| tag | TEXT | 标签名 |
| confidence | REAL | 置信度 0-1 |

索引：`idx_semantic_tags_material ON (material_id)`

#### 6.1.3 publish_history（发布历史）

| 列 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| text_id | INTEGER FK | 文案素材 ID |
| image_ids | TEXT | 图片 ID 列表（逗号分隔）|
| music_id | INTEGER FK | 配乐 ID |
| publish_time | DATETIME | 发布时间 |
| real_likes | INTEGER | 真实点赞数 |
| real_comments | INTEGER | 真实评论数 |
| real_views | INTEGER | 真实浏览数 |
| engagement_rate | REAL | 互动率 |
| evaluation_score | REAL | Agent 评估分 |
| evaluation_level | TEXT | Agent 评估等级 |

索引：`idx_publish_history_time ON (publish_time)`, `idx_publish_history_score ON (evaluation_score)`

#### 6.1.4 conversations（对话会话）

| 列 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| conversation_id | TEXT UNIQUE | UUID 格式对话 ID |
| title | TEXT | 对话标题 |
| user_id | TEXT | 用户标识 |
| created_at | DATETIME | 创建时间 |
| updated_at | DATETIME | 更新时间 |
| is_active | BOOLEAN | 是否活跃 |

#### 6.1.5 conversation_history（对话消息）

| 列 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| conversation_id | TEXT | 关联对话 |
| role | TEXT | 'user' / 'assistant' |
| content | TEXT | 消息内容 |
| metadata | TEXT | JSON 元数据 |
| created_at | DATETIME | 消息时间 |

索引：`idx_conversation_history_conv_id ON (conversation_id)`, `idx_conversation_history_created ON (created_at)`

#### 6.1.6 其他表

| 表 | 用途 |
|------|------|
| `music_library` | 配乐库（名称、URL、标签、风格）|
| `material_performance` | 素材表现统计（使用次数、点赞/浏览/评论总计）|
| `skill_execution_log` | Skill 执行追踪（会话、Skill、状态、耗时）|
| `rollback_history` | 回滚操作历史 |

### 6.2 短期记忆

**文件**：`state/current_session.json`

```json
{
  "session_id": "20260623_131613",
  "stage": "标签推荐",
  "text": "用户文案",
  "tags": ["#标签1", "#标签2"],
  "images": [{"local_path": "...", "description": "..."}],
  "music": {"name": "曲名", "style": "风格"},
  "evaluation": {"score": 4.2, "level": "较好", ...},
  "iteration": 0,
  "iteration_history": [
    {"round": 1, "score": 4.2, "action": "初始执行"}
  ],
  "score_threshold": 4.0
}
```

---

## 七、API 参考

### 7.1 Agent 执行

#### `POST /api/agent/run`

执行完整 Agent 流水线。

**请求体**：
```json
{
  "text": "夕阳把影子拉得很长",
  "tags": [],
  "images": [],
  "music": [],
  "session_id": "optional",
  "conversation_id": "optional"
}
```

**响应**：
```json
{
  "creator_content": { "text": "...", "tags": [...], "images": [...], "music": [...] },
  "agent_suggestions": { "Skill1": [...], "Skill2": [...], "Skill3": [...] },
  "execution_log": [{ "skill": "标签推荐", "status": "completed" }],
  "evaluation": {
    "score": 4.2,
    "level": "较好",
    "report": "## 评估报告...",
    "suggestions": ["建议1", "建议2"],
    "showcase": { "text": "...", "tags": [...], "images": [...], "music": [...] }
  },
  "loop_history": [{ "round": 1, "score": 4.2, "action": "初始执行" }]
}
```

### 7.2 对话管理

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/conversations` | 创建对话 |
| GET | `/api/conversations` | 列出对话 |
| GET | `/api/conversations/{id}` | 获取对话详情 |
| DELETE | `/api/conversations/{id}` | 删除对话（级联删除消息）|
| POST | `/api/conversations/messages` | 添加消息 |
| GET | `/api/conversations/{id}/messages` | 获取对话历史 |
| GET | `/api/conversations/{id}/context` | 获取 Agent 上下文 |
| GET | `/api/conversations/{id}/stats` | 对话统计 |
| GET | `/api/conversations/search?keyword=` | 搜索对话 |

### 7.3 素材管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/materials?type=` | 获取素材列表 |
| POST | `/api/materials` | 添加素材 |
| PUT | `/api/materials/{id}` | 更新素材 |
| DELETE | `/api/materials/{id}` | 删除素材 |
| GET | `/api/materials/by-tags?tags=` | 按标签搜索 |
| GET | `/api/materials/top?type=&limit=` | 热门素材 |

### 7.4 发布与数据

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/publish/history` | 发布历史 |
| PUT | `/api/publish/{id}/data` | 更新发布数据 |
| GET | `/api/analytics/overview` | 分析概览 |
| GET | `/api/analytics/tags` | 标签表现 |
| POST | `/api/douyin/login` | 触发扫码登录 |
| GET | `/api/douyin/status` | 登录状态检查 |
| POST | `/api/douyin/sync` | 手动同步发布数据 |
| POST | `/api/douyin/sync-auto` | 自动拉取创作者数据 |

### 7.5 系统

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查（DeepSeek API 状态、DB 状态）|
| GET | `/api/session` | 获取当前会话 |
| POST | `/api/session/save` | 保存会话 |
| POST | `/api/session/reset` | 重置会话 |
| WS | `/ws/agent/{session_id}` | WebSocket 实时推送 |

---

## 八、前端页面指南

### 8.1 创作工作台（Workspace）

**路径**：`/`

**功能**：
- 对话式交互界面，输入文案/主题 → Agent 四步推荐
- 实时显示 ExecutionFlow 执行进度（标签→图片→配乐→评估）
- 对话列表管理（创建/切换/删除）
- 本地消息缓存（后端不可用时降级）
- 预填来自 PublishHistory 的"重新发布"数据

### 8.2 素材库（MaterialLibrary）

**路径**：`/materials`

**功能**：
- CRUD 管理文案/图片/配乐素材
- 按类型筛选（text/image/music）
- 语义标签关联

### 8.3 发布历史（PublishHistory）

**路径**：`/history`

**功能**：
- 时间线查看发布记录
- 互动率/点赞/浏览趋势图（Recharts）
- 删除/重新发布操作

### 8.4 数据分析（Analytics）

**路径**：`/analytics`

**功能**：
- 关键指标卡片（总发布、平均互动率、总点赞）
- 热门标签排行
- 最佳内容展示

### 8.5 抖音同步（DouyinSync）

**路径**：`/sync`

**功能**：
- 抖音创作者平台登录状态检查
- 手动/自动同步发布数据

### 8.6 设置（Settings）

**路径**：`/settings`

**功能**：
- Mock 模式开关
- API 连接测试（DeepSeek/Unsplash/Pexels）
- API 端点文档参考
- 清除所有本地数据

---

## 九、配置手册

### 9.1 环境变量（.env）

| 变量 | 必需 | 说明 |
|------|:---:|------|
| `ANTHROPIC_AUTH_TOKEN` | ✅ | DeepSeek API Key |
| `UNSPLASH_ACCESS_KEY` | 否 | Unsplash 图片搜索 |
| `PEXELS_API_KEY` | 否 | Pexels 图片搜索 |
| `DOUYIN_CLIENT_KEY` | 否 | 抖音开放平台 |
| `DOUYIN_CLIENT_SECRET` | 否 | 抖音开放平台密钥 |
| `PROXY_URL` | 否 | HTTP 代理（如 `http://127.0.0.1:7897`）|
| `HEADLESS` | 否 | Playwright 无头模式（`true`/`1`）|

### 9.2 Skill CLI 参数

| Skill | 参数 | 默认值 | 说明 |
|-------|------|:---:|------|
| Skill1 | `--count N` | 10 | 推荐标签数量（1-20）|
| Skill1 | `--strategy S` | balanced | 推荐策略 |
| Skill1 | `--no-api` | false | 禁用 DeepSeek API |
| Skill1 | `--json` | false | JSON 输出 |
| Skill2 | `--count N` | 4 | 推荐图片数量 |
| Skill2 | `--no-api` | false | 仅使用模拟数据 |
| Skill3 | `--no-api` | false | 仅使用规则映射 |
| Skill3 | `--json` | false | JSON 输出 |
| Skill4 | `--no-api` | false | 仅使用本地评分 |
| Skill4 | `--threshold N` | 4.0 | 评分门槛 |

### 9.3 启动命令

```bash
# 后端
python backend/server.py          # 端口 9000

# 前端开发
cd frontend && npm run dev        # 端口 5173

# CLI 模式（不启动服务）
python agent/douyin_agent.py --text "文案" --enable-blackbox
```

---

## 十、部署指南

### 10.1 开发环境

```bash
# 1. 克隆项目
git clone <repo>
cd douyin-agent

# 2. 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. 安装 Python 依赖
pip install -r requirements.txt

# 4. 安装 Playwright 浏览器
playwright install chromium

# 5. 配置环境变量
cp .env.example .env
# 编辑 .env，填入 DeepSeek API Key

# 6. 安装前端依赖
cd frontend && npm install

# 7. 启动后端
cd .. && python backend/server.py &

# 8. 启动前端
cd frontend && npm run dev
```

### 10.2 生产构建

```bash
# 构建前端
cd frontend && npm run build
# 产出 dist/ 目录，部署到任意静态文件服务

# 后端使用 uvicorn 多 worker
uvicorn backend.server:app --host 0.0.0.0 --port 9000 --workers 4
```

### 10.3 目录结构

```
douyin-agent/
├── agent/              # Agent 层（分析/决策/调度/循环）
├── skills/             # Skill 模块（标签/图片/配乐/评估/发布）
├── utils/              # 工具层（配置/记忆/关键词）
├── backend/            # FastAPI 后端
├── frontend/           # React 前端
│   ├── src/
│   │   ├── pages/      # 6 个页面
│   │   ├── components/ # 6 个组件
│   │   ├── services/   # API 客户端 + WebSocket
│   │   ├── stores/     # Zustand 状态管理
│   │   └── types/      # TypeScript 类型定义
│   └── dist/           # 生产构建产物
├── state/              # 会话状态
├── approved_images/    # 下载的推荐图片
├── docs/               # 文档
├── .env                # 环境变量（不提交）
├── .env.example        # 环境变量模板
├── CLAUDE.md           # Agent 行为规格说明
├── memory.db           # SQLite 数据库
└── requirements.txt    # Python 依赖
```

---

**文档版本**：1.0.0-alpha | **最后更新**：2026-06-23
