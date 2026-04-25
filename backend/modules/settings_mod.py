"""设置路由：/settings, /reload-model, /config-info, /save-aibrain-config"""
import os
import json
import threading
import torch
from flask import request, jsonify


# ── 默认配置常量 ──────────────────────────────────────────────
DEFAULT_MEM0 = {
    "wiki_dir": "wiki",
    "lightrag_dir": "rag/lightrag_data",
    "language": "Chinese",
    "chunk_token_size": 1200,
    "llm": {
        "provider": "",
        "model": "",
        "api_key": "",
        "base_url": ""
    },
    "search_timeout": 30
}

DEFAULT_WIKI = {
    "llm_provider": "minimax",
    "llm_model": "MiniMax-M2.7",
    "api_key": "",
    "base_url": "https://api.minimaxi.com/v1",
    "collection_name": "mem0_memories"
}


# ── 配置管理器 ──────────────────────────────────────────────
class AibrainConfigManager:
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
        """初始化默认配置文件（仅当文件不存在时）"""
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
        current = self.read_mem0()
        current.update(data)
        with open(self._mem0_path, 'w', encoding='utf-8') as f:
            json.dump(current, f, indent=2, ensure_ascii=False)

    def read_wiki(self) -> dict:
        if os.path.exists(self._wiki_path):
            with open(self._wiki_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return DEFAULT_WIKI.copy()

    def write_wiki(self, data: dict):
        self.ensure_config_dir()
        current = self.read_wiki()
        current.update(data)
        with open(self._wiki_path, 'w', encoding='utf-8') as f:
            json.dump(current, f, indent=2, ensure_ascii=False)

    def get_default_mem0(self) -> dict:
        return DEFAULT_MEM0.copy()

    def get_default_wiki(self) -> dict:
        return DEFAULT_WIKI.copy()


# ── Flask 路由 ──────────────────────────────────────────────
def register(app, settings_mgr, model_mgr):
    @app.route('/settings', methods=['GET'])
    def get_settings():
        return jsonify(settings_mgr.load())

    @app.route('/config-info', methods=['GET'])
    def get_config_info():
        """获取用户目录的配置文件信息"""
        cfg_mgr = AibrainConfigManager.get_instance()
        user_home = os.path.expanduser("~")
        aibrain_dir = os.path.join(user_home, '.aibrain')
        config_dir = cfg_mgr.config_dir

        def format_size(size):
            if size < 1024:
                return f"{size}B"
            elif size < 1024 * 1024:
                return f"{size/1024:.1f}KB"
            elif size < 1024 * 1024 * 1024:
                return f"{size/1024/1024:.1f}MB"
            else:
                return f"{size/1024/1024/1024:.2f}GB"

        def get_dir_size(path):
            try:
                total = 0
                for dirpath, dirnames, filenames in os.walk(path):
                    for f in filenames:
                        fp = os.path.join(dirpath, f)
                        try:
                            total += os.path.getsize(fp)
                        except:
                            pass
                return total
            except Exception:
                return 0

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
                                data = json.load(f)
                            # 不再隐藏api_key，直接显示
                            configs['aibrain']['configs'][fname] = {
                                'size': format_size(os.path.getsize(fpath)),
                                'data': data
                            }
                        except Exception:
                            pass

        return jsonify(configs)

    @app.route('/settings', methods=['POST'])
    def save_settings():
        data = request.get_json() or {}
        current = settings_mgr.load()
        current.update({k: v for k, v in data.items() if k in ('device',)})
        settings_mgr.save(current)
        return jsonify({"result": "已保存"})

    @app.route('/reload-model', methods=['POST'])
    def reload_model():
        data = request.get_json() or {}
        device_setting = data.get('device', settings_mgr.load().get('device', 'auto'))
        settings_mgr.save({"device": device_setting})

        warning = None
        if device_setting == "gpu" and not torch.cuda.is_available():
            warning = "选择了 GPU 模式但未安装 GPU 版 PyTorch"

        threading.Thread(target=model_mgr.load, args=(device_setting,), daemon=True).start()
        return jsonify({"result": f"模型重载中，设备: {device_setting}", "warning": warning})

    @app.route('/save-aibrain-config', methods=['POST'])
    def save_aibrain_config():
        """保存 .aibrain/config 下的配置文件"""
        cfg_mgr = AibrainConfigManager.get_instance()
        data = request.get_json() or {}
        result = {}

        if 'mem0' in data:
            cfg_mgr.write_mem0(data['mem0'])
            result['mem0'] = '已保存'

        if 'wiki' in data:
            cfg_mgr.write_wiki(data['wiki'])
            result['wiki'] = '已保存'

        return jsonify({"result": result})

    @app.route('/aibrain-config', methods=['GET'])
    def get_aibrain_config():
        """获取 aibrain 配置（动态扫描配置文件字段）"""
        cfg_mgr = AibrainConfigManager.get_instance()
        mem0 = cfg_mgr.read_mem0()
        wiki = cfg_mgr.read_wiki()
        defaults_mem0 = cfg_mgr.get_default_mem0()
        defaults_wiki = cfg_mgr.get_default_wiki()

        # 动态构建字段列表（扁平化嵌套字段）
        DIR_KEYWORDS = ('dir', 'path', 'folder', 'directory')
        URL_KEYWORDS = ('url', 'endpoint', 'api_key', 'key')
        NUMBER_KEYWORDS = ('size', 'timeout', 'count', 'limit')

        def build_fields(data, defaults, prefix=''):
            fields = []
            for key, value in data.items():
                field_key = prefix + key if prefix else key
                lower_key = key.lower()

                if isinstance(value, dict):
                    # 嵌套对象：展平为 parent_child 格式
                    nested_defaults = defaults.get(key, {}) if isinstance(defaults.get(key), dict) else {}
                    fields.extend(build_fields(value, nested_defaults, key + '_'))
                else:
                    # 自动推断类型
                    if any(k in lower_key for k in NUMBER_KEYWORDS) and isinstance(value, int):
                        ftype = 'number'
                    elif any(k in lower_key for k in DIR_KEYWORDS):
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

        return jsonify({
            'mem0': {
                'data': mem0,
                'fields': build_fields(mem0, defaults_mem0)
            },
            'wiki': {
                'data': wiki,
                'fields': build_fields(wiki, defaults_wiki)
            }
        })

    @app.route('/check-path', methods=['POST'])
    def check_path():
        """检查路径是否存在"""
        data = request.get_json() or {}
        path = data.get('path', '').strip()
        if not path:
            return jsonify({"exists": False})
        return jsonify({"exists": os.path.exists(path)})

    @app.route('/select-directory', methods=['POST'])
    def select_directory():
        """通过系统对话框选择目录（使用tkinter）"""
        try:
            import tkinter as tk
            from tkinter import filedialog
            # 获取项目根目录作为默认路径
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            project_root = os.path.normpath(os.path.join(project_root, '..'))
            root = tk.Tk()
            root.withdraw()
            root.attributes('-topmost', True)
            folder = filedialog.askdirectory(initialdir=project_root or None)
            root.destroy()
            if folder:
                return jsonify({"path": folder})
            return jsonify({"path": ""})
        except Exception as e:
            return jsonify({"error": str(e), "path": ""})
