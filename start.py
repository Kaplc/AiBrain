"""
Python 启动脚本 - 等效于 start.bat，但用 Python 实现
用法: python start.py
"""
import subprocess
import sys
import os
import time
import urllib.request
import shutil

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VENV_PY = os.path.join(BASE_DIR, "venv312", "Scripts", "python.exe")
BACKEND_DIR = os.path.join(BASE_DIR, "backend")
LAUNCHER_DIR = os.path.join(BASE_DIR, "backend", "launcher")


def run(args, **kwargs):
    """执行命令并打印输出"""
    print(f"  > {' '.join(args)}")
    kwargs.setdefault("capture_output", True)
    kwargs.setdefault("text", True)
    kwargs.setdefault("cwd", BASE_DIR)
    result = subprocess.run(args, **kwargs)
    if result.stdout:
        print(result.stdout.strip())
    if result.stderr:
        print(result.stderr.strip(), file=sys.stderr)
    return result


def wait_for_qdrant(port, timeout=60):
    """等待 Qdrant 就绪"""
    url = f"http://127.0.0.1:{port}/healthz"
    for i in range(timeout):
        try:
            urllib.request.urlopen(url, timeout=3)
            print(f"  Qdrant is ready on port {port}")
            return True
        except Exception:
            time.sleep(1)
    return False


def main():
    print("=== Memory Manager ===")

    # 1. 杀掉旧进程
    print("\n[1/5] Killing old processes...")
    kill_script = os.path.join(LAUNCHER_DIR, "kill_old.py")
    if os.path.exists(kill_script):
        run([VENV_PY, kill_script])

    # 2. 检查虚拟环境
    print("\n[2/5] Checking virtual environment...")
    if not os.path.exists(VENV_PY):
        print("  Virtual env not found, creating...")
        result = shutil.which("python") or shutil.which("python3")
        subprocess.run([sys.executable, "-m", "venv", "venv312"], cwd=BASE_DIR)
        print("  Virtual env created")

    py_ver = subprocess.run([VENV_PY, "--version"], capture_output=True, text=True)
    print(f"  Python: {py_ver.stdout.strip()}")

    # 3. 检查依赖
    print("\n[3/5] Checking dependencies...")
    boot_helper = os.path.join(LAUNCHER_DIR, "_boot_helper.py")
    result = run([VENV_PY, boot_helper, "deps"])
    if result.returncode != 0:
        print("  Installing dependencies...")
        req_file = os.path.join(BASE_DIR, "requirements.txt")
        subprocess.run([VENV_PY, "-m", "pip", "install", "-r", req_file], cwd=BASE_DIR)

    # 4. 获取端口
    print("\n[4/5] Allocating ports...")
    result = subprocess.run([VENV_PY, boot_helper, "ports"], capture_output=True, text=True, cwd=BASE_DIR)
    ports_line = result.stdout.strip().split("\n")[0]
    flask_port, qdrant_http, qdrant_grpc = ports_line.split(",")[:3]
    print(f"  Flask: {flask_port}, Qdrant HTTP: {qdrant_http}, Qdrant gRPC: {qdrant_grpc}")

    # 5. 生成 Qdrant 配置
    print("\n[5/5] Generating Qdrant config...")
    qdrant_config_dir = os.path.join(BASE_DIR, "qdrant", "config")
    os.makedirs(qdrant_config_dir, exist_ok=True)
    qdrant_config = os.path.join(qdrant_config_dir, "config.yaml")
    with open(qdrant_config, "w") as f:
        f.write(f"""service:
  host: 0.0.0.0
  http_port: {qdrant_http}
  grpc_port: {qdrant_grpc}

storage:
  storage_path: ./qdrant/storage
""")
    print(f"  Config written to {qdrant_config}")

    # 6. 启动 Qdrant
    print("\n[6/6] Starting Qdrant...")
    qdrant_exe = os.path.join(BASE_DIR, "qdrant", "qdrant.exe")
    if os.path.exists(qdrant_exe):
        subprocess.Popen(
            [qdrant_exe, "--config-path", qdrant_config],
            cwd=BASE_DIR,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        print(f"  Qdrant started (PID not tracked)")
        if not wait_for_qdrant(int(qdrant_http)):
            print("  WARNING: Qdrant did not respond, continuing anyway...")
    else:
        print(f"  Qdrant executable not found: {qdrant_exe}")

    # 7. 启动 Flask
    print("\n=== Starting Memory Manager ===")
    env = os.environ.copy()
    env["PYTHONPATH"] = BASE_DIR + ";" + BACKEND_DIR
    env["FLASK_PORT"] = flask_port
    env["QDRANT_HTTP_PORT"] = qdrant_http
    env["QDRANT_GRPC_PORT"] = qdrant_grpc

    app_py = os.path.join(BACKEND_DIR, "app.py")
    print(f"  Running: {VENV_PY} {app_py}")
    print(f"  Ports: Flask={flask_port}, Qdrant HTTP={qdrant_http}")

    subprocess.run([VENV_PY, app_py], cwd=BASE_DIR, env=env)


if __name__ == "__main__":
    main()
