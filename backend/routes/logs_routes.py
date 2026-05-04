"""Logs 路由 - /logs/api（纯转发）
读取后端日志文件，支持分页和控制行数"""
from flask import request, jsonify
from modules.Log.log_mod import LogManager

_mgr = LogManager.get_instance()


def register(app, ready_state, logger, stats_db):
    @app.route('/logs/api', methods=['GET'])
    def get_logs():
        """读取后端日志文件最后 N 行"""
        project_root = app.config.get('_PROJECT_ROOT', '')
        log_file, fname = _mgr.get_latest_log_file(project_root)
        if not log_file:
            return jsonify({"lines": [], "file": None})
        lines_param = request.args.get('lines', 300, type=int)
        lines_param = min(max(lines_param, 10), 1000)
        result = _mgr.read_log_tail(log_file, lines_param)
        result["file"] = fname
        return jsonify(result)