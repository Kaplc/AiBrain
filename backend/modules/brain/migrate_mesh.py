"""
迁移脚本：将所有已有记忆的实体两两互联，形成局部网状结构。

用途：方案 A 实施前存入的记忆，其实体间没有横向连接，运行本脚本补建。
用法：python -m modules.brain.migrate_mesh
"""
import logging
import os
import sqlite3
import sys

# 确保上层目录可导入
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
logger = logging.getLogger('migrate_mesh')


def _exec(conn: sqlite3.Connection, sql: str, params=()) -> list[tuple]:
    return conn.execute(sql, params).fetchall()


def migrate(db_path: str):
    logger.info(f"[migrate_mesh] 打开数据库: {db_path}")
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys=ON")

    # 遍历所有记忆
    rows = _exec(conn, "SELECT mem0_id FROM memory_nodes")
    total = len(rows)
    logger.info(f"[migrate_mesh] 共 {total} 条记忆待处理")

    updated = 0
    for (mem0_id,) in rows:
        # 取出该记忆关联的所有实体
        entity_rows = _exec(
            conn,
            "SELECT entity_name FROM mentions WHERE mem0_id = ?",
            (mem0_id,),
        )
        entity_names = [r[0] for r in entity_rows]
        if len(entity_names) < 2:
            continue  # 少于2个实体无需建网

        # 两两建边（双向）
        for i, a in enumerate(entity_names):
            for b in entity_names[i + 1:]:
                conn.execute(
                    "INSERT OR IGNORE INTO entity_relations (from_entity, to_entity) VALUES (?, ?)",
                    (a, b),
                )
                conn.execute(
                    "INSERT OR IGNORE INTO entity_relations (from_entity, to_entity) VALUES (?, ?)",
                    (b, a),
                )
        conn.commit()
        updated += 1
        logger.info(f"[migrate_mesh] {mem0_id[:8]}: {entity_names} → mesh built")

    logger.info(f"[migrate_mesh] 完成，共处理 {updated} 条记忆")


if __name__ == '__main__':
    db_path = os.path.join(
        os.path.expanduser("~"), ".aibrain", "data", "memory_graph.db"
    )
    if not os.path.exists(db_path):
        logger.error(f"[migrate_mesh] 数据库不存在: {db_path}")
        sys.exit(1)

    migrate(db_path)
    logger.info("[migrate_mesh] 迁移完成")