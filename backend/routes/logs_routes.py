"""Logs 路由 - /logs/api（纯转发）
读取后端日志文件，支持分页、类型选择和关键词过滤"""
from flask import request, jsonify
from modules.Log.log_mod import LogManager

_mgr = LogManager.get_instance()


def register(app, ready_state, logger, stats_db):
    @app.route('/logs/api', methods=['GET'])
    def get_logs():
        """读取后端日志文件最后 N 行，支持类型选择和关键词过滤

        Query 参数：
        - lines: 行数（默认 300）
        - type: 日志类型（flask/mem0/embed/app/ui/all，默认 flask）
        - keywords: 逗号分隔的关键词（可选，传则启用过滤模式）
        """
        project_root = app.config.get('_PROJECT_ROOT', '')
        log_type = request.args.get('type', 'flask')
        log_file, fname = _mgr.get_latest_log_file(project_root, prefix=log_type)
        if not log_file:
            return jsonify({"lines": [], "file": None, "type": log_type})
        lines_param = request.args.get('lines', 300, type=int)
        lines_param = min(max(lines_param, 10), 1000)

        keywords_param = request.args.get('keywords', '')
        if keywords_param:
            kws = [k.strip() for k in keywords_param.split(',') if k.strip()]
            result = _mgr.read_log_tail_filtered(log_file, kws, lines_param)
            result["file"] = fname
            result["type"] = log_type
            return jsonify(result)
        else:
            result = _mgr.read_log_tail(log_file, lines_param)
            result["file"] = fname
            result["type"] = log_type
            return jsonify(result)