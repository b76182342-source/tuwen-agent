"""
[已禁用] 抖音图文发布 Skill
本 Skill 已永久禁用。产品定位为创作顾问，不提供自动发布功能。
发布操作由用户手动完成（遵守抖音用户协议）。

以下代码保留仅供技术参考，不在 Agent 流水线中调用。

TODO: [架构] 当前文件保留作为技术参考，不删除。
      如需启用发布功能，需重新评估合规性、用户协议和技术可行性。
"""
import os
import time
import json
from datetime import datetime, timezone
from typing import List, Dict, Optional
from playwright.sync_api import sync_playwright, Page, BrowserContext, TimeoutError

from utils.config import PROJECT_ROOT, get_headless


# ============================================================================
# 可配置项
# ============================================================================
STATE_FILE = str(PROJECT_ROOT / "douyin_state.json")
CREATOR_URL = "https://creator.douyin.com/creator-micro/content/upload"
TIMEOUT = 60000
HEADLESS = get_headless()  # 从 HEADLESS 环境变量读取，默认 False（有头模式）
LOGIN_CONFIRM_WAIT = 3    # 登录确认等待（秒），从 10 秒缩减为 3 秒
STEP_CONFIRM_WAIT = 5     # 步骤间确认等待（秒），从 10 秒缩减为 5 秒
LOGIN_TIMEOUT = 120       # 扫码登录超时（秒）

# ============================================================================
# 选择器配置（网页结构变更时需要更新）
# ============================================================================
SELECTORS = {
    # 文案输入框
    "title_input": "textarea[placeholder*='标题']",
    "content_input": "textarea[placeholder*='文案']",
    
    # 图片上传
    "image_upload_input": "input[type='file'][accept*='image']",
    "image_mode_tab": "button:has-text('图文')",
    "video_mode_indicator": "button:has-text('视频')",
    
    # 标签
    "tag_input": "input[placeholder*='标签']",
    "tag_button": "button:has-text('#')",
    "tag_container": ".tag-input-container",
    
    # 发布按钮
    "publish_button": "button:has-text('发布')",
    "confirm_button": "button:has-text('确认')",
    
    # 成功提示
    "success_indicator": ".success-message",
    "content_manage_url": "https://creator.douyin.com/creator-micro/content/manage",
}


# ============================================================================
# 登录前置检查（独立于 publish 流程，可单独调用）
# ============================================================================

def check_login_status(force_check: bool = False) -> Dict:
    """
    前置检查抖音登录状态（轻量，不启动完整的 publish 流程）

    Args:
        force_check: 强制重新验证（即使 Cookie 未过期也打开浏览器确认）

    Returns:
        {"status": "valid"|"expired"|"missing"|"error",
         "message": "..."}

    使用方式：
        python skills/douyin_publisher.py --check-login
    """
    # Step 1: 检查文件是否存在
    if not os.path.exists(STATE_FILE):
        return {
            "status": "missing",
            "message": f"登录状态文件不存在 ({STATE_FILE})，首次使用需扫码登录"
        }

    # Step 2: 读取 Cookie 并检查过期时间
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            state = json.load(f)

        cookies = state.get("cookies", [])
        if not cookies:
            return {
                "status": "expired",
                "message": "登录状态文件中无 Cookie 数据"
            }

        now = datetime.now(timezone.utc).timestamp()
        expired_cookies = 0
        total_cookies = len(cookies)

        for cookie in cookies:
            expires = cookie.get("expires", -1)
            if expires > 0 and expires < now:
                expired_cookies += 1

        if expired_cookies > total_cookies * 0.5:
            return {
                "status": "expired",
                "message": f"超过半数 Cookie 已过期 ({expired_cookies}/{total_cookies})"
            }

    except (json.JSONDecodeError, KeyError) as e:
        return {
            "status": "error",
            "message": f"登录状态文件损坏: {e}"
        }

    # Step 3: 如需强制验证，打开浏览器做真实检测
    if force_check:
        return _verify_login_with_browser()

    # Cookie 检查通过
    return {
        "status": "valid",
        "message": f"登录状态有效 (Cookie 数量: {total_cookies}, 过期: {expired_cookies})"
    }


def _verify_login_with_browser() -> Dict:
    """
    启动轻量浏览器验证登录状态（不进入发布流程）

    如果无效，引导用户扫码登录并保存新的 Cookie。
    """
    print("\n" + "=" * 60)
    print("[前置] 启动浏览器验证登录状态...")
    print("=" * 60)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=HEADLESS)

            if os.path.exists(STATE_FILE):
                try:
                    context = browser.new_context(storage_state=STATE_FILE)
                    print(f"[前置] 已加载登录状态: {STATE_FILE}")
                except Exception:
                    context = browser.new_context()
                    print("[前置] 状态文件无效，创建新上下文")
            else:
                context = browser.new_context()

            page = context.new_page()

            try:
                page.goto(CREATOR_URL, timeout=TIMEOUT, wait_until="domcontentloaded")
            except TimeoutError:
                print("[前置] 页面加载超时，尝试继续...")
                time.sleep(3)

            current_url = page.url

            if "login" not in current_url and "passport" not in current_url:
                print(f"[前置] [OK] 登录状态有效 -> {current_url}")
                context.storage_state(path=STATE_FILE)
                browser.close()
                return {"status": "valid", "message": "登录状态有效"}

            # 需要扫码
            print("\n" + "=" * 60)
            print("[前置] 请使用抖音 App 扫码登录")
            print("=" * 60)

            # 等待扫码（最多 LOGIN_TIMEOUT 秒）
            for i in range(LOGIN_TIMEOUT):
                time.sleep(1)
                current_url = page.url
                if "login" not in current_url and "passport" not in current_url:
                    print(f"\n[前置] [OK] 登录成功！耗时 {i + 1} 秒")

                    # 用户确认
                    print(f"\n[确认] 请在浏览器中确认登录状态")
                    print(f"[确认] 当前页面: {current_url}")
                    print(f"[确认] 等待 {LOGIN_CONFIRM_WAIT} 秒...")
                    time.sleep(LOGIN_CONFIRM_WAIT)

                    context.storage_state(path=STATE_FILE)
                    print(f"[前置] 登录状态已保存到: {STATE_FILE}")
                    browser.close()
                    return {"status": "valid", "message": "登录成功"}

                if i % 15 == 0 and i > 0:
                    print(f"[前置] 等待扫码... ({i}/{LOGIN_TIMEOUT}秒)")

            browser.close()
            return {
                "status": "expired",
                "message": f"扫码超时（{LOGIN_TIMEOUT}秒内未完成登录）"
            }

    except Exception as e:
        return {"status": "error", "message": str(e)}


def _ensure_login(context: BrowserContext, page: Page) -> bool:
    """
    检查并确保登录状态
    
    Args:
        context: 浏览器上下文
        page: 页面对象
    
    Returns:
        是否成功登录
    
    流程：
        1. 检查是否存在 douyin_state.json 登录状态文件
        2. 如果存在且有效（页面能跳转到创作首页），直接复用
        3. 如果无效，提示用户扫码登录，等待后保存状态
        4. 登录成功后，等待用户确认登录状态
    """
    try:
        # 检查是否存在登录状态文件
        if os.path.exists(STATE_FILE):
            print(f"[登录] 发现登录状态文件: {STATE_FILE}")
            print("[登录] 尝试复用登录状态...")
            
            # 尝试访问创作者页面
            try:
                page.goto(CREATOR_URL, timeout=TIMEOUT, wait_until="domcontentloaded")
            except TimeoutError:
                print("[登录] 页面加载超时，尝试继续...")
                # 即使超时，也可能已经加载了关键元素，继续尝试
                time.sleep(5)
            except Exception as e:
                print(f"[登录] 页面访问出错: {e}")
                return False
            
            time.sleep(2)
            
            # 检查是否跳转到登录页
            current_url = page.url
            if "login" not in current_url and "passport" not in current_url:
                print("[登录] 登录状态有效，已自动登录")
                
                # ===== 登录状态确认断点 =====
                print("\n" + "="*60)
                print("[确认] 请确认浏览器中是否已成功登录到抖音创作者后台")
                print("[确认] 当前页面URL: " + current_url)
                print(f"[确认] 等待 {LOGIN_CONFIRM_WAIT} 秒后自动继续...")
                print("[确认] 如果未登录，请手动关闭浏览器并重新运行脚本")
                print("="*60)
                
                time.sleep(LOGIN_CONFIRM_WAIT)

                return True
            else:
                print("[登录] 登录状态已过期，需要重新登录")

        # 需要重新登录
        print("\n" + "="*60)
        print("请使用抖音 App 扫码登录")
        print("="*60)
        print("[登录] 等待扫码登录...")

        # 打开登录页面
        try:
            page.goto(CREATOR_URL, timeout=TIMEOUT, wait_until="domcontentloaded")
        except TimeoutError:
            print("[登录] 页面加载超时，尝试继续...")
            time.sleep(5)
        except Exception as e:
            print(f"[登录] 页面访问出错: {e}")
            return False

        # 等待用户扫码登录（最多等待 LOGIN_TIMEOUT 秒）
        login_success = False
        for i in range(LOGIN_TIMEOUT):
            time.sleep(1)
            current_url = page.url

            if "login" not in current_url and "passport" not in current_url:
                login_success = True
                print(f"\n[登录] 登录成功！耗时 {i+1} 秒")
                break

            if i % 15 == 0 and i > 0:
                print(f"[登录] 等待扫码... ({i}/{LOGIN_TIMEOUT}秒)")

        if not login_success:
            print("\n[登录] 登录超时，请重试")
            return False

        # ===== 登录状态确认断点 =====
        print("\n" + "="*60)
        print("[确认] 请确认浏览器中是否已成功登录到抖音创作者后台")
        print("[确认] 当前页面URL: " + page.url)
        print(f"[确认] 等待 {LOGIN_CONFIRM_WAIT} 秒后自动继续...")
        print("[确认] 如果登录失败，请手动关闭浏览器并重新运行脚本")
        print("="*60)

        time.sleep(LOGIN_CONFIRM_WAIT)
        
        # 保存登录状态
        print("[登录] 保存登录状态...")
        context.storage_state(path=STATE_FILE)
        print(f"[登录] 登录状态已保存到: {STATE_FILE}")
        
        return True
        
    except Exception as e:
        print(f"[登录] 登录过程出错: {e}")
        return False


def _switch_to_image_mode(page: Page) -> bool:
    """
    检测并切换到图文模式
    
    Args:
        page: 页面对象
    
    Returns:
        是否成功切换或已是图文模式
    
    流程：
        1. 检测当前是否为视频上传模式
        2. 如果是，点击切换到"图文"模式标签
        3. 如果已经是图文模式或找不到切换按钮，继续执行
    """
    try:
        print("[模式] 检测当前上传模式...")
        
        # 等待页面加载
        time.sleep(2)
        
        # 尝试多种方式检测视频模式
        video_mode_selectors = [
            SELECTORS["video_mode_indicator"],
            "button:has-text('视频')",
            "[class*='video']",
            "[class*='Video']",
        ]
        
        video_mode = None
        for selector in video_mode_selectors:
            try:
                video_mode = page.query_selector(selector)
                if video_mode:
                    print(f"[模式] 检测到视频模式指示器: {selector}")
                    break
            except Exception as e:
                continue
        
        if video_mode:
            print("[模式] 当前为视频模式，尝试切换到图文模式...")
            
            # 尝试多种方式查找图文模式切换按钮
            image_mode_selectors = [
                SELECTORS["image_mode_tab"],
                "button:has-text('图文')",
                "button:has-text('图片')",
                "[class*='image']",
                "[class*='Image']",
                "[data-tab*='image']",
                "[data-tab*='picture']",
            ]
            
            image_mode_tab = None
            for selector in image_mode_selectors:
                try:
                    image_mode_tab = page.query_selector(selector)
                    if image_mode_tab:
                        print(f"[模式] 找到图文模式切换按钮: {selector}")
                        break
                except Exception as e:
                    continue
            
            if image_mode_tab:
                image_mode_tab.click()
                time.sleep(3)
                print("[模式] 已切换到图文模式")
                return True
            else:
                print("[模式] 未找到图文模式切换按钮，继续执行")
                return True
        else:
            print("[模式] 已是图文模式或无需切换")
            return True
            
    except Exception as e:
        print(f"[模式] 模式切换出错: {e}")
        return True  # 继续执行


def _safe_click(page: Page, selector: str, timeout: int = 10000) -> bool:
    """
    安全点击，等待元素可见后再点击
    
    Args:
        page: 页面对象
        selector: 元素选择器
        timeout: 超时时间（毫秒）
    
    Returns:
        是否成功点击
    
    异常：
        如果超时，抛出异常并指明哪一步失败
    """
    try:
        # 等待元素可见
        element = page.wait_for_selector(selector, timeout=timeout, state="visible")
        
        # 点击元素
        element.click()
        return True
        
    except TimeoutError:
        raise TimeoutError(f"元素未找到或不可见: {selector}")
    except Exception as e:
        raise Exception(f"点击失败: {selector}, 错误: {e}")


def _fill_text(page: Page, text: str) -> Dict:
    """
    步骤 1: 填写文案
    
    Args:
        page: 页面对象
        text: 文案内容
    
    Returns:
        结果字典
    """
    try:
        print("\n[步骤1] 填写文案...")
        
        # ===== 步骤1断点：等待用户确认页面已加载 =====
        print("\n" + "="*60)
        print("[确认] 请在浏览器中确认页面已完全加载")
        print(f"[确认] 等待 {STEP_CONFIRM_WAIT} 秒后自动继续...")
        print("="*60)
        time.sleep(10)
        
        # 尝试多个可能的文案输入框
        selectors_to_try = [
            SELECTORS["title_input"],
            SELECTORS["content_input"],
            "textarea",
            "textarea[placeholder]",
            "input[type='text']",
            "input[placeholder]",
            "div[contenteditable='true']",
            "[contenteditable='true']",
        ]
        
        text_input = None
        for selector in selectors_to_try:
            try:
                text_input = page.wait_for_selector(selector, timeout=3000, state="visible")
                if text_input:
                    print(f"[步骤1] 找到文案输入框: {selector}")
                    break
            except Exception:
                continue
        
        if not text_input:
            # 输出页面调试信息
            print("\n[调试] 尝试获取页面 HTML 结构...")
            try:
                # 打印所有文本输入元素
                all_textareas = page.query_selector_all("textarea")
                print(f"[调试] 发现 {len(all_textareas)} 个 textarea 元素")
                for i, el in enumerate(all_textareas):
                    placeholder = el.get_attribute("placeholder")
                    print(f"  [{i}] placeholder='{placeholder}'")
                
                all_inputs = page.query_selector_all("input[type='text']")
                print(f"[调试] 发现 {len(all_inputs)} 个 input[type='text'] 元素")
                for i, el in enumerate(all_inputs):
                    placeholder = el.get_attribute("placeholder")
                    print(f"  [{i}] placeholder='{placeholder}'")
                
                all_editable = page.query_selector_all("[contenteditable='true']")
                print(f"[调试] 发现 {len(all_editable)} 个 contenteditable 元素")
                
                # 获取页面标题
                title = page.title()
                print(f"[调试] 页面标题: {title}")
                
                # 获取当前 URL
                print(f"[调试] 当前 URL: {page.url}")
                
            except Exception as e:
                print(f"[调试] 获取页面信息失败: {e}")
            
            return {
                "status": "failed",
                "message": "未找到文案输入框。请手动在页面中定位文案输入框。",
                "step": "填写文案"
            }
        
        # 清空已有内容
        text_input.fill("")
        time.sleep(0.5)
        
        # 填入文案
        text_input.fill(text)
        time.sleep(1)
        
        # ===== 步骤1断点：填写文案后确认 =====
        print("\n" + "="*60)
        print(f"[确认] 文案已填写: {text[:50]}...")
        print("[确认] 请在浏览器中确认文案是否已正确填入")
        print(f"[确认] 等待 {STEP_CONFIRM_WAIT} 秒后自动继续...")
        print("[确认] 如果有问题，请手动修改")
        print("="*60)
        time.sleep(STEP_CONFIRM_WAIT)
        
        return {"status": "success"}
        
    except Exception as e:
        return {
            "status": "failed",
            "message": str(e),
            "step": "填写文案"
        }


def _upload_images(page: Page, image_paths: List[str]) -> Dict:
    """
    步骤 2: 上传图片
    
    Args:
        page: 页面对象
        image_paths: 图片路径列表
    
    Returns:
        结果字典
    """
    try:
        print("\n[步骤2] 上传图片...")
        
        # 切换到图文模式
        _switch_to_image_mode(page)
        
        # ===== 步骤2断点：切换模式后确认 =====
        print("\n" + "="*60)
        print("[确认] 请在浏览器中确认当前模式是否为图文模式")
        print("[确认] 如果不是，请手动切换到图文模式")
        print(f"[确认] 等待 {STEP_CONFIRM_WAIT} 秒后自动继续...")
        print("="*60)
        time.sleep(10)
        
        # 等待页面完全加载
        time.sleep(3)
        
        # 尝试多种方式查找文件上传 input
        upload_input = None
        selectors_to_try = [
            SELECTORS["image_upload_input"],
            "input[type='file']",
            "input[type='file'][accept='image/*']",
            "input[type='file'][accept*='.jpg']",
            "input[type='file'][accept*='.png']",
            "input[type='file'][accept*='.jpeg']",
            ".upload-container input[type='file']",
            ".image-upload input[type='file']",
            ".upload-area input[type='file']",
        ]
        
        print("[步骤2] 尝试查找文件上传输入框...")
        
        for selector in selectors_to_try:
            try:
                upload_input = page.query_selector(selector)
                if upload_input:
                    print(f"[步骤2] 找到文件上传输入框: {selector}")
                    break
            except Exception as e:
                continue
        
        # 如果还是找不到，尝试查找所有 input[type='file'] 元素
        if not upload_input:
            print("[步骤2] 尝试查找所有文件上传输入框...")
            all_file_inputs = page.query_selector_all("input[type='file']")
            if all_file_inputs:
                print(f"[步骤2] 找到 {len(all_file_inputs)} 个文件上传输入框")
                # 选择第一个 accept 包含 image 的
                for input_el in all_file_inputs:
                    accept = input_el.get_attribute("accept")
                    if accept and ("image" in accept or "jpg" in accept or "png" in accept):
                        upload_input = input_el
                        print(f"[步骤2] 选择 accept='{accept}' 的输入框")
                        break
                    
                    # 如果没有找到 image 类型的，选择第一个
                    if not upload_input:
                        upload_input = all_file_inputs[0]
                        print("[步骤2] 选择第一个文件上传输入框")
        
        # 如果仍然找不到，尝试点击上传区域
        if not upload_input:
            print("[步骤2] 尝试查找上传区域并点击...")
            upload_area_selectors = [
                ".upload-area",
                ".upload-container",
                ".image-upload",
                "[class*='upload']",
                "[class*='Upload']",
                "button:has-text('上传')",
                "button:has-text('添加')",
                "div:has-text('上传图片')",
                "div:has-text('添加图片')",
            ]
            
            for selector in upload_area_selectors:
                try:
                    upload_area = page.query_selector(selector)
                    if upload_area:
                        print(f"[步骤2] 找到上传区域: {selector}")
                        upload_area.click()
                        time.sleep(2)
                        
                        # 再次尝试查找文件上传输入框
                        upload_input = page.query_selector("input[type='file']")
                        if upload_input:
                            print("[步骤2] 点击上传区域后找到文件上传输入框")
                            break
                except Exception as e:
                    continue
        
        # 如果还是找不到，尝试点击页面上的按钮触发上传
        if not upload_input:
            print("[步骤2] 尝试查找可能触发上传的按钮...")
            trigger_selectors = [
                "button[aria-label*='上传']",
                "button[aria-label*='添加']",
                "[data-testid*='upload']",
            ]
            
            for selector in trigger_selectors:
                try:
                    trigger = page.query_selector(selector)
                    if trigger:
                        print(f"[步骤2] 找到触发按钮: {selector}")
                        trigger.click()
                        time.sleep(2)
                        
                        upload_input = page.query_selector("input[type='file']")
                        if upload_input:
                            print("[步骤2] 点击触发按钮后找到文件上传输入框")
                            break
                except Exception as e:
                    continue
        
        if not upload_input:
            # 输出页面调试信息
            print("[步骤2] 调试信息 - 页面上所有 input[type='file']:")
            try:
                all_inputs = page.query_selector_all("input[type='file']")
                for i, inp in enumerate(all_inputs):
                    accept = inp.get_attribute("accept")
                    visible = inp.is_visible()
                    print(f"  [{i}] accept='{accept}', visible={visible}")
            except Exception:
                pass
            
            # 输出可能的点击元素
            print("[步骤2] 调试信息 - 页面上可能的点击元素:")
            try:
                all_buttons = page.query_selector_all("button")
                for i, btn in enumerate(all_buttons[:20]):  # 最多显示20个
                    text = btn.inner_text()
                    print(f"  [{i}] button: '{text[:30]}'")
            except Exception:
                pass
            
            return {
                "status": "failed",
                "message": "未找到图片上传输入框。请检查抖音网页结构是否变更，或手动在页面上查找上传按钮。",
                "step": "上传图片"
            }
        
        # 准备图片路径（转换为绝对路径）
        abs_paths = []
        for path in image_paths:
            abs_path = os.path.abspath(path)
            if not os.path.exists(abs_path):
                return {
                    "status": "failed",
                    "message": f"图片文件不存在: {abs_path}",
                    "step": "上传图片"
                }
            abs_paths.append(abs_path)
        
        print(f"[步骤2] 准备上传 {len(abs_paths)} 张图片...")
        
        # 上传所有图片
        upload_input.set_input_files(abs_paths)
        
        # 等待图片上传完成（等待缩略图出现）
        print("[步骤2] 等待图片上传完成...")
        time.sleep(5)
        
        # ===== 步骤2断点：上传图片后确认 =====
        print("\n" + "="*60)
        print(f"[确认] 已尝试上传 {len(abs_paths)} 张图片")
        print("[确认] 请在浏览器中确认图片是否已成功上传")
        print(f"[确认] 等待 {STEP_CONFIRM_WAIT} 秒后自动继续...")
        print("[确认] 如果上传失败，请手动上传")
        print("="*60)
        time.sleep(10)
        
        # 检查是否有图片缩略图
        thumbnails = page.query_selector_all(
            ".image-thumbnail, .upload-item, img[src*='blob'], "
            ".preview-image, .image-preview, [class*='thumbnail'] img"
        )
        
        if len(thumbnails) >= len(image_paths):
            print(f"[步骤2] 图片上传成功，共 {len(thumbnails)} 张")
            return {"status": "success"}
        else:
            # 再等待一段时间
            time.sleep(5)
            thumbnails = page.query_selector_all(
                ".image-thumbnail, .upload-item, img[src*='blob'], "
                ".preview-image, .image-preview, [class*='thumbnail'] img"
            )
            
            if len(thumbnails) >= len(image_paths):
                print(f"[步骤2] 图片上传成功，共 {len(thumbnails)} 张")
                return {"status": "success"}
            else:
                # 虽然缩略图数量不够，但让用户手动确认
                print(f"[步骤2] 检测到 {len(thumbnails)} 个缩略图，期望 {len(image_paths)} 个")
                print("[步骤2] 继续执行，用户已手动确认")
                return {"status": "success"}
        
    except Exception as e:
        return {
            "status": "failed",
            "message": str(e),
            "step": "上传图片"
        }


def _add_tags(page: Page, tags: List[str]) -> Dict:
    """
    步骤 3: 填入标签
    
    Args:
        page: 页面对象
        tags: 标签列表
    
    Returns:
        结果字典
    """
    try:
        print("\n[步骤3] 添加标签...")
        
        # ===== 步骤3断点：等待用户确认页面状态 =====
        print("\n" + "="*60)
        print("[确认] 请在浏览器中确认当前页面状态")
        print(f"[确认] 等待 {STEP_CONFIRM_WAIT} 秒后自动继续...")
        print("="*60)
        time.sleep(STEP_CONFIRM_WAIT)
        
        # 尝试查找标签输入框
        tag_input = None
        selectors_to_try = [
            SELECTORS["tag_input"],
            "input[placeholder*='标签']",
            "input[placeholder*='话题']",
            "input[placeholder*='#']",
            "input[placeholder*='添加']",
            SELECTORS["tag_container"],
        ]
        
        for selector in selectors_to_try:
            try:
                tag_input = page.wait_for_selector(selector, timeout=3000, state="visible")
                if tag_input:
                    print(f"[步骤3] 找到标签输入框: {selector}")
                    break
            except Exception:
                continue
        
        # 如果找不到，尝试点击 "#" 按钮
        if not tag_input:
            print("[步骤3] 未找到标签输入框，尝试点击 # 按钮...")
            try:
                tag_button = page.query_selector(SELECTORS["tag_button"])
                if not tag_button:
                    # 尝试其他按钮
                    all_buttons = page.query_selector_all("button")
                    for btn in all_buttons:
                        text = btn.inner_text()
                        if "#" in text or "标签" in text or "话题" in text:
                            tag_button = btn
                            print(f"[步骤3] 找到 # 相关按钮: '{text}'")
                            break
                
                if tag_button:
                    tag_button.click()
                    time.sleep(2)
                    
                    # 再次尝试查找标签输入框
                    for selector in selectors_to_try:
                        try:
                            tag_input = page.query_selector(selector)
                            if tag_input:
                                print(f"[步骤3] 点击按钮后找到标签输入框: {selector}")
                                break
                        except Exception:
                            continue
            except Exception as e:
                print(f"[步骤3] 点击按钮失败: {e}")
        
        if not tag_input:
            # 输出调试信息
            print("[步骤3] 调试信息 - 页面上可能的标签输入位置:")
            try:
                all_inputs = page.query_selector_all("input")
                for i, inp in enumerate(all_inputs[:15]):
                    placeholder = inp.get_attribute("placeholder")
                    print(f"  [{i}] placeholder='{placeholder}'")
            except Exception:
                pass
            
            print("[步骤3] 未找到标签输入框，跳过标签添加")
            return {"status": "success"}  # 标签可选，不影响发布
        
        # 逐个添加标签
        for i, tag in enumerate(tags):
            try:
                # 清空输入框
                tag_input.fill("")
                time.sleep(0.3)
                
                # 输入标签（去掉 # 号）
                tag_clean = tag.replace("#", "")
                tag_input.fill(tag_clean)
                time.sleep(0.5)
                
                # 按回车或逗号确认
                tag_input.press("Enter")
                time.sleep(0.5)
                
                print(f"[步骤3] 已添加标签: #{tag_clean}")
            except Exception as e:
                print(f"[步骤3] 添加标签失败: {e}")
        
        # ===== 步骤3断点：添加标签后确认 =====
        print("\n" + "="*60)
        print(f"[确认] 已尝试添加 {len(tags)} 个标签")
        print("[确认] 请在浏览器中确认标签是否已正确添加")
        print(f"[确认] 等待 {STEP_CONFIRM_WAIT} 秒后自动继续...")
        print("[确认] 如果有问题，请手动修改")
        print("="*60)
        time.sleep(STEP_CONFIRM_WAIT)
        
        return {"status": "success"}
        
    except Exception as e:
        print(f"[步骤3] 标签添加出错: {e}")
        return {"status": "success"}  # 标签可选，继续执行


def _click_publish(page: Page) -> Dict:
    """
    步骤 4: 点击发布
    
    Args:
        page: 页面对象
    
    Returns:
        结果字典
    """
    try:
        print("\n[步骤4] 点击发布...")
        
        # ===== 步骤4断点：等待用户确认页面状态 =====
        print("\n" + "="*60)
        print("[确认] 请在浏览器中确认当前页面状态")
        print("[确认] 检查：文案、图片、标签是否都已填写完成")
        print(f"[确认] 等待 {STEP_CONFIRM_WAIT} 秒后自动继续...")
        print("="*60)
        time.sleep(10)
        
        # 查找发布按钮
        publish_button = None
        selectors_to_try = [
            SELECTORS["publish_button"],
            "button:has-text('发布')",
            "button:has-text('发表')",
            "button.publish-btn",
            "button[type='submit']",
            "button.primary",
            "button[class*='publish']",
            "button[class*='submit']",
        ]
        
        for selector in selectors_to_try:
            try:
                publish_button = page.wait_for_selector(selector, timeout=3000, state="visible")
                if publish_button:
                    print(f"[步骤4] 找到发布按钮: {selector}")
                    break
            except Exception:
                continue
        
        # 如果找不到，输出调试信息
        if not publish_button:
            print("[步骤4] 调试信息 - 页面上所有按钮:")
            try:
                all_buttons = page.query_selector_all("button")
                for i, btn in enumerate(all_buttons[:20]):
                    text = btn.inner_text()
                    classes = btn.get_attribute("class")
                    print(f"  [{i}] text='{text[:30]}', class='{classes}'")
            except Exception:
                pass
            
            return {
                "status": "failed",
                "message": "未找到发布按钮。请手动点击发布按钮完成发布。",
                "step": "点击发布"
            }
        
        # ===== 步骤4断点：发布前最终确认 =====
        print("\n" + "="*60)
        print("[确认] 即将点击发布按钮！")
        print("[确认] 请最后一次确认所有内容是否正确")
        print(f"[确认] 等待 {STEP_CONFIRM_WAIT} 秒后自动点击发布...")
        print("[确认] 如果需要取消，请手动关闭浏览器")
        print("="*60)
        time.sleep(10)
        
        # 点击发布按钮
        publish_button.click()
        time.sleep(2)
        
        # ===== 步骤4断点：点击发布后确认 =====
        print("\n" + "="*60)
        print("[确认] 已点击发布按钮")
        print("[确认] 请在浏览器中确认发布结果")
        print("[确认] 如果出现确认弹窗，请手动确认...")
        print(f"[确认] 等待 {STEP_CONFIRM_WAIT} 秒后检查发布状态...")
        print("="*60)
        time.sleep(10)
        
        # 处理可能的二次确认弹窗
        confirm_button = page.query_selector(SELECTORS["confirm_button"])
        if confirm_button:
            print("[步骤4] 发现确认弹窗，点击确认...")
            confirm_button.click()
            time.sleep(2)
        
        # 等待页面跳转到内容管理页或出现成功提示
        print("[步骤4] 检查发布结果...")
        
        for i in range(15):
            current_url = page.url
            
            # 检查是否跳转到内容管理页
            if "manage" in current_url or "content" in current_url:
                print(f"[步骤4] 发布成功！已跳转到: {current_url}")
                return {"status": "success"}
            
            # 检查是否有成功提示
            success_selectors = [
                SELECTORS["success_indicator"],
                ".success",
                ".success-message",
                "[class*='success']",
                "text=发布成功",
            ]
            
            for sel in success_selectors:
                try:
                    success_msg = page.query_selector(sel)
                    if success_msg:
                        print("[步骤4] 发布成功！")
                        return {"status": "success"}
                except Exception:
                    pass
            
            time.sleep(1)
        
        # ===== 步骤4断点：发布状态最终确认 =====
        print("\n" + "="*60)
        print("[确认] 无法自动检测发布结果")
        print("[确认] 请在浏览器中手动确认发布是否成功")
        print(f"[确认] 等待 {STEP_CONFIRM_WAIT} 秒后继续...")
        print("[确认] 如果发布失败，请按 Ctrl+C 关闭并重新运行")
        print("="*60)
        time.sleep(10)
        
        return {"status": "success"}
        
    except Exception as e:
        return {
            "status": "failed",
            "message": str(e),
            "step": "点击发布"
        }


def publish(text: str, image_paths: List[str], tags: List[str]) -> Dict:
    """
    主函数：发布图文内容到抖音
    
    Args:
        text: 最终文案
        image_paths: 本地图片路径列表（至少 1 张，最多 6 张）
        tags: 标签列表（如 ["猫咪日常", "萌宠"]）
    
    Returns:
        结果字典：
        - {"status": "success", "message": "发布成功"}
        - {"status": "failed", "message": "错误描述", "step": "步骤名"}
    
    流程：
        1. 填写文案
        2. 上传图片
        3. 填入标签
        4. 点击发布
    """
    print("\n" + "="*60)
    print("抖音图文发布 - 开始")
    print("="*60)
    print(f"文案: {text[:50]}...")
    print(f"图片: {len(image_paths)} 张")
    print(f"标签: {len(tags)} 个")
    print("="*60)
    
    # 参数验证
    if not text:
        return {
            "status": "failed",
            "message": "文案不能为空",
            "step": "参数验证"
        }
    
    if not image_paths:
        return {
            "status": "failed",
            "message": "图片列表不能为空",
            "step": "参数验证"
        }
    
    if len(image_paths) > 6:
        return {
            "status": "failed",
            "message": "图片数量超过限制（最多 6 张）",
            "step": "参数验证"
        }
    
    # 启动浏览器
    print("\n[启动] 正在启动浏览器...")
    
    with sync_playwright() as p:
        try:
            # 启动浏览器（有头模式）
            browser = p.chromium.launch(headless=HEADLESS)
            
            # 创建上下文（尝试加载登录状态）
            context = None
            if os.path.exists(STATE_FILE):
                try:
                    context = browser.new_context(storage_state=STATE_FILE)
                    print(f"[启动] 已加载登录状态: {STATE_FILE}")
                except Exception:
                    context = browser.new_context()
                    print("[启动] 登录状态文件无效，创建新上下文")
            else:
                context = browser.new_context()
                print("[启动] 创建新浏览器上下文")
            
            # 创建页面
            page = context.new_page()
            
            # 确保登录
            if not _ensure_login(context, page):
                browser.close()
                return {
                    "status": "failed",
                    "message": "登录失败或超时",
                    "step": "登录"
                }
            
            # 步骤 1: 填写文案
            result1 = _fill_text(page, text)
            if result1["status"] == "failed":
                browser.close()
                return result1
            
            # 步骤 2: 上传图片
            result2 = _upload_images(page, image_paths)
            if result2["status"] == "failed":
                browser.close()
                return result2
            
            # 步骤 3: 填入标签
            result3 = _add_tags(page, tags)
            if result3["status"] == "failed":
                browser.close()
                return result3
            
            # 步骤 4: 点击发布
            result4 = _click_publish(page)
            if result4["status"] == "failed":
                browser.close()
                return result4
            
            # 发布成功
            print("\n" + "="*60)
            print("发布成功！")
            print("="*60)
            
            # 保存登录状态（以防万一）
            try:
                context.storage_state(path=STATE_FILE)
            except Exception:
                pass
            
            # 关闭浏览器
            browser.close()
            
            return {
                "status": "success",
                "message": "发布成功"
            }
            
        except Exception as e:
            return {
                "status": "failed",
                "message": str(e),
                "step": "未知错误"
            }


# ============================================================================
# TODO: 可扩展功能
# ============================================================================
# - 定时发布：添加 schedule 参数，在指定时间发布
# - 定时删除：添加 auto_delete 参数，在指定时间自动删除内容
# - 内容管理：添加查看、编辑、删除已发布内容的功能
# - 数据统计：添加查看内容数据（播放量、点赞数等）的功能
# - 批量发布：支持批量发布多条内容
# - 发布预览：在发布前预览内容效果


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="抖音图文发布")
    parser.add_argument("text", nargs="?", help="文案内容")
    parser.add_argument("images", nargs="?", help="图片路径，逗号分隔")
    parser.add_argument("tags", nargs="?", help="标签，逗号分隔")
    parser.add_argument("--check-login", action="store_true",
                        help="前置检查登录状态（不发布内容）")
    parser.add_argument("--force-check", action="store_true",
                        help="强制浏览器验证登录（配合 --check-login）")

    args = parser.parse_args()

    # --check-login 模式：仅检查登录状态，不发布
    if args.check_login:
        result = check_login_status(force_check=args.force_check)
        print(f"\n{'='*60}")
        print(f"登录状态: {result['status']}")
        print(f"详情: {result['message']}")
        print(f"{'='*60}")

        if result["status"] != "valid":
            print("\n[提示] 登录状态无效，请运行以下命令重新登录：")
            print("  python skills/douyin_publisher.py --check-login --force-check")
            sys.exit(1)
        else:
            print("\n[OK] 登录状态有效，可以进行发布")
            sys.exit(0)

    # 发布模式：需要完整参数
    if not args.text or not args.images or not args.tags:
        print("\n使用方法:")
        print("  python skills/douyin_publisher.py <文案> <图片路径> <标签>")
        print("  python skills/douyin_publisher.py --check-login           # 检查登录状态")
        print("\n示例:")
        print("  python skills/douyin_publisher.py \"测试文案\" \"img1.jpg,img2.jpg\" \"标签1,标签2\"")
        print("\n注意:")
        print("  - 图片路径用逗号分隔，最多 6 张")
        print("  - 标签用逗号分隔")
        print("  - 首次使用请先运行: python skills/douyin_publisher.py --check-login --force-check")
        sys.exit(1)

    # 发布前先检查登录
    login_status = check_login_status()
    if login_status["status"] != "valid":
        print(f"\n[警告] 登录状态异常: {login_status['message']}")
        print("[提示] 正在尝试重新登录...")
        login_status = check_login_status(force_check=True)
        if login_status["status"] != "valid":
            print(f"\n[错误] 登录失败: {login_status['message']}")
            sys.exit(1)

    # 解析参数并发布
    text = args.text
    image_paths = args.images.split(",")
    tags = args.tags.split(",")

    result = publish(text, image_paths, tags)

    print("\n最终结果:")
    print(json.dumps(result, indent=2, ensure_ascii=False))

    if result["status"] == "success":
        print("\n[OK] 发布成功！")
    else:
        print(f"\n[FAIL] 发布失败: {result['message']}")
        print(f"失败步骤: {result.get('step', '未知')}")