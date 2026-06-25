"""
情景记忆图索引层（Scene Graph）— 替代旧实体图的主扩散职责

设计目标（见 plan/scene-memory-graph-diffusion.md）：
  - 旧实体图（graph.py）以「名词共现」为中心，无法表达 why/result/lesson/affect。
  - 情景图以「场景之间的联想」为中心：scene → anchor → scene。
  - nodes 是第一类输入（锚点），episodic 是扩散判别信号，affect/importance 是扩散权重。

三张表（对应数据结构章节的 SceneAnchorEdge / SceneSceneEdge / AnchorNode）：
  - anchor_nodes:   规范化锚点 {name, type, memory_count}（name 唯一）
  - scene_anchors:  scene ↔ anchor 边 {scene_id, anchor_name, role, weight}
                    （role: seed/bridge/emotion/goal，扩散种子与桥接）
  - scene_edges:    scene ↔ scene 预计算候选边 {from_scene, to_scene, relation_type,
                    weight, via_anchor}，建边时 topN 限边（FR-011 防止图爆炸）

锚点规范化复用 qdrant/store.dedup_node_name（向量去重 aibrain_nodes），不在本层重复 embed。
scene_edges 是 scene_anchors 的「物化、限边」视图：每次 link_scene 时增量重建该 scene 的边。

模块单例：外部经 get_scene_graph() 转发访问。
"""
import logging
import math
import os
import sqlite3
import threading

logger = logging.getLogger('scene_graph')

_GRAPH_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "scene_graph.db"
)

_INSTANCE = None
_INSTANCE_LOCK = threading.Lock()

# 锚点类型 → 扩散权重（与旧图 search_related_new 的权重口径一致，保证可比性）
_TYPE_WEIGHT = {
    "person": 1.0,
    "goal": 0.9,
    "concept": 0.7,
    "emotion": 0.5,
}

# node.type → scene_anchor.role
_TYPE_TO_ROLE = {
    "emotion": "emotion",
    "goal": "goal",
    "person": "seed",
    "concept": "seed",
}

# 图规模控制（FR-011）：每条 scene 最多保留多少条强边
_MAX_EDGES_PER_SCENE = 8

_CREATE_TABLES = """
CREATE TABLE IF NOT EXISTS anchor_nodes (
    name TEXT PRIMARY KEY,
    type TEXT NOT NULL DEFAULT 'concept',
    memory_count INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS scene_anchors (
    scene_id TEXT NOT NULL,
    anchor_name TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'seed',
    weight REAL NOT NULL DEFAULT 1.0,
    PRIMARY KEY (scene_id, anchor_name),
    FOREIGN KEY (anchor_name) REFERENCES anchor_nodes(name) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_scene_anchors_anchor ON scene_anchors(anchor_name);
CREATE INDEX IF NOT EXISTS idx_scene_anchors_scene ON scene_anchors(scene_id);
CREATE TABLE IF NOT EXISTS scene_edges (
    from_scene TEXT NOT NULL,
    to_scene TEXT NOT NULL,
    relation_type TEXT NOT NULL DEFAULT 'shared_node',
    weight REAL NOT NULL DEFAULT 1.0,
    via_anchor TEXT,
    PRIMARY KEY (from_scene, to_scene)
);
CREATE INDEX IF NOT EXISTS idx_scene_edges_from ON scene_edges(from_scene);
CREATE INDEX IF NOT EXISTS idx_scene_edges_to ON scene_edges(to_scene);
-- 迁移来源映射：legacy_id → scene_id（幂等去重的依据）
CREATE TABLE IF NOT EXISTS scene_origin (
    scene_id TEXT PRIMARY KEY,
    legacy_id TEXT UNIQUE,
    user_id TEXT,
    created_at TEXT
);
"""


class SceneGraph:
    """情景图索引单例

    线程安全：写操作通过 _write_lock 串行化（SQLite 单连接 + WAL）。
    """

    def __init__(self, db_path: str):
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(_CREATE_TABLES)
        self._write_lock = threading.Lock()
        logger.info(f"[scene_graph] initialized at {db_path}")

    def _exec(self, sql: str, params=()) -> list[tuple]:
        cur = self._conn.execute(sql, params)
        return cur.fetchall()

    # ── 写入：link_scene ───────────────────────────────────────

    def link_scene(self, scene_id: str, nodes: list[dict],
                   affect: dict | None = None, importance: float = 0.3,
                   legacy_id: str | None = None, user_id: str | None = None,
                   created_at: str | None = None) -> None:
        """建立/更新一条情景的图索引：锚点登记 + scene-anchor 边 + scene-scene 候选边（限边）

        nodes 已由 encoder 规范化（含 dedup_node_name），本层不再 embed，避免重复开销。
        幂等：同一 scene_id 重写时先清除其旧边再重建（迁移回放可重复执行）。

        Args:
            scene_id: Qdrant point id（情景主键）
            nodes: [{name, type}]，核心锚点
            affect: {intensity: float, ...}，情感烈度用于边权重
            importance: 0-1 重要性权重
            legacy_id: 迁移来源（幂等去重）
        """
        if not scene_id:
            return
        affect = affect or {}
        intensity = _clamp(affect.get("intensity", 0.0), -3.0, 3.0, 0.0)
        # affect 烈度绝对值归一化到 0-1，作为边权加成
        affect_boost = 1.0 + min(1.0, abs(intensity) / 3.0) * 0.3
        importance = _clamp(importance, 0.0, 1.0, 0.3)

        with self._write_lock:
            # 幂等：先删该 scene 的旧锚点边与候选边，再重建
            self._clear_scene(scene_id)

            valid_nodes = _dedup_nodes(nodes)
            if not valid_nodes:
                logger.info(f"[scene_graph:link] {scene_id[:8]} no valid nodes, scene recorded without edges")
                self._record_origin(scene_id, legacy_id, user_id, created_at)
                self._conn.commit()
                return

            # 1. 登记/更新 anchor_nodes + 计数
            anchor_roles = {}
            for nd in valid_nodes:
                name = nd["name"]
                typ = nd.get("type", "concept")
                role = _TYPE_TO_ROLE.get(typ, "seed")
                anchor_roles[name] = role
                self._upsert_anchor(name, typ)
                # scene-anchor 边权重：锚点类型权重 × importance × affect_boost
                edge_weight = round(
                    _TYPE_WEIGHT.get(typ, 0.7) * (0.5 + importance) * affect_boost, 4
                )
                self._conn.execute(
                    "INSERT OR REPLACE INTO scene_anchors "
                    "(scene_id, anchor_name, role, weight) VALUES (?, ?, ?, ?)",
                    (scene_id, name, role, edge_weight),
                )

            # 2. 增量重建该 scene 的候选边（共享锚点 → 邻居 scene）
            self._rebuild_scene_edges(scene_id, valid_nodes)

            # 3. 迁移来源（幂等）
            self._record_origin(scene_id, legacy_id, user_id, created_at)

            self._conn.commit()
            logger.info(
                f"[scene_graph:link] {scene_id[:8]} → {len(valid_nodes)} anchors | "
                f"importance={importance} intensity={intensity}"
            )

    def _upsert_anchor(self, name: str, typ: str) -> None:
        """登记锚点（type 冲突保留更高权重类型）"""
        self._conn.execute(
            "INSERT INTO anchor_nodes (name, type, memory_count) VALUES (?, ?, 0) "
            "ON CONFLICT(name) DO UPDATE SET type = ?",
            (name, typ, typ),
        )

    def _record_origin(self, scene_id: str, legacy_id: str | None,
                       user_id: str | None, created_at: str | None) -> None:
        if legacy_id:
            self._conn.execute(
                "INSERT OR REPLACE INTO scene_origin "
                "(scene_id, legacy_id, user_id, created_at) VALUES (?, ?, ?, ?)",
                (scene_id, legacy_id, user_id, created_at),
            )

    def _clear_scene(self, scene_id: str) -> None:
        """清除一条 scene 的所有锚点边与候选边（幂等重建的前置）"""
        self._conn.execute("DELETE FROM scene_anchors WHERE scene_id = ?", (scene_id,))
        self._conn.execute(
            "DELETE FROM scene_edges WHERE from_scene = ? OR to_scene = ?",
            (scene_id, scene_id),
        )

    def _rebuild_scene_edges(self, scene_id: str, nodes: list[dict]) -> None:
        """为 scene 生成候选边：通过共享锚点找邻居 scene，按权重排序保留 topN（双向存储）

        边权重 = Σ(共享锚点的 scene_anchor.weight) × importance 因子，体现 affect/importance 加权。
        每条 scene 的出边限 _MAX_EDGES_PER_SCENE 条，防止图爆炸（FR-011）。
        """
        anchor_names = [nd["name"] for nd in nodes]
        if not anchor_names:
            return
        ph = ",".join("?" * len(anchor_names))
        # 查共享锚点的其它 scene，聚合共享锚点权重
        rows = self._exec(
            f"""SELECT scene_id, SUM(weight) AS shared_w
                FROM scene_anchors
                WHERE anchor_name IN ({ph}) AND scene_id != ?
                GROUP BY scene_id""",
            (*anchor_names, scene_id),
        )
        if not rows:
            return
        # 取每个邻居的代表性锚点（权重最高的共享锚点）作为 via_anchor / relation_type
        affected_neighbors = []
        for neighbor_id, shared_w in rows:
            neighbor_id = str(neighbor_id)
            via = self._top_shared_anchor(scene_id, neighbor_id, anchor_names)
            weight = round((shared_w or 0.0) * 0.5, 4)  # 候选边权取共享锚点和的一半
            rel = _relation_for_role(self._role_of(scene_id, via))
            # 双向插入（邻居方向在它自己 link 时也会重建，这里双向保证查询简单）
            self._conn.execute(
                "INSERT OR REPLACE INTO scene_edges "
                "(from_scene, to_scene, relation_type, weight, via_anchor) VALUES (?, ?, ?, ?, ?)",
                (scene_id, neighbor_id, rel, weight, via),
            )
            self._conn.execute(
                "INSERT OR REPLACE INTO scene_edges "
                "(from_scene, to_scene, relation_type, weight, via_anchor) VALUES (?, ?, ?, ?, ?)",
                (neighbor_id, scene_id, rel, weight, via),
            )
            affected_neighbors.append(neighbor_id)
        # 限边：当前 scene 与每个受影响邻居的出边都裁剪到 topN，
        # 保证高频锚点不会让任一 scene 的出边无限增长（FR-011）。
        self._prune_scene_edges(scene_id)
        for nb in affected_neighbors:
            self._prune_scene_edges(nb)

    def _top_shared_anchor(self, scene_a: str, scene_b: str, anchor_names: list) -> str | None:
        """两个 scene 共享锚点中权重最高的一个"""
        ph = ",".join("?" * len(anchor_names))
        rows = self._exec(
            f"""SELECT anchor_name FROM scene_anchors
                WHERE scene_id IN (?, ?) AND anchor_name IN ({ph})
                GROUP BY anchor_name ORDER BY MAX(weight) DESC LIMIT 1""",
            (scene_a, scene_b, *anchor_names),
        )
        return rows[0][0] if rows else None

    def _role_of(self, scene_id: str, anchor_name: str | None) -> str:
        if not anchor_name:
            return "seed"
        rows = self._exec(
            "SELECT role FROM scene_anchors WHERE scene_id = ? AND anchor_name = ?",
            (scene_id, anchor_name),
        )
        return rows[0][0] if rows else "seed"

    def _prune_scene_edges(self, scene_id: str) -> None:
        """限制单 scene 出边数量：按 weight 降序保留 topN，删除多余"""
        rows = self._exec(
            "SELECT to_scene FROM scene_edges WHERE from_scene = ? ORDER BY weight DESC",
            (scene_id,),
        )
        if len(rows) <= _MAX_EDGES_PER_SCENE:
            return
        drop = [r[0] for r in rows[_MAX_EDGES_PER_SCENE:]]
        if not drop:
            return
        ph = ",".join("?" * len(drop))
        self._conn.execute(
            f"DELETE FROM scene_edges WHERE from_scene = ? AND to_scene IN ({ph})",
            (scene_id, *drop),
        )

    # ── 读取：扩散与查询 ───────────────────────────────────────

    def get_scene_anchors(self, scene_id: str) -> list[dict]:
        """返回一条 scene 的锚点列表（含 role/weight）"""
        rows = self._exec(
            "SELECT anchor_name, role, weight FROM scene_anchors WHERE scene_id = ?",
            (scene_id,),
        )
        return [{"name": r[0], "role": r[1], "weight": r[2]} for r in rows]

    def get_scenes_for_anchor(self, anchor_name: str, limit: int = 50) -> list[str]:
        """反查锚点关联的 scene 列表（1 跳共享锚点召回的基础）"""
        rows = self._exec(
            "SELECT scene_id FROM scene_anchors WHERE anchor_name = ? LIMIT ?",
            (anchor_name, limit),
        )
        return [r[0] for r in rows]

    def get_anchor_neighbors(self, anchor_names: list[str], exclude: set[str] | None = None,
                             limit: int = 100) -> list[tuple[str, float]]:
        """1 跳共享锚点召回：返回 (scene_id, 共享权重) 列表，排除已在 exclude 中的 scene"""
        exclude = exclude or set()
        if not anchor_names:
            return []
        ph = ",".join("?" * len(anchor_names))
        rows = self._exec(
            f"""SELECT scene_id, SUM(weight) AS w FROM scene_anchors
                WHERE anchor_name IN ({ph}) GROUP BY scene_id ORDER BY w DESC LIMIT ?""",
            (*anchor_names, limit),
        )
        return [(str(r[0]), r[1] or 0.0) for r in rows if str(r[0]) not in exclude]

    def get_scene_neighbors(self, scene_id: str, limit: int = 20) -> list[dict]:
        """返回 scene 的候选边邻居（含 weight/relation_type/via_anchor），供扩散用"""
        rows = self._exec(
            "SELECT to_scene, weight, relation_type, via_anchor "
            "FROM scene_edges WHERE from_scene = ? ORDER BY weight DESC LIMIT ?",
            (scene_id, limit),
        )
        return [
            {"scene_id": r[0], "weight": r[1], "relation_type": r[2], "via_anchor": r[3]}
            for r in rows
        ]

    def find_anchor(self, name: str) -> dict | None:
        """查询单个锚点（存在则返回 {name,type,memory_count}）"""
        rows = self._exec(
            "SELECT name, type, memory_count FROM anchor_nodes WHERE name = ?",
            (name,),
        )
        if not rows:
            return None
        return {"name": rows[0][0], "type": rows[0][1], "memory_count": rows[0][2]}

    def has_legacy(self, legacy_id: str) -> str | None:
        """迁移幂等：legacy_id 是否已迁移（返回对应 scene_id）"""
        rows = self._exec(
            "SELECT scene_id FROM scene_origin WHERE legacy_id = ?",
            (legacy_id,),
        )
        return rows[0][0] if rows else None

    # ── 维护：删除 / 重建 / 统计 ────────────────────────────────

    def delete_scene(self, scene_id: str) -> None:
        """删除一条 scene 的全部图索引（锚点边 + 候选边 + 来源），并清理孤立锚点"""
        with self._write_lock:
            # 先记录该 scene 的锚点，删除后判断是否变为孤立锚点
            anchors = [r[0] for r in self._exec(
                "SELECT anchor_name FROM scene_anchors WHERE scene_id = ?", (scene_id,)
            )]
            self._clear_scene(scene_id)
            self._conn.execute("DELETE FROM scene_origin WHERE scene_id = ?", (scene_id,))
            # 清理不再被任何 scene 引用的孤立锚点
            for name in anchors:
                cnt = self._exec(
                    "SELECT COUNT(*) FROM scene_anchors WHERE anchor_name = ?", (name,)
                )[0][0]
                if cnt == 0:
                    self._conn.execute("DELETE FROM anchor_nodes WHERE name = ?", (name,))
            self._conn.commit()
            logger.info(f"[scene_graph:delete] {scene_id[:8]} removed")

    def reindex(self, batch_callback=None) -> dict:
        """从 Qdrant payload 全量重建情景图索引（清空三表后按 payload 重建）

        用于 /memory/scene/reindex：后端重启后图索引可从主存储自动恢复（兼容性要求 #3）。
        batch_callback(n) 每 100 条调用一次，便于上报进度。
        """
        from modules.qdrant.store import get_qdrant_client, NEW_COLLECTION

        client = get_qdrant_client()
        offset = None
        total = 0
        linked = 0
        with self._write_lock:
            self._conn.executescript(
                "DELETE FROM scene_edges; DELETE FROM scene_anchors; "
                "DELETE FROM anchor_nodes; DELETE FROM scene_origin;"
            )
            self._conn.commit()
        # 释放锁后分批 scroll 重建（scroll 是只读，不需要持锁）
        while True:
            try:
                points, offset = client.scroll(
                    collection_name=NEW_COLLECTION, offset=offset, limit=100,
                    with_payload=True, with_vectors=False,
                )
            except Exception as e:
                logger.warning(f"[scene_graph:reindex] scroll failed: {e}")
                break
            if not points:
                break
            for p in points:
                total += 1
                payload = p.payload or {}
                nodes = payload.get("nodes") or []
                if not nodes:
                    continue
                try:
                    # link_scene 内部自管 _write_lock，此处不可再加锁（Lock 不可重入，否则死锁）
                    self.link_scene(
                        str(p.id), nodes,
                        affect=payload.get("affect"),
                        importance=payload.get("importance", 0.3),
                        legacy_id=(payload.get("origin") or {}).get("legacy_id"),
                        user_id=payload.get("user_id"),
                        created_at=payload.get("created_at"),
                    )
                    linked += 1
                except Exception as e:
                    logger.warning(f"[scene_graph:reindex] link failed for {str(p.id)[:8]}: {e}")
            if batch_callback:
                batch_callback(total)
            if offset is None:
                break
        logger.info(f"[scene_graph:reindex] DONE | linked={linked}/{total}")
        return {"total": total, "linked": linked}

    def rebuild_anchor_counts(self) -> None:
        """全量重建 anchor_nodes.memory_count（场景数）"""
        with self._write_lock:
            rows = self._exec(
                "SELECT anchor_name, COUNT(DISTINCT scene_id) FROM scene_anchors GROUP BY anchor_name"
            )
            for name, cnt in rows:
                self._conn.execute(
                    "UPDATE anchor_nodes SET memory_count = ? WHERE name = ?",
                    (cnt, name),
                )
            self._conn.commit()

    def get_stats(self) -> dict:
        """图规模与边数（FR-012 运行观测）"""
        try:
            scenes = self._exec(
                "SELECT COUNT(DISTINCT scene_id) FROM scene_anchors"
            )[0][0]
            anchors = self._exec("SELECT COUNT(*) FROM anchor_nodes")[0][0]
            sa_edges = self._exec("SELECT COUNT(*) FROM scene_anchors")[0][0]
            ss_edges = self._exec("SELECT COUNT(*) FROM scene_edges")[0][0]
            migrated = self._exec("SELECT COUNT(*) FROM scene_origin")[0][0]
            return {
                "scenes_indexed": scenes,
                "anchor_count": anchors,
                "scene_anchor_edges": sa_edges,
                "scene_scene_edges": ss_edges,
                "migrated_count": migrated,
            }
        except Exception as e:
            logger.warning(f"[scene_graph:stats] failed: {e}")
            return {}


# ── 工具函数 ─────────────────────────────────────────────────


def _clamp(v, lo, hi, default):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, f))


def _dedup_nodes(nodes: list[dict]) -> list[dict]:
    """nodes 去重保序（同名保留高权重 type）

    长度规则由 encoder 负责保证，本层只去重、不二次过滤，避免误丢有效锚点名。
    """
    if not nodes:
        return []
    rank = {"person": 4, "goal": 3, "concept": 2, "emotion": 1}
    seen = {}
    for nd in nodes:
        if not isinstance(nd, dict):
            continue
        name = str(nd.get("name", "")).strip()
        if not name:
            continue
        typ = str(nd.get("type", "concept")).strip() or "concept"
        key = name
        if key in seen and rank.get(typ, 0) <= rank.get(seen[key]["type"], 0):
            continue
        seen[key] = {"name": name, "type": typ}
    return list(seen.values())


def _relation_for_role(role: str) -> str:
    """锚点角色 → 候选边 relation_type（可解释扩散路径）"""
    return {
        "goal": "same_goal",
        "emotion": "shared_emotion",
    }.get(role, "shared_node")


def get_scene_graph() -> "SceneGraph | None":
    """全局单例，初始化失败返回 None（非致命，调用方需兜底）"""
    global _INSTANCE
    if _INSTANCE is not None:
        return _INSTANCE
    with _INSTANCE_LOCK:
        if _INSTANCE is None:
            try:
                os.makedirs(os.path.dirname(_GRAPH_DB_PATH), exist_ok=True)
                _INSTANCE = SceneGraph(_GRAPH_DB_PATH)
            except Exception as e:
                logger.warning(f"[scene_graph] init failed (non-fatal): {e}")
                _INSTANCE = None
    return _INSTANCE
