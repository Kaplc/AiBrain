"""Stats 路由 - /chart-data（纯转发）
提供图表统计数据：每日/每周/每月的 added/updated/total 趋势"""
from flask import request, jsonify
from modules.Stats.stats_mod import StatsManager

_mgr = StatsManager.get_instance()


def register(app, ready_state, logger, stats_db):
    @app.route('/chart-data', methods=['GET'])
    def chart_data():
        """获取图表数据，支持 today(24小时)/week(7天)/month(30天)"""
        range_type = request.args.get('range', 'week')
        import datetime as _dt
        today = _dt.date.today()

        if range_type == 'today':
            return jsonify({"range": range_type, "data": _mgr.get_hourly_chart_data(stats_db)})

        if range_type == 'week':
            start = today - _dt.timedelta(days=6)
        elif range_type == 'month':
            start = today - _dt.timedelta(days=29)
        else:
            start = None

        data = _mgr.get_daily_chart_data(stats_db, start, today, range_type)
        return jsonify({"range": range_type, "data": data})