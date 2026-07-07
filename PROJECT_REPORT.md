# 抖音图文创作 Agent — 项目技术报告

> **项目类型**：业余独立开发项目  
> **开发周期**：2026 年 1 月 — 至今（持续迭代）  
> **代码仓库**：[github.com/b76182342-source/tuwen-agent](https://github.com/b76182342-source/tuwen-agent)  
> **当前版本**：v1.0.0  
> **报告日期**：2026 年 6 月 26 日  

---

## 目录

1. [项目概述](#一项目概述)
2. [系统架构设计](#二系统架构设计)
3. [核心模块详细设计](#三核心模块详细设计)
4. [数据库设计](#四数据库设计)
5. [前端设计](#五前端设计)
6. [浏览器扩展设计](#六浏览器扩展设计)
7. [API 接口设计](#七api-接口设计)
8. [安全设计](#八安全设计)
9. [部署与运行](#九部署与运行)
10. [项目统计](#十项目统计)
11. [总结与展望](#十一总结与展望)

---

## 一、项目概述

### 1.1 项目背景

抖音图文创作者在内容生产流程中面临三个核心痛点：

**(1) 创作决策成本高。** 写完文案后，创作者需要自行决定配什么标签、选什么图片、搭什么配乐。这些决策依赖经验，新手创作者往往无从下手。

**(2) 缺乏质量反馈。** 抖音平台不提供发布前的质量评估，创作者无法预判内容的传播效果，只能在发布后被动等待数据反馈。

**(3) "创作 → 评估 → 优化" 三个环节割裂。** 市面上有单独的文案工具、图片素材库、音乐推荐，但没有将它们串联为一个完整工作流的工具——创作者需要在多个平台之间反复切换。

### 1.2 项目定位

本项目定位为 **通用图文创作协助 Agent**：用户以自由文本（主题 / 草稿文案 / 图片 / 想法）输入，系统自动理解意图，推理缺失的创作组件，补全标签、图片、配乐三个维度的推荐，最终给出综合质量评分与发布预测。**系统不自动发布内容，发布操作由用户手动完成。**

### 1.3 核心功能

| 输入 | 处理 | 输出 |
|------|------|------|
| 用户自由文本（主题/草稿/想法） | 语义理解 → 意图分类 → 组件补全 → 质量评估 | 文案建议 + 标签推荐 + 图片推荐 + 配乐推荐 + 综合评分 + 发布预测 |

### 1.4 技术选型

| 层次 | 技术 | 选型理由 |
|------|------|----------|
| 大模型 | DeepSeek Chat API | 国产大模型，中文理解能力强，API 兼容 OpenAI 格式 |
| 后端 | Python + FastAPI | 异步高性能，自动生成 Swagger 文档，生态丰富 |
| 前端 | React + TypeScript + TailwindCSS | 组件化开发，类型安全，快速构建 UI |
| 数据库 | SQLite | 零配置，适合单机部署，满足当前数据量 |
| 缓存 | Redis | 高性能，支持多种数据结构，适合会话缓存和限流 |
| 向量数据库 | Qdrant | 开源，支持 COSINE 相似度，部署简单 |
| 向量化 | BGE (bge-small-zh-v1.5) | 中文 Embedding 效果优秀，模型体积小（~100MB） |
| 浏览器自动化 | Playwright | 跨浏览器支持，API 设计优秀 |
| 浏览器扩展 | Chrome Extension (Manifest V3) | 直接注入抖音页面，无缝数据提取 |

---

## 二、系统架构设计

### 2.1 总体架构

项目采用 **经典的前后端分离 + 分层 Agent 架构**，共分为 7 个层次：

```
┌──────────────────────────────────────────────────────────────┐
│                      接入层 (Access Layer)                     │
│  React Web 前端  │  FastAPI REST API  │  Chrome 浏览器扩展     │
├──────────────────────────────────────────────────────────────┤
│                      Agent 核心层 (Agent Core)                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │ AnalysisLayer│→│DecisionLayer │→│LightweightScheduler│   │
│  │   语义分析    │  │   Skill 决策  │  │    Skill 编排执行  │   │
│  └──────────────┘  └──────────────┘  └──────────────────┘   │
│                         ↑ 可选启用                              │
│                  ┌──────────────────┐                         │
│                  │IntelligentBlackbox│  RAG 智能路径推理       │
│                  └──────────────────┘                         │
├──────────────────────────────────────────────────────────────┤
│                     Skill 执行层 (Skills Layer)                 │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐   │
│  │ Skill 1  │ │ Skill 2  │ │ Skill 3  │ │   Skill 4    │   │
│  │ 标签推荐 │ │ 图片推荐 │ │ 配乐推荐 │ │  内容评估    │   │
│  │ Hashtag  │ │  Image   │ │  Music   │ │   Content    │   │
│  │Recommender│ │Recommender│ │Recommender│ │  Evaluator  │   │
│  └──────────┘ └──────────┘ └──────────┘ └──────────────┘   │
│                      [Skill 5 已禁用]                           │
├──────────────────────────────────────────────────────────────┤
│                     数据与记忆层 (Data Layer)                    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │ MemoryManager │  │ CacheManager │  │   VectorStore    │   │
│  │   SQLite      │  │    Redis     │  │     Qdrant       │   │
│  │  长期记忆     │  │  短期缓存    │  │  向量语义检索    │   │
│  └──────────────┘  └──────────────┘  └──────────────────┘   │
├──────────────────────────────────────────────────────────────┤
│                     基础设施层 (Infrastructure)                  │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐   │
│  │  Config  │ │Embeddings│ │  Cache   │ │  Web Tools   │   │
│  │ 配置管理 │ │ 向量化   │ │ Redis    │ │  预留接口    │   │
│  └──────────┘ └──────────┘ └──────────┘ └──────────────┘   │
└──────────────────────────────────────────────────────────────┘
```

### 2.2 Agent 核心流程

Agent 的执行流程遵循 **分析 → 决策 → 执行 → 评估 → 循环** 五阶段：

```
用户输入
    │
    ▼
┌──────────────┐
│  语义分析     │  AnalysisLayer: NLP 特征提取、情感分析、主题检测、数据搜集
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  组件决策     │  DecisionLayer: 判断需要补全哪些组件（标签/图片/配乐）
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  Skill 执行   │  LightweightScheduler: 按计划执行 Skill1→2→3→4
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  质量评估     │  Skill4: 5 维度加权评分 (1.0~5.0)
└──────┬───────┘
       │
       ▼
   score ≥ 4.0 ?
   /          \
  是           否
  │            │
  ▼            ▼
输出结果    ┌──────────────┐
           │ 定位最低分维度 │
           │ 重试对应 Skill │  ← 最多循环 3 轮
           │ 重新评估      │
           └──────────────┘
```

### 2.3 质量闭环机制

质量闭环是本项目的核心创新点之一，设计原则：

- **精准回滚**：评分 < 4.0 时自动定位最低分维度（标签匹配 / 素材丰富度 / 音乐协调性），**仅重试对应的 Skill 而非全流程重跑**，保留用户已确认的内容
- **循环上限**：最多 3 轮自动优化，超过 3 轮仍未达标则输出当前最优结果并提示用户手动干预
- **用户驱动重试**：评分达标后，用户仍可针对特定组件发起重试（"换标签"、"换个配乐"），此类重试不计入自动循环次数

---

## 三、核心模块详细设计

### 3.1 Agent 核心层

#### 3.1.1 AnalysisLayer（分析层）

**文件**：[agent/analysis_layer.py](agent/analysis_layer.py) — 253 行  
**职责**：对用户输入进行自然语言处理分析，输出结构化的 NLP 特征。

**核心方法**：

| 方法 | 功能 | 实现方式 |
|------|------|----------|
| `_nlp_analysis()` | 提取关键词、判断情感、检测主题/基调 | 正则匹配 + 配置规则库 |
| `_tag_similarity_analysis()` | 计算文案-标签、标签-标签、标签-热点三维相似度 | 关键词匹配 + 热点标签对比 |
| `_collect_relevant_data()` | 搜集热点话题、热门音乐、历史成功案例 | 调用抖音公开 API + 记忆层检索 |

**输入**：`{"text": str, "tags": List[str], "images": List[dict], "music": List[dict]}`  
**输出**：`{"nlp_features": {...}, "tag_similarity": {...}, "collected_data": {...}}`

**配置驱动**：情感词典、主题关键词、基调模式、情绪词库均从 [config/analysis_rules.json](config/analysis_rules.json) 加载，支持无代码修改分析规则。

#### 3.1.2 DecisionLayer（决策层）

**文件**：[agent/decision_layer.py](agent/decision_layer.py) — 216 行  
**职责**：基于分析结果推断需要执行哪些 Skill。

**决策规则**：

| Skill | 触发条件 |
|-------|----------|
| Skill1 标签推荐 | 用户未提供标签 / 标签与文案相似度 < 50% / 标签非热点 |
| Skill2 图片推荐 | 用户未提供图片 / 图片数量 < 2 张 |
| Skill3 配乐推荐 | 用户未提供配乐 / 配乐风格与文案基调不匹配 |
| Skill4 内容评估 | **始终执行**（质量把关必要环节） |

**置信度计算**：基于相似历史成功案例数量 — ≥10 个案例 → 90%，≥5 → 70%，≥3 → 50%，<3 → 30%。

#### 3.1.3 LightweightScheduler（调度器）

**文件**：[agent/lightweight_scheduler.py](agent/lightweight_scheduler.py) — 185 行  
**职责**：根据决策层的 Skill 组合计划，按序执行各 Skill，管理执行状态。

**核心能力**：

- **计划执行** (`execute_plan`)：顺序执行 Skill 列表，区分"创作者内容"（用户原始输入）和"Agent 建议"（系统推荐）
- **单 Skill 重试** (`execute_single_skill`)：支持自动循环中的精准重试，每次重试改变策略参数（标签推荐轮换 balanced / aggressive / hot_only / super_only 四种策略，图片推荐每轮多要一张，标签数量每轮 +2）
- **并行优化**（后端 server.py 中）：Skill1 + Skill2 并行启动，Skill1 完成后 Skill3 立即启动与 Skill2 并行，总耗时从串行 ~20s 降至 ~8s

#### 3.1.4 IntelligentBlackbox（智能黑箱）

**文件**：[agent/intelligent_blackbox.py](agent/intelligent_blackbox.py) — 160 行  
**职责**：基于 RAG（检索增强生成）自动推理最优执行路径。

**RAG 流程**：

```
用户文案 → 检索相似历史成功案例 → 提取成功模式（高频标签/配乐风格）
         → 增强生成上下文 → 推荐最优执行路径
```

**触发条件**：用户可选启用（默认关闭），评分 < 4.0 时自动激活。

### 3.2 Skill 执行层

#### 3.2.1 Skill 1：标签推荐

**文件**：[skills/hashtag_recommender.py](skills/hashtag_recommender.py) — 424 行  
**类**：`HashtagRecommender`

**推荐流程**（三层降级）：

```
① DeepSeek API 语义理解 → 返回带推荐理由的标签 JSON
    ↓ (API 不可用)
② Qdrant 向量语义检索 → 基于文案 Embedding 搜索最匹配标签
    ↓ (Qdrant 不可用)
③ 关键词匹配 + 硬编码标签库 → 从 tag_rules.json 加载分类标签
```

**策略模式**：支持 5 种推荐策略：

| 策略 | 行为 |
|------|------|
| `balanced` | 超级热门 + 热门 + 潜力标签按比例混合 |
| `super_only` | 仅超级热门标签 |
| `hot_only` | 仅热门标签 |
| `potential_only` | 仅潜力标签 |
| `aggressive` | 激进策略，超级热门标签权重翻倍 |

**记忆加权**：优先推荐历史表现好的标签（综合平均点赞数和上次效果评级），历史表现"优秀"的标签权重 ×1.5，"良好"的权重 ×1.2。

**缓存**：Redis 缓存 DeepSeek 响应（TTL 24h），相同文案复用。

#### 3.2.2 Skill 2：图片推荐

**文件**：[skills/image_recommender.py](skills/image_recommender.py) — 542 行  
**函数**：`recommend_images()`

**数据源优先级**：

```
① Qdrant 向量语义图片搜索（零成本）
② Pexels API 中文搜索（支持中文，命中率高）
③ DeepSeek 生成英文搜索词 → Unsplash API 英文搜索
④ 本地模拟数据（兜底）
```

**SSRF 防护**：下载前验证 URL 域名白名单（pexels.com / images.pexels.com / unsplash.com / images.unsplash.com / picsum.photos / i.picsum.photos）。

**图片管理**：下载到 `approved_images/` 目录，自动去重，记录到记忆层。

#### 3.2.3 Skill 3：配乐推荐

**文件**：[skills/music_recommender.py](skills/music_recommender.py) — 805 行  
**函数**：`recommend_music()`

**数据源优先级**：

```
① 抖音官方音乐榜单 API（OAuth 2.0 Client Credentials 认证）
    ├── 热歌榜 (hot)
    ├── 飙升榜 (rising)
    └── 原创榜 (original)
② GD Studio Music API 真实歌曲搜索（含可播放 URL）
③ 本地规则映射（TAG_TO_STYLE → STYLE_TO_MUSIC 华语经典曲库）
```

**抖音榜单匹配流程**：

```
获取 access_token → 拉取榜单（去重）→ DeepSeek 从榜单中匹配最合适歌曲
```

包含 **19 大类标签→风格映射** 和 **8 种情绪→风格映射**，以及 **17 类风格→具体歌曲** 的硬编码回退曲库。

#### 3.2.4 Skill 4：内容评估

**文件**：[skills/content_evaluator.py](skills/content_evaluator.py) — 921 行  
**函数**：`evaluate()`

**5 维度加权评分体系**：

| 维度 | 权重 | 评分标准 |
|------|------|----------|
| 文案质量 (text_quality) | 30% | 长度适中（30-100 字最佳）、是否有问句/悬念/情绪词、无标签符号嵌入 |
| 标签匹配 (tag_match) | 25% | 标签与文案语义关联度、数量（3-8 个最佳）、是否含抖音热点标签 |
| 素材丰富度 (image_richness) | 20% | 图片数量（≥2 张加分）、描述完整度、来源质量（Unsplash 加分） |
| 音乐协调性 (music_harmony) | 15% | 配乐风格与内容情绪匹配度、是否使用热门音乐 |
| 结构完整性 (completeness) | 10% | 是否具备文案+图片+标签+配乐全套组件 |

**评估流程**：`DeepSeek API 综合评估（优先）→ 本地规则评分（回退）`

**输出**：综合评分（1.0~5.0）+ 8 级评级（很差→很好）+ Markdown 评估报告 + 优化建议 + 发布预测（曝光范围 + 建议时段）。

**热点感知**：通过抖音公开 Web API 获取实时热点话题和热门音乐（5 分钟内存缓存），评估时检查标签和配乐是否命中当前热点，命中后加分。

### 3.3 数据与记忆层

#### 3.3.1 MemoryManager（长期记忆）

**文件**：[utils/memory.py](utils/memory.py) — 672 行  
**类**：`MemoryManager`

基于 SQLite 的长期持久化存储，管理 6 张核心数据表（详见第四章数据库设计）。关键特性：

- **线程安全**：使用 `threading.Lock()` 保护所有写操作
- **连接管理**：`contextlib.contextmanager` 自动管理连接生命周期
- **会话管理**：完整 CRUD + 搜索 + 统计
- **数据同步**：批量导入抖音数据导出，自动去重
- **数据分析**：播放量/点赞/评论/分享/粉丝等多维度聚合统计

#### 3.3.2 CacheManager（短期缓存）

**文件**：[utils/cache.py](utils/cache.py) — 252 行  
**类**：`CacheManager`（单例模式）

基于 Redis 的短期热数据缓存，TTL 策略：

| 数据类型 | TTL | 说明 |
|----------|-----|------|
| 会话状态 (session:*) | 7 天 | 当前对话上下文 |
| LLM 响应缓存 (llm:cache:*) | 24 小时 | DeepSeek API 返回结果 |
| 限流计数器 (ratelimit:*) | 24 小时 | API 调用频率控制 |
| 每日统计 (stats:daily:*) | 30 天 | 使用量实时统计 |
| 创作草稿 (draft:*) | 24 小时 | 用户暂存内容 |

**降级策略**：Redis 不可用时所有缓存方法自动返回空/跳过，不影响主流程。

#### 3.3.3 VectorStore（向量数据库）

**文件**：[utils/vector_store.py](utils/vector_store.py) — 334 行  
**类**：`VectorStore`（单例模式）

基于 Qdrant 的向量语义检索，4 个 Collection：

| Collection | 用途 | 向量来源 |
|------------|------|----------|
| `public_tags` | 公共标签库语义搜索 | 标签名 Embedding |
| `public_texts` | 相似文案搜索 + 质量参考 | 文案内容 Embedding |
| `public_images` | 图文匹配搜索 | 图片描述 Embedding |
| `topic_trends` | 话题趋势检测 | 话题名 Embedding |

**向量化**：使用 BAAI/bge-small-zh-v1.5 模型（512 维），支持本地离线加载和 HuggingFace 镜像站加速下载。

---

## 四、数据库设计

### 4.1 ER 模型

```
┌──────────────┐       ┌──────────────────┐
│ conversations│       │ conversation_msg │
│──────────────│       │──────────────────│
│ id (PK)      │──┐    │ id (PK)          │
│ title        │  │    │ conv_id (FK) ────│──┐
│ user_id      │  │    │ role             │  │
│ created_at   │  └───>│ content          │  │
│ updated_at   │       │ metadata (JSON)  │  │
└──────────────┘       │ created_at       │  │
                       └──────────────────┘  │
                                             │
┌──────────────┐                            │
│ content_posts│                            │
│──────────────│                            │
│ id (PK)      │                            │
│ text         │                            │
│ publish_time │                            │
│ views        │                            │
│ likes        │       ┌──────────────┐     │
│ comments     │       │    tags      │     │
│ shares       │       │──────────────│     │
│ favorites    │       │ id (PK)      │     │
│ swipe_away   │       │ name (UNIQUE)│     │
│ copy_expand  │       │ usage_count  │     │
│ fan_gain     │       │ total_likes  │     │
│ fan_loss     │       │ total_views  │     │
│ eval_score   │       │ created_at   │     │
│ eval_level   │       └──────────────┘     │
│ tags_json    │                            │
│ images_json  │       ┌──────────────┐     │
│ music_json   │       │traffic_daily │     │
│ source       │       │──────────────│     │
│ created_at   │       │ id (PK)      │     │
│ updated_at   │       │ content_id───│─────┘
└──────────────┘       │ date         │
        │              │ views        │
        │              │ source       │
        │              └──────────────┘
        │
        │              ┌───────────────┐
        │              │follower_daily │
        └──────────────│───────────────│
                       │ id (PK)       │
                       │ content_id ───│
                       │ date          │
                       │ fan_gain      │
                       │ fan_loss      │
                       │ source        │
                       └───────────────┘
```

### 4.2 表详细设计

#### content_posts（核心发布表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| text | TEXT NOT NULL | 发布文案 |
| publish_time | TEXT | 发布时间 |
| views | INTEGER | 播放/浏览量 |
| likes | INTEGER | 点赞数 |
| comments | INTEGER | 评论数 |
| shares | INTEGER | 分享数 |
| favorites | INTEGER | 收藏数 |
| swipe_away_rate | REAL | 划走率 |
| copy_expand_rate | REAL | 文案展开率 |
| avg_images_viewed | REAL | 平均图片查看数 |
| fan_gain | INTEGER | 涨粉数 |
| fan_loss | INTEGER | 脱粉数 |
| fan_play_ratio | REAL | 粉丝播放占比 |
| source | TEXT | 来源（manual/extension/agent） |
| evaluation_score | REAL | Agent 评估分 |
| evaluation_level | TEXT | 评估等级 |
| tags_json | TEXT | 标签 JSON |
| images_json | TEXT | 图片 JSON |
| music_json | TEXT | 配乐 JSON |

#### conversations（对话会话表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | TEXT PK | 会话 ID（secrets.token_urlsafe 生成） |
| title | TEXT | 会话标题 |
| user_id | TEXT | 用户标识 |
| created_at | TEXT | 创建时间 |
| updated_at | TEXT | 更新时间 |

#### conversation_messages（对话消息表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| conv_id | TEXT FK | 关联会话 ID |
| role | TEXT | 角色（user/assistant） |
| content | TEXT | 消息内容 |
| metadata | TEXT | 附加数据 JSON |
| created_at | TEXT | 创建时间 |

#### tags（标签效果统计表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| name | TEXT UNIQUE | 标签名 |
| usage_count | INTEGER | 使用次数 |
| total_likes | INTEGER | 累计点赞 |
| total_views | INTEGER | 累计播放 |
| created_at | TEXT | 创建时间 |

#### traffic_daily（流量日趋势表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| content_id | INTEGER FK | 关联内容 ID |
| date | TEXT | 日期 |
| views | INTEGER | 日播放量 |
| source | TEXT | 来源平台 |
| UNIQUE | (content_id, date, source) | 联合唯一约束 |

#### follower_daily（粉丝日趋势表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| content_id | INTEGER FK | 关联内容 ID |
| date | TEXT | 日期 |
| fan_gain | INTEGER | 日涨粉 |
| fan_loss | INTEGER | 日脱粉 |
| source | TEXT | 来源平台 |
| UNIQUE | (content_id, date, source) | 联合唯一约束 |

---

## 五、前端设计

### 5.1 技术栈

| 层面 | 技术 |
|------|------|
| 框架 | React 18 + TypeScript |
| 构建工具 | Vite |
| 样式 | TailwindCSS |
| 状态管理 | Zustand (appStore.ts) |
| 实时通信 | WebSocket |
| 路由 | React Router |

### 5.2 页面结构

| 页面 | 文件 | 行数 | 功能 |
|------|------|------|------|
| **Workspace** | [Workspace.tsx](frontend/src/pages/Workspace.tsx) | 390 | 主导工作区：对话列表 + 创作输入 + 结果展示 |
| **Analytics** | [Analytics.tsx](frontend/src/pages/Analytics.tsx) | 245 | 数据分析看板：播放/点赞/粉丝趋势 |
| **MaterialLibrary** | [MaterialLibrary.tsx](frontend/src/pages/MaterialLibrary.tsx) | 464 | 素材库管理：图片/音乐素材浏览与管理 |
| **PublishHistory** | [PublishHistory.tsx](frontend/src/pages/PublishHistory.tsx) | 161 | 发布历史列表 |
| **DouyinSync** | [DouyinSync.tsx](frontend/src/pages/DouyinSync.tsx) | 387 | 抖音数据同步：手动录入 / 批量导入 |
| **Settings** | [Settings.tsx](frontend/src/pages/Settings.tsx) | 194 | 系统设置 |

### 5.3 核心组件

| 组件 | 文件 | 行数 | 功能 |
|------|------|------|------|
| **AppLayout** | [AppLayout.tsx](frontend/src/components/AppLayout.tsx) | 107 | 全局布局：侧边栏 + 内容区 |
| **ChatMessage** | [ChatMessage.tsx](frontend/src/components/ChatMessage.tsx) | 266 | 聊天消息气泡：Markdown 渲染 + 素材展示 |
| **ResultDisplay** | [ResultDisplay.tsx](frontend/src/components/ResultDisplay.tsx) | 175 | 结果展示卡片：评分 + 标签 + 图片 + 配乐 |
| **ExecutionFlow** | [ExecutionFlow.tsx](frontend/src/components/ExecutionFlow.tsx) | 74 | Skill 执行流程可视化：步骤进度 + 状态 |
| **BlackboxRecommendation** | [BlackboxRecommendation.tsx](frontend/src/components/BlackboxRecommendation.tsx) | 59 | 智能黑箱推荐面板 |

### 5.4 实时通信

前端通过 WebSocket 与后端建立持久连接，实现 Skill 执行进度的实时推送。API 服务层（[api.ts](frontend/src/services/api.ts)，393 行）封装了全部 30+ 接口的 TypeScript 调用函数，提供类型安全的请求/响应处理。

---

## 六、浏览器扩展设计

### 6.1 概述

Chrome 浏览器扩展（Manifest V3），注入抖音创作者中心页面，实现发布数据的一键提取与回传，形成"线下创作 → 线上发布 → 数据回收"的闭环。

### 6.2 文件结构

| 文件 | 行数 | 职责 |
|------|------|------|
| [manifest.json](browser-extension/manifest.json) | 49 | 扩展配置：权限、内容脚本、Service Worker |
| [background.js](browser-extension/background.js) | 348 | Service Worker：消息路由、数据导入、通知 |
| [content.js](browser-extension/content.js) | 540 | 内容脚本：DOM 数据提取 + 导入按钮注入 |
| [config.js](browser-extension/config.js) | 42 | 配置管理：后端地址持久化存储 |
| [popup.html](browser-extension/popup.html) | — | 弹窗界面 |
| [popup.js](browser-extension/popup.js) | 331 | 弹窗逻辑：设置管理、手动录入 |
| [content.css](browser-extension/content.css) | — | 注入样式 |

### 6.3 数据提取策略

内容脚本采用 **DOM-agnostic 多策略回退** 设计，不依赖特定 CSS 类名：

```
策略 ①：标准 HTML 表格提取          → 解析 <table> 元素，自动映射列名
    ↓ (无表格)
策略 ②：统计数字卡片提取            → 扫描包含 ≥3 个数字的容器元素
    ↓ (无卡片)
策略 ③：列表项提取                  → 解析 <ul>/<ol>/[role="list"] 元素
    ↓ (无列表)
策略 ④：全局变量扫描                → 搜索 window 下包含 text/views/likes 的 JS 对象
```

**数字解析能力**：支持中文单位（1.2 万 → 12000、1.5 亿 → 150000000）、英文后缀（k/w）。

---

## 七、API 接口设计

### 7.1 接口概览

基于 FastAPI 的 RESTful API，共 30+ 个端点，自动生成 Swagger 文档。

| 分类 | 端点 | 方法 | 说明 |
|------|------|------|------|
| **会话** | `/api/session` | GET | 获取当前会话 |
| | `/api/session/save` | POST | 保存会话状态 |
| | `/api/session/reset` | POST | 重置会话 |
| **对话** | `/api/conversations` | GET/POST | 列出/创建对话 |
| | `/api/conversations/{id}` | GET/PUT/DELETE | 获取/更新/删除对话 |
| | `/api/conversations/{id}/messages` | GET | 获取对话历史 |
| | `/api/conversations/{id}/context` | GET | 获取 Agent 上下文 |
| | `/api/conversations/search` | GET | 搜索对话 |
| **Agent** | `/api/agent/run` | POST | 执行 Agent 全流程 |
| **素材** | `/api/materials` | GET/POST | 获取/添加素材 |
| | `/api/materials/{id}` | PUT/DELETE | 更新/删除素材 |
| **数据** | `/api/publish/history` | GET | 发布历史 |
| | `/api/publish/{id}/data` | PUT | 更新发布数据 |
| | `/api/analytics/overview` | GET | 分析概览 |
| | `/api/analytics/traffic-trend` | GET | 流量趋势 |
| | `/api/analytics/follower-trend` | GET | 粉丝趋势 |
| **同步** | `/api/douyin/sync` | POST | 批量同步抖音数据 |
| | `/api/douyin/status` | GET | 抖音登录状态 |
| **其他** | `/api/upload` | POST | 图片上传 |
| | `/api/health` | GET | 健康检查 |

### 7.2 安全措施

- **认证**：API Key 中间件，支持 Bearer Token 和 X-API-Key 两种方式
- **校验**：Pydantic 模型验证所有请求体
- **CORS**：环境变量白名单
- **错误处理**：通用错误响应，不暴露内部堆栈

---

## 八、安全设计

### 8.1 安全审计

项目已完成全面的白盒安全审计（46 个源文件，~5600 行代码），基于 OWASP Top 10 + CWE Top 25 标准，共发现 21 个安全问题，已全部修复。详见 [SECURITY_AUDIT_REPORT.md](SECURITY_AUDIT_REPORT.md)。

### 8.2 已实施的安全措施

| 措施 | 实现位置 | 说明 |
|------|----------|------|
| SSRF 防护 | [utils/config.py](utils/config.py) | `is_safe_url()` + `ALLOWED_IMAGE_DOMAINS` 白名单 |
| 参数化查询 | 全部 SQL | 100% 使用 `?` 占位符，零 SQL 注入风险 |
| API 认证 | [backend/server.py](backend/server.py) | API Key 中间件（Bearer / X-API-Key） |
| 文件上传校验 | [backend/server.py](backend/server.py) | 扩展名白名单（6 种图片格式） |
| 命令注入防护 | [run_backend.py](run_backend.py) | 移除所有 `shell=True`，改用列表传参 |
| CORS 白名单 | [backend/server.py](backend/server.py) | 环境变量动态配置 |
| 敏感文件排除 | [.gitignore](.gitignore) | `.env`/`*.db`/`douyin_state.json`/图片目录 |
| 凭据管理 | [utils/config.py](utils/config.py) | 环境变量统一管理，零硬编码 |
| 安全会话 ID | [utils/memory.py](utils/memory.py) | `secrets.token_urlsafe()` 替代时间戳 |

---

## 九、部署与运行

### 9.1 环境要求

| 组件 | 要求 |
|------|------|
| Python | ≥ 3.10 |
| Node.js | ≥ 18 |
| Redis | 可选（用于缓存和限流） |
| Qdrant | 可选（用于向量语义检索） |

### 9.2 快速启动

```bash
# 1. 克隆项目
git clone https://github.com/b76182342-source/tuwen-agent.git
cd tuwen-agent

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env，填入 DeepSeek API Key

# 3. 安装 Python 依赖
pip install -r requirements.txt

# 4. 启动后端（端口 9000）
python run_backend.py

# 5. 启动前端（另一个终端，端口 5173）
cd frontend
npm install
npm run dev
```

### 9.3 项目路径结构

```
douyin-agent/
├── agent/                  # Agent 核心层
│   ├── douyin_agent.py     # Agent 主入口
│   ├── analysis_layer.py   # NLP 分析层
│   ├── decision_layer.py   # Skill 决策层
│   ├── lightweight_scheduler.py  # Skill 调度器
│   └── intelligent_blackbox.py   # RAG 智能黑箱
├── skills/                 # Skill 执行层
│   ├── hashtag_recommender.py  # Skill 1: 标签推荐
│   ├── image_recommender.py    # Skill 2: 图片推荐
│   ├── music_recommender.py    # Skill 3: 配乐推荐
│   ├── content_evaluator.py    # Skill 4: 内容评估
│   └── douyin_publisher.py     # [已禁用] Skill 5: 图文发布
├── backend/
│   └── server.py           # FastAPI 后端服务器
├── frontend/
│   └── src/
│       ├── components/     # React 组件 (5 个)
│       ├── pages/          # 页面 (6 个)
│       └── services/       # API + WebSocket 服务
├── browser-extension/      # Chrome 扩展
├── utils/
│   ├── config.py           # 配置管理 + DeepSeek API Helper
│   ├── memory.py           # SQLite 记忆层
│   ├── cache.py            # Redis 缓存层
│   ├── embeddings.py       # 文本向量化
│   └── vector_store.py     # Qdrant 向量数据库
├── config/
│   ├── tag_rules.json      # 标签规则配置
│   └── analysis_rules.json # NLP 分析规则
├── .env.example            # 环境变量模板
├── run_backend.py          # 后端启动脚本
└── requirements.txt        # Python 依赖
```

---

## 十、项目统计

### 10.1 代码量统计

| 语言 | 文件数 | 代码行数 | 占比 |
|------|--------|----------|------|
| Python | 19 | ~7,400 | 51% |
| TypeScript/TSX | 18 | ~3,800 | 26% |
| JavaScript | 4 | ~1,260 | 9% |
| Markdown | 15 | ~3,600 | — |
| JSON/YAML/TOML | 10 | ~475 | 3% |
| CSS/HTML | 3 | ~200 | 1% |
| **合计** | **91** | **~14,900** | **100%** |

> 注：代码行数仅统计项目源代码（不含 .venv、node_modules、package-lock.json 等三方文件）。含已禁用的 douyin_publisher.py（1,223 行），实际活跃代码约 13,500 行。

### 10.2 已知问题与待清理代码

| 类型 | 文件/位置 | 行数 | 说明 |
|------|-----------|------|------|
| 🔴 废弃模块 | `utils/web_tools.py` | 3 | 仅含 docstring 占位符，从未被任何模块导入 |
| 🔴 未使用函数 | `run_backend.py::wait_for_server()` | ~15 | 定义了但从未调用（服务由 uvicorn.run 直接启动） |
| 🟡 预留接口 | `image_recommender.py::search_tuchong()` | ~10 | 图虫创意 API 预留，未接入 |
| 🟡 未使用 | `utils/config.py::get_state_dir()` | 2 | 定义了但其他模块自行计算路径 |
| 🟡 未使用 | `utils/config.py::get_db_path()` | 2 | 同上 |
| 🟡 未使用 | `frontend/src/services/websocket.ts` | 81 | WebSocket 服务类完整实现但未在任何组件中导入 |
| 🟡 未使用 | `frontend/src/utils/animations.ts` | 90 | 11 个 Framer Motion 动画变体导出但未被引用 |
| ⚫ 已禁用 | `skills/douyin_publisher.py` | 1,223 | Skill 5 永久禁用，保留仅作技术参考 |
| ⚫ 已禁用 | `server.py::douyin_login()` | ~10 | 返回硬编码"已禁用"消息 |
| ⚫ 已禁用 | `server.py::douyin_sync_auto()` | ~5 | 同上 |

> 合计约 1,440 行可清理代码（含已禁用的发布模块），实际活跃代码约 13,500 行。

### 10.3 功能覆盖

| 维度 | 已完成 | 说明 |
|------|--------|------|
| Agent 核心调度 | ✅ | 分析→决策→执行→评估→循环，5 阶段完整闭环 |
| 标签推荐 | ✅ | API + 向量 + 规则三层降级，5 种策略，记忆加权 |
| 图片推荐 | ✅ | Pexels + Unsplash + Qdrant + 模拟数据四源，SSRF 防护 |
| 配乐推荐 | ✅ | 抖音榜单 + GD API + 规则三层，含可播放 URL |
| 内容评估 | ✅ | 5 维加权评分，热点感知，Markdown 报告 |
| 记忆层 | ✅ | SQLite 长期 + Redis 短期，数据飞轮 |
| 向量检索 | ✅ | Qdrant 4 个 Collection，BGE Embedding |
| Web 前端 | ✅ | React + TS，6 页面 + 5 组件，WebSocket 实时推送 |
| 浏览器扩展 | ✅ | Chrome MV3，多策略数据提取 |
| REST API | ✅ | FastAPI，30+ 端点，Swagger 文档 |
| 安全审计 | ✅ | 21 项发现已全部修复 |
| 自动发布 | ❌ | 永久禁用（合规原因） |

### 10.4 Git 状态

| 指标 | 数值 |
|------|------|
| 分支 | master |
| 提交数 | 1 |
| 已跟踪文件 | 83 |
| 远程仓库 | github.com/b76182342-source/tuwen-agent |
| .gitignore 规则数 | 28 |

---

## 十一、总结与展望

### 11.1 项目成果

本项目从零构建了一个覆盖"分析→决策→执行→评估→优化"全流程的 AI Agent 系统，实现了以下核心能力：

1. **模块化 Agent 架构**：4 个解耦 Skill + 统一调度器 + 质量闭环，可独立测试与替换
2. **三层容错体系**：API 优先 → 向量检索 → 本地规则，确保系统在任何外部服务异常时正常运行
3. **数据飞轮**：发布后真实数据回写 → 推荐权重动态调整 → 越用越精准
4. **完整工程化**：后端 API + 前端界面 + 浏览器扩展 + 安全审计，具备生产级部署标准

### 11.2 技术亮点

- **工作流编排**：ThreadPoolExecutor 实现 Skill 并行 + 流水线，耗时降低 60%
- **安全实践**：21 项漏洞的发现→修复全流程，代码零硬编码凭据
- **多层降级**：6 个外部 API 的容错编排，任何单点故障不影响整体
- **DOM-agnostic 扩展**：4 种回退策略的数据提取，不依赖特定网页结构

### 11.3 未来方向

| 方向 | 说明 |
|------|------|
| 多模型支持 | 接入更多 LLM（通义千问、文心一言等），支持模型切换与 A/B 对比 |
| 效果归因 | 发布后自动关联推荐参数与实际数据，量化每个维度的贡献 |
| 竞品分析 | 抓取同类爆款内容，提取共性标签/配乐/发布时间模式 |
| 多平台 | 扩展到小红书、快手等内容平台 |
| Docker 化 | 一键部署，降低环境配置门槛 |

---

> **项目地址**：[https://github.com/b76182342-source/tuwen-agent](https://github.com/b76182342-source/tuwen-agent)  
> **报告版本**：v1.0 · 2026-06-26
