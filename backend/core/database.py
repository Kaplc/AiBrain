"""SQLite 统计数据库（单例）：存储每日统计、操作流、搜索历史"""
import os
import sqlite3
import datetime as _dt
import logging
import traceback as _tb

_db_logger = logging.getLogger('memory')


class StatsDB:
    _instance = None

    def __init__(self, db_path):
        self._path = db_path
        self._init_db()
        self.trim_chat_messages(keep_last=1000)

    @classmethod
    def get_instance(cls, db_path):
        if cls._instance is None:
            cls._instance = cls(db_path)
        return cls._instance

    @property
    def path(self):
        """返回数据库文件路径"""
        return self._path

    def _get_conn(self):
        """获取 SQLite 连接（每次操作新建，关闭释放）"""
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """初始化数据库表结构：daily_stats、stream、search_history"""
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
                created_at TEXT DEFAULT (datetime('now','localtime')),
                status TEXT DEFAULT 'done',
                entities TEXT DEFAULT ''
            )
        ''')
        # 迁移：给已有的 stream 表添加 status 列
        try:
            db.execute('ALTER TABLE stream ADD COLUMN status TEXT DEFAULT "done"')
        except Exception:
            pass  # 列已存在则忽略
        # 迁移：给已有的 stream 表添加 entities 列
        try:
            db.execute('ALTER TABLE stream ADD COLUMN entities TEXT DEFAULT ""')
        except Exception:
            pass  # 列已存在则忽略
        db.execute('CREATE INDEX IF NOT EXISTS idx_stream_time ON stream(created_at DESC)')
        db.execute('''
            CREATE TABLE IF NOT EXISTS search_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now','localtime'))
            )
        ''')
        # ── chat_messages：意识流聊天消息持久化 ──
        db.execute('''
            CREATE TABLE IF NOT EXISTS chat_messages (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                role        TEXT NOT NULL,
                content     TEXT NOT NULL,
                is_thought  INTEGER NOT NULL DEFAULT 0,
                tokens_in   INTEGER NOT NULL DEFAULT 0,
                tokens_out  INTEGER NOT NULL DEFAULT 0,
                created_at  TEXT DEFAULT (datetime('now','localtime'))
            )
        ''')
        db.execute('CREATE INDEX IF NOT EXISTS idx_chat_created ON chat_messages(created_at DESC)')
        # ── token_usage：LLM Token 用量记录 ──
        db.execute('''
            CREATE TABLE IF NOT EXISTS token_usage (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                prompt_tokens     INTEGER NOT NULL DEFAULT 0,
                completion_tokens INTEGER NOT NULL DEFAULT 0,
                cache_hit_tokens  INTEGER NOT NULL DEFAULT 0,
                cache_miss_tokens INTEGER NOT NULL DEFAULT 0,
                total_tokens      INTEGER NOT NULL DEFAULT 0,
                model             TEXT DEFAULT '',
                source            TEXT DEFAULT 'chat',
                created_at        TEXT DEFAULT (datetime('now','localtime'))
            )
        ''')
        db.execute('CREATE INDEX IF NOT EXISTS idx_token_usage_created ON token_usage(created_at DESC)')
        db.execute('''
            CREATE TABLE IF NOT EXISTS build_status (
                build_id TEXT PRIMARY KEY,
                status TEXT DEFAULT 'building',
                msg TEXT DEFAULT '',
                updated_at TEXT DEFAULT (datetime('now','localtime'))
            )
        ''')
        db.commit()
        db.close()

    def update(self, date_str, added_delta=0, deleted_delta=0):
        """原子 upsert 更新指定日期的统计（added/deleted 增量）"""
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
        """快捷方法：记录今天的 added/deleted 操作增量"""
        self.update(_dt.date.today().isoformat(), added_delta=added, deleted_delta=deleted)
        self.prune_old_stats(keep_days=30)

    def prune_old_stats(self, keep_days=30):
        """删除 keep_days 天之前的 daily_stats 旧数据"""
        db = self._get_conn()
        cutoff = (_dt.date.today() - _dt.timedelta(days=keep_days)).isoformat()
        db.execute('DELETE FROM daily_stats WHERE date < ?', (cutoff,))
        db.commit()
        db.close()

    def query_range(self, start_date=None):
        """查询指定日期范围内的每日统计数据（按日期升序）"""
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

    def append_stream(self, action, content='', memory_id='', status='done', entities=''):
        """写入一条操作流记录（如 store/update/delete），自动裁剪旧记录"""
        db = self._get_conn()
        db.execute(
            'INSERT INTO stream (action, content, memory_id, status, entities) VALUES (?, ?, ?, ?, ?)',
            (action, content[:500], memory_id, status, entities)
        )
        db.commit()
        rowid = db.execute('SELECT last_insert_rowid()').fetchone()[0]
        db.close()

        # 写入后自动裁剪该 action 的旧记录（保留 30 条）
        self.trim_stream(action, keep=30)

        return rowid

    def update_stream_status(self, rowid, status):
        """更新流记录的状态（如 pending -> done）"""
        db = self._get_conn()
        db.execute('UPDATE stream SET status=? WHERE id=?', (status, rowid))
        db.commit()
        db.close()

    def update_stream_content(self, rowid, content):
        """更新流记录的内容（如保存成功后替换为实际存储的事实）"""
        db = self._get_conn()
        db.execute('UPDATE stream SET content=? WHERE id=?', (content, rowid))
        db.commit()
        db.close()

    def update_stream_entities(self, rowid, entities):
        """更新流记录的实体标签"""
        db = self._get_conn()
        db.execute('UPDATE stream SET entities=? WHERE id=?', (entities, rowid))
        db.commit()
        db.close()

    def update_build_status(self, build_id, status, msg=''):
        """更新构建状态（building/done/failed）"""
        db = self._get_conn()
        db.execute(
            'INSERT OR REPLACE INTO build_status (build_id, status, msg, updated_at) VALUES (?, ?, ?, datetime("now","localtime"))',
            (build_id, status, msg)
        )
        db.commit()
        db.close()

    def get_build_status(self, build_id):
        """获取构建状态和消息"""
        db = self._get_conn()
        row = db.execute('SELECT status, msg FROM build_status WHERE build_id=?', (build_id,)).fetchone()
        db.close()
        if row:
            return row['status'], row['msg']
        return 'unknown', ''

    def query_stream(self, action=None, limit=50):
        """查询最近的操作流记录，最新的在前面"""
        db = self._get_conn()
        if action:
            rows = db.execute(
                'SELECT id, action, content, memory_id, created_at, status, entities FROM stream WHERE action=? ORDER BY id DESC LIMIT ?',
                (action, limit)
            ).fetchall()
        else:
            rows = db.execute(
                'SELECT id, action, content, memory_id, created_at, status, entities FROM stream ORDER BY id DESC LIMIT ?',
                (limit,)
            ).fetchall()
        db.close()
        return [dict(r) for r in rows]

    def query_stream_days(self, action=None, days=3):
        """查询最近 N 天内的所有操作流记录"""
        db = self._get_conn()
        cutoff = f"{-days} days"
        if action:
            rows = db.execute(
                "SELECT id, action, content, memory_id, created_at, status, entities "
                "FROM stream WHERE action=? AND created_at >= datetime('now','localtime',?) "
                "ORDER BY id DESC",
                (action, cutoff)
            ).fetchall()
        else:
            rows = db.execute(
                "SELECT id, action, content, memory_id, created_at, status, entities "
                "FROM stream WHERE created_at >= datetime('now','localtime',?) "
                "ORDER BY id DESC",
                (cutoff,)
            ).fetchall()
        db.close()
        return [dict(r) for r in rows]

    def stream_count(self, action=None):
        """获取流记录总数"""
        db = self._get_conn()
        if action:
            cnt = db.execute('SELECT COUNT(*) as c FROM stream WHERE action=?', (action,)).fetchone()[0]
        else:
            cnt = db.execute('SELECT COUNT(*) as c FROM stream').fetchone()[0]
        db.close()
        return cnt

    def trim_stream(self, action, keep=30):
        """每个 action 类型只保留最近 keep 条记录"""
        db = self._get_conn()
        # 先查该 action 的总条数
        total = db.execute('SELECT COUNT(*) as c FROM stream WHERE action=?', (action,)).fetchone()[0]
        if total > keep:
            # 删除多余的旧记录（保留 id 最大的 keep 条）
            db.execute(f'''
                DELETE FROM stream WHERE action=? AND id NOT IN (
                    SELECT id FROM stream WHERE action=? ORDER BY id DESC LIMIT ?
                )
            ''', (action, action, keep))
            db.commit()
        db.close()

    def get_memory_count(self):
        """获取记忆总数（所有日期 added - deleted 的累计值）"""
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

            client = QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port, check_compatibility=False)
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

    # ── 搜索历史 ──────────────────────────────────────────────

    def add_search_history(self, query: str):
        """添加搜索记录（去重：先删同query再插，保持最多20条）"""
        caller = ''.join(_tb.format_stack()[-4:-1])
        _db_logger.info(f"[TRACE] add_search_history called | query={query[:80]!r}\nCaller:\n{caller}")
        db = self._get_conn()
        db.execute('DELETE FROM search_history WHERE query = ?', (query,))
        db.execute(
            'INSERT INTO search_history (query) VALUES (?)',
            (query[:500],)
        )
        db.commit()

        # 只保留最近20条
        total = db.execute('SELECT COUNT(*) as c FROM search_history').fetchone()[0]
        if total > 20:
            db.execute(f'''
                DELETE FROM search_history WHERE id NOT IN (
                    SELECT id FROM search_history ORDER BY id DESC LIMIT 20
                )
            ''')
            db.commit()
        db.close()

    def get_search_history(self, limit: int = 20):
        """获取最近的搜索记录"""
        db = self._get_conn()
        rows = db.execute(
            'SELECT id, query, created_at FROM search_history ORDER BY id DESC LIMIT ?',
            (limit,)
        ).fetchall()
        db.close()
        return [dict(r) for r in rows]

    def clear_search_history(self):
        """清空搜索历史"""
        db = self._get_conn()
        db.execute('DELETE FROM search_history')
        db.commit()
        db.close()

    # ── Chat Messages（意识流聊天消息）────────────────────────

    def append_chat_message(self, role, content, is_thought=0, tokens_in=0, tokens_out=0):
        """写入一条聊天消息（user / assistant / system）"""
        db = self._get_conn()
        db.execute(
            'INSERT INTO chat_messages (role, content, is_thought, tokens_in, tokens_out) VALUES (?, ?, ?, ?, ?)',
            (role, content, is_thought, tokens_in, tokens_out)
        )
        db.commit()
        rowid = db.execute('SELECT last_insert_rowid()').fetchone()[0]
        db.close()
        return rowid

    def list_chat_messages(self, limit=100):
        """查询聊天消息（按 created_at ASC，最新在最后）"""
        db = self._get_conn()
        rows = db.execute(
            'SELECT id, role, content, is_thought, tokens_in, tokens_out, created_at '
            'FROM chat_messages ORDER BY id ASC LIMIT ?',
            (limit,)
        ).fetchall()
        db.close()
        return [dict(r) for r in rows]

    def clear_chat_messages(self):
        """清空正常对话消息（is_thought=0），保留 idle 思绪（is_thought=1）"""
        db = self._get_conn()
        db.execute('DELETE FROM chat_messages WHERE is_thought = 0')
        db.commit()
        db.close()

    def trim_chat_messages(self, keep_last=1000):
        """启动时裁剪：只保留最近 keep_last 条"""
        db = self._get_conn()
        total = db.execute('SELECT COUNT(*) as c FROM chat_messages').fetchone()[0]
        if total > keep_last:
            db.execute('''
                DELETE FROM chat_messages WHERE id NOT IN (
                    SELECT id FROM chat_messages ORDER BY id DESC LIMIT ?
                )
            ''', (keep_last,))
            db.commit()
        db.close()

    # ── Token Usage（LLM 调用用量记录）─────────────────────

    def record_token_usage(self, prompt_tokens=0, completion_tokens=0,
                           cache_hit_tokens=0, cache_miss_tokens=0,
                           model='', source='chat'):
        """记录一次 LLM 调用的 Token 用量（非阻塞，失败只打日志）"""
        total = prompt_tokens + completion_tokens
        try:
            db = self._get_conn()
            db.execute(
                'INSERT INTO token_usage '
                '(prompt_tokens, completion_tokens, cache_hit_tokens, cache_miss_tokens, '
                'total_tokens, model, source) VALUES (?, ?, ?, ?, ?, ?, ?)',
                (prompt_tokens, completion_tokens, cache_hit_tokens,
                 cache_miss_tokens, total, model, source)
            )
            db.commit()
            db.close()
        except Exception as e:
            _db_logger.warning(f"[token_usage] record failed: {e}")

    def get_token_usage_summary(self, hours=24):
        """查询最近 N 小时的聚合摘要 + 时序数据

        Args:
            hours: 时间范围（小时）

        Returns:
            {
                "summary": {prompt_tokens, completion_tokens, cache_hit_tokens,
                            cache_miss_tokens, total_tokens, cache_hit_rate},
                "data": [{date, prompt_tokens, completion_tokens,
                          cache_hit_tokens, total_tokens}, ...]
            }
        """
        db = self._get_conn()
        cutoff = f'-{hours} hours'

        # 聚合摘要
        row = db.execute(
            "SELECT COALESCE(SUM(prompt_tokens),0) as p,"
            "       COALESCE(SUM(completion_tokens),0) as c,"
            "       COALESCE(SUM(cache_hit_tokens),0) as ch,"
            "       COALESCE(SUM(cache_miss_tokens),0) as cm,"
            "       COALESCE(SUM(total_tokens),0) as t "
            "FROM token_usage WHERE created_at >= datetime('now','localtime',?)",
            (cutoff,)
        ).fetchone()

        summary = {
            "prompt_tokens": row[0],
            "completion_tokens": row[1],
            "cache_hit_tokens": row[2],
            "cache_miss_tokens": row[3],
            "total_tokens": row[4],
            "cache_hit_rate": round(row[2] / (row[2] + row[3]), 4) if (row[2] + row[3]) > 0 else 0,
        }

        # 时序分组：24h → 按15分钟, 7d/30d → 按天
        if hours <= 24:
            period_expr = "strftime('%H:', created_at) || printf('%02d', cast(strftime('%M', created_at) as integer) / 15 * 15)"
        else:
            period_expr = "strftime('%m-%d', created_at)"

        rows = db.execute(
            f"SELECT {period_expr} as period,"
            "       SUM(prompt_tokens) as p, SUM(completion_tokens) as c,"
            "       SUM(cache_hit_tokens) as ch, SUM(total_tokens) as t "
            "FROM token_usage WHERE created_at >= datetime('now','localtime',?) "
            "GROUP BY period ORDER BY MIN(created_at)",
            (cutoff,)
        ).fetchall()

        data = [
            {
                "date": r[0],
                "prompt_tokens": r[1],
                "completion_tokens": r[2],
                "cache_hit_tokens": r[3],
                "total_tokens": r[4],
            }
            for r in rows
        ]

        db.close()
        return {"summary": summary, "data": data}

    # ── DeepSeek 模型参考定价（元/百万 token） ───────────
    _MODEL_COST_TABLE = {
        'deepseek-chat':      {'input': 0.14, 'output': 0.28, 'cache_hit_input': 0.07},
        'deepseek-reasoner':  {'input': 0.55, 'output': 2.19, 'cache_hit_input': 0.07},
        'gpt-4o-mini':        {'input': 0.15, 'output': 0.60, 'cache_hit_input': 0.075},
        'gpt-4o':             {'input': 2.50, 'output': 10.0, 'cache_hit_input': 1.25},
    }

    def get_today_cost(self) -> dict:
        """查询今日 Token 消耗及预估费用

        Returns:
            {
                "total_cost": 0.00,        # 预估总费用（元）
                "prompt_cost": 0.00,        # 输入费用
                "completion_cost": 0.00,    # 输出费用
                "prompt_tokens": 0,         # 输入 token 数
                "completion_tokens": 0,     # 输出 token 数
            }
        """
        db = self._get_conn()
        rows = db.execute(
            "SELECT model,"
            "       SUM(prompt_tokens) as p, SUM(completion_tokens) as c,"
            "       SUM(cache_hit_tokens) as ch, SUM(cache_miss_tokens) as cm "
            "FROM token_usage "
            "WHERE created_at >= datetime('now','localtime','start of day') "
            "GROUP BY model"
        ).fetchall()

        total_cost = 0.0
        prompt_cost = 0.0
        completion_cost = 0.0
        total_prompt = 0
        total_completion = 0

        for row in rows:
            model_name = row[0] or 'unknown'
            p_tokens, c_tokens, ch_tokens, cm_tokens = row[1:5]
            total_prompt += p_tokens
            total_completion += c_tokens

            pricing = self._MODEL_COST_TABLE.get(model_name)
            if pricing:
                in_p  = pricing['input']
                in_ch = pricing['cache_hit_input']
                out_p = pricing['output']
            else:
                # 未识别的模型按 input ¥2 / output ¥8 估算
                in_p, in_ch, out_p = 2.0, 0.5, 8.0

            p_cost = (cm_tokens * in_p + ch_tokens * in_ch) / 1_000_000
            c_cost = (c_tokens * out_p) / 1_000_000
            total_cost += p_cost + c_cost
            prompt_cost += p_cost
            completion_cost += c_cost

        db.close()
        return {
            "total_cost": round(total_cost, 4),
            "prompt_cost": round(prompt_cost, 4),
            "completion_cost": round(completion_cost, 4),
            "prompt_tokens": total_prompt,
            "completion_tokens": total_completion,
        }
