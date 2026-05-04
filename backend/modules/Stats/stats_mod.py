"""图表统计业务逻辑（单例） - 供 routes/stats_routes.py 调用"""
import datetime as _dt


class StatsManager:
    _instance = None

    def __init__(self):
        pass

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def get_update_counts(self, stats_db, start_date=None, end_date=None):
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

    def get_daily_chart_data(self, stats_db, start_date, end_date, range_type):
        """获取指定日期范围内的每日图表数据"""
        rows = stats_db.query_range(start_date)
        update_counts = self.get_update_counts(stats_db, start_date, end_date)
        data_map = {}
        for r in rows:
            data_map[r['date']] = {'added': r['added'], 'deleted': r['deleted']}
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

    def get_hourly_chart_data(self, stats_db):
        """获取最近24小时按小时统计的图表数据"""
        now = _dt.datetime.now()
        current_hour = now.replace(minute=0, second=0, microsecond=0)
        since = current_hour - _dt.timedelta(hours=23)
        since_str = since.strftime('%Y-%m-%d %H:%M:%S')

        db = stats_db._get_conn()
        rows = db.execute('''
            SELECT strftime('%Y-%m-%d %H:00:00', created_at) as hour_slot,
                   action, COUNT(*) as cnt
            FROM stream
            WHERE created_at >= ?
            GROUP BY hour_slot, action
            ORDER BY hour_slot
        ''', (since_str,)).fetchall()
        db.close()

        hour_stats = {}
        for r in rows:
            slot = r['hour_slot']
            if slot not in hour_stats:
                hour_stats[slot] = {'added': 0, 'updated': 0}
            if r['action'] == 'store':
                hour_stats[slot]['added'] += r['cnt']
            elif r['action'] == 'update':
                hour_stats[slot]['updated'] += r['cnt']

        db = stats_db._get_conn()
        prev_total = db.execute('''
            SELECT SUM(added - deleted) as total FROM daily_stats
            WHERE date < ?
        ''', (since.date().isoformat(),)).fetchone()
        db.close()
        total_so_far = prev_total['total'] or 0 if prev_total else 0

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