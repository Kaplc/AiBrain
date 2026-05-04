"""设置文件管理（单例）"""
import json
import os


class SettingsManager:
    _instance = None

    def __init__(self, settings_file=None):
        self._file = settings_file

    @classmethod
    def get_instance(cls, settings_file=None):
        if cls._instance is None:
            cls._instance = cls(settings_file)
        return cls._instance

    def load(self) -> dict:
        try:
            with open(self._file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {"device": "cpu"}

    def save(self, data: dict):
        current = self.load()
        current.update(data)
        with open(self._file, 'w', encoding='utf-8') as f:
            json.dump(current, f, indent=2, ensure_ascii=False)


# ── 默认配置 ─────────────────────────────────────────────────
DEFAULT_MEM0 = {
    "llm_provider": "minimax",
    "llm_model": "MiniMax-M2.7",
    "api_key": "",
    "base_url": "https://api.minimaxi.com/v1",
    "collection_name": "mem0_memories"
}

DEFAULT_WIKI = {
    "wiki_dir": "wiki",
    "lightrag_dir": "rag/lightrag_data",
    "language": "Chinese",
    "chunk_token_size": 1200,
    "llm_provider": "minimax",
    "llm_model": "MiniMax-M2.7",
    "api_key": "",
    "base_url": "https://api.minimaxi.com/v1",
    "collection_name": "aibrain_wiki",
    "search_timeout": 30
}


class ConfigManager:
    _instance = None

    def __init__(self):
        self._user_home = os.path.expanduser("~")
        self._config_dir = os.path.join(self._user_home, '.aibrain', 'config')
        self._mem0_path = os.path.join(self._config_dir, 'mem0.json')
        self._wiki_path = os.path.join(self._config_dir, 'wiki.json')

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @property
    def config_dir(self):
        return self._config_dir

    def ensure_config_dir(self):
        os.makedirs(self._config_dir, exist_ok=True)

    def init_default_configs(self):
        self.ensure_config_dir()
        if not os.path.exists(self._mem0_path):
            with open(self._mem0_path, 'w', encoding='utf-8') as f:
                json.dump(DEFAULT_MEM0, f, indent=2, ensure_ascii=False)
        if not os.path.exists(self._wiki_path):
            with open(self._wiki_path, 'w', encoding='utf-8') as f:
                json.dump(DEFAULT_WIKI, f, indent=2, ensure_ascii=False)

    def read_mem0(self) -> dict:
        if os.path.exists(self._mem0_path):
            with open(self._mem0_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return DEFAULT_MEM0.copy()

    def write_mem0(self, data: dict):
        self.ensure_config_dir()
        current = {}
        for key, value in data.items():
            if isinstance(value, dict):
                for k, v in value.items():
                    current[f'{key}_{k}'] = v
            else:
                current[key] = value
        with open(self._mem0_path, 'w', encoding='utf-8') as f:
            json.dump(current, f, indent=2, ensure_ascii=False)

    def read_wiki(self) -> dict:
        if os.path.exists(self._wiki_path):
            with open(self._wiki_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return DEFAULT_WIKI.copy()

    def write_wiki(self, data: dict):
        self.ensure_config_dir()
        current = {}
        for key, value in data.items():
            if isinstance(value, dict):
                for k, v in value.items():
                    current[f'{key}_{k}'] = v
            else:
                current[key] = value
        with open(self._wiki_path, 'w', encoding='utf-8') as f:
            json.dump(current, f, indent=2, ensure_ascii=False)

    def get_default_mem0(self) -> dict:
        return DEFAULT_MEM0.copy()

    def get_default_wiki(self) -> dict:
        return DEFAULT_WIKI.copy()


def resolve_device(setting: str) -> str:
    """根据设置解析实际 device 字符串"""
    import torch
    force_cpu = os.environ.get('FORCE_CPU', '0') == '1'
    if force_cpu:
        return "cpu"
    if setting == "gpu":
        return "cuda" if torch.cuda.is_available() else "cpu"
    elif setting == "cpu":
        return "cpu"
    else:
        return "cuda" if torch.cuda.is_available() else "cpu"
