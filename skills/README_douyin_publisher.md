# 通用图文发布 Skill - 安装和使用说明

## 环境要求

- Python 3.7+
- Playwright 浏览器自动化工具

## 安装步骤

### 1. 安装 Python 依赖

```bash
pip install playwright
```

### 2. 安装浏览器驱动

```bash
python -m playwright install chromium
```

如果安装失败，可以尝试：
```bash
playwright install chromium
```

或者安装所有浏览器：
```bash
playwright install
```

### 3. 验证安装

```bash
python -c "from playwright.sync_api import sync_playwright; print('Playwright 安装成功')"
```

## 使用方法

### 基本用法

```bash
python skills/douyin_publisher.py <文案> <图片路径列表> <标签列表>
```

### 示例

```bash
python skills/douyin_publisher.py "测试文案" "img1.jpg,img2.jpg" "标签1,标签2"
```

### 参数说明

- **文案**: 最终发布的文案内容
- **图片路径列表**: 本地图片路径，用逗号分隔（最多 6 张）
- **标签列表**: 标签内容，用逗号分隔

## 重要提示

### 首次使用

1. **首次运行会打开浏览器窗口**
2. **需要手动扫码登录抖音账号**
3. **登录状态会保存在 `douyin_state.json` 文件中**
4. **下次运行无需重复扫码**

### 使用频率

- 发布频率不宜过高，建议每天不超过 5 条
- 合理控制使用频率，避免账号异常

### 网页结构变更

如果抖音网页结构变更导致脚本失效，需要更新 `SELECTORS` 配置字典中的选择器。

### 用户协议

请遵守抖音用户协议，本脚本仅供个人学习研究使用。

## 发布流程

脚本会按照以下四个步骤执行：

1. **填写文案** - 定位文案输入框并填入文本
2. **上传图片** - 使用文件上传 input 上传所有图片
3. **填入标签** - 逐个添加标签
4. **点击发布** - 点击发布按钮并处理确认弹窗

## 错误处理

如果发布失败，脚本会返回具体的错误信息：

```python
{
  "status": "failed",
  "message": "错误描述",
  "step": "失败步骤"
}
```

常见失败场景：

- **登录状态过期** → 提示重新扫码
- **找不到元素** → 提示手动检查网页结构
- **上传超时** → 提示检查图片大小和网络

## 配置项

可以在文件顶部修改以下配置：

```python
STATE_FILE = "douyin_state.json"  # 登录状态文件
CREATOR_URL = "https://creator.douyin.com/creator-micro/content/upload"
TIMEOUT = 30000  # 默认超时时间（毫秒）
HEADLESS = False  # 是否使用无头模式
```

## 可扩展功能（TODO）

- [ ] 定时发布功能
- [ ] 定时删除功能
- [ ] 内容管理功能
- [ ] 数据统计功能
- [ ] 批量发布功能
- [ ] 发布预览功能

## 故障排查

### 问题 1: ImportError: DLL load failed

**原因**: greenlet 或 Playwright 安装不完整

**解决方案**:
```bash
pip uninstall greenlet playwright -y
pip install playwright
python -m playwright install chromium
```

### 问题 2: 浏览器无法启动

**原因**: 浏览器驱动未安装

**解决方案**:
```bash
python -m playwright install chromium
```

### 问题 3: 登录状态失效

**原因**: 登录状态文件过期或损坏

**解决方案**:
- 删除 `douyin_state.json` 文件
- 重新运行脚本，扫码登录

### 问题 4: 元素定位失败

**原因**: 抖音网页结构变更

**解决方案**:
- 手动检查网页结构
- 更新 `SELECTORS` 配置字典中的选择器

## 技术架构

```
douyin_publisher.py
├── publish()              # 主函数
├── _ensure_login()        # 登录状态管理
├── _switch_to_image_mode() # 模式切换
├── _safe_click()          # 安全点击
├── _fill_text()           # 步骤1: 填写文案
├── _upload_images()       # 步骤2: 上传图片
├── _add_tags()            # 步骤3: 填入标签
└── _click_publish()       # 步骤4: 点击发布
```

## 安全提示

- 不要在公共电脑上保存登录状态
- 定期清理登录状态文件
- 不要分享登录状态文件给他人
- 使用完毕后关闭浏览器窗口