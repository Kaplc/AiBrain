"""SQLite 统计数据库"""
import os
import sqlite3
import datetime as _dt


class StatsDB:
    def __init__(self, db_path):
        self._path = db_path
        self._init_db()

    @property
    def path(self):
        return self._path

    def _get_conn(self):
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        db = self._get_conn()
        db.execute('''
            CREATE TABLE IF NOT EXISTS daily_stats (
                date TEXT PRIMARY KEY,
                added INTEGER DEFAULT 0,
                deleted INTEGER DEFAULT 0
            )
        ''')
        db.execute('''
            CREATE TABLE IF NOT EXISTS stream (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT NOT NULL,
                content TEXT,
                memory_id TEXT,
                created_at TEXT DEFAULT (datetime('now','localtime'))
            )
        ''')
        db.execute('CREATE INDEX IF NOT EXISTS idx_stream_time ON stream(created_at DESC)')
        db.commit()
        db.close()

    def update(self, date_str, added_delta=0, deleted_delta=0):
        """原子 upsert 更新日期统计"""
        db = self._get_conn()
        row = db.execute('SELECT * FROM daily_stats WHERE date = ?', (date_str,)).fetchone()
        if row:
            new_added = row['added'] + added_delta
            new_deleted = row['deleted'] + deleted_delta
            db.execute(
                'UPDATE daily_stats SET added=?, deleted=? WHERE date=?',
                (new_added, new_deleted, date_str)
            )
        else:
            db.execute(
                'INSERT INTO daily_stats (date, added, deleted) VALUES (?, ?, ?)',
                (date_str, max(0, added_delta), max(0, deleted_delta))
            )
        db.commit()
        db.close()

    def record_action(self, added=0, deleted=0):
        """记录今天的操作（快捷方法）"""
        self.update(_dt.date.today().isoformat(), added_delta=added, deleted_delta=deleted)

    def query_range(self, start_date=None):
        """查询范围内的数据，按 date 排序"""
        db = self._get_conn()
        if start_date:
            rows = db.execute(
                'SELECT date, added, deleted FROM daily_stats WHERE date >= ? ORDER BY date',
                (start_date.isoformat() if hasattr(start_date, 'isoformat') else str(start_date),)
            ).fetchall()
        else:
            rows = db.execute('SELECT date, added, deleted FROM daily_stats ORDER BY date').fetchall()
        db.close()
        return rows

    def status(self):
        """返回数据库状态摘要"""
        import os as _os
        db = self._get_conn()
        cnt = db.execute('SELECT COUNT(*) as cnt FROM daily_stats').fetchone()['cnt']
        latest = db.execute('SELECT date FROM daily_stats ORDER BY date DESC LIMIT 1').fetchone()
        db.close()
        size = _os.path.getsize(self._path) if _os.path.exists(self._path) else 0
        return {
            "records": cnt,
            "latest_date": latest['date'] if latest else None,
            "size_kb": round(size / 1024, 1),
        }

    # ── Stream（操作流）─────────────────────────────────────

    def append_stream(self, action, content='', memory_id=''):
        """写入一条操作记录"""
        db = self._get_conn()
        db.execute(
            'INSERT INTO stream (action, content, memory_id) VALUES (?, ?, ?)',
            (action, content[:500], memory_id)  # content 截断防过长
        )
        db.commit()
        rowid = db.execute('SELECT last_insert_rowid()').fetchone()[0]
        db.close()
        return rowid

    def query_stream(self, limit=50):
        """查询最近的操作流，最新的在前面"""
        db = self._get_conn()
        rows = db.execute(
            'SELECT id, action, content, memory_id, created_at FROM stream ORDER BY id DESC LIMIT ?',
            (limit,)
        ).fetchall()
        db.close()
        return [dict(r) for r in rows]

    def stream_count(self):
        """流记录总数"""
        db = self._get_conn()
        cnt = db.execute('SELECT COUNT(*) as c FROM stream').fetchone()[0]
        db.close()
        return cnt

    def get_memory_count(self):
        """获取记忆总数（所有日期的 added - deleted 总和）"""
        db = self._get_conn()
        result = db.execute('SELECT SUM(added - deleted) as total FROM daily_stats').fetchone()
        db.close()
        return result[0] or 0

    def sync_qdrant_count(self):
        """从 Qdrant 获取实际记忆数量并同步到数据库"""
        try:
            import sys
            import os
            # 添加项目根目录到路径以导入 brain_mcp
            backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            project_root = os.path.dirname(backend_dir)
            if project_root not in sys.path:
                sys.path.insert(0, project_root)

            from brain_mcp.config import settings
            from qdrant_client import QdrantClient
            
            client = QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)
            collection_info = client.get_collection(settings.collection_name)
            qdrant_count = collection_info.points_count
            
            # 获取当前数据库中的总数
            db = self._get_conn()
            current_total = db.execute('SELECT SUM(added - deleted) as total FROM daily_stats').fetchone()[0] or 0
            
            # 如果 Qdrant 数量与数据库不一致，调整今天的记录
            if qdrant_count != current_total:
                today_str = _dt.date.today().isoformat()
                diff = qdrant_count - current_total
                
                # 获取今天的记录
                row = db.execute('SELECT * FROM daily_stats WHERE date = ?', (today_str,)).fetchone()
                if row:
                    new_added = max(0, row['added'] + diff)
                    db.execute(
                        'UPDATE daily_stats SET added = ? WHERE date = ?',
                        (new_added, today_str)
                    )
                else:
                    db.execute(
                        'INSERT INTO daily_stats (date, added, deleted) VALUES (?, ?, 0)',
                        (today_str, max(0, qdrant_count))
                    )
                db.commit()
            
            db.close()
            return qdrant_count
        except Exception as e:
            print(f"[database] Failed to sync qdrant count: {e}")
            return None
