"""统计图表路由：/chart-data"""
import datetime as _dt
from flask import request, jsonify


def register(app, stats_db):
    @app.route('/chart-data', methods=['GET'])
    def chart_data():
        range_type = request.args.get('range', 'week')
        today = _dt.date.today()

        if range_type == 'today':
            return jsonify({"range": range_type, "data": _get_hourly_data(stats_db)})
        elif range_type == 'week':
            start = today - _dt.timedelta(days=6)
        elif range_type == 'month':
            start = today - _dt.timedelta(days=29)
        else:
            start = None

        data = _get_daily_data(stats_db, start, today, range_type)
        return jsonify({"range": range_type, "data": data})


def _get_update_counts(stats_db, start_date=None, end_date=None):
    """从 stream 表查询每日/每小时的 update 操作数"""
    db = stats_db._get_conn()
    if start_date and end_date:
        rows = db.execute(
            '''SELECT DATE(created_at) as d, COUNT(*) as cnt
               FROM stream WHERE action='update'
                 AND DATE(created_at) BETWEEN ? AND ?
               GROUP BY d ORDER BY d''',
            (start_date.isoformat(), end_date.isoformat())
        ).fetchall()
    elif end_date:
        rows = db.execute(
            '''SELECT DATE(created_at) as d, COUNT(*) as cnt
               FROM stream WHERE action='update' AND DATE(created_at) <= ?
               GROUP BY d ORDER BY d''',
            (end_date.isoformat(),)
        ).fetchall()
    else:
        rows = db.execute(
            '''SELECT DATE(created_at) as d, COUNT(*) as cnt
               FROM stream WHERE action='update'
               GROUP BY d ORDER BY d'''
        ).fetchall()
    db.close()
    return {r['d']: r['cnt'] for r in rows}


def _get_daily_data(stats_db, start_date, end_date, range_type):
    """获取指定日期范围内的每日数据"""
    rows = stats_db.query_range(start_date)

    # 获取更新计数（来自 stream 表）
    update_counts = _get_update_counts(stats_db, start_date, end_date)

    # 日期到数据的映射
    data_map = {}
    for r in rows:
        data_map[r['date']] = {'added': r['added'], 'deleted': r['deleted']}

    # 计算起始累计值
    total_so_far = 0
    if start_date:
        db = stats_db._get_conn()
        prev_total = db.execute(
            'SELECT SUM(added - deleted) as total FROM daily_stats WHERE date < ?',
            (start_date.isoformat(),)
        ).fetchone()
        db.close()
        total_so_far = prev_total['total'] or 0

    data = []
    if range_type == 'week':
        for i in range(6, -1, -1):
            date = end_date - _dt.timedelta(days=i)
            ds = date.isoformat()
            stats = data_map.get(ds, {'added': 0, 'deleted': 0})
            total_so_far += stats['added'] - stats['deleted']
            data.append({
                "date": ds,
                "added": stats['added'],
                "updated": update_counts.get(ds, 0),
                "total": max(0, total_so_far),
            })
    elif range_type == 'month':
        for i in range(29, -1, -1):
            date = end_date - _dt.timedelta(days=i)
            ds = date.isoformat()
            stats = data_map.get(ds, {'added': 0, 'deleted': 0})
            total_so_far += stats['added'] - stats['deleted']
            data.append({
                "date": ds,
                "added": stats['added'],
                "updated": update_counts.get(ds, 0),
                "total": max(0, total_so_far),
            })
    else:
        for r in rows:
            total_so_far += r['added'] - r['deleted']
            data.append({
                "date": r['date'],
                "added": r['added'],
                "updated": update_counts.get(r['date'], 0),
                "total": max(0, total_so_far),
            })

    return data


def _get_hourly_data(stats_db):
    """获取最近24小时按小时统计的数据，最新刻度为当前小时"""
    now = _dt.datetime.now()
    # 当前已过的整小时（如 01:46 → 01:00）
    current_hour = now.replace(minute=0, second=0, microsecond=0)
    # 24小时前的整点
    since = current_hour - _dt.timedelta(hours=23)
    since_str = since.strftime('%Y-%m-%d %H:%M:%S')

    db = stats_db._get_conn()

    # 查询24小时内的操作记录
    rows = db.execute('''
        SELECT strftime('%Y-%m-%d %H:00:00', created_at) as hour_slot,
               action, COUNT(*) as cnt
        FROM stream
        WHERE created_at >= ?
        GROUP BY hour_slot, action
        ORDER BY hour_slot
    ''', (since_str,)).fetchall()
    db.close()

    # 按小时槽聚合
    hour_stats = {}
    for r in rows:
        slot = r['hour_slot']
        if slot not in hour_stats:
            hour_stats[slot] = {'added': 0, 'updated': 0}
        if r['action'] == 'store':
            hour_stats[slot]['added'] += r['cnt']
        elif r['action'] == 'update':
            hour_stats[slot]['updated'] += r['cnt']

    # 获取24小时之前的累计总数
    db = stats_db._get_conn()
    prev_total = db.execute('''
        SELECT SUM(added - deleted) as total FROM daily_stats
        WHERE date < ?
    ''', (since.date().isoformat(),)).fetchone()
    db.close()
    total_so_far = prev_total['total'] or 0 if prev_total else 0

    # 生成24小时数据（从 since=23小时前 到 current_hour=当前小时，共24个）
    hourly_data = []
    for i in range(24):
        slot_time = since + _dt.timedelta(hours=i)
        iso_slot = slot_time.strftime('%Y-%m-%d %H:00:00')
        stats = hour_stats.get(iso_slot, {'added': 0, 'updated': 0})
        total_so_far += stats['added']
        hourly_data.append({
            "date": slot_time.strftime('%H:00'),
            "added": stats['added'],
            "updated": stats['updated'],
            "total": max(0, total_so_far),
        })

    return hourly_data
