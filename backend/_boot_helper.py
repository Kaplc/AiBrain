"""启动辅助：端口管理（首次分配+读取配置+杀旧实例）"""
import socket
import os
import sys
import subprocess
import hashlib


# 基础端口（每个项目根据路径 hash 自动偏移，避免冲突）
BASE_FLASK = 18765
BASE_QDRANT_HTTP = 6333
BASE_QDRANT_GRPC = 6334

# 端口范围：offset 最大值（确保不超出合法端口）
MAX_OFFSET = 2000


def project_hash_offset():
    """根据项目根目录路径生成确定性偏移量，不同项目自动分配不同端口"""
    # 项目根目录 = backend/ 的上级目录
    project_root = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
    path_bytes = project_root.encode('utf-8')
    digest = hashlib.md5(path_bytes).hexdigest()
    offset = int(digest[:8], 16) % MAX_OFFSET
    return offset, project_root


def is_port_free(port):
    """检查端口是否空闲（TCP）"""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind(('127.0.0.1', port))
        s.close()
        return True
    except OSError:
        s.close()
        return False


def find_free_ports():
    """从项目专属基础端口递增，找到一组可用的 Flask+Qdrant 端口"""
    offset, _ = project_hash_offset()
    for i in range(100):
        o = offset + i * 3
        f = BASE_FLASK + (o % (MAX_OFFSET * 10))
        h = BASE_QDRANT_HTTP + (o % (MAX_OFFSET * 10))
        g = BASE_QDRANT_GRPC + (o % (MAX_OFFSET * 10))
        if is_port_free(f) and is_port_free(h) and is_port_free(g):
            return {"flask": f, "http": h, "grpc": g}
    raise RuntimeError("无法找到可用端口")


def get_ports():
    """返回端口字典：优先读 .port_config，否则分配并保存"""
    config_path = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', '.port_config'))

    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                line = f.read().strip()
            parts = line.split(',')
            if len(parts) >= 3:
                return {"flask": int(parts[0]), "http": int(parts[1]), "grpc": int(parts[2])}
        except Exception:
            pass

    # 首次：分配并保存
    ports = find_free_ports()
    try:
        with open(config_path, 'w') as f:
            f.write(f"{ports['flask']},{ports['http']},{ports['grpc']}")
    except Exception:
        pass
    return ports


def kill_old_instance():
    """检测并清理旧实例"""
    port_file = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', '.port'))
    old_port = None

    if os.path.exists(port_file):
        try:
            with open(port_file, 'r') as f:
                old_port = int(f.read().strip())
        except Exception:
            pass

    if old_port:
        import urllib.request
        try:
            urllib.request.urlopen(f'http://127.0.0.1:{old_port}/health', timeout=2)
            # 实例存活，杀掉
            result = subprocess.run(
                ['netstat', '-ano'], capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.splitlines():
                if f':{old_port}' in line and 'LISTENING' in line:
                    pid = line.strip().split()[-1]
                    subprocess.run(['taskkill', '/F', '/PID', pid],
                                   capture_output=True, timeout=5)
                    print(f'KILLED:{old_port}:{pid}')
                    return True
        except Exception:
            pass
    return False


if __name__ == '__main__':
    action = sys.argv[1] if len(sys.argv) > 1 else ''
    if action == 'ports':
        p = get_ports()
        print(f"{p['flask']},{p['http']},{p['grpc']}")
    elif action == 'kill':
        kill_old_instance()
