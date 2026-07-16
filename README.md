# 抖音图文创作 Agent 

> **项目类型**：业余独立开发项目  
> **开发周期**：2026 年 1 月 — 至今（持续迭代）  
> **代码仓库**：[github.com/b76182342-source/tuwen-agent](https://github.com/b76182342-source/tuwen-agent)  
> **当前版本**：v2.0.0（LangGraph 架构重构）  
> **报告日期**：2026 年 7 月 10 日  

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

v2.0 核心升级：从传统的类方法调用架构重构为 **LangGraph 状态机 + ReAct Agent 对话** 双模式，支持确定性 Workflow 管线与 LLM 自主推理的自由对话两种交互方式。

### 1.3 核心功能

| 输入 | 处理 | 输出 |
|------|------|------|
| 用户自由文本（主题/草稿/想法） | 语义理解 → 意图分类 → 组件补全 → 质量评估 | 文案建议 + 标签推荐 + 图片推荐 + 配乐推荐 + 综合评分 + 发布预测 |
| 用户的创作问题 / 闲聊 | ReAct Agent 自由对话 | 专业建议 + 按需调用工具（评估/情绪分析/推荐） |

### 1.4 交互模式

| 模式 | 触发条件 | 处理方式 | 适用场景 |
|------|----------|----------|----------|
| **Workflow 管线** | 用户提供文案/主题，需完整素材包 | LangGraph 确定性状态机：文案生成 → 标签 → 图片 → 配乐 → 评估 → 循环优化 | 一键生成完整图文包 |
| **Agent 对话** | 用户提问/闲聊/"帮我看看这个" | LLM + tools 自由 ReAct 循环 → LLM 自主决定是否进入管线 | 创作咨询、内容分析、灵感碰撞 |

### 1.5 技术选型

| 层次 | 技术 | 选型理由 |
|------|------|----------|
| 大模型 | DeepSeek Chat API | 国产大模型，中文理解能力强，API 兼容 OpenAI 格式 |
| 状态机 | LangGraph (StateGraph) | 声明式图编排，支持条件路由、循环、状态持久化 |
| Agent | LangChain ReAct + @tool | LLM 自主工具调用，函数调用模式 (function_calling) |
| 后端 | Python + FastAPI | 异步高性能，自动生成 Swagger 文档，生态丰富 |
| 前端 | React 18 + TypeScript + TailwindCSS | 组件化开发，类型安全，快速构建 UI |
| 数据库 | SQLite (长期) + Redis (短期) | SQLite 零配置适合单机部署；Redis 高性能缓存与会话管理 |
| 向量数据库 | Qdrant | 开源，支持 COSINE 相似度，4 个 Collection 覆盖标签/文案/图片/话题 |
| 向量化 | BGE (bge-small-zh-v1.5) | 中文 Embedding 效果优秀，模型体积小（~100MB），512 维 |
| 浏览器自动化 | Playwright | 跨浏览器支持，API 设计优秀 |
| 浏览器扩展 | Chrome Extension (Manifest V3) | 直接注入抖音页面，无缝数据提取 |

---

## 二、系统架构设计

### 2.1 总体架构

项目采用 **LangGraph 状态机编排 + 分层解耦** 架构，共分为 5 个层次：

```
┌──────────────────────────────────────────────────────────────┐
│                      接入层 (Access Layer)                     │
│  React Web 前端  │  FastAPI REST API (9 路由模块)  │  Chrome 扩展 │
├──────────────────────────────────────────────────────────────┤
│                    LangGraph 编排层 (Orchestration)              │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              StateGraph (builder.py)                  │   │
│  │                                                      │   │
│  │  14 个节点 · 7 条条件边 · 1 条循环边                    │   │
│  │                                                      │   │
│  │  initialize → classify_intent ─┬─ topic → generate   │   │
│  │                                ├─ create → skip      │   │
│  │                                ├─ optimize → rewrite │   │
│  │                                ├─ modify → parse     │   │
│  │                                └─ question → Agent   │   │
│  │                                      ↓               │   │
│  │                              analyze_emotion         │   │
│  │                                      ↓               │   │
│  │                              analyze_content          │   │
│  │                                      ↓               │   │
│  │                          execute_all_skills (并行)    │   │
│  │                                      ↓               │   │
│  │                              evaluate                 │   │
│  │                                      ↓               │   │
│  │                    check_threshold ──→ loop or END    │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│              ┌──────────────────────────┐                    │
│              │  agent_dialogue (ReAct)   │ ← LLM + 6 tools  │
│              │  enter_workflow? ─→ 进入管线 │                 │
│              └──────────────────────────┘                    │
├──────────────────────────────────────────────────────────────┤
│                     Skill 执行层 (Skills Layer)                 │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐   │
│  │ Skill 1  │ │ Skill 2  │ │ Skill 3  │ │   Skill 4    │   │
│  │ 标签推荐 │ │ 图片推荐 │ │ 配乐推荐 │ │  内容评估    │   │
│  │ Hashtag  │ │  Image   │ │  Music   │ │   Content    │   │
│  │Recommender│ │Recommender│ │Recommender│ │  Evaluator  │   │
│  └──────────┘ └──────────┘ └──────────┘ └──────────────┘   │
├──────────────────────────────────────────────────────────────┤
│                     数据与记忆层 (Data Layer)                    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │ MemoryManager │  │ CacheManager │  │   VectorStore    │   │
│  │   SQLite (6表)│  │  Redis (单例) │  │ Qdrant (4集合)  │   │
│  │  长期记忆     │  │  短期缓存    │  │  向量语义检索    │   │
│  └──────────────┘  └──────────────┘  └──────────────────┘   │
├──────────────────────────────────────────────────────────────┤
│                     基础设施层 (Infrastructure)                  │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐   │
│  │  Config  │ │Embeddings│ │ Prompts  │ │   Schemas    │   │
│  │ 配置管理 │ │ BGE 512d │ │ YAML模板 │ │ Pydantic 验证│   │
│  └──────────┘ └──────────┘ └──────────┘ └──────────────┘   │
└──────────────────────────────────────────────────────────────┘
```

### 2.2 LangGraph 状态机：核心流程

v2.0 的核心变化：将 v1.0 的 `AnalysisLayer → DecisionLayer → LightweightScheduler → DouyinAgent._auto_loop()` 类方法调用，重构为 **声明式 StateGraph**。

**v1.0 vs v2.0 对照**：

| v1.0 (类方法调用) | v2.0 (LangGraph 节点) | 变化 |
|---|---|---|
| `DouyinAgent.run()` 中的 session 初始化 | `initialize` 节点 | 自动恢复 SQLite 历史上下文 |
| `AnalysisLayer._nlp_analysis()` | `classify_intent` + `analyze_emotion_node` | LLM 五分类 + 情绪分析，拆分为 2 节点 |
| `AnalysisLayer._tag_similarity_analysis()` | 已移除 | 不再需要独立分析，由 evaluate 统一处理 |
| `DecisionLayer.decide_skill_combination()` | `analyze_content` + `decide_skills` | 简化为布尔标记判断 |
| `LightweightScheduler.execute_plan()` (串行) | `execute_all_skills` (并行) | ThreadPoolExecutor 并行执行 Skill1/2/3 |
| `DouyinAgent._auto_loop()` (while 循环) | `check_threshold` → `identify_weak` → `rerun_skill` → `rerun_evaluate` (图环路) | 循环条件写死在路由函数中 |
| `question_response` (死胡同) | `agent_dialogue` (ReAct + 可进入管线) | 从固定模板升级为 LLM+6 tools 自由对话 |
| session_state dict 手动传递 | `AgentState` TypedDict (18+3 字段) | Reducer 自动合并，类型安全 |

**完整图结构**：

```
                      ┌──────────┐
                      │ 1. init  │ ← 入口：加载会话上下文
                      └────┬─────┘
                           ↓
                      ┌──────────┐
                      │2. intent │ ← LLM 五分类
                      └────┬─────┘
       ┌──────┬──────┬────┼────┬──────┐
       ↓      ↓      ↓    ↓    ↓      ↓          条件边: route_by_intent
    topic  create optim mod question
       ↓      ↓      ↓    ↓    ↓
      gen    skip   opt  parse agent_dialogue
       ↓      ↓      ↓    ↓    ↓   ↓
       └──────┴──────┴────┘      │   │
              ↓                  │   │
         analyze_emotion ←───────┘   │
              ↓                      │
         analyze_content              │
              ↓                      │
         decide_skills                │
              ↓                      │
    ┌──────────────────┐              │
    │execute_all_skills│ ← 并行3Skill │
    └────────┬─────────┘              │
             ↓                        │
         evaluate ←────────────────────┘ (Agent 进入管线)
             ↓
      check_threshold
        ↙         ↘
    ≥4.0/iter≥3  <4.0 & iter<3      条件边: route_by_score
       ↓              ↓
      END      identify_weak
                   ↓
               rerun_skill
                   ↓
             rerun_evaluate ──→ check_threshold (循环边)
```

### 2.3 AgentState：全局状态定义

```python
# backend/graph/state.py — 21 字段 TypedDict
class AgentState(TypedDict, total=False):
    # 输入
    user_input: dict          # {text, tags, images, music}
    conversation_id: str

    # 意图路由
    intent: str               # topic|create|optimize|modify|question

    # 上下文（initialize 节点自动恢复）
    session: dict
    has_context: bool
    prev_copy_text: str
    prev_evaluation: dict
    prev_tags / prev_images / prev_music: list

    # 当前处理
    copy_text: str
    need_tags / need_images / need_music: bool
    modify_flags: dict
    emotion: dict             # {mood, intensity, energy, keywords}

    # Skill 输出
    final_tags / final_images / final_music: list

    # 评估 + 循环
    evaluation: dict          # {score, level, dimensions, suggestions, report}
    iteration: int
    best_score: float         # 追踪最佳结果
    best_evaluation: dict
    loop_history: Annotated[list, _merge_lists]  # Reducer 自动追加

    # Agent 对话
    dialogue_messages: Annotated[list, _merge_lists]  # ReAct 消息历史
    should_enter_workflow: bool    # LLM 是否决定进入管线
    workflow_intent_override: str  # 从 Agent 进入时的意图覆盖

    # 终端
    execution_log: Annotated[list, _merge_lists]
    error: Optional[str]
```

**关键设计：Annotated Reducer**

```python
# 普通字段：写入即覆盖
copy_text: str

# Reducer 字段：写入即追加（支持并行节点同时写）
loop_history: Annotated[list, _merge_lists]  # a + b
execution_log: Annotated[list, _merge_lists]
dialogue_messages: Annotated[list, _merge_lists]
```

### 2.4 质量闭环机制

评分 < 4.0 时，`check_threshold` → `identify_weak_dimension` → `rerun_skill` → `rerun_evaluate` → `check_threshold` 形成环路：

| 环节 | 节点 | 行为 |
|------|------|------|
| 检查阈值 | `check_threshold` | score ≥ 4.0 → END；iter ≥ 3 → END；否则 → identify_weak |
| 定位短板 | `identify_weak_dimension` | 遍历 5 维度找最低分 → 映射到 Skill1/2/3 |
| 精准重跑 | `rerun_skill` | 仅重跑最低分对应的 Skill（strategy="aggressive"） |
| 重新评估 | `rerun_evaluate` | 调用 Skill4 |
| 循环 | 边: rerun_evaluate → check_threshold | 环路回到检查点 |
| 最佳追踪 | `check_threshold` 中的 best_score | 每轮保留最佳结果，即使后续降分也不丢失 |

维度→Skill 映射：`tag_match→Skill1` / `image_richness→Skill2` / `music_harmony→Skill3` / `text_quality+completeness→Skill1`

最多 3 轮自动优化，用户驱动的重试不计入次数。

### 2.5 双模式语义路由

```
classify_intent (LLM 五分类)
    │
    ├─ topic → generate_copy → 汇入主流程
    ├─ create → 直接汇入主流程
    ├─ optimize → optimize_copy → 汇入主流程
    ├─ modify → parse_modify_intent → 精确定向重跑
    └─ question → agent_dialogue (ReAct + 6 tools)
                      │
                ┌─────┴─────┐
                ↓           ↓
          进入管线      对话结束
        (→ emo → ...)    (→ END)
```

Agent 对话中的 `enter_creation_workflow` tool 是两种模式的桥梁：LLM 判断用户需要完整素材包时调用此工具，图引擎检测到 `should_enter_workflow=True` 后路由到 `analyze_emotion`，进入确定性 Workflow 管线。

---

## 三、核心模块详细设计

### 3.1 LangGraph 编排层

#### 3.1.1 图构建器（builder.py）

**文件**：[backend/graph/builder.py](backend/graph/builder.py) — 306 行  
**职责**：定义 StateGraph 的节点注册、边连接、条件路由和执行入口。

**7 条条件路由函数**：

| 路由函数 | 触发节点 | 判断逻辑 | 可能去向 |
|----------|----------|----------|----------|
| `route_by_intent` | classify_intent | 读 intent + has_context | generate_copy / optimize_copy / parse_modify_intent / agent_dialogue / analyze_emotion |
| `route_after_modify` | parse_modify_intent | 读 modify_flags.change_copy | optimize_copy / analyze_emotion |
| `route_by_score` | check_threshold | score ≥ 4.0 或 iter ≥ 3 | END / identify_weak |
| `route_after_weak` | identify_weak | 能否定位弱点维度 | rerun_skill / END |
| `route_after_dialogue` | agent_dialogue | should_enter_workflow? | analyze_emotion / END |

**入口函数** `run_agent()`：构造 initial_state → `graph.invoke()` → 组装兼容旧 API 的 JSON 响应。

#### 3.1.2 节点函数（nodes.py）

**文件**：[backend/graph/nodes.py](backend/graph/nodes.py) — ~720 行  
**包含 14 个节点函数 + 1 个 Agent 对话节点**。

| 节点 | 行数 | 功能 | LLM 调用 |
|------|------|------|----------|
| `initialize` | ~60 | 从 SQLite 恢复会话上下文 | 否 |
| `classify_intent` | ~40 | LLM 五分类意图 (topic/create/optimize/modify/question) | ✅ DeepSeek |
| `generate_copy` | ~40 | topic 意图：根据想法生成 30-120 字抖音文案 | ✅ DeepSeek |
| `optimize_copy` | ~35 | optimize/modify 意图：基于上轮评估建议改写文案 | ✅ DeepSeek |
| `parse_modify_intent` | ~50 | modify 意图：LLM 解析想改/保留哪些组件 | ✅ DeepSeek |
| `agent_dialogue` | ~170 | **v2.0 新增**：ReAct 循环 + 6 tools，LLM 自主决定进入管线或仅对话 | ✅ DeepSeek |
| `analyze_emotion_node` | ~10 | 委托 Skill1 的 analyze_emotion 函数 | ✅ DeepSeek |
| `analyze_content` | ~35 | 纯 Python：根据 intent + modify_flags 布尔判断 need_* | 否 |
| `decide_skills` | ~5 | 占位节点，返回空 | 否 |
| `execute_all_skills` | ~105 | ThreadPoolExecutor 并行 Skill1/2/3，合并去重 | 间接调用 |
| `execute_skill1/2/3` | ~55×3 | 保留给 retry loop 使用的独立 Skill 节点 | 间接调用 |
| `evaluate_node` | ~20 | 委托 Skill4 综合评估 | 间接调用 |
| `check_threshold` | ~30 | 评分判断 + 最佳结果追踪 + 迭代计数 | 否 |
| `identify_weak_dimension` | ~30 | 找最低分维度 → 映射到 Skill | 否 |
| `rerun_skill` | ~40 | 重跑最低分对应的 Skill | 间接调用 |
| `rerun_evaluate` | ~5 | 重评估（复用 evaluate_node） | 间接调用 |

#### 3.1.3 agent_dialogue — ReAct Agent 对话节点

**v2.0 核心新增**，替代 v1.0 的简单模板回答。

```
agent_dialogue 节点内部流程：

1. 构建系统 prompt（包含上一轮文案/标签/评分上下文）
2. 从 SQLite 恢复历史对话消息
3. 追加当前用户消息
4. ReAct 循环 (max 5 轮):
   while 未结束:
     LLM + 6 tools → 获取响应
     if 无 tool_calls → 对话结束
     for each tool_call:
       执行工具 → ToolMessage 追加到消息列表
       if tool == "enter_creation_workflow" → 标记 should_enter=True，break
5. 持久化对话到 SQLite
6. 返回 should_enter_workflow 标志
```

**6 个可用工具**（tools.py）：

| 工具名 | 对应 Skill | 用途 |
|--------|-----------|------|
| `recommend_hashtags` | Skill 1 | 推荐标签 |
| `recommend_images_tool` | Skill 2 | 推荐图片 |
| `recommend_music_tool` | Skill 3 | 推荐配乐 |
| `evaluate_content` | Skill 4 | 综合评估 |
| `analyze_emotion_tool` | Skill 1 | 情绪分析 |
| `enter_creation_workflow` | — | **特殊工具**：LLM 调用即触发进入 Workflow 管线 |

### 3.2 Skill 执行层

#### 3.2.1 Skill 1：标签推荐

**文件**：[skills/hashtag_recommender.py](skills/hashtag_recommender.py) — 325 行  
**类**：`HashtagRecommender`

**三阶段流水线**：

```
Stage 1: 规则关键词提取（正则匹配，零成本，永可用）
    ↓
Stage 2: Qdrant 向量泛化（embedding → 语义搜索 → 扩展候选标签）
    ↓
Stage 3: DeepSeek LLM 重排序（从候选中精选 Top-N + 生成推荐理由）
    ↓
Fallback: 每层失败优雅降级到下一层
```

**情绪分析**：`analyze_emotion()` 函数（供标签推荐和配乐推荐复用），返回 `{mood, intensity, energy, keywords}`。支持 LLM + 规则双模式，带内存缓存。

**记忆加权**：推荐完成后自动记录到 SQLite `tags` 表（`increment_tag_usage`），用于后续推荐偏好。

**缓存**：Redis 缓存 LLM 精选结果（TTL 24h），相同文案复用。

#### 3.2.2 Skill 2：图片推荐

**文件**：[skills/image_recommender.py](skills/image_recommender.py) — 542 行  

**多数据源优先级**：

```
① Qdrant 向量语义图片搜索（零成本，已缓存图片）
② Pexels API 中文搜索（支持中文，命中率高）
③ DeepSeek 生成英文搜索词 → Unsplash API 英文搜索（覆盖面广）
④ 本地模拟数据（最终兜底）
```

**SSRF 防护**：下载前验证 URL 域名白名单（pexels.com / unsplash.com / picsum.photos）。

#### 3.2.3 Skill 3：配乐推荐

**文件**：[skills/music_recommender.py](skills/music_recommender.py) — 805 行  

**多数据源融合**：

```
① 情绪分析驱动：emotion → 音乐风格列表
② 抖音官方音乐榜单 API（OAuth 2.0 Client Credentials）
    ├── 热歌榜 (hot)
    ├── 飙升榜 (rising)
    └── 原创榜 (original)
③ GD Studio Music API 真实歌曲搜索（含可播放 URL）
④ 本地规则映射（TAG_TO_STYLE → STYLE_TO_MUSIC 华语经典曲库）
```

**抖音榜单匹配流程**：

```
获取 access_token → 拉取榜单（去重）→ DeepSeek 从榜单中匹配最合适 5 首歌曲
```

**情绪→风格映射**：13 种情绪覆盖（搞笑/温馨/伤感/励志/日常/吐槽/兴奋/浪漫/恐怖/怀旧/时尚/美食/旅行），每种映射到 2-4 个音乐风格。

#### 3.2.4 Skill 4：内容评估

**文件**：[skills/content_evaluator.py](skills/content_evaluator.py) — 927 行  

**5 维度加权评分体系**：

| 维度 | 权重 | 评分标准 |
|------|------|----------|
| 文案质量 (text_quality) | 30% | 长度适中（30-100 字最佳）、是否有问句/悬念/情绪词、无标签符号嵌入 |
| 标签匹配 (tag_match) | 25% | 标签与文案语义关联度、数量（3-8 个最佳）、是否含抖音热点标签 |
| 素材丰富度 (image_richness) | 20% | 图片数量（≥2 张加分）、描述完整度、来源质量（Unsplash 加分） |
| 音乐协调性 (music_harmony) | 15% | 配乐风格与内容情绪匹配度、是否使用热门音乐 |
| 结构完整性 (completeness) | 10% | 是否具备文案+图片+标签+配乐全套组件 |

**评估模式**：

- **API 模式**（优先）：DeepSeek 结构化输出 `EvaluationOutput`（含各维度分 + Markdown 报告 + 建议）
- **规则模式**（回退）：每个维度独立规则打分 + 加权求和

**热点感知**：通过抖音公开 Web API 获取实时热点话题和热门音乐（5 分钟内存缓存），评估时检查标签和配乐是否命中当前热点并加分。

**发布预测**：基于评分输出曝光范围预测（如 5000~20000 播放）和建议发布时段（如 12:00-13:00 休息时间）。

### 3.3 工具层（tools.py）

**文件**：[backend/graph/tools.py](backend/graph/tools.py) — ~140 行

使用 LangChain `@tool` 装饰器将 4 个 Skill + 情绪分析 + 管线入口包装为标准 Tool 接口，供 Agent 对话节点使用。每个 Tool 包含完整的 docstring（描述 + 参数说明 + 返回值格式），LLM 根据 docstring 自动推理何时调用。

```python
ALL_TOOLS = [
    recommend_hashtags,           # 标签推荐
    recommend_images_tool,        # 图片推荐
    recommend_music_tool,         # 配乐推荐
    evaluate_content,             # 内容评估
    analyze_emotion_tool,         # 情绪分析
    enter_creation_workflow,      # 桥梁：Agent → Workflow
]
TOOL_BY_NAME = {t.name: t for t in ALL_TOOLS}
```

### 3.4 数据与记忆层

#### 3.4.1 MemoryManager（长期记忆 — SQLite）

**文件**：[utils/memory.py](utils/memory.py) — 942 行  
**类**：`MemoryManager`

- **线程安全**：`threading.Lock()` + WAL 模式（读写不互斥）
- **连接管理**：`contextlib.contextmanager` 自动管理生命周期
- **6 张核心表**：content_posts / traffic_daily / follower_daily / tags / conversations / conversation_messages + 1 张素材表 personal_material_library
- **数据分析**：播放量/点赞/评论/分享/粉丝等多维度聚合统计
- **数据同步**：批量导入抖音数据，自动去重

#### 3.4.2 CacheManager（短期缓存 — Redis）

**文件**：[utils/cache.py](utils/cache.py) — 252 行  
**类**：`CacheManager`（单例模式）

| 数据类型 | TTL | 说明 |
|----------|-----|------|
| 会话状态 (session:*) | 7 天 | 当前对话上下文 |
| LLM 响应缓存 (deepseek:*) | 24 小时 | DeepSeek API 返回结果，降本 |
| 限流计数器 (ratelimit:*) | 24 小时 | API 调用频率控制 |
| 每日统计 (stats:daily:*) | 30 天 | 使用量实时统计 |
| 创作草稿 (draft:*) | 24 小时 | 用户暂存内容 |

#### 3.4.3 VectorStore（向量数据库 — Qdrant）

**文件**：[utils/vector_store.py](utils/vector_store.py) — 335 行  
**类**：`VectorStore`（单例模式）

| Collection | 用途 | 检索方式 |
|------------|------|----------|
| `public_tags` | 公共标签库语义搜索 | 文案 → embedding → Qdrant 查询 → 匹配标签 |
| `public_texts` | 相似文案搜索 + 质量参考 | 文案 → embedding → 返回真实表现数据 |
| `public_images` | 图文匹配搜索 | 文案 → embedding → 匹配图片描述 |
| `topic_trends` | 话题趋势检测 | scroll 按 hot_score 排序 |

**向量化**：BAAI/bge-small-zh-v1.5（512 维），支持本地离线加载 + HuggingFace 镜像站加速。

#### 3.4.4 Embeddings（文本向量化）

**文件**：[utils/embeddings.py](utils/embeddings.py) — 120 行

- 模型加载策略：本地 ModelScope 路径 → HF 镜像在线下载 → 离线缓存降级
- 批量嵌入 `embed_batch()` 比逐条快 3-5 倍
- 模型不可用时返回零向量，主流程不中断

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
│ views        │       ┌──────────────┐     │
│ likes        │       │    tags      │     │
│ comments     │       │──────────────│     │
│ shares       │       │ id (PK)      │     │
│ favorites    │       │ name (UNIQUE)│     │
│ swipe_away   │       │ usage_count  │     │
│ copy_expand  │       │ total_likes  │     │
│ fan_gain     │       │ total_views  │     │
│ fan_loss     │       │ created_at   │     │
│ eval_score   │       └──────────────┘     │
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

┌────────────────────────┐
│ personal_material_lib  │
│────────────────────────│
│ id (PK)                │
│ material_type          │
│ original_content       │
│ image_path             │
│ music_name / music_url │
│ usage_count            │
│ avg_engagement_rate    │
│ semantic_tags_json     │
└────────────────────────┘
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
| metadata | TEXT | 附加数据 JSON（含 tool_calls / evaluation） |
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

| 页面 | 文件 | 功能 |
|------|------|------|
| **Workspace** | Workspace.tsx | 主导工作区：对话列表 + 创作输入 + 结果展示 |
| **Analytics** | Analytics.tsx | 数据分析看板：播放/点赞/粉丝趋势 |
| **MaterialLibrary** | MaterialLibrary.tsx | 素材库管理：图片/音乐素材浏览与管理 |
| **PublishHistory** | PublishHistory.tsx | 发布历史列表 |
| **DouyinSync** | DouyinSync.tsx | 抖音数据同步：手动录入 / 批量导入 |
| **Settings** | Settings.tsx | 系统设置 |

### 5.3 核心组件

| 组件 | 文件 | 功能 |
|------|------|------|
| **AppLayout** | AppLayout.tsx | 全局布局：侧边栏 + 内容区 |
| **ChatMessage** | ChatMessage.tsx | 聊天消息气泡：Markdown 渲染 + 素材展示 |
| **ResultDisplay** | ResultDisplay.tsx | 结果展示卡片：评分 + 标签 + 图片 + 配乐 |
| **ExecutionFlow** | ExecutionFlow.tsx | Skill 执行流程可视化：步骤进度 + 状态 |
| **BlackboxRecommendation** | BlackboxRecommendation.tsx | 智能黑箱推荐面板 |

### 5.4 实时通信

前端通过 WebSocket 与后端建立持久连接，实现 Skill 执行进度的实时推送。API 服务层（api.ts）封装了全部 30+ 接口的 TypeScript 调用函数，提供类型安全的请求/响应处理。

---

## 六、浏览器扩展设计

### 6.1 概述

Chrome 浏览器扩展（Manifest V3），注入抖音创作者中心页面，实现发布数据的一键提取与回传，形成"线下创作 → 线上发布 → 数据回收"的闭环。

### 6.2 文件结构

| 文件 | 职责 |
|------|------|
| [manifest.json](browser-extension/manifest.json) | 扩展配置：权限、内容脚本、Service Worker |
| [background.js](browser-extension/background.js) | Service Worker：消息路由、数据导入、通知 |
| [content.js](browser-extension/content.js) | 内容脚本：DOM 数据提取 + 导入按钮注入 |
| [config.js](browser-extension/config.js) | 配置管理：后端地址持久化存储 |
| [popup.html](browser-extension/popup.html) | 弹窗界面 |
| [popup.js](browser-extension/popup.js) | 弹窗逻辑：设置管理、手动录入 |

### 6.3 数据提取策略

内容脚本采用 **DOM-agnostic 多策略回退** 设计：

```
策略 ①：标准 HTML 表格提取          → 解析 <table> 元素，自动映射列名
    ↓
策略 ②：统计数字卡片提取            → 扫描包含 ≥3 个数字的容器元素
    ↓
策略 ③：列表项提取                  → 解析 <ul>/<ol>/[role="list"] 元素
    ↓
策略 ④：全局变量扫描                → 搜索 window 下包含 text/views/likes 的 JS 对象
```

**数字解析**：支持中文单位（1.2 万 → 12000）、英文后缀（k/w）。

---

## 七、API 接口设计

### 7.1 接口概览

基于 FastAPI 的 RESTful API，共 30+ 个端点，路由拆分为 9 个模块。

| 路由模块 | 端点 | 方法 | 说明 |
|----------|------|------|------|
| **health** | `/api/health` | GET | 健康检查 |
| **conversations** | `/api/conversations` | GET/POST | 列出/创建对话 |
| | `/api/conversations/{id}` | GET/PUT/DELETE | 获取/更新/删除对话 |
| | `/api/conversations/{id}/messages` | GET | 获取对话历史 |
| | `/api/conversations/{id}/context` | GET | 获取 Agent 上下文 |
| | `/api/conversations/search` | GET | 搜索对话 |
| **agent** | `/api/agent/run` | POST | 执行 Agent 全流程（LangGraph 入口） |
| **materials** | `/api/materials` | GET/POST | 获取/添加素材 |
| | `/api/materials/{id}` | PUT/DELETE | 更新/删除素材 |
| **publish** | `/api/publish/history` | GET | 发布历史 |
| | `/api/publish/{id}/data` | PUT | 更新发布数据 |
| **analytics** | `/api/analytics/overview` | GET | 分析概览 |
| | `/api/analytics/traffic-trend` | GET | 流量趋势 |
| | `/api/analytics/follower-trend` | GET | 粉丝趋势 |
| **douyin** | `/api/douyin/sync` | POST | 批量同步抖音数据 |
| **upload** | `/api/upload` | POST | 图片上传 |
| **stats** | `/api/stats/*` | GET | Redis/Qdrant 统计 |

### 7.2 安全措施

- **认证**：API Key 中间件，支持 Bearer Token 和 X-API-Key 两种方式。公开路径（/api/health、/docs）免认证
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
| 文件上传校验 | [backend/routers/upload.py](backend/routers/upload.py) | 扩展名白名单（6 种图片格式） |
| 命令注入防护 | [run_backend.py](run_backend.py) | 移除所有 `shell=True`，改用列表传参 |
| CORS 白名单 | [backend/server.py](backend/server.py) | 环境变量动态配置 |
| 凭据管理 | [utils/config.py](utils/config.py) | 环境变量统一管理，零硬编码 |
| 安全会话 ID | [utils/memory.py](utils/memory.py) | `secrets.token_urlsafe()` 替代时间戳 |

---

## 九、部署与运行

### 9.1 环境要求

| 组件 | 要求 |
|------|------|
| Python | ≥ 3.10 |
| Node.js | ≥ 18 |
| Docker | 用于 Qdrant + Redis（docker compose up -d） |
| Redis | 可选（通过 Docker 启动） |
| Qdrant | 可选（通过 Docker 启动） |

### 9.2 快速启动

```bash
# 1. 配置环境变量
cp .env.example .env
# 编辑 .env，填入 DEEPSEEK_API_KEY

# 2. 启动基础服务 (Docker)
docker compose up -d

# 3. 安装 Python 依赖
pip install fastapi uvicorn pydantic python-dotenv python-multipart websockets requests
pip install sentence-transformers qdrant-client redis

# 4. 启动后端（端口 9000）
python run_backend.py

# 5. 启动前端（另一个终端）
cd frontend && npm install && npx vite --host
```

### 9.3 项目路径结构

```
tuwen-agent/
├── backend/
│   ├── server.py                  # FastAPI 入口 + 中间件 + 路由注册
│   ├── constants.py               # 全局常量
│   ├── schemas.py                 # Pydantic 结构化输出模型 (13 个类)
│   ├── graph/                     # LangGraph 状态机
│   │   ├── state.py               # AgentState (21 字段 TypedDict)
│   │   ├── nodes.py               # 15 个节点函数
│   │   ├── builder.py             # 图编译 + 7 条件路由 + run_agent 入口
│   │   ├── tools.py               # LangChain @tool 包装 (6 tools)
│   │   └── intelligent_blackbox.py # [预留] RAG 智能黑箱
│   └── routers/                   # API 路由 (9 个模块)
│       ├── agent.py               # Agent 执行管线
│       ├── conversations.py       # 对话管理
│       ├── materials.py           # 素材管理
│       ├── publish.py             # 发布记录
│       ├── analytics.py           # 数据分析
│       ├── douyin.py              # 抖音同步
│       ├── upload.py              # 图片上传
│       ├── stats.py               # Redis/Qdrant 统计
│       └── health.py              # 健康检查
├── skills/                        # 4 个核心 Skill
│   ├── hashtag_recommender.py     # Skill 1: 标签推荐（三阶段流水线）
│   ├── image_recommender.py       # Skill 2: 图片推荐（多源搜索）
│   ├── music_recommender.py       # Skill 3: 配乐推荐（情绪+榜单融合）
│   └── content_evaluator.py       # Skill 4: 内容评估（5维加权）
├── utils/                         # 工具层
│   ├── config.py                  # 配置 + DeepSeek LLM 工厂 + 关键词提取
│   ├── memory.py                  # SQLite 记忆层 (6+1 表)
│   ├── cache.py                   # Redis 缓存层 (单例)
│   ├── vector_store.py            # Qdrant 向量库 (4 Collection, 单例)
│   └── embeddings.py              # BGE 文本向量化
├── prompts/                       # LLM Prompt 模板 (YAML)
│   ├── intent.yaml / copy_gen.yaml / copy_optimize.yaml
│   ├── tag_recommend.yaml / music_match.yaml
│   ├── evaluate.yaml / modify_parse.yaml
├── frontend/                      # React 前端 (Vite + TS)
│   └── src/
│       ├── components/            # React 组件 (5 个)
│       ├── pages/                 # 页面 (6 个)
│       ├── services/              # API + WebSocket
│       ├── stores/                # Zustand 状态管理
│       └── types/                 # TypeScript 类型
├── browser-extension/             # Chrome 扩展 (Manifest V3)
├── config/
│   └── tag_rules.json             # 标签规则库 + 热门标签 + 推荐理由模板
├── docker-compose.yml             # Qdrant + Redis 容器编排
├── run_backend.py                 # 后端启动脚本
├── requirements.txt               # Python 依赖
└── CLAUDE.md                      # Claude Code 项目指令
```

---

## 十、项目统计

### 10.1 代码量统计

| 语言 | 主要文件 | 代码行数 | 占比 |
|------|----------|----------|------|
| Python | 19 | ~8,100 | 54% |
| TypeScript/TSX | 18 | ~3,800 | 25% |
| JavaScript | 4 | ~1,260 | 8% |
| Markdown | 15 | ~4,000 | — |
| JSON/YAML | 12 | ~550 | 4% |
| CSS/HTML | 3 | ~200 | 1% |
| **合计** | **~71** | **~15,500** | **100%** |

> 注：代码行数仅统计项目源代码（不含 .venv、node_modules、package-lock.json 等三方文件）。

### 10.2 v1.0 → v2.0 架构变化

| 维度 | v1.0 | v2.0 |
|------|------|------|
| Agent 核心 | `DouyinAgent` 类 + 4 个 Layer 类 | LangGraph StateGraph 14 节点 + 7 条件边 |
| 状态管理 | session_state dict 手动传递 | AgentState TypedDict 自动注入 |
| Skill 执行 | LightweightScheduler 串行 for 循环 | execute_all_skills ThreadPoolExecutor 并行 |
| 质量闭环 | `_auto_loop()` while 循环 | 图环路 (check→weak→rerun→check) |
| 问答 | question_response 固定模板 | agent_dialogue ReAct + 6 tools |
| 后端路由 | server.py 单文件 (~1200 行) | 9 个路由模块 + server.py (122 行) |
| 路由方式 | if-else 条件语句 | 条件边 + 路由函数 |
| LLM 调用 | call_deepseek 手动 JSON 解析 | with_structured_output (Pydantic) |
| 意图分类 | 规则匹配 (AnalysisLayer) | LLM 五分类 (classify_intent) |
| Agent 模式 | ❌ | ✅ (ReAct Agent 对话节点) |

### 10.3 功能覆盖

| 维度 | 状态 | 说明 |
|------|------|------|
| LangGraph 状态机编排 | ✅ | 14 节点 + 7 条件边 + 1 循环边，完整闭环 |
| ReAct Agent 对话 | ✅ | LLM + 6 tools 自由交互 + 可进入 Workflow |
| 标签推荐 | ✅ | 三阶段流水线：规则 → 向量 → LLM 重排序 |
| 图片推荐 | ✅ | 四源降级：Qdrant → Pexels → Unsplash → Mock |
| 配乐推荐 | ✅ | 情绪驱动 + 抖音榜单 + GD API + 规则映射 |
| 内容评估 | ✅ | 5 维加权评分，LLM + 规则双模式，热点感知 |
| 记忆层 | ✅ | SQLite (7 表) + Redis (5 类缓存) |
| 向量检索 | ✅ | Qdrant 4 个 Collection，BGE 512d Embedding |
| Web 前端 | ✅ | React 18 + TS，6 页面 + 5 组件 |
| 浏览器扩展 | ✅ | Chrome MV3，DOM-agnostic 多策略提取 |
| REST API | ✅ | FastAPI，9 路由模块，30+ 端点 |
| 安全审计 | ✅ | 21 项发现已全部修复 |
| 数据闭环 | 🟡 | 已实现数据回传存储，标签权重优化待完善 |
| 自动发布 | ❌ | 永久禁用（合规原因） |

### 10.4 Git 状态

| 指标 | 数值 |
|------|------|
| 分支 | master |
| 提交数 | 3 |
| 最新提交 | 8695f18 feat: 架构重构 — LangGraph 工作流 + 路由模块化 + 前端增强 |
| 远程仓库 | github.com/b76182342-source/tuwen-agent |

---

## 十一、总结与展望

### 11.1 项目成果

本项目从零构建了一个覆盖"分析→决策→执行→评估→优化"全流程的 AI 图文创作系统，并在 v2.0 完成了从传统类方法调用到 LangGraph 状态机 + ReAct Agent 的架构升级：

1. **声明式状态机编排**：14 个节点 + 7 条条件边 + 1 条循环边，将原本隐藏在 while/if-else 中的控制流显式化，任何熟悉 LangGraph 的开发者可快速理解全流程
2. **双模式交互**：确定性 Workflow 管线（适合一键生成）+ LLM 自主 Agent 对话（适合自由创作），两层通过 `enter_creation_workflow` tool 无缝衔接
3. **三层容错体系**：API 优先 → 向量检索 → 本地规则，确保系统在任何外部服务异常时正常运行
4. **完整工程化**：后端 API（9 路由模块）+ 前端界面（6 页面）+ 浏览器扩展 + 安全审计，具备生产级部署标准

### 11.2 技术亮点

- **LangGraph 状态机**：用图论模型表达 Agent 流程，条件边替代 if-else，环路替代 while
- **ReAct Agent**：LangChain @tool 包装 + function_calling 模式，LLM 自主推理工具调用
- **并行优化**：ThreadPoolExecutor 并行执行 3 个 Skill，耗时降低 60%
- **结构化输出**：Pydantic 模型 + `with_structured_output`，消除手动 JSON 解析
- **多层降级**：6 个外部 API 的容错编排，任何单点故障不影响整体
- **DOM-agnostic 扩展**：4 种回退策略的数据提取，不依赖特定网页结构

### 11.3 未来方向

| 方向 | 说明 |
|------|------|
| Agent 能力增强 | 丰富 tools 数量（竞品分析工具、热点趋势工具），让 LLM 能做更深度的创作辅助 |
| 多模型支持 | 接入更多 LLM（通义千问、文心一言等），支持模型切换与 A/B 对比 |
| 效果归因 | 发布后自动关联推荐参数与实际数据，量化每个维度的贡献 |
| 竞品分析 | 抓取同类爆款内容，提取共性标签/配乐/发布时间模式 |
| 多平台 | 扩展到小红书、快手等内容平台 |
| 人类反馈强化 | 用户对推荐结果的采纳/拒绝行为 → 微调推荐权重 |

---

> **项目地址**：[https://github.com/b76182342-source/tuwen-agent](https://github.com/b76182342-source/tuwen-agent)  
> **报告版本**：v2.0 · 2026-07-10
