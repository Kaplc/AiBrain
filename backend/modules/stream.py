"""记忆流路由：/stream"""
from flask import request, jsonify


def register(app, stats_db):
    @app.route('/stream', methods=['GET'])
    def stream():
        action = request.args.get('action')
        limit = min(int(request.args.get('limit', 30)), 200)
        data = stats_db.query_stream(action=action, limit=limit)
        return jsonify({"items": data, "total": stats_db.stream_count(action=action)})
