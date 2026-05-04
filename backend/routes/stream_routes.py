"""Stream 模块 - 记忆流 /stream"""
from flask import request, jsonify


def register(app, ready_state, logger, stats_db):
    @app.route('/stream/api', methods=['GET'])
    def stream():
        action = request.args.get('action')
        days = request.args.get('days')
        if days is not None:
            try:
                days = min(int(days), 30)
            except (ValueError, TypeError):
                return jsonify({"error": "days 参数必须是整数", "items": [], "total": 0})
            data = stats_db.query_stream_days(action=action, days=days)
        else:
            limit = min(int(request.args.get('limit', 30)), 200)
            data = stats_db.query_stream(action=action, limit=limit)
        return jsonify({"items": data, "total": stats_db.stream_count(action=action)})