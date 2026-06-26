# 抖音图文半自动发布 Agent - 项目总结

## 项目概述

本项目是一个基于 Python 的抖音图文内容半自动发布 Agent，包含 5 个核心 Skill 模块，实现了从内容创作到发布的完整流程。

## 项目结构

```
D:\douyin-agent\
├── skills/                      # Skill 模块目录
│   ├── hashtag_recommender.py   # Skill 1: 标签推荐
│   ├── image_recommender.py     # Skill 2: 图片推荐
│   ├── music_recommender.py     # Skill 3: 配乐推荐
│   ├── content_evaluator.py     # Skill 4: 内容评估
│   ├── douyin_publisher.py      # Skill 5: 图文发布（核心执行层）
│   ├── test_publisher_logic.py  # 发布逻辑测试脚本
│   └── README_douyin_publisher.md # 发布 Skill 使用说明
│
├── utils/                       # 工具函数目录
│   └── web_tools.py             # Web 工具（图片搜索、音乐搜索）
│
├── approved_images/             # 图片保存目录
│   └── img_*.jpg                # 推荐并保存的图片
│
├── requirements.txt             # Python 依赖列表
│
└── douyin_state.json            # 登录状态文件（首次运行后生成）
```

## 五个核心 Skill

### Skill 1: 标签推荐 (hashtag_recommender.py)

**功能**: 根据中文文案自动推荐抖音标签

**主函数**: `recommend(text: str) -> list`

**输入**: 文案（如 "我家猫今天又把花瓶推倒了"）

**输出**: 5~10 个标签，格式：
```python
[{"tag": "#猫咪日常", "reason": "相关话题近期热度上升"}, ...]
```

**测试命令**:
```bash
python skills/hashtag_recommender.py
```

---

### Skill 2: 图片推荐 (image_recommender.py)

**功能**: 根据文案推荐相关图片，支持用户审核并保存

**主函数**: `recommend_images(text: str, save_dir: str = "approved_images") -> list`

**输入**: 文案 + 保存目录

**输出**: 图片列表，格式：
```python
[
  {
    "local_path": "approved_images/img_1.jpg",
    "description": "橘猫在窗台上张望",
    "source": "mock",
    "record_tags": ["猫咪", "室内", "暖色调"]
  },
  ...
]
```

**测试命令**:
```bash
python skills/image_recommender.py
```

---

### Skill 3: 配乐推荐 (music_recommender.py)

**功能**: 根据标签列表推荐抖音配乐（只推荐歌名/风格，不自动添加）

**主函数**: `recommend_music(tags: list, text: str = "") -> list`

**输入**: 标签列表（如 ["#猫咪日常", "#萌宠", "#搞笑"]）+ 原始文案（可选）

**输出**: 配乐列表，格式：
```python
[
  {
    "name": "欢快卡点",
    "style": "欢快/卡点",
    "mood": "搞笑、轻松",
    "reason": "适用于萌宠搞笑类内容，节奏明快能提升完播率",
    "source": "抖音曲库"
  },
  ...
]
```

**测试命令**:
```bash
python skills/music_recommender.py
```

---

### Skill 4: 内容评估 (content_evaluator.py)

**功能**: 综合评估图文内容潜力，生成 Markdown 格式的评估报告

**主函数**: `evaluate(text: str, tags: list, images: list = None, music: list = None) -> dict`

**输入**: 文案 + 标签 + 图片（可选）+ 配乐（可选）

**输出**: 评估结果，格式：
```python
{
  "score": 4.1,          # 综合评分 1~5
  "level": "良好",       # 评级文字
  "report": "Markdown 格式的详细报告",
  "suggestions": ["建议1", "建议2"]
}
```

**评估维度**:
- 文案质量（40%）：长度、关键词、情感、互动性
- 标签质量（30%）：数量、热门标签、多样性
- 图片质量（20%）：数量、描述、标签
- 配乐质量（10%）：数量、风格、情绪

**测试命令**:
```bash
python skills/content_evaluator.py
```

---

### Skill 5: 图文发布 (douyin_publisher.py) ⭐️

**功能**: 通过 Playwright 自动化操作抖音创作者网页端，完成图文发布

**主函数**: `publish(text: str, image_paths: list, tags: list) -> dict`

**输入**: 
- 文案
- 图片路径列表（最多 6 张）
- 标签列表

**输出**: 
```python
{"status": "success", "message": "发布成功"}
{"status": "failed", "message": "错误描述", "step": "步骤名"}
```

**发布流程**:
1. 填写文案
2. 上传图片
3. 填入标签
4. 点击发布

**测试命令**:
```bash
# 模拟测试（不依赖 Playwright）
python skills/test_publisher_logic.py

# 实际测试（需要安装 Playwright）
pip install playwright
python -m playwright install chromium
python skills/douyin_publisher.py "测试文案" "img1.jpg,img2.jpg" "标签1,标签2"
```

**重要提示**:
- 首次运行需要手动扫码登录
- 登录状态保存在 `douyin_state.json`
- 发布频率不宜过高，建议每天不超过 5 条
- 请遵守抖音用户协议

---

## 工具函数 (utils/web_tools.py)

### mock_search(query: str, count: int = 5) -> list

模拟图片搜索，支持猫、狗、美食、旅行、生活等关键词。

### mock_search_music(tags: list, count: int = 5) -> list

模拟音乐搜索，支持根据标签匹配音乐。

---

## 使用流程

### 1. 内容创作阶段

```python
# Step 1: 标签推荐
from skills.hashtag_recommender import recommend
tags = recommend("我家猫今天又把花瓶推倒了")

# Step 2: 图片推荐
from skills.image_recommender import recommend_images
images = recommend_images("我家猫今天又把花瓶推倒了")

# Step 3: 配乐推荐
from skills.music_recommender import recommend_music
music = recommend_music([tag["tag"] for tag in tags])
```

### 2. 内容评估阶段

```python
# Step 4: 内容评估
from skills.content_evaluator import evaluate
result = evaluate(
    text="我家猫今天又把花瓶推倒了",
    tags=[tag["tag"] for tag in tags],
    images=images,
    music=music
)

print(f"评分: {result['score']}/5.0")
print(f"评级: {result['level']}")
print(result['report'])
```

### 3. 内容发布阶段

```python
# Step 5: 图文发布
from skills.douyin_publisher import publish

# 准备发布内容
final_text = "我家猫今天又把花瓶推倒了，太调皮了！"
final_images = [img["local_path"] for img in images[:3]]
final_tags = [tag["tag"].replace("#", "") for tag in tags[:5]]

# 执行发布
result = publish(final_text, final_images, final_tags)

if result["status"] == "success":
    print("发布成功！")
else:
    print(f"发布失败: {result['message']}")
```

---

## 安装和配置

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 安装浏览器驱动（仅发布 Skill 需要）

```bash
pip install playwright
python -m playwright install chromium
```

### 3. 验证安装

```bash
# 测试各 Skill
python skills/hashtag_recommender.py
python skills/image_recommender.py
python skills/music_recommender.py
python skills/content_evaluator.py
python skills/test_publisher_logic.py
```

---

## 测试结果总结

### Skill 1-4: 全部通过 ✅

- **标签推荐**: 成功推荐 5~10 个相关标签
- **图片推荐**: 成功推荐并保存图片到 approved_images/
- **配乐推荐**: 成功推荐 3~5 首匹配音乐
- **内容评估**: 成功生成 Markdown 评估报告

### Skill 5: 逻辑验证通过 ✅

- **模拟测试**: 所有逻辑测试通过（参数验证、选择器配置、函数签名、错误处理）
- **实际测试**: 需要手动安装 Playwright 和浏览器驱动

---

## 后续优化方向

### 功能扩展

- [ ] 接入真实 API（抖音官方 API、图片搜索 API、音乐库 API）
- [ ] 使用机器学习模型进行更精准的推荐
- [ ] 添加定时发布功能
- [ ] 添加内容管理功能（查看、编辑、删除）
- [ ] 添加数据统计功能（播放量、点赞数等）
- [ ] 支持批量发布

### 技术优化

- [ ] 添加日志系统
- [ ] 添加配置文件管理
- [ ] 添加错误重试机制
- [ ] 添加性能监控
- [ ] 添加单元测试框架

### 安全优化

- [ ] 添加账号安全检测
- [ ] 添加发布频率限制
- [ ] 添加内容合规检测
- [ ] 添加敏感词过滤

---

## 重要提示

1. **首次使用**: 需要手动扫码登录抖音账号
2. **发布频率**: 建议每天不超过 5 条，避免账号异常
3. **网页变更**: 如果抖音网页结构变更，需要更新选择器配置
4. **用户协议**: 请遵守抖音用户协议，本脚本仅供个人学习研究
5. **数据安全**: 不要在公共电脑上保存登录状态

---

## 项目亮点

1. **完整的创作流程**: 从标签推荐到内容发布，覆盖全流程
2. **模块化设计**: 5 个独立 Skill，易于维护和扩展
3. **智能推荐**: 基于关键词和热门标签的智能推荐算法
4. **内容评估**: 多维度评估内容质量，提供改进建议
5. **自动化发布**: Playwright 自动化操作，减少手动操作
6. **详细文档**: 每个模块都有详细的使用说明和测试脚本

---

## 技术栈

- **Python 3.7+**: 主要开发语言
- **Playwright**: 浏览器自动化工具
- **正则表达式**: 关键词提取和匹配
- **Markdown**: 评估报告格式
- **JSON**: 登录状态保存

---

## 开发者信息

- **项目类型**: 个人学习研究项目
- **开发目的**: 探索自动化内容创作和发布流程
- **使用限制**: 请遵守抖音用户协议，合理使用

---

## 联系和反馈

如有问题或建议，请通过以下方式联系：
- 项目文档: `skills/README_douyin_publisher.md`
- 测试脚本: `skills/test_publisher_logic.py`

---

**祝您使用愉快！** 🎉