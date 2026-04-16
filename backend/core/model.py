"""模型加载管理"""
import os
import torch
from .settings import resolve_device


class ModelManager:
    def __init__(self, ready_state, settings_manager, logger):
        self._ready = ready_state
        self._settings = settings_manager
        self._logger = logger

    def load(self, device_setting=None):
        from brain_mcp import embedding as emb

        if device_setting is None:
            device_setting = self._settings.load().get("device", "cpu")

        device = resolve_device(device_setting)
        self._logger.info(f"Loading model on device: {device} (setting={device_setting})")

        self._ready["model"] = False
        self._ready["device"] = device

        # 显式释放旧模型显存
        if emb._model is not None:
            try:
                emb._model.to('cpu')
                for p in emb._model.parameters():
                    p.data = p.data.cpu()
            except Exception:
                pass
            del emb._model
            emb._model = None
            emb._model_name = None
            import gc
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.synchronize()
                self._logger.info(
                    f"GPU VRAM released, free: {torch.cuda.memory_reserved(0)//1024//1024}MB reserved"
                )

        from sentence_transformers import SentenceTransformer
        try:
            model = SentenceTransformer(
                emb.get_model_name(),
                device=device,
                local_files_only=True
            )
            emb._model = model
            self._ready["model"] = True
            self._logger.info(f"Model loaded successfully on {device}")
        except Exception as e:
            self._logger.error(f"Model load failed: {e}")
            self._ready["model"] = False

    def get_model_info(self):
        from brain_mcp import embedding as emb
        raw = emb.get_model_name() if hasattr(emb, 'get_model_name') else 'BAAI/bge-m3'
        if raw and ('/' in str(raw) or '\\' in str(raw)):
            name = str(raw).replace('\\', '/').split('/')[-1]
        else:
            name = raw

        size = ""
        try:
            if emb._model is not None:
                total_params = sum(p.numel() for p in emb._model.parameters())
                if total_params > 1e9:
                    size = f"{total_params/1e9:.1f}B"
                elif total_params > 1e6:
                    size = f"{total_params/1e6:.0f}M"
                else:
                    size = f"{total_params/1e3:.0f}K"
        except Exception:
            pass

        return {"name": name, "size": size}
