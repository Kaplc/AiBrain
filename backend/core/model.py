"""模型加载管理

语义模型 BGE-M3 已独立为 embed_server 进程（port 19402），
主 Flask 不再本地加载，改为 HTTP 调用。

ModelManager 保留兼容接口，load() 为重载标记。
"""
import logging
from .settings import resolve_device


class ModelManager:
    _instance = None

    def __init__(self, ready_state, settings_manager, logger):
        self._ready = ready_state
        self._settings = settings_manager
        self._logger = logger

    @classmethod
    def get_instance(cls, ready_state=None, settings_manager=None, logger=None):
        if cls._instance is None:
            cls._instance = cls(ready_state, settings_manager, logger)
        return cls._instance

    def load(self, device_setting=None):
        """标记模型就绪（语义模型已独立为 embed_server 进程）

        不再本地加载 SentenceTransformer，直接标记就绪。
        """
        if device_setting is None:
            device_setting = self._settings.load().get("device", "cpu")

        device = resolve_device(device_setting)
        self._ready["model"] = True
        self._ready["device"] = device
        self._logger.info(
            f"Model ready (embedded service), device={device} setting={device_setting}"
        )

    def get_model_info(self):
        """返回模型信息"""
        return {"name": "bge-m3 (remote)", "size": ""}
