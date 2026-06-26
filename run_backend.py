"""
抖音创作顾问 Agent — 后端启动脚本

在 PyCharm 中右键 → Run 'run_backend' 即可启动。
自动清理端口占用，启动后保持运行。
"""
import os
import sys
import socket
import subprocess
import time

PORT = 9000
HOST = "127.0.0.1"


def kill_port(port: int):
    """释放被占用的端口（不使用 shell=True，防止命令注入）"""
    if sys.platform == "win32":
        # Windows: 用 netstat -ano 找 PID 然后 taskkill
        try:
            result = subprocess.run(
                ["netstat", "-ano"], capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.splitlines():
                if f":{port}" in line and "LISTENING" in line:
                    parts = line.split()
                    if len(parts) >= 5:
                        pid = parts[-1]
                        subprocess.run(
                            ["taskkill", "/f", "/pid", pid],
                            capture_output=True, timeout=5
                        )
                        print(f"[启动] 已释放端口 {port} (PID {pid})")
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
        except Exception:
            pass


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


if __name__ == "__main__":
    # 1. 切换到项目根目录
    project_root = os.path.dirname(os.path.abspath(__file__))
    os.chdir(project_root)
    # 将项目根目录加入 Python 路径（仅入口点需要）
    # 各模块已改为标准包导入，不再依赖 sys.path.insert
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    print("=" * 50)
    print("  抖音创作顾问 Agent — 后端服务")
    print(f"  端口: {HOST}:{PORT}")
    print("=" * 50)

    # 2. 释放端口
    kill_port(PORT)
    time.sleep(1)

    # 3. 启动 FastAPI 服务
    print(f"[启动] 正在启动 Uvicorn...")
    import uvicorn
    from backend.server import app

    # 4. uvicorn 接管进程，保持运行直到手动停止
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")
