# 抖音图文助手 → Dify 迁移完整指南（v2.1）

> 基于 Dify Chatflow 实际操作的精确步骤。每个节点配置均可在 Dify UI 中直接复制粘贴。
> 验证环境：Dify v0.15+ / DeepSeek API

---

## 一、架构对比

```
当前 Python 架构                       Dify 架构
─────────────────                     ─────────
douyin_agent.py (编排)        →       Chatflow 画布 + 条件分支
analysis_layer.py (意图)      →       LLM节点 + 结构化输出（JSON Schema）
decision_layer.py (决策)      →       条件分支（IF/ELSE 5路分流）
hashtag_recommender.py        →       知识检索节点 + LLM 标签精选节点
image_recommender.py          →       HTTP请求节点(Pexels) + 代码节点整理
music_recommender.py          →       代码节点（规则映射，内嵌Python3）
content_evaluator.py          →       LLM节点 + 结构化输出（5维度评分）
Qdrant 向量库                 →       Dify 知识库（自带 embedding + 向量检索）
Redis 缓存                    →       Dify 内置缓存
memory.db (SQLite)            →       会话变量（跨节点持久化）
auto_loop (max 3轮)           →       Chatflow 对话式迭代（用户→优化→重新生成）
backend/server.py             →       Dify 发布 → API 端点
```

---

## 二、环境准备

### 步骤 1：部署 Dify

```bash
# 方式一：Dify Cloud（推荐，5 分钟）
# 浏览器访问 https://cloud.dify.ai → 注册 → 登录

# 方式二：Docker 本地部署（需要 ≥8GB 内存）
git clone https://github.com/langgenius/dify.git
cd dify/docker
cp .env.example .env
docker compose up -d
# 访问 http://localhost，按向导创建管理员账号
```

### 步骤 2：配置 DeepSeek 模型供应商

1. Dify 右上角头像 → **设置** → **模型供应商**
2. 找到 **DeepSeek** → 点击「添加到供应商」
3. 填入 API Key（你原项目 `.env` 中的 `DEEPSEEK_API_KEY`）
4. 保存，确认出现绿色对勾 ✅

### 步骤 3：创建两个知识库

**知识库一：抖音标签推荐知识库**

1. 顶部导航 → **知识库** → **创建知识库**
2. 名称：`抖音标签推荐知识库`
3. 索引方式：**高质量**
4. **Embedding 模型**：推荐 `text-embedding-3-small`（若有）或系统默认
5. **分段设置**：
   - 分段最大长度：`500` tokens
   - 分段重叠长度：`50` tokens
   - 分段标识符：`###`（markdown 标题，确保每个标签条目为一个独立分段）
6. 上传文档：`dify-migration/knowledge/tags_database.md`
7. 等待处理完成（状态变绿 ✅）

**知识库二：配乐推荐规则库**

1. 同上创建，名称：`配乐推荐规则库`
2. 分段最大长度：`800` tokens
3. 分段标识符：`###`
4. 上传文档：`dify-migration/knowledge/music_styles.md`

> **分段设置为什么重要？** tags_database.md 每个标签条目以 `### #标签名` 开头。将 `###` 设为分段标识符后，每个标签就是一个独立分段，检索时不会把不相关的标签混在一起。

---

## 三、创建 Chatflow 应用 + 配置会话变量

### 步骤 4：创建应用

Dify 首页 → **创建应用** → 选 **Chatflow** → 名称：`抖音图文助手`

> **为什么选 Chatflow 而非 Workflow？**
> - Chatflow 支持多轮对话记忆，用户可以连续交互（"再优化一下""换一批标签"）
> - 会话变量在整段对话中持久化，适合记住当前生成的所有素材
> - Workflow 是一次性执行，无法做对话式迭代优化

### 步骤 5：配置会话变量（⚠️ 重要）

进入 Chatflow 编辑器 → 左侧面板找到 **「变量」** → 选 **「会话变量」** Tab（不是系统变量），点击「添加」：

| 变量名 | 类型 | 默认值 | 用途 |
|--------|------|--------|------|
| `current_text` | `string` | （留空） | 当前轮生成的文案 |
| `current_tags` | `array[string]` | `[]` | 当前轮推荐的标签列表 |
| `current_images_json` | `string` | `""` | 当前轮图片结果（JSON字符串） |
| `current_music_json` | `string` | `""` | 当前轮配乐结果（JSON字符串） |
| `last_score` | `number` | `0` | 上一轮综合评分 |

> **设计说明：**
> - `current_images` 和 `current_music` 改用 `string` 类型存储 JSON，因为 Dify 的 `array[object]` 类型在会话变量赋值和模板引用时存在兼容性差异。代码节点生成 JSON 字符串，输出时用代码节点解析渲染。
> - 移除了 `loop_count` — Chatflow 的对话式迭代不需要计数回路，每轮优化都是用户主动触发的新对话回合。
> - 系统变量 `sys.query` 是只读的，存储用户当前输入，不能写入。
> - 会话变量生命周期 = 整个对话，所有节点均可读写。

---

## 四、搭建节点：意图分类 → 条件分流

### 步骤 6：开始节点（默认已有）

画布上已有一个 **开始** 节点，无需配置。用户输入通过 `{{#sys.query#}}` 自动传入。

---

### 步骤 7：LLM 节点 — 意图分类

从左侧拖入 **LLM** 节点，命名为 `意图分类`，连接到开始节点。

> **命名提示**：节点名称会出现在变量引用路径中（如 `{{#意图分类.intent#}}`），建议使用简短中文命名，便于后续引用。

| 配置项 | 值 |
|--------|-----|
| 模型 | `deepseek-chat` |
| 上下文 | **不设置**（留空） |
| 记忆 | 开启，窗口大小填 `20` |
| 温度 | `0.3`（分类任务用低温保证一致性） |

**SYSTEM Prompt：**

```text
你是一个抖音内容创作助手的意图分类器。根据用户的输入，判断意图类型。

## 意图类型定义

1. **topic** — 用户给出主题/想法，缺少完整文案
   示例: "帮我写一段关于浴室用品的文案"、"春天到了想发个图文"

2. **create** — 用户已提供完整文案，需要标签/图片/配乐
   示例: "夕阳把影子拉得很长，我想念那个夏天"

3. **optimize** — 用户对上一次结果不满意，希望整体改进
   示例: "优化一下"、"再改改"、"加点创意"、"分数太低了重来"

4. **modify** — 用户对特定组件不满意
   示例: "换一批标签"、"这个配乐不太合适"、"换个图"、"换张猫的图片"

5. **question** — 用户提问或闲聊
   示例: "这个标签适合吗？"、"为什么推荐这个配乐？"
```

**USER Prompt：**

```text
用户输入：{{#sys.query#}}

请分析意图。
```

**⚠️ 关键操作：开启结构化输出**

在 LLM 节点右侧配置面板 → **输出** 区域 → 打开 **「结构化输出」** 开关 → 粘贴以下 JSON Schema：

```json
{
  "type": "object",
  "properties": {
    "intent": {
      "type": "string",
      "description": "意图类型",
      "enum": ["topic", "create", "optimize", "modify", "question"]
    },
    "confidence": {
      "type": "number",
      "description": "置信度 0.0-1.0"
    },
    "reason": {
      "type": "string",
      "description": "判定理由，简短说明"
    },
    "identified_topic": {
      "type": "string",
      "description": "从用户输入提取的主题关键词，如'浴室用品''春天''猫咪'"
    },
    "missing_text": {
      "type": "boolean",
      "description": "是否需要生成文案"
    },
    "missing_tags": {
      "type": "boolean",
      "description": "是否需要推荐标签"
    },
    "missing_images": {
      "type": "boolean",
      "description": "是否需要推荐图片"
    },
    "missing_music": {
      "type": "boolean",
      "description": "是否需要推荐配乐"
    }
  },
  "required": ["intent", "confidence", "reason", "identified_topic", "missing_text", "missing_tags", "missing_images", "missing_music"],
  "additionalProperties": false
}
```

> **设计说明：**
> - `additionalProperties: false` — 防止 LLM 输出多余字段
> - `intent` 用 `enum` 限制只能输出 5 种值，不会出现 `"create_content"` 这种非预期变体
> - 将 `missing_components` 拍平为 4 个顶层 boolean — 条件分支中直接 `{{#意图分类.missing_text#}}` 即可，无需嵌套路径
> - 结构化输出开启后，LLM 节点的输出字段会直接出现在后续节点的变量选择器中

---

### 步骤 8：条件分支 — 意图分流

连接在 `意图分类` 节点后面 → 添加 **条件分支** (IF/ELSE) 节点。

Dify 的 IF/ELSE 节点通过**链式嵌套**实现多路分流。按以下顺序配置（每个 ELSE 下再添加新的条件判断）：

```
IF {{#意图分类.intent#}} = "topic"
  → 文案生成 → 全流程 Skill
ELSE
  IF {{#意图分类.intent#}} = "create"
    → 跳过文案生成，直接进入 Skill
  ELSE
    IF {{#意图分类.intent#}} = "optimize"
      → 基于会话变量中的上次结果重新执行全流程
    ELSE
      IF {{#意图分类.intent#}} = "modify"
        → 解析修改目标，只重跑对应 Skill
      ELSE（默认 = question）
        → 直接回答问题
```

> **操作提示**：Dify 的 IF/ELSE 节点默认只有 IF 和 ELSE 两个出口。要加第三个条件，在 ELSE 出口下再拖入一个新的 IF/ELSE 节点，形成链式嵌套。

---

## 五、搭建节点：各意图分支

### 步骤 9：LLM 节点 — 文案生成（topic / optimize 分支）

从 topic 和 optimize 两个分支出口各拖一条线，汇合后接一个 **LLM** 节点，命名为 `文案生成`。

> **注意**：create 分支不经过此节点（用户已有文案）。

| 配置项 | 值 |
|--------|-----|
| 模型 | `deepseek-chat` |
| 上下文 | 不设置 |
| 记忆 | 开启，窗口 `20` |
| 温度 | `0.7`（创作任务需要一定创造性） |

**SYSTEM Prompt：**

```text
你是一个抖音图文创作专家。根据用户给出的主题，生成一条适合发布的抖音图文文案。

## 创作要求
1. 字数控制在 50-120 字（抖音图文最佳阅读长度）
2. 风格口语化、有网感、适合碎片化阅读
3. 适当使用问句增加互动（如"你们家猫也这样吗？"）
4. 文案中不要出现 # 或 @ 符号，标签会单独添加
5. 可以用换行分隔不同段落

## 根据主题调整风格
- 宠物 → 可爱+拟人化+日常趣事
- 美食 → 诱人描述+制作关键点
- 旅行 → 画面感描写+打卡地标
- 穿搭 → 单品亮点+搭配要点
- 情感 → 引发共鸣+讨论
- 日常 → 轻松自然+vlog风
- 励志 → 简短有力+金句型
- 产品测评 → 实用对比+使用前后效果
```

**USER Prompt：**

```text
用户主题：{{#意图分类.identified_topic#}}

{{#IF 当前为 optimize 意图}}
上一轮评分较低（{{#last_score#}}/5.0），请你：
1. 重新审视用户需求，调整文案方向
2. 特别注意改进：文案质量和原创性
{{#ENDIF}}

用户原文输入：{{#sys.query#}}

请生成抖音图文文案。
```

> **optimize 分支的处理**：当意图为 optimize 时，USER Prompt 中明确告诉 LLM 上一轮评分偏低、需要改进的方向。如果上一轮结果存储在会话变量中，也可以通过 `{{#current_text#}}` 引用，在 Prompt 中让 LLM 参考并改进。

**结构化输出（JSON Schema）：**

```json
{
  "type": "object",
  "properties": {
    "body": {
      "type": "string",
      "description": "文案正文，50-120字"
    },
    "style": {
      "type": "string",
      "description": "文案风格描述，如'俏皮日常风'"
    }
  },
  "required": ["body", "style"],
  "additionalProperties": false
}
```

---

### 步骤 10：变量赋值 — 文案写入会话变量

`文案生成` 节点后，先接一个 **「变量赋值」** 节点：

| 会话变量 | 赋值来源 |
|----------|---------|
| `current_text` | `{{#文案生成.body#}}` |

> 对于 create 分支（用户已有文案），也需要一个变量赋值节点将 `{{#sys.query#}}` 或经过提取的纯文案写入 `current_text`。

---

### 步骤 11：知识检索节点 — 标签候选

拖入 **知识检索** 节点，命名为 `标签检索`。注意：topic、create、optimize 三条分支都要汇合到此节点。

| 配置项 | 值 |
|--------|-----|
| 知识库 | `抖音标签推荐知识库` |
| 检索模式 | **混合检索**（同时使用关键词和语义，覆盖面更全） |
| TopK | `20` |
| 得分阈值 | `0.5`（过滤不相关结果，实际测试中 0.5 能较好平衡召回率和准确率） |

**查询内容：**

```text
{{#current_text#}}
{{#意图分类.identified_topic#}}
```

> 双变量查询：`current_text` 提供语义上下文，`identified_topic` 提供关键词锚点。即使 create 分支尚未写入 `current_text`（汇合点次序问题），`identified_topic` 也会确保有查询内容。

---

### 步骤 12：LLM 节点 — 标签精选排序

知识检索节点后面，接一个 **LLM** 节点，命名为 `标签精选`。

| 配置项 | 值 |
|--------|-----|
| 模型 | `deepseek-chat` |
| 温度 | `0.5`（允许一定灵活性） |

**SYSTEM Prompt：**

```text
你是抖音运营专家。根据文案内容，从候选标签中精选最合适的标签。

## 选标签原则
1. 相关性第一：标签必须与文案主题直接相关
2. 大小搭配：1-2个大流量标签（super级）+ 2-3个精准标签（hot级）+ 1-2个长尾标签（potential级）
3. 数量控制：精选 5-8 个
4. 多样性：避免选多个同义标签（如同时选 #猫咪日常 #猫主子）
```

**USER Prompt：**

```text
文案内容：
{{#current_text#}}

候选标签（知识库检索结果）：
{{#标签检索.result#}}

请精选最合适的标签，按相关度从高到低排序。
```

**结构化输出（JSON Schema）：**

```json
{
  "type": "object",
  "properties": {
    "tags": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "tag": { "type": "string", "description": "标签名，带#号，如 #萌宠" },
          "level": { "type": "string", "enum": ["super", "hot", "potential"], "description": "热度等级" },
          "reason": { "type": "string", "description": "推荐理由，10字以内" }
        },
        "required": ["tag", "level", "reason"]
      },
      "description": "精选标签列表，5-8个",
      "minItems": 5,
      "maxItems": 8
    }
  },
  "required": ["tags"],
  "additionalProperties": false
}
```

---

### 步骤 13：变量赋值 — 标签写入会话变量

| 会话变量 | 赋值来源 |
|----------|---------|
| `current_tags` | `{{#标签精选.tags#}}` |

---

### 步骤 14：HTTP 请求节点 — Pexels 图片搜索

与标签检索分支**并行**（不是串行，节省等待时间），拖入 **HTTP 请求** 节点，命名为 `Pexels搜索`。

> ⚠️ 前置条件：到 https://www.pexels.com/api/ 免费注册获取 API Key。

| 配置项 | 值 |
|--------|-----|
| API | **自定义** |
| Method | `GET` |
| URL | `https://api.pexels.com/v1/search` |

**Headers：**

| Key | Value |
|-----|-------|
| `Authorization` | `{{#pexels_api_key#}}` |

> 在 Dify 左侧「变量」面板 → 添加变量 → 类型选 **「密钥」** → 名称填 `pexels_api_key` → 值填你的 Pexels API Key。这样可以避免在配置中硬编码密钥。

**Query Parameters：**

| Key | Value |
|-----|-------|
| `query` | `{{#意图分类.identified_topic#}}` |
| `per_page` | `6` |
| `locale` | `zh-CN` |
| `orientation` | `portrait` |

> **错误处理提示**：Pexels API 限速为 200 次/小时（免费版）。建议在 HTTP 节点配置中开启「异常处理」→ 设置为「继续执行，输出空结果」，避免 API 失败导致整个流程中断。

---

### 步骤 15：代码节点 — 图片结果整理

`Pexels搜索` 节点后面，接一个 **代码** 节点（Python3），命名为 `图片整理`。

**输入变量：**

| 变量名 | 来源 |
|--------|------|
| `pexels_body` | `{{#Pexels搜索.body#}}` |
| `pexels_status` | `{{#Pexels搜索.status_code#}}` |

**代码：**

```python
import json


def main(pexels_body: dict, pexels_status: int = 0) -> dict:
    """整理 Pexels 图片搜索结果，返回 JSON 字符串存入会话变量"""
    images = []

    # 正常响应
    if pexels_status == 200 and pexels_body and isinstance(pexels_body, dict):
        photos = pexels_body.get("photos", [])
        for photo in photos[:6]:
            images.append({
                "url": photo.get("src", {}).get("large", ""),
                "thumb": photo.get("src", {}).get("small", ""),
                "description": photo.get("alt", "推荐配图"),
                "photographer": photo.get("photographer", ""),
                "source": "pexels"
            })

    # 兜底：API 失败时提示用户
    if not images:
        images.append({
            "url": "",
            "thumb": "",
            "description": "图片获取失败，请稍后重试或手动选择图片",
            "photographer": "",
            "source": "fallback"
        })

    return {
        "images": images,
        "images_json": json.dumps(images, ensure_ascii=False),
        "count": len(images)
    }
```

**输出变量：** `images_result`

> 同时返回 `images`（list，供后续模板节点直接遍历）和 `images_json`（string，写入会话变量持久化）。

---

### 步骤 16：变量赋值 — 图片写入会话变量

| 会话变量 | 赋值来源 |
|----------|---------|
| `current_images_json` | `{{#图片整理.images_result.images_json#}}` |

---

### 步骤 17：代码节点 — 配乐规则匹配

与图片分支**并行**，拖入 **代码** 节点（Python3），命名为 `配乐匹配`。

**输入变量：**

| 变量名 | 来源 |
|--------|------|
| `tags` | `{{#标签精选.tags#}}` |
| `text` | `{{#current_text#}}` |

**代码：**

```python
import json


def main(tags: list, text: str = "") -> dict:
    """基于标签+文案主题，规则映射生成配乐推荐"""

    # 标签 → 风格映射
    TAG_TO_STYLE = {
        "萌宠": ["欢快卡点", "轻松活泼", "软萌可爱"],
        "猫咪": ["欢快卡点", "轻松活泼"],
        "狗狗": ["欢快卡点", "动感活力"],
        "搞笑": ["欢快卡点", "搞笑音效", "魔性循环"],
        "美食": ["轻松舒缓", "美食BGM", "烹饪节奏"],
        "旅行": ["轻音乐", "自然音效", "治愈系"],
        "风景": ["轻音乐", "大气磅礴"],
        "情感": ["抒情慢歌", "钢琴曲", "伤感BGM"],
        "时尚": ["电子音乐", "节奏感强"],
        "穿搭": ["电子音乐", "时尚BGM"],
        "励志": ["激昂", "励志BGM", "热血BGM"],
        "读书": ["安静", "民谣"],
        "日常": ["轻松舒缓", "生活BGM", "轻快旋律"],
        "治愈": ["轻音乐", "治愈系"],
    }

    STYLE_TO_MUSIC = {
        "欢快卡点": {"name": "快乐崇拜", "mood": "开心、活泼", "reason": "经典欢快曲目，节奏明快"},
        "轻松活泼": {"name": "阳光彩虹小白马", "mood": "快乐、阳光", "reason": "旋律轻快，适合日常"},
        "轻音乐": {"name": "菊次郎的夏天", "mood": "治愈、温暖", "reason": "适合风景和日常记录"},
        "抒情慢歌": {"name": "后来", "mood": "伤感、回忆", "reason": "引发情感共鸣"},
        "激昂": {"name": "追梦赤子心", "mood": "励志、热血", "reason": "激发斗志"},
        "安静": {"name": "南山南", "mood": "安静、深沉", "reason": "适合思考感悟类内容"},
        "电子音乐": {"name": "Fade", "mood": "电子、动感", "reason": "适合时尚穿搭"},
        "治愈系": {"name": "小幸运", "mood": "幸运、美好", "reason": "温馨治愈"},
        "搞笑音效": {"name": "魔性笑声", "mood": "搞笑、幽默", "reason": "增强喜剧效果"},
        "励志BGM": {"name": "平凡之路", "mood": "励志、坚持", "reason": "引发共鸣"},
        "民谣": {"name": "成都", "mood": "温暖、怀旧", "reason": "民谣经典"},
        "钢琴曲": {"name": "卡农", "mood": "浪漫、优美", "reason": "经典钢琴曲"},
        "美食BGM": {"name": "干饭人之歌", "mood": "开心、期待", "reason": "增强食欲感"},
        "自然音效": {"name": "森林鸟鸣", "mood": "宁静、放松", "reason": "沉浸式自然体验"},
        "软萌可爱": {"name": "学猫叫", "mood": "可爱、俏皮", "reason": "适合萌宠内容"},
        "魔性循环": {"name": "江南皮革厂", "mood": "搞笑、魔性", "reason": "洗脑循环"},
        "热血BGM": {"name": "少年", "mood": "青春、活力", "reason": "充满正能量"},
        "生活BGM": {"name": "这世界那么多人", "mood": "温暖、治愈", "reason": "适合生活记录"},
        "轻松舒缓": {"name": "晚风心里吹", "mood": "放松、温暖", "reason": "适合日常记录"},
        "时尚BGM": {"name": "夜曲", "mood": "酷炫、动感", "reason": "时尚感强"},
        "大气磅礴": {"name": "天空之城", "mood": "宁静、深远", "reason": "适合风景大片"},
        "烹饪节奏": {"name": "舌尖上的中国", "mood": "认真、专注", "reason": "适合美食制作"},
        "伤感BGM": {"name": "遗憾也值得", "mood": "遗憾、释然", "reason": "适合情感语录"},
    }

    # 提取标签文本（去除#号）
    tag_text = ""
    if tags:
        for t in tags:
            if isinstance(t, dict):
                tag_text += t.get("tag", "").replace("#", "") + " "
            else:
                tag_text += str(t).replace("#", "") + " "

    # 匹配风格（去重保持顺序）
    matched_styles = []
    seen_styles = set()
    for keyword, styles in TAG_TO_STYLE.items():
        if keyword in tag_text:
            for s in styles:
                if s not in seen_styles:
                    seen_styles.add(s)
                    matched_styles.append(s)

    if not matched_styles:
        matched_styles = ["治愈系", "轻音乐", "民谣"]

    # 匹配音乐（去重）
    music_list = []
    seen_names = set()
    for style in matched_styles:
        if style in STYLE_TO_MUSIC:
            m = STYLE_TO_MUSIC[style]
            name = m["name"]
            if name not in seen_names:
                seen_names.add(name)
                music_list.append({
                    "name": name,
                    "style": style,
                    "mood": m["mood"],
                    "reason": m["reason"],
                    "source": "智能推荐"
                })

    return {
        "music_list": music_list[:5],
        "music_json": json.dumps(music_list[:5], ensure_ascii=False),
        "matched_styles": matched_styles
    }
```

**输出变量：** `music_result`

---

### 步骤 18：变量赋值 — 配乐写入会话变量

| 会话变量 | 赋值来源 |
|----------|---------|
| `current_music_json` | `{{#配乐匹配.music_result.music_json#}}` |

---

### 步骤 19：LLM 节点 — 综合评估

标签、图片、配乐三条分支全部汇合后，接一个 **LLM** 节点，命名为 `综合评估`。

| 配置项 | 值 |
|--------|-----|
| 模型 | `deepseek-chat` |
| 温度 | `0.3`（评分类任务用低温，输出更稳定一致） |

**SYSTEM Prompt：**

```text
你是抖音内容质量评估专家。对以下图文内容进行 5 维度评分，每项 1.0-5.0 分。

## 评分维度
1. 文案质量（权重30%）：长度是否适中(50-120字)、是否有互动设计(问句)、是否原创有网感
2. 标签匹配（权重25%）：语义相关性、数量是否3-8个、是否包含热门话题
3. 素材丰富度（权重20%）：图片数量≥2加分、图文内容匹配度
4. 音乐协调性（权重15%）：配乐风格与内容情绪匹配度
5. 结构完整性（权重10%）：是否四项组件(文案+标签+图片+配乐)齐全

## 分数等级
≥4.5=很好 | ≥4.0=较好 | ≥3.5=中等偏上 | ≥3.0=中等 | ≥2.5=中等偏下 | ≥2.0=一般 | ≥1.5=较差 | <1.5=很差

## 曝光预测
≥4.5: 5000~20000 | ≥4.0: 2000~8000 | ≥3.5: 1000~3000 | ≥3.0: 500~1500 | <3.0: 100~500

## 发布时段建议
- 宠物/搞笑 → 12:00-13:00 或 21:00-23:00
- 美食 → 11:00-13:00 或 17:00-19:00
- 时尚/穿搭 → 10:00-12:00 或 20:00-22:00
- 励志/职场 → 08:00-09:00 或 22:00-23:00
- 其他 → 12:00-13:00 或 18:00-20:00
```

**USER Prompt：**

```text
## 待评估内容
文案：{{#current_text#}}
标签：{{#current_tags#}}
图片数量：{{#图片整理.images_result.count#}} 张
配乐：{{#配乐匹配.music_result.music_list#}}

请评估。
```

**结构化输出（JSON Schema）：**

```json
{
  "type": "object",
  "properties": {
    "score": {
      "type": "number",
      "description": "综合评分 1.0-5.0，保留1位小数"
    },
    "level": {
      "type": "string",
      "description": "评级",
      "enum": ["很好", "较好", "中等偏上", "中等", "中等偏下", "一般", "较差", "很差"]
    },
    "text_quality_score": { "type": "number" },
    "text_quality_analysis": { "type": "string" },
    "tag_match_score": { "type": "number" },
    "tag_match_analysis": { "type": "string" },
    "image_richness_score": { "type": "number" },
    "image_richness_analysis": { "type": "string" },
    "music_harmony_score": { "type": "number" },
    "music_harmony_analysis": { "type": "string" },
    "completeness_score": { "type": "number" },
    "completeness_analysis": { "type": "string" },
    "suggestions": {
      "type": "array",
      "items": { "type": "string" },
      "description": "优化建议，最多3条",
      "maxItems": 3
    },
    "exposure_range": { "type": "string", "description": "预测曝光范围" },
    "best_publish_time": { "type": "string", "description": "建议发布时段" }
  },
  "required": ["score", "level", "suggestions", "exposure_range", "best_publish_time"],
  "additionalProperties": false
}
```

---

### 步骤 20：变量赋值 — 评分存储

评估节点后接变量赋值，将评分写入会话变量（供下一轮 optimize 参考）：

| 会话变量 | 赋值来源 |
|----------|---------|
| `last_score` | `{{#综合评估.score#}}` |

---

### 步骤 21：条件分支 — 评分判断 + 模板输出

评估节点后面，接 **条件分支**：

**分支 1：** `{{#综合评估.score#}}` >= `4.0` → 输出「完整结果」
**分支 2：** `{{#综合评估.score#}}` >= `3.0` → 输出「结果 + 优化建议」（提示用户可继续优化）
**分支 3（ELSE）：** → 输出「结果 + 强建议优化」

---

### 步骤 22：直接回复节点 — 最终输出

三个分支各接一个 **「直接回复」** 节点。以达标分支（≥4.0）的输出为例：

```markdown
## 🎯 图文创作结果

### 📝 文案
{{#current_text#}}

---

### 🏷️ 推荐标签
{{#current_tags#}}

---

### 🖼️ 推荐图片

{{#图片整理.images_result.images#}}

---

### 🎵 推荐配乐
{{#配乐匹配.music_result.music_list#}}

---

### 📊 综合评估

| 维度 | 得分 | 分析 |
|------|------|------|
| 文案质量 | {{#综合评估.text_quality_score#}} | {{#综合评估.text_quality_analysis#}} |
| 标签匹配 | {{#综合评估.tag_match_score#}} | {{#综合评估.tag_match_analysis#}} |
| 素材丰富度 | {{#综合评估.image_richness_score#}} | {{#综合评估.image_richness_analysis#}} |
| 音乐协调性 | {{#综合评估.music_harmony_score#}} | {{#综合评估.music_harmony_analysis#}} |
| 结构完整性 | {{#综合评估.completeness_score#}} | {{#综合评估.completeness_analysis#}} |

- **综合评分**：{{#综合评估.score#}}/5.0 — {{#综合评估.level#}}
- **预测曝光**：{{#综合评估.exposure_range#}}
- **建议发布时段**：{{#综合评估.best_publish_time#}}

### 💡 优化建议
{{#综合评估.suggestions#}}
```

对于不达标分支（<4.0），在输出末尾加上引导语：

```markdown
> 📉 当前评分 {{#综合评估.score#}}/5.0，建议输入 **"优化一下"** 让助手改进内容质量。
```

---

## 六、modify 意图分支：定向修改

当用户说"换一批标签"、"换个图"时，进入 modify 分支。这里需要一个 LLM 节点来解析修改目标。

### 步骤 23：LLM 节点 — 解析修改目标

modify 分支下接一个 **LLM** 节点，命名为 `修改解析`。

**SYSTEM Prompt：**

```text
你是修改意图解析器。用户对上一轮图文结果有不满，需要你判断他们想修改哪个组件。

## 组件类型
- text: 文案（"文案不太行""字数太多""换个风格"）
- tags: 标签（"换标签""标签不对""没加热门标签"）
- images: 图片（"换图""想要猫咪的图""图片不对"）
- music: 配乐（"换个音乐""这个BGM不对""要快节奏"）
```

**结构化输出：**

```json
{
  "type": "object",
  "properties": {
    "target": {
      "type": "string",
      "enum": ["text", "tags", "images", "music"],
      "description": "修改目标组件"
    },
    "reason": { "type": "string", "description": "用户不满的原因归纳" }
  },
  "required": ["target", "reason"],
  "additionalProperties": false
}
```

然后根据 `{{#修改解析.target#}}` 用条件分支分流：
- `text` → 回到 `文案生成` 节点（复用现有节点，USER Prompt 中传入当前文案让 LLM 修改）
- `tags` → 回到 `标签检索` 节点（调整查询词重新检索）
- `images` → 回到 `Pexels搜索` 节点（更换搜索关键词）
- `music` → 回到 `配乐匹配` 节点（调整标签输入）

> **注意**：modify 后也需走评估节点，给用户看到新结果。

---

## 七、完整节点链路总览

```
[开始]
  │  {{#sys.query#}}
  ▼
[LLM-意图分类] ← 结构化输出（JSON Schema）
  │            输出: intent, identified_topic, missing_*
  ▼
[条件分支链] ← IF/ELSE 嵌套判断 {{#意图分类.intent#}}
  │
  ├─ topic ──────────────────────┐
  ├─ optimize ───────────────────┤
  ├─ create ─────────────────────┤
  ├─ modify → [LLM-修改解析] ────┤
  └─ question → [LLM-直接回答]   │
                                  │
                    ┌─────────────┘
                    ▼
              [变量赋值] ← current_text = 文案
                    │
                    ▼
              [LLM-文案生成] ← topic/optimize 分支
                    │          create 分支跳过此节点
                    ▼
              [变量赋值] ← current_text = {{#文案生成.body#}}
                    │
                    ▼
         ┌─────────┴─────────┐
         ▼                   ▼
  [知识检索-标签检索]   [HTTP-Pexels搜索]
         │                   │
         ▼                   ▼
  [LLM-标签精选]        [代码-图片整理]
         │                   │
         ▼                   ▼
  [变量赋值]             [变量赋值]
  current_tags           current_images_json
         │                   │
         │    ┌──────────────┘
         │    │
         ▼    ▼
  [代码-配乐匹配]
         │
         ▼
  [变量赋值] ← current_music_json
         │
         ▼
  [LLM-综合评估] ← 结构化输出: score, level, suggestions...
         │
         ▼
  [变量赋值] ← last_score = {{#综合评估.score#}}
         │
         ▼
  [条件分支] ← {{#综合评估.score#}}
         │
    ┌────┼────┐
    ▼    ▼    ▼
  ≥4.0  3.0-4.0  <3.0
    │    │    │
    ▼    ▼    ▼
[直接回复] [直接回复+优化建议] [直接回复+强建议]
   最终输出    引导用户优化        引导用户优化

   用户看到结果后，可输入：
   "优化一下" → 下一轮对话 → intent=optimize → 重新走全流程
   "换个标签" → 下一轮对话 → intent=modify → 只重新走标签分支
```

> **核心设计理念**：不再尝试在画布上画回路（Dify Chatflow 不支持），而是利用 Chatflow 的多轮对话特性实现迭代优化。评分偏低时，输出中引导用户发送"优化一下"，下一个对话回合自动触发 optimize 分支重新生成。这比硬编码的 3 次循环更灵活——用户可以在任意节点终止，或根据实际效果决定是否继续优化。

---

## 八、测试验证

在 Chatflow 右侧预览面板，依次测试：

| 测试场景 | 输入 | 预期意图 | 预期行为 |
|----------|------|---------|---------|
| 主题创作 | "帮我写一个浴室用品的文案" | `topic` | 生成文案→标签→图片→配乐→评分→输出 |
| 已有文案 | "我的猫把新买的花瓶推倒了" | `create` | 跳过文案生成，直接推荐标签/图片/配乐 |
| 优化请求 | "优化一下，加点网感" | `optimize` | 基于 `current_text` 重新生成全流程 |
| 换标签 | "换一批标签" | `modify` | 修改解析→仅重跑标签分支 |
| 换图片 | "换个猫的图片" | `modify` | 修改解析→更换 Pexels 搜索词→重跑图片分支 |
| 闲聊 | "为什么推荐这个配乐" | `question` | 直接 LLM 回答，不触发 Skill 流程 |
| 连续优化 | 先 topic→结果→输入"优化一下" | optimize | 基于上一轮的 `current_text` 和 `last_score` 改进 |

---

## 九、外部服务

Dify 无法运行 Playwright 浏览器，发布功能保留为独立微服务。

### 部署发布微服务

```bash
cd dify-migration/external-services/douyin_publisher/
pip install fastapi uvicorn playwright
python -m playwright install chromium
python server.py
# 服务运行在 http://localhost:9001
# API 文档: http://localhost:9001/docs
```

### Dify 中调用

在 Chatflow 最后加一个 **HTTP 请求节点**：

| 配置项 | 值 |
|--------|-----|
| Method | `POST` |
| URL | `http://your-server:9001/publish` |
| Headers | `Content-Type: application/json` |
| Body（JSON） | 见下方 |

```json
{
  "text": "{{#current_text#}}",
  "image_paths": ["需要先下载 Pexels 图片到本地"],
  "tags": ["从 current_tags 提取标签文本"],
  "schedule_time": null
}
```

> 注意：Dify 中 Pexels 返回的是远程 URL，发布服务需要本地文件路径。需要在 Dify 中添加代码节点下载图片，或将发布服务改造为支持 URL 下载。

---

## 十、检查清单

### 阶段 1：基础设施
- [ ] 部署 Dify（Cloud 或 Docker，Docker 需 ≥8GB 内存）
- [ ] 配置 DeepSeek 模型供应商，确认绿色对勾 ✅
- [ ] 创建「抖音标签推荐知识库」+ 设置分段标识符为 `###`
- [ ] 创建「配乐推荐规则库」+ 设置分段标识符为 `###`
- [ ] 在变量面板创建密钥 `pexels_api_key`

### 阶段 2：核心流水线
- [ ] 创建 Chatflow + 配置 5 个会话变量
- [ ] LLM-意图分类 + 结构化输出（JSON Schema）+ 温度 0.3
- [ ] 条件分支链（IF/ELSE 嵌套，5 路分流）
- [ ] LLM-文案生成 + 结构化输出 + 温度 0.7
- [ ] 变量赋值 → current_text
- [ ] 知识检索-标签检索（混合检索，TopK=20，阈值 0.5）
- [ ] LLM-标签精选 + 结构化输出 + 温度 0.5
- [ ] 变量赋值 → current_tags
- [ ] HTTP-Pexels搜索 + 代码节点整理 + 错误兜底
- [ ] 变量赋值 → current_images_json
- [ ] 代码-配乐规则匹配
- [ ] 变量赋值 → current_music_json
- [ ] LLM-综合评估 + 结构化输出（拍平字段）+ 温度 0.3
- [ ] 变量赋值 → last_score
- [ ] 条件分支（≥4.0 / 3.0-4.0 / <3.0 三路输出）
- [ ] 三个直接回复节点（含优化引导语）

### 阶段 3：modify 分支 + 测试
- [ ] LLM-修改解析 + 结构化输出（target 字段）
- [ ] modify 条件分支（4 路：text/tags/images/music）
- [ ] 端到端测试 7 种场景（见测试表）
- [ ] 验证会话变量在连续对话中正确传递

### 阶段 4：外部服务
- [ ] 部署发布微服务
- [ ] Dify HTTP 节点对接
- [ ] 验证图片下载+发布链路

---

## 十一、注意事项

| 注意点 | 说明 |
|--------|------|
| **Chatflow 不支持回路** | Dify 画布是 DAG（有向无环图），不能从后面节点画线回前面。迭代优化通过"用户→新对话回合"实现 |
| **必须开启结构化输出** | LLM 节点默认输出纯文本 `text`，不开启结构化输出时条件分支只能做字符串匹配，无法引用 `intent`、`score` 等字段 |
| **节点命名即变量路径** | `{{#节点名.字段名#}}` 中的"节点名"必须是画布上节点的实际名称，建议用简短中文如"意图分类"而非"LLM-意图分类-v2" |
| **字段拍平不要嵌套** | 嵌套对象在变量引用中路径太长且易出错，输出 Schema 尽量用顶层字段 |
| **additionalProperties: false** | 防止 LLM 输出多余字段，破坏下游节点的变量引用 |
| **enum 限制关键字段** | `intent`、`target` 等分流字段用 enum 约束，避免出现非预期变体值 |
| **会话变量 ≠ 系统变量** | 系统变量 `sys.query` 是当前输入，只读；自定义持久化状态只能用会话变量 |
| **评分温度 0.3** | 评估类任务需要稳定一致的输出，高温会导致同一内容两次评分差异大 |
| **创作温度 0.7** | 文案生成需要一定创造性，温度过低会显得生硬模板化 |
| **知识检索阈值 ≥0.5** | TopK=20 时阈值太低会混入大量噪声，实际测试中 0.5-0.6 是最佳区间 |
| **图片/配乐用 JSON 字符串存储** | Dify 的 array[object] 会话变量在模板中直接引用时渲染效果差，改用 string 存储 JSON，输出时由代码节点解析为数组再渲染 |
| **密钥变量用于 API Key** | Pexels API Key 等敏感信息应放在「变量」→「密钥」类型中，不在节点配置中硬编码 |

---

## 十二、常见问题 (FAQ)

### Q1：为什么我的条件分支看不到 LLM 节点的 intent 字段？

**A：** 检查两个地方：
1. LLM 节点右侧面板，「结构化输出」开关是否已打开且 Schema 正确粘贴
2. 条件分支节点的变量选择器中，确保选了该 LLM 节点（节点名称对应）

如果 Schema 的 `required` 字段缺少 `intent`，也可能导致输出不稳定。

### Q2：Pexels API 返回空结果怎么办？

**A：** 代码节点中已包含兜底逻辑——API 失败时返回 `"图片获取失败"` 的提示。此外建议检查：
- `query` 参数是否正确传入（看看 `{{#意图分类.identified_topic#}}` 是否有值）
- Pexels API Key 是否正确，免费版限速 200 次/小时
- 如果中文搜索效果差，可以在代码节点前加一个 LLM 节点把中文主题翻译成英文关键词

### Q3：知识检索返回的结果与文案完全无关？

**A：** 可能原因：
- 知识库文档的分段太大（整篇文档当一段），Dify 无法精准检索到具体标签条目。解决方案：重建知识库，分段标识符设为 `###`，分段最大长度 500 tokens
- 得分阈值设太低。建议从 0.3 逐步调到 0.5-0.6，观察实际检索结果
- 查询内容太短或太模糊。在查询中同时传入 `current_text` 和 `identified_topic`

### Q4：modify 分支怎么在不同组件间切换？

**A：** modify 分支 → LLM-修改解析（输出 target 字段）→ IF/ELSE 判断 target 值 → 分别路由到对应节点的**上游**。例如要改图片，路由到 Pexels搜索 节点之前（可能需要重新设置搜索参数）。最简单的方式是让 modify 分支汇合到对应 Skill 节点的入口。

### Q5：Chatflow 和 Workflow 到底选哪个？

**A：** 总结：
- **Chatflow**：有对话记忆，适合需要多轮交互、用户反馈和迭代优化的场景。本项目选这个。
- **Workflow**：一次性执行，适合批量处理、定时任务、API 触发场景。有 Iteration 节点可以做真正的循环。
- 如果你的场景是"上传 100 个主题，批量生成文案"，应该用 Workflow。

### Q6：Dify 升级后节点配置丢失？

**A：** Dify 大版本升级（如 v0.14→v0.15）可能会改变节点配置结构。建议：
- 升级前在 Dify 中 **导出** 应用（右上角 → 导出 DSL）
- 升级后如果出问题，用导出的 DSL 文件重新导入
- 本项目中的 Prompt 和 Schema 都是纯文本，升级后可直接复制粘贴恢复

---

## 十三、与原 Python 项目的差异总结

| 维度 | 原 Python 项目 | Dify Chatflow |
|------|---------------|---------------|
| 自动循环 | 代码实现 max 3 次循环 | 对话式迭代（用户主动触发 optimize） |
| 图片获取 | 本地搜索 + Pexels API | 仅 Pexels API（通过 HTTP 节点） |
| 配乐推荐 | 规则映射 + API 回退 | 纯规则映射（代码节点内嵌） |
| 标签推荐 | Qdrant 向量检索 + LLM 精选 | Dify 知识库检索 + LLM 精选 |
| 状态管理 | SQLite memory.db | 会话变量（会话内持久化，会话结束清空） |
| 发布功能 | Playwright 自动化 | 独立微服务 + HTTP 节点调用 |
| 可观测性 | 日志文件 | Dify 内置「日志与标注」面板 |
| 修改灵活性 | 改代码重新部署 | Dify UI 直接改 Prompt / Schema，即时生效 |
