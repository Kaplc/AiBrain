"""Settings 路由 - /settings/*（纯转发）"""
from flask import request, jsonify
from modules.Settings.settings_mod import SettingsManager

_mgr = SettingsManager.get_instance()


def register(app, ready_state, logger, stats_db, settings_mgr, model_mgr):
    @app.route('/settings/api', methods=['GET', 'POST'])
    def settings_api():
        if request.method == 'GET':
            return jsonify(_mgr.load_settings_api(settings_mgr))
        return jsonify(_mgr.save_settings_api(settings_mgr, request.get_json() or {}))

    @app.route('/settings/config-info', methods=['GET'])
    def get_config_info_route():
        return jsonify(_mgr.get_config_info())

    @app.route('/settings/reload-model', methods=['POST'])
    def reload_model_route():
        data = request.get_json() or {}
        device = data.get('device', settings_mgr.load().get('device', 'auto'))
        return jsonify(_mgr.reload_model(settings_mgr, model_mgr, device))

    @app.route('/settings/aibrain-config', methods=['GET'])
    def get_aibrain_config_route():
        return jsonify(_mgr.get_aibrain_config())

    @app.route('/settings/save-aibrain-config', methods=['POST'])
    def save_aibrain_config_route():
        return jsonify(_mgr.save_aibrain_config(request.get_json() or {}))

    @app.route('/settings/check-path', methods=['POST'])
    def check_path_route():
        path = (request.get_json() or {}).get('path', '').strip()
        return jsonify(_mgr.check_path(path))

    @app.route('/settings/select-directory', methods=['POST'])
    def select_directory_route():
        return jsonify(_mgr.select_directory(app.config.get('_PROJECT_ROOT', '')))

    @app.route('/settings/llm/test', methods=['POST'])
    def test_llm_route():
        """用给定的 LLM 配置真发一次请求，验证连通性"""
        return jsonify(_mgr.test_llm_config(request.get_json() or {}))

    # ── Chat 意识流配置 ─────────────────────────────────────
    @app.route('/settings/chat', methods=['GET'])
    def get_chat_config_route():
        """读取 chat.json 配置"""
        return jsonify(_mgr.get_chat_config())

    @app.route('/settings/chat', methods=['POST'])
    def save_chat_config_route():
        """保存 chat.json 配置并热更新 loop"""
        result = _mgr.save_chat_config(request.get_json() or {})
        return jsonify(result)

    @app.route('/settings/chat/test', methods=['POST'])
    def test_chat_config_route():
        """测试 Chat LLM 连通性"""
        return jsonify(_mgr.test_chat_config(request.get_json() or {}))