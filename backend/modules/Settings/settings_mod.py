"""Settings 业务逻辑（单例）"""
import json
import os
import threading
import torch

from core.settings import ConfigManager


# ── 工具函数 ──────────────────────────────────────────────────
def format_size(size: int) -> str:
    if size < 1024: return f"{size}B"
    elif size < 1024 * 1024: return f"{size/1024:.1f}KB"
    elif size < 1024 * 1024 * 1024: return f"{size/1024/1024:.1f}MB"
    else: return f"{size/1024/1024/1024:.2f}GB"


def get_dir_size(path: str) -> int:
    try:
        total = 0
        for dirpath, dirnames, filenames in os.walk(path):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                try:
                    total += os.path.getsize(fp)
                except Exception:
                    pass
        return total
    except Exception:
        return 0


_DIR_KEYWORDS = ('dir', 'path', 'folder', 'directory')
_NUMBER_KEYWORDS = ('size', 'timeout', 'count', 'limit')


def build_fields(data: dict, defaults: dict, prefix: str = '') -> list:
    fields = []
    for key, value in data.items():
        field_key = prefix + key if prefix else key
        lower_key = key.lower()
        if isinstance(value, dict):
            nested_defaults = defaults.get(key, {}) if isinstance(defaults.get(key), dict) else {}
            fields.extend(build_fields(value, nested_defaults, key + '_'))
        else:
            if any(k in lower_key for k in _NUMBER_KEYWORDS) and isinstance(value, int):
                ftype = 'number'
            elif any(k in lower_key for k in _DIR_KEYWORDS):
                ftype = 'dir'
            else:
                ftype = 'text'
            fields.append({
                'key': field_key,
                'label': key,
                'value': value if value is not None else '',
                'default': defaults.get(key, '') if not isinstance(defaults.get(key), dict) else '',
                'type': ftype
            })
    return fields


# ── SettingsManager 单例 ─────────────────────────────────────
class SettingsManager:
    _instance = None

    def __init__(self):
        pass

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def load_settings_api(self, settings_mgr) -> dict:
        return settings_mgr.load()

    def save_settings_api(self, settings_mgr, data: dict) -> dict:
        current = settings_mgr.load()
        current.update({k: v for k, v in data.items() if k in ('device',)})
        settings_mgr.save(current)
        return {"result": "已保存"}

    def get_config_info(self) -> dict:
        cfg_mgr = ConfigManager.get_instance()
        user_home = os.path.expanduser("~")
        aibrain_dir = os.path.join(user_home, '.aibrain')
        config_dir = cfg_mgr.config_dir
        configs = {'user_home': user_home, 'aibrain': {}}
        if os.path.exists(aibrain_dir):
            configs['aibrain']['path'] = aibrain_dir
            configs['aibrain']['size'] = format_size(get_dir_size(aibrain_dir))
            if os.path.exists(config_dir):
                configs['aibrain']['configs'] = {}
                for fname in ['mem0.json', 'wiki.json']:
                    fpath = os.path.join(config_dir, fname)
                    if os.path.exists(fpath):
                        try:
                            with open(fpath, 'r', encoding='utf-8') as f:
                                d = json.load(f)
                            configs['aibrain']['configs'][fname] = {
                                'size': format_size(os.path.getsize(fpath)),
                                'data': d
                            }
                        except Exception:
                            pass
        return configs

    def reload_model(self, settings_mgr, model_mgr, device_setting: str) -> dict:
        settings_mgr.save({"device": device_setting})
        warning = None
        if device_setting == "gpu" and not torch.cuda.is_available():
            warning = "选择了 GPU 模式但未安装 GPU 版 PyTorch"
        threading.Thread(target=model_mgr.load, args=(device_setting,), daemon=True).start()
        return {"result": f"模型重载中，设备: {device_setting}", "warning": warning}

    def get_aibrain_config(self) -> dict:
        cfg_mgr = ConfigManager.get_instance()
        mem0 = cfg_mgr.read_mem0()
        wiki = cfg_mgr.read_wiki()
        defaults_mem0 = cfg_mgr.get_default_mem0()
        defaults_wiki = cfg_mgr.get_default_wiki()
        return {
            'mem0': {'data': mem0, 'fields': build_fields(mem0, defaults_mem0)},
            'wiki': {'data': wiki, 'fields': build_fields(wiki, defaults_wiki)}
        }

    def save_aibrain_config(self, data: dict) -> dict:
        cfg_mgr = ConfigManager.get_instance()
        result = {}
        if 'mem0' in data:
            cfg_mgr.write_mem0(data['mem0'])
            result['mem0'] = '已保存'
        if 'wiki' in data:
            cfg_mgr.write_wiki(data['wiki'])
            result['wiki'] = '已保存'
        return {"result": result}

    def check_path(self, path: str) -> dict:
        return {"exists": bool(path) and os.path.exists(path)}

    def select_directory(self, project_root: str) -> dict:
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            root.attributes('-topmost', True)
            folder = filedialog.askdirectory(initialdir=project_root or None)
            root.destroy()
            return {"path": folder or ""}
        except Exception as e:
            return {"error": str(e), "path": ""}