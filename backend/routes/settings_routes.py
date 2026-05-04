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