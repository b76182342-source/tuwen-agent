# 抖音创作顾问 Agent

AI 驱动的图文内容创作顾问。输入主题/文案/图片，自动补全标签、配乐、图片推荐，并给出综合评分和发布预测。

## 快速启动

```bash
# 1. 配置环境
cp .env.example .env
# 编辑 .env 填入 DEEPSEEK_API_KEY

# 2. 启动基础服务 (Docker)
docker compose up -d

# 3. 安装 Python 依赖
pip install fastapi uvicorn pydantic python-dotenv python-multipart websockets requests
pip install sentence-transformers qdrant-client redis

# 4. 启动后端 (:9000)
python run_backend.py

# 5. 启动前端 (:3000)
cd frontend && npm install && npx vite --host
```

## 架构

```
用户输入 → LangGraph 状态机 → 文案/标签/图片/配乐 → 评估 → 发布预测
           ├─ intent_classify (LLM 意图路由)
           ├─ generate_copy (文案生成/改写, DeepSeek)
           ├─ skill_hashtag → skill_image → skill_music (并行)
           ├─ evaluate (5 维度评分)
           └─ auto_loop (评分 < 4.0 自动重试, 最多 3 轮)
```

| 层 | 技术 |
|----|------|
| 前端 | React 18 + TypeScript + Vite + Ant Design 5 |
| 后端 | Python 3.10+ / FastAPI / LangGraph |
| AI | DeepSeek Chat API (语义理解 + 内容生成) |
| 向量检索 | Qdrant + sentence-transformers (bge-small-zh-v1.5) |
| 缓存 | Redis + SQLite |
| 图片 | Pexels API + Unsplash API |
| 基础设施 | Docker Compose (Qdrant + Redis) |

## 项目结构

```
tuwen-agent/
├── backend/
│   ├── server.py              # FastAPI 入口 (122行)
│   ├── constants.py / schemas.py
│   ├── graph/                 # LangGraph 状态机
│   │   ├── state.py           # AgentState (18字段 TypedDict)
│   │   ├── nodes.py           # 18 个处理节点
│   │   ├── builder.py         # 图编译 + 条件路由
│   │   └── tools.py           # Skill Tool 包装
│   └── routers/               # API 路由 (9 个模块)
├── skills/                    # 4 个核心 Skill
│   ├── hashtag_recommender.py
│   ├── image_recommender.py
│   ├── music_recommender.py
│   └── content_evaluator.py
├── utils/                     # 工具层
│   ├── config.py              # 配置 + DeepSeek API
│   ├── memory.py              # SQLite 记忆层
│   ├── cache.py               # Redis 缓存
│   ├── vector_store.py        # Qdrant 向量库
│   └── embeddings.py          # 文本向量化
├── frontend/                  # React 前端
├── prompts/                   # LLM Prompt 模板
├── docker-compose.yml         # Qdrant + Redis
└── docs/                      # 文档
```

## API 端点

| 路径 | 说明 |
|------|------|
| `POST /api/agent/run` | Agent 主流程 |
| `GET/POST /api/conversations` | 对话管理 |
| `GET/POST/PUT/DELETE /api/materials` | 素材管理 |
| `GET /api/publish/history` | 发布记录 |
| `GET /api/analytics/overview` | 数据分析 |
| `POST /api/douyin/sync` | 数据同步 |
| `GET /api/health` | 健康检查 |

完整 API 文档: `http://localhost:9000/docs`
