"""系统信息采集工具（单例） - 供 routes/overview_routes.py、statusbar_routes.py 调用"""
import os
import platform
import subprocess
import logging
import torch

logger = logging.getLogger(__name__)


class SystemInfoManager:
    _instance = None

    def __init__(self):
        self._flask_start_time = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def set_flask_start_time(self, ts: float):
        self._flask_start_time = ts

    def get_flask_uptime(self) -> int:
        if self._flask_start_time is None:
            return 0
        import time
        return int(time.time() - self._flask_start_time)

    def has_nvidia_gpu(self) -> bool:
        try:
            import pynvml
            pynvml.nvmlInit()
            count = pynvml.nvmlDeviceGetCount()
            pynvml.nvmlShutdown()
            return count > 0
        except Exception:
            pass
        try:
            result = subprocess.run(
                'wmic path win32_VideoController get name,AdapterRAM /format=csv',
                shell=True, capture_output=True, timeout=5, text=True
            )
            lines = [l.strip() for l in result.stdout.split('\n') if l.strip()]
            if len(lines) >= 2:
                name = lines[-1].split(',')[2] if len(lines[-1].split(',')) >= 3 else ''
                return 'nvidia' in name.lower()
        except Exception:
            pass
        return False

    def get_system_info(self) -> dict:
        import psutil
        info = {
            "cpu_percent": psutil.cpu_percent(interval=0.1),
            "memory_total": psutil.virtual_memory().total,
            "memory_used": psutil.virtual_memory().used,
            "memory_percent": psutil.virtual_memory().percent,
            "platform": platform.platform(),
            "os_name": platform.system(),
            "os_version": platform.version(),
            "python_version": platform.python_version(),
            "gpu": None,
        }
        if torch.cuda.is_available():
            try:
                import pynvml
                pynvml.nvmlInit()
                handle = pynvml.nvmlDeviceGetHandleByIndex(0)
                mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
                temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
                info["gpu"] = {
                    "name": torch.cuda.get_device_name(0),
                    "memory_total": mem_info.total,
                    "memory_used": mem_info.used,
                    "memory_free": mem_info.free,
                    "memory_percent": int(mem_info.used / mem_info.total * 100) if mem_info.total > 0 else 0,
                    "temperature": temp,
                }
                pynvml.nvmlShutdown()
            except Exception as e:
                logger.warning(f"[system-info] pynvml failed: {e}")
        if info["gpu"] is None:
            try:
                result = subprocess.run(
                    'wmic path win32_VideoController get name,AdapterRAM /format=csv',
                    shell=True, capture_output=True, timeout=5
                )
                lines = result.stdout.decode('utf-8', errors='ignore').strip().split('\n')
                lines = [l.strip() for l in lines if l.strip()]
                if len(lines) >= 2:
                    parts = lines[-1].split(',')
                    if len(parts) >= 3:
                        name, vram = parts[2].strip(), 0
                        try:
                            vram = int(parts[1].strip())
                        except Exception:
                            pass
                        info["gpu"] = {
                            "name": name,
                            "memory_total": vram,
                            "memory_used": 0,
                            "memory_free": vram,
                            "memory_percent": 0,
                            "temperature": None
                        }
            except Exception as e:
                logger.warning(f"[system-info] wmic failed: {e}")
        return info

    def get_qdrant_info(self, settings, project_root: str, logger=None):
        if self._qdrant_cache["data"] is not None:
            return self._qdrant_cache["data"]
        try:
            from qdrant_client import QdrantClient
            client = QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port, check_compatibility=False)
            collection_info = client.get_collection(settings.collection_name)
            count = collection_info.points_count
            storage_path = os.path.join(project_root, 'qdrant', 'storage')
            disk_size = 0
            try:
                for root, dirs, files in os.walk(storage_path):
                    for f in files:
                        fp = os.path.join(root, f)
                        try:
                            disk_size += os.path.getsize(fp)
                        except Exception:
                            pass
            except Exception:
                pass
            data = {"count": count, "disk_size": disk_size, "storage_path": os.path.relpath(storage_path, project_root)}
            self._qdrant_cache["data"] = data
            if logger:
                logger.info(f"[qdrant] cache: {count} pts, disk={disk_size}")
            return data
        except Exception as e:
            if logger:
                logger.warning(f"[qdrant] cache failed: {e}")
            return {"count": 0, "disk_size": 0, "storage_path": ""}

    def init_qdrant_cache(self, settings, project_root: str, logger=None):
        self.get_qdrant_info(settings, project_root, logger)

    def get_model_info(self):
        from core.model import ModelManager
        return ModelManager.get_instance().get_model_info()

    def write_restart_flag(self, project_root: str):
        # 注意：process_manager.py 的 monitor() 在 backend/ 目录检查 .restart_flask
        # 所以这里要写入 backend/.restart_flask，而非 project_root/
        _backend_dir = os.path.join(project_root, 'backend') if os.path.basename(project_root) != 'backend' else project_root
        flag_path = os.path.join(_backend_dir, '.restart_flask')
        import time
        with open(flag_path, 'w') as f:
            f.write(str(time.time()))
        return flag_path

    _qdrant_cache = {"data": None}