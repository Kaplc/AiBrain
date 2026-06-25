"""Stats 路由 - /chart-data（纯转发）
提供图表统计数据：每日/每周/每月的 added/updated/total 趋势"""
from flask import request, jsonify
from modules.Stats.stats_mod import StatsManager

_mgr = StatsManager.get_instance()


def _anchor_to_actual(data: list) -> list:
    """将累计曲线的最后一点锚定到实际记忆数量，整体平移保持曲线形状不变"""
    if not data:
        return data
    try:
        from main_brain.memory import get_memory_count
        actual = get_memory_count()
        if actual <= 0:
            return data
        offset = actual - data[-1]['total']
        if offset == 0:
            return data
        for d in data:
            d['total'] = max(0, d['total'] + offset)
    except Exception:
        pass
    return data


def register(app, ready_state, logger, stats_db):
    @app.route('/chart-data', methods=['GET'])
    def chart_data():
        """获取图表数据，支持 today(24小时)/week(7天)/month(30天)"""
        range_type = request.args.get('range', 'week')
        import datetime as _dt
        today = _dt.date.today()

        if range_type == 'today':
            data = _mgr.get_hourly_chart_data(stats_db)
            return jsonify({"range": range_type, "data": _anchor_to_actual(data)})

        if range_type == 'week':
            start = today - _dt.timedelta(days=6)
        elif range_type == 'month':
            start = today - _dt.timedelta(days=29)
        else:
            start = None

        data = _mgr.get_daily_chart_data(stats_db, start, today, range_type)
        return jsonify({"range": range_type, "data": _anchor_to_actual(data)})