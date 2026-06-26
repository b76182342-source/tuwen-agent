# 抖音图文创作 Agent - 前后端完整实现

## 项目结构

```
d:\douyin-agent\
├── agent/                          # Agent核心模块
│   ├── analysis_layer.py          # 分析层
│   ├── decision_layer.py          # 决策层
│   ├── intelligent_blackbox.py    # 智能黑箱
│   ├── lightweight_scheduler.py   # 轻量级调度器
│   └── douyin_agent.py            # 主入口
├── skills/                         # Skill模块
│   ├── hashtag_recommender.py     # Skill1: 标签推荐
│   ├── image_recommender.py       # Skill2: 图片推荐
│   ├── music_recommender.py       # Skill3: 配乐推荐
│   ├── content_evaluator.py       # Skill4: 内容评估
│   └── douyin_publisher.py        # Skill5: 图文发布
├── utils/                          # 工具模块
│   ├── config.py                  # 配置
│   ├── memory.py                  # 记忆层
│   └── web_tools.py               # Web工具
├── backend/                        # 后端API服务
│   ├── api_server.py              # FastAPI服务器
│   └── requirements.txt           # 后端依赖
├── frontend/                       # 前端应用
│   ├── src/
│   │   ├── components/            # 组件
│   │   ├── pages/                 # 页面
│   │   ├── services/              # API服务
│   │   ├── stores/                # 状态管理
│   │   ├── types/                 # TypeScript类型
│   │   ├── main.tsx               # 入口文件
│   │   └── index.css              # 样式
│   ├── package.json               # 前端依赖
│   ├── vite.config.ts             # Vite配置
│   └── tsconfig.json              # TypeScript配置
├── memory.db                       # SQLite数据库
├── .env                            # 环境变量
└── requirements.txt                # Python依赖
```

## 技术栈

### 前端
- **React 18** + TypeScript
- **Vite** - 构建工具
- **Ant Design 5** - UI组件库
- **Zustand** - 状态管理
- **React Query** - 服务端状态管理
- **Recharts** - 数据可视化
- **React Router v6** - 路由管理

### 后端
- **FastAPI** - 高性能异步API框架
- **WebSocket** - 实时通信
- **SQLite** - 数据库
- **Pydantic** - 数据验证

## 快速开始

### 1. 安装后端依赖

```bash
cd d:\douyin-agent
pip install -r requirements.txt
pip install -r backend/requirements.txt
```

### 2. 启动后端服务

```bash
cd d:\douyin-agent
python backend/api_server.py
```

后端服务将在 `http://localhost:8000` 启动

### 3. 安装前端依赖

```bash
cd d:\douyin-agent\frontend
npm install
```

### 4. 启动前端开发服务器

```bash
cd d:\douyin-agent\frontend
npm run dev
```

前端应用将在 `http://localhost:3000` 启动

## 功能说明

### 1. 创作工作台
- 输入文案内容
- 添加标签
- 上传图片
- 选择配乐
- 启用/禁用智能黑箱
- 实时查看执行流程
- 查看创作者内容、Agent建议、评估结果
- 智能黑箱建议（评估不通过时）

### 2. 素材库管理
- 文案素材管理
- 图片素材管理
- 配乐库管理
- 按标签筛选
- 添加/编辑/删除素材
- 查看素材表现数据

### 3. 发布历史
- 查看所有发布记录
- 查看互动数据（点赞、评论、浏览）
- 查看互动率趋势图
- 重新发布
- 删除记录

### 4. 数据分析
- 核心指标展示（总发布数、平均互动率等）
- 热门标签排行
- 标签使用分布图
- 互动数据分布
- 最佳内容展示

## API文档

启动后端服务后，访问 `http://localhost:8000/docs` 查看完整的API文档。

### 主要API端点

#### Agent相关
- `POST /api/agent/run` - 执行Agent
- `GET /api/agent/status/{session_id}` - 获取执行状态
- `POST /api/agent/rollback` - 回滚操作

#### 素材管理
- `GET /api/materials` - 获取素材列表
- `POST /api/materials` - 添加素材
- `PUT /api/materials/{id}` - 更新素材
- `DELETE /api/materials/{id}` - 删除素材

#### 发布历史
- `GET /api/publish/history` - 获取发布历史
- `GET /api/publish/{id}` - 获取单个发布记录
- `PUT /api/publish/{id}/data` - 更新发布数据

#### 数据分析
- `GET /api/analytics/overview` - 获取概览数据
- `GET /api/analytics/tags` - 获取标签表现
- `GET /api/analytics/materials` - 获取素材表现

## WebSocket连接

前端通过WebSocket与后端实时通信：

```javascript
ws://localhost:8000/ws/agent/{session_id}
```

消息格式：
```json
{
  "type": "stage_update",
  "stage": "分析层",
  "status": "completed",
  "data": {...}
}
```

## 环境变量

在 `.env` 文件中配置：

```env
# DeepSeek API
DEEPSEEK_API_KEY=your_api_key_here

# 其他配置...
```

## 数据库

项目使用SQLite数据库，数据库文件为 `memory.db`，包含以下表：

- `personal_material_library` - 个人素材库
- `semantic_tags` - 语义标签
- `music_library` - 配乐库
- `publish_history` - 发布历史
- `material_performance` - 素材表现统计
- `skill_execution_log` - Skill执行日志
- `rollback_history` - 回滚历史

## 开发说明

### 前端开发

```bash
cd frontend
npm run dev        # 启动开发服务器
npm run build      # 构建生产版本
npm run preview    # 预览生产版本
```

### 后端开发

```bash
python backend/api_server.py
```

### 代码规范

- 前端使用TypeScript，严格类型检查
- 后端使用Python 3.10+
- 遵循PEP 8代码规范

## 部署

### 前端部署

```bash
cd frontend
npm run build
```

构建产物在 `frontend/dist` 目录，可以部署到任何静态文件服务器。

### 后端部署

```bash
# 使用gunicorn部署
pip install gunicorn
gunicorn backend.api_server:app -w 4 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000
```

## 注意事项

1. 确保后端服务先启动，再启动前端
2. 前端默认代理 `/api` 和 `/ws` 到后端 `http://localhost:8000`
3. 首次运行会自动创建SQLite数据库
4. 确保安装了所有依赖

## 许可证

MIT License

## 联系方式

如有问题，请提交Issue或联系开发者。