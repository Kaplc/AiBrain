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
_NUMBER_KEYWORDS = ('size', 'timeout', 'count', 'limit', 'tokens', 'temperature')


# ── Provider 分组（按接口协议） ─────────────────────────────
# 前端 Tab 只暴露 openai / anthropic 两个最常用的；其它 provider（deepseek/ollama/...）
# LLM 模块底层仍支持，feature 模块（如 chat）可以直接构造 LLMConfig 使用
LLM_PROVIDER_GROUPS = [
    {
        'label': 'OpenAI 兼容',
        'protocol': 'openai',
        'providers': ['openai'],
    },
    {
        'label': 'Anthropic 兼容',
        'protocol': 'anthropic',
        'providers': ['anthropic'],
    },
]

# 扁平化的 options 列表（向后兼容老前端代码）
LLM_PROVIDER_OPTIONS = [p for g in LLM_PROVIDER_GROUPS for p in g['providers']]


def _llm_fields(data: dict, defaults: dict) -> list:
    """LLM 专用字段定义

    - `provider` 字段在 UI 上叫"接口类型"（label），用户选 openai/anthropic 之一
    - key 仍是 `provider` 以兼容 LLMConfig / mem0.json 等下游模块
    """
    return [
        {'key': 'provider',  'label': '接口类型',   'type': 'select',  'value': data.get('provider', ''),   'default': defaults.get('provider', ''),  'options': LLM_PROVIDER_OPTIONS, 'option_groups': LLM_PROVIDER_GROUPS, 'placeholder': '选择 LLM 接口类型'},
        {'key': 'model',     'label': 'Model',      'type': 'text',    'value': data.get('model', ''),      'default': defaults.get('model', ''), 'placeholder': '如 gpt-4o-mini / claude-sonnet-4-20250514'},
        {'key': 'api_key',   'label': 'API Key',    'type': 'password','value': data.get('api_key', ''),    'default': defaults.get('api_key', ''), 'placeholder': '从对应平台获取'},
        {'key': 'base_url',  'label': 'Base URL',   'type': 'text',    'value': data.get('base_url', ''),   'default': defaults.get('base_url', ''), 'placeholder': '可选，留空用接口默认端点'},
        {'key': 'temperature', 'label': 'Temperature', 'type': 'number', 'value': data.get('temperature', 0.7), 'default': defaults.get('temperature', 0.7)},
        {'key': 'max_tokens',  'label': 'Max Tokens',  'type': 'number', 'value': data.get('max_tokens', 1024), 'default': defaults.get('max_tokens', 1024)},
        {'key': 'timeout',     'label': 'Timeout (秒)', 'type': 'number', 'value': data.get('timeout', 60),   'default': defaults.get('timeout', 60)},
    ]


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
                for fname in ['mem0.json', 'wiki.json', 'chat.json']:
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
        wiki = cfg_mgr.read_wiki()
        llm = cfg_mgr.read_llm()
        defaults_wiki = cfg_mgr.get_default_wiki()
        defaults_llm = cfg_mgr.get_default_llm()
        return {
            'wiki': {'data': wiki, 'fields': build_fields(wiki, defaults_wiki)},
            'llm':  {'data': llm,  'fields': _llm_fields(llm, defaults_llm)},
        }

    def save_aibrain_config(self, data: dict) -> dict:
        cfg_mgr = ConfigManager.get_instance()
        result = {}
        if 'wiki' in data:
            cfg_mgr.write_wiki(data['wiki'])
            result['wiki'] = '已保存'
        if 'llm' in data:
            cfg_mgr.write_llm(data['llm'])
            result['llm'] = '已保存'
        return {"result": result}

    def test_llm_config(self, data: dict) -> dict:
        """用给定的 LLM 配置真发一次请求，验证连通性。

        Returns: {"ok": bool, "message": str, "response": str|None, "latency_ms": int}
        """
        import time
        from modules.LLM import LLMConfig, get_llm_manager

        try:
            cfg = LLMConfig.from_dict(data)
            ok, err = cfg.validate()
            if not ok:
                return {"ok": False, "message": f"配置无效: {err}", "response": None, "latency_ms": 0}

            # 用一个超短 prompt 测连通性，max_tokens 压到 16 省成本
            test_cfg = LLMConfig(
                provider=cfg.provider,
                model=cfg.model,
                api_key=cfg.api_key,
                base_url=cfg.base_url,
                temperature=0,
                max_tokens=16,
                timeout=min(cfg.timeout, 30),
            )
            t0 = time.time()
            text = get_llm_manager().complete("只回 OK", "ping", test_cfg)
            latency_ms = int((time.time() - t0) * 1000)
            return {
                "ok": True,
                "message": f"连接成功 ({cfg.provider}/{cfg.model})",
                "response": text[:100],
                "latency_ms": latency_ms,
            }
        except Exception as e:
            return {"ok": False, "message": str(e), "response": None, "latency_ms": 0}

    def check_path(self, path: str) -> dict:
        return {"exists": bool(path) and os.path.exists(path)}

    # ── Chat 意识流配置 ─────────────────────────────────────

    def get_chat_config(self) -> dict:
        """读取 chat.json 配置"""
        cfg_mgr = ConfigManager.get_instance()
        data = cfg_mgr.read_chat()
        defaults = cfg_mgr.get_default_chat()
        return {'data': data, 'defaults': defaults}

    def save_chat_config(self, data: dict) -> dict:
        """保存 chat.json 并热更新 ChatManager"""
        cfg_mgr = ConfigManager.get_instance()
        cfg_mgr.write_chat(data)
        chat_cfg = cfg_mgr.read_chat()
        # 热更新
        try:
            from modules.chat import ChatManager
            mgr = ChatManager.get_instance()
            mgr.load_config(chat_cfg)
            # 尝试创建并启动空闲思绪线程
            if mgr.get_loop_state().get('is_running') is False:
                from core.database import StatsDB
                import os
                db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'stats.db')
                stats_db = StatsDB.get_instance(db_path)
                mgr.init_agentloop(stats_db, chat_cfg)
                try:
                    from modules.qdrant.store import get_qdrant_client
                    m = get_mem0_client()
                    if m:
                        mgr.set_mem0_add_fn(lambda **kw: m.add(**kw))
                except Exception:
                    pass
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"[settings] chat loop reload failed: {e}")
        return {"result": "已保存，下次 tick 生效"}

    def test_chat_config(self, data: dict) -> dict:
        """测试 Chat LLM 连通性"""
        import time
        from modules.LLM import LLMConfig, get_llm_manager

        try:
            provider = data.get('chat_provider', 'openai')
            cfg = LLMConfig(
                provider=provider,
                model=data.get('chat_model', 'gpt-4o-mini'),
                api_key=data.get('chat_api_key', ''),
                base_url=data.get('chat_base_url', ''),
                temperature=0,
                max_tokens=16,
                timeout=15,
            )
            ok, err = cfg.validate()
            if not ok:
                return {"ok": False, "message": f"配置无效: {err}", "response": None, "latency_ms": 0}

            t0 = time.time()
            text = get_llm_manager().complete("只回 OK", "ping", cfg)
            latency_ms = int((time.time() - t0) * 1000)
            return {
                "ok": True,
                "message": f"连接成功 ({provider}/{cfg.model})",
                "response": text[:100],
                "latency_ms": latency_ms,
            }
        except Exception as e:
            return {"ok": False, "message": str(e), "response": None, "latency_ms": 0}

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