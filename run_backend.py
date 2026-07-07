"""
抖音创作顾问 Agent — 后端启动脚本

在 PyCharm 中右键 → Run 'run_backend' 即可启动。
自动清理端口占用，启动后保持运行。
"""
import os
import sys
import io
import socket
import signal
import subprocess
import time

# 强制 UTF-8 输出，避免 Windows GBK 编码报错
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

PORT = 9000
HOST = "127.0.0.1"


def kill_port(port: int):
    """释放被占用的端口（增强版：多策略 + 等待释放）"""
    killed = False
    if sys.platform == "win32":
        # 策略1：netstat + taskkill
        try:
            result = subprocess.run(
                ["netstat", "-ano"], capture_output=True, text=True, timeout=10
            )
            for line in result.stdout.splitlines():
                if f":{port}" in line and "LISTENING" in line:
                    parts = line.split()
                    if len(parts) >= 5:
                        pid = parts[-1]
                        r = subprocess.run(
                            ["taskkill", "/f", "/pid", pid],
                            capture_output=True, timeout=10
                        )
                        if r.returncode == 0:
                            print(f"[启动] 已释放端口 {port} (PID {pid})")
                            killed = True
        except Exception as e:
            print(f"[启动] 端口扫描异常: {e}")

        # 策略2：如果 netstat 失败，尝试用 PowerShell
        if not killed:
            try:
                r = subprocess.run(
                    ["powershell", "-Command",
                     f"Get-NetTCPConnection -LocalPort {port} -ErrorAction SilentlyContinue | "
                     f"Select-Object -ExpandProperty OwningProcess | "
                     f"ForEach-Object {{ Stop-Process -Id $_ -Force }}"],
                    capture_output=True, timeout=10
                )
                if r.returncode == 0:
                    print(f"[启动] PowerShell 已释放端口 {port}")
                    killed = True
            except Exception:
                pass
    else:
        try:
            result = subprocess.run(
                ["lsof", "-ti", f":{port}"],
                capture_output=True, text=True, timeout=5
            )
            for pid in result.stdout.strip().split("\n"):
                if pid:
                    subprocess.run(["kill", "-9", pid], capture_output=True, timeout=5)
                    print(f"[启动] 已释放端口 {port} (PID {pid})")
                    killed = True
        except Exception:
            pass

    # 等待端口释放
    if killed:
        for _ in range(10):
            try:
                s = socket.create_connection((HOST, port), timeout=0.5)
                s.close()
                time.sleep(0.3)  # 端口还在用，继续等
            except (ConnectionRefusedError, OSError):
                print(f"[启动] 端口 {port} 已释放")
                return
    else:
        # 即使没杀进程，也检查端口是否可用
        try:
            s = socket.create_connection((HOST, port), timeout=0.5)
            s.close()
            print(f"[启动] 警告: 端口 {port} 仍被占用，尝试强制启动")
        except (ConnectionRefusedError, OSError):
            pass  # 端口空闲，无需操作


def wait_for_server(port: int, timeout: int = 10) -> bool:
    """等待服务器就绪"""
    for _ in range(timeout):
        try:
            s = socket.create_connection((HOST, port), timeout=1)
            s.close()
            return True
        except (ConnectionRefusedError, OSError):
            time.sleep(1)
    return False


_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))


def _load_env():
    """在启动诊断前手动加载 .env，避免因导入顺序导致的环境变量缺失"""
    env_file = os.path.join(_PROJECT_ROOT, ".env")
    if not os.path.exists(env_file):
        return
    with open(env_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key, value = key.strip(), value.strip()
            if key and value and not os.environ.get(key):
                os.environ[key] = value


def _startup_diagnostics():
    """启动前诊断：检查关键依赖和环境"""
    # 先加载 .env，确保后续检查能读到环境变量
    _load_env()

    # 检查 API Key
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key or api_key.startswith("sk-your-") or api_key == "":
        print("[诊断] [WARN] DEEPSEEK_API_KEY 未设置或使用占位符 -- LLM 功能将不可用")
    else:
        print(f"[诊断] [OK] DEEPSEEK_API_KEY 已配置 ({api_key[:8]}...)")

    # 检查 Redis
    redis_url = os.environ.get("REDIS_URL", "")
    if redis_url:
        try:
            r = socket.create_connection(("127.0.0.1", 6379), timeout=1)
            r.close()
            print("[诊断] [OK] Redis 端口 6379 可达")
        except (ConnectionRefusedError, OSError):
            print("[诊断] [WARN] Redis 端口 6379 不可达 -- 缓存功能降级")

    # 检查 Qdrant
    qdrant_url = os.environ.get("QDRANT_URL", "")
    if qdrant_url:
        try:
            r = socket.create_connection(("127.0.0.1", 6333), timeout=1)
            r.close()
            print("[诊断] [OK] Qdrant 端口 6333 可达")
        except (ConnectionRefusedError, OSError):
            print("[诊断] [WARN] Qdrant 端口 6333 不可达 -- 向量检索降级")

    # 检查 SQLite 数据库
    db_path = os.path.join(_PROJECT_ROOT, "memory.db")
    if os.path.exists(db_path):
        print(f"[诊断] [OK] memory.db 存在 ({os.path.getsize(db_path) / 1024:.0f} KB)")
    else:
        print("[诊断] [INFO] memory.db 不存在，将在首次请求时创建")

    # 检查端口 9000 是否空闲
    try:
        s = socket.create_connection(("127.0.0.1", 9000), timeout=0.5)
        s.close()
        print("[诊断] [WARN] 端口 9000 被占用，将尝试释放")
    except (ConnectionRefusedError, OSError):
        print("[诊断] [OK] 端口 9000 空闲")


def _cleanup_temp_files():
    """清理临时上传文件"""
    try:
        import glob
        for f in glob.glob(os.path.join(_PROJECT_ROOT, "approved_images", "*.tmp*")):
            try:
                os.remove(f)
            except OSError:
                pass
    except Exception:
        pass


if __name__ == "__main__":
    # 1. 切换到项目根目录
    project_root = os.path.dirname(os.path.abspath(__file__))
    os.chdir(project_root)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    # 添加 D 盘外部包路径（sentence-transformers / torch 等大型包安装位置）
    _external_packages = r"D:\python-packages"
    if os.path.isdir(_external_packages) and _external_packages not in sys.path:
        sys.path.insert(0, _external_packages)

    print("=" * 50)
    print("  抖音创作顾问 Agent — 后端服务")
    print(f"  端口: {HOST}:{PORT}")
    print("=" * 50)

    # 启动前诊断
    _startup_diagnostics()

    # 2. 释放端口
    kill_port(PORT)
    time.sleep(1)

    # 3. 启动 FastAPI 服务
    print(f"[启动] 正在启动 Uvicorn...")
    import uvicorn
    from backend.server import app

    # 4. 配置 uvicorn
    config = uvicorn.Config(app, host=HOST, port=PORT, log_level="info")
    server = uvicorn.Server(config)

    # 5. 注册信号处理，确保优雅关闭
    def _shutdown(sig, frame):
        print("\n[关闭] 正在优雅关闭服务...")
        server.should_exit = True
    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    try:
        server.run()
    except KeyboardInterrupt:
        print("\n[关闭] 已停止")
    finally:
        # 清理临时文件
        _cleanup_temp_files()
