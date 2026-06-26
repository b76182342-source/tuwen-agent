# 抖音图文创作 Agent - 升级版

## 项目架构

这是一个**协作型智能Agent**，基于创作者主导的设计理念，提供智能辅助功能。

### 核心架构

```
用户输入
    ↓
【分析层：agent/analysis_layer.py】
    ├─ NLP分析（关键词、情感、主题、基调）
    ├─ 标签相似度分析
    └─ 数据搜集（热点、历史案例）
    ↓
【决策层：agent/decision_layer.py】
    ├─ 基于分析结果
    ├─ 推理Skill组合（5个Skill自由组合）
    └─ 生成执行计划
    ↓
【智能黑箱：agent/intelligent_blackbox.py】
    ├─ RAG检索成功案例
    ├─ 模式提取
    └─ 路径推荐（可选）
    ↓
【调度器：agent/lightweight_scheduler.py】
    ├─ 执行Skill组合
    └─ 管理执行状态
    ↓
【执行层：skills/】
    ├─ Skill1（标签推荐）
    ├─ Skill2（图片推荐）
    ├─ Skill3（配乐推荐）
    ├─ Skill4（内容评估）
    └─ Skill5（图文发布）
    ↓
【评测层：skills/content_evaluator.py】
    └─ 集成智能黑箱选项
    ↓
【记忆层：utils/memory.py】
    ├─ 长期记忆：个人素材库 + 发布历史 + 表现统计
    └─ 短期记忆：Skill执行追踪 + 回滚管理
```

## 新增功能

### 1. 分析层（AnalysisLayer）
- **NLP分析**：提取关键词、分析情感、检测主题和基调
- **标签相似度分析**：计算文案-标签、标签-标签、标签-热点相似度
- **数据搜集**：获取抖音热点话题、热门音乐、历史成功案例

### 2. 决策层（DecisionLayer）
- **智能推理**：基于分析结果推理最优Skill组合
- **动态决策**：根据用户输入决定是否需要执行各个Skill
- **置信度计算**：基于历史案例数量计算决策置信度

### 3. 智能黑箱（IntelligentBlackbox）
- **RAG检索**：检索历史成功案例
- **模式提取**：分析高频标签和配乐风格
- **路径推荐**：推荐最优执行路径和优化建议
- **用户可选**：评估不通过时由用户决定是否启用

### 4. 轻量级调度器（LightweightScheduler）
- **自由组合**：执行决策层推荐的Skill组合
- **状态管理**：区分创作者内容和Agent建议
- **执行追踪**：记录每个Skill的执行结果

### 5. 升级记忆层（MemoryManager）

#### 长期记忆
- **个人素材库**：存储文案和图片素材，支持语义标签
- **配乐库**：存储配乐信息和风格标签
- **发布历史**：记录发布内容、评估分数、发布后数据
- **表现统计**：统计素材使用次数、互动率、表现数据
- **数据分析**：分析个人账号数据，提供热门标签和最佳内容

#### 短期记忆
- **Skill执行追踪**：记录每个Skill的执行状态、输入输出、执行时长
- **用户确认机制**：支持用户确认Skill执行结果
- **回滚管理**：支持用户随时打断并回滚到已确认的Skill

## 使用方法

### 命令行使用

```bash
# 基础使用
python agent/douyin_agent.py --text "我家猫今天又把花瓶推倒了"

# 提供标签
python agent/douyin_agent.py --text "我家猫今天又把花瓶推倒了" --tags "#猫咪,#萌宠"

# 启用智能黑箱
python agent/douyin_agent.py --text "我家猫今天又把花瓶推倒了" --enable-blackbox
```

### Python API 使用

```python
from agent.douyin_agent import DouyinAgent

agent = DouyinAgent()

user_input = {
    "text": "我家猫今天又把花瓶推倒了",
    "tags": [],
    "images": [],
    "music": []
}

result = agent.run(user_input, enable_blackbox=True)

print(f"评分: {result['evaluation']['score']}/5.0")
print(f"建议: {result['agent_suggestions']}")
```

### 记忆层使用

#### 长期记忆

```python
from utils.memory import MemoryManager

memory = MemoryManager()

# 添加文案素材
text_id = memory.add_text_material(
    text="我家猫今天又把花瓶推倒了",
    semantic_tags=[
        {"tag": "猫咪", "confidence": 0.95},
        {"tag": "搞笑", "confidence": 0.88}
    ]
)

# 添加图片素材
image_id = memory.add_image_material(
    image_path="path/to/cat.jpg",
    semantic_tags=[
        {"tag": "猫咪", "confidence": 0.92}
    ]
)

# 添加配乐
music_id = memory.add_music(
    music_name="欢快卡点",
    music_url="https://example.com/music.mp3",
    music_tags=["欢快", "搞笑"],
    style="轻松搞笑"
)

# 记录发布
publish_id = memory.record_publish(
    text_id=text_id,
    image_ids=[image_id],
    music_id=music_id,
    evaluation_score=4.5,
    evaluation_level="优秀",
    session_id="session_123"
)

# 更新发布后数据
memory.update_publish_data(publish_id, likes=1200, comments=50, views=5000)

# 分析个人数据
analysis = memory.analyze_personal_data()
print(f"平均互动率: {analysis['avg_engagement_rate']:.2%}")
print(f"最佳内容: {analysis['best_content']['text']}")
print(f"热门标签: {analysis['top_tags']}")
```

#### 短期记忆

```python
# 开始执行Skill
execution_id = memory.start_skill_execution(
    session_id="session_123",
    skill_name="Skill1",
    input_data={"text": "我家猫今天又把花瓶推倒了"}
)

# 完成Skill执行
memory.complete_skill_execution(
    execution_id=execution_id,
    output_data={"tags": ["#猫咪", "#萌宠", "#搞笑"]},
    is_confirmed=True  # 用户确认
)

# 用户不满意，回滚
rollback_result = memory.rollback_to_skill(
    session_id="session_123",
    target_skill="Skill1"
)

if rollback_result["success"]:
    print(f"回滚成功: {rollback_result['from_skill']} → {rollback_result['to_skill']}")
    print(f"恢复数据: {rollback_result['output_data']}")
```

## 设计理念

### 创作者主导
- 用户输入核心内容（文案、图片、配乐）
- Agent提供智能补全和建议
- 最终决策权在用户手中

### 智能辅助
- 基于NLP深度理解用户输入
- 接入抖音真实数据（热点话题、热门音乐）
- RAG检索历史成功案例，提供优化建议

### 伦理约束
- 保持原创性，不修改核心内容
- 评估不通过时用户选择是否启用智能黑箱
- 避免机器替代人类创作

### 灵活回滚
- 支持用户随时打断执行
- 回滚到已确认的Skill
- 重新执行不满意的Skill

## 数据库表结构

### 长期记忆表
- `personal_material_library` - 个人素材库
- `semantic_tags` - 语义推理标签
- `music_library` - 配乐库
- `publish_history` - 发布历史
- `material_performance` - 素材表现统计

### 短期记忆表
- `skill_execution_log` - Skill执行记录
- `rollback_history` - 回滚历史

## 文件结构

```
d:\douyin-agent\
├── agent/                          # Agent模块
│   ├── __init__.py
│   ├── analysis_layer.py          # 分析层
│   ├── decision_layer.py          # 决策层
│   ├── intelligent_blackbox.py    # 智能黑箱
│   ├── lightweight_scheduler.py   # 轻量级调度器
│   └── douyin_agent.py            # 主入口
├── skills/                         # Skill模块
│   ├── hashtag_recommender.py     # Skill1: 标签推荐
│   ├── image_recommender.py       # Skill2: 图片推荐
│   ├── music_recommender.py       # Skill3: 配乐推荐
│   ├── content_evaluator.py       # Skill4: 内容评估（已升级）
│   └── douyin_publisher.py        # Skill5: 图文发布
├── utils/                          # 工具模块
│   ├── config.py                  # 配置
│   ├── memory.py                  # 记忆层（已升级）
│   └── web_tools.py               # Web工具
├── .env                            # 环境变量
├── memory.db                       # SQLite数据库
└── state/                          # 会话状态目录
    └── current_session.json        # 当前会话状态
```

## 兼容性

升级后的系统完全兼容旧版本API：
- 保留了所有旧版本的函数和方法
- 旧代码无需修改即可正常运行
- 新功能通过新API提供

## 总结

这个升级方案完整实现了你的设计理念：

1. **创作者主导**：用户输入核心内容
2. **智能辅助**：Agent自动补全和建议
3. **分析层固定**：NLP分析、相似度分析、数据搜集
4. **决策层智能**：基于分析结果推理Skill组合
5. **执行层自由**：所有5个Skill都可以自由组合
6. **评测层固定**：最终评测
7. **智能黑箱可选**：评估不通过时用户选择是否启用
8. **记忆层升级**：长期记忆+短期记忆，支持回滚管理

升级后的系统是一个完整的**协作型Agent**，具备感知、规划、决策、执行、学习能力，同时尊重创作者的主导地位。