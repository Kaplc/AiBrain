"""
SQLite 图记忆层 - 实体枢纽链接
图结构：Memory 节点通过 MENTIONS 边连接 Entity 枢纽节点
实体由调用方在保存时显式传入，不需要 LLM 提取
"""
import logging
import math
import os
import re
import sqlite3
import threading
from typing import Optional

try:
    import networkx as nx
    HAS_NETWORKX = True
except ImportError:
    HAS_NETWORKX = False
    nx = None

logger = logging.getLogger('graph')

_GRAPH_DB_PATH = os.path.join(
    os.path.expanduser("~"), ".aibrain", "data", "memory_graph.db"
)

_INSTANCE = None

_DEFAULT_ENTITIES = [
    ("自己", "self"),
    ("用户", "user"),
    ("事实", "rule"),
    ("经验", "exp"),
]

_CREATE_TABLES = """
CREATE TABLE IF NOT EXISTS memory_nodes (
    mem0_id TEXT PRIMARY KEY,
    text TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS entity_nodes (
    name TEXT PRIMARY KEY,
    type TEXT NOT NULL DEFAULT 'concept',
    memory_count INT DEFAULT 0,
    pending_count INT DEFAULT 0
);
CREATE TABLE IF NOT EXISTS mentions (
    mem0_id TEXT NOT NULL,
    entity_name TEXT NOT NULL,
    PRIMARY KEY (mem0_id, entity_name),
    FOREIGN KEY (mem0_id) REFERENCES memory_nodes(mem0_id) ON DELETE CASCADE,
    FOREIGN KEY (entity_name) REFERENCES entity_nodes(name) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_mentions_entity ON mentions(entity_name);
CREATE INDEX IF NOT EXISTS idx_mentions_memory ON mentions(mem0_id);
CREATE TABLE IF NOT EXISTS entity_relations (
    from_entity TEXT NOT NULL,
    to_entity TEXT NOT NULL,
    PRIMARY KEY (from_entity, to_entity),
    FOREIGN KEY (from_entity) REFERENCES entity_nodes(name) ON DELETE CASCADE,
    FOREIGN KEY (to_entity) REFERENCES entity_nodes(name) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_relations_from ON entity_relations(from_entity);
CREATE INDEX IF NOT EXISTS idx_relations_to ON entity_relations(to_entity);
-- Phase 2: Memory-to-memory relations via shared entities
CREATE TABLE IF NOT EXISTS memory_relations (
    from_mem TEXT NOT NULL,
    to_mem TEXT NOT NULL,
    via_entity TEXT NOT NULL,
    weight REAL DEFAULT 1.0,
    PRIMARY KEY (from_mem, to_mem)
);
-- Phase 2: Typed entity relations with weights
CREATE TABLE IF NOT EXISTS typed_entity_relations (
    from_entity TEXT NOT NULL,
    to_entity TEXT NOT NULL,
    relation_type TEXT NOT NULL DEFAULT 'related',
    weight REAL DEFAULT 1.0,
    PRIMARY KEY (from_entity, to_entity, relation_type)
);
-- 事件记忆召回
CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    subject TEXT NOT NULL,
    action TEXT NOT NULL,
    object TEXT,
    context TEXT,
    time_expr TEXT,
    summary TEXT NOT NULL,
    emotion TEXT,
    emotion_intensity REAL DEFAULT 0.5,
    importance REAL DEFAULT 0.5,
    is_first_occurrence BOOLEAN DEFAULT 0,
    memory_count INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS event_memories (
    event_id TEXT NOT NULL,
    memory_id TEXT NOT NULL,
    PRIMARY KEY (event_id, memory_id),
    FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS event_relations (
    source_event_id TEXT NOT NULL,
    target_event_id TEXT NOT NULL,
    relation_type TEXT NOT NULL,
    confidence REAL DEFAULT 0.5,
    PRIMARY KEY (source_event_id, target_event_id, relation_type),
    FOREIGN KEY (source_event_id) REFERENCES events(id) ON DELETE CASCADE,
    FOREIGN KEY (target_event_id) REFERENCES events(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_event_memories_memory ON event_memories(memory_id);
CREATE INDEX IF NOT EXISTS idx_event_memories_event ON event_memories(event_id);
CREATE INDEX IF NOT EXISTS idx_event_relations_source ON event_relations(source_event_id);
CREATE INDEX IF NOT EXISTS idx_event_relations_target ON event_relations(target_event_id);
"""


# Phase 4: Activation spreading algorithm
# 激活扩散算法 —— 从初始节点沿图边传播激活值，每跳乘以衰减因子和边权重，
# 低于阈值的节点不再继续传播，最终返回所有可达节点的激活分数。
#   G              NetworkX 图对象
#   initial_nodes  起始节点 ID 列表
#   initial_scores 起始节点对应的初始激活分数
#   decay          每跳衰减因子（默认 0.5）
#   threshold      最低传播阈值（默认 0.1）
#   max_iter       最大迭代次数（默认 100）
#   返回           dict {node_id: activation_score}
_TYPE_MULTIPLIER = {
    'causal': 1.2,
    'partof': 1.3,
    'similar': 1.1,
    'temporal': 1.0,
    'contradicts': 0.5,
    'associated': 1.0,
}


def spreading_activation(G, initial_nodes, initial_scores, decay=0.5, threshold=0.1, max_iter=100):
    """Spread activation through graph edges

    Args:
        G: NetworkX graph
        initial_nodes: list of starting node IDs
        initial_scores: list of initial activation scores
        decay: decay factor per hop
        threshold: minimum activation to propagate
        max_iter: maximum iterations

    Returns:
        dict {node_id: activation_score}
    """
    if not G or not initial_nodes:
        return {}

    activation = dict(zip(initial_nodes, initial_scores))
    queue = [(n, s) for n, s in zip(initial_nodes, initial_scores)]
    visited = set()

    while queue and len(visited) < max_iter:
        node, score = queue.pop(0)
        if node in visited or score < threshold:
            continue
        visited.add(node)
        for neighbor in G.neighbors(node):
            edge_data = G[node][neighbor]
            edge_weight = edge_data.get('weight', 1.0)
            relation_type = edge_data.get('relation_type', 'associated')
            type_mult = _TYPE_MULTIPLIER.get(relation_type, 1.0)
            new_act = score * decay * edge_weight * type_mult
            logger.debug(f"[graph:spreading] node={node} score={score:.4f} → neighbor={neighbor} new_act={new_act:.4f} type={relation_type}")
            if neighbor not in activation or new_act > activation[neighbor]:
                activation[neighbor] = new_act
                queue.append((neighbor, new_act))
    return activation


class GraphMemory:
    def __init__(self, db_path: str):
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(_CREATE_TABLES)
        # 兼容旧数据库：添加 memory_count / pending_count 字段
        try:
            self._conn.execute("ALTER TABLE entity_nodes ADD COLUMN memory_count INT DEFAULT 0")
        except Exception:
            pass
        try:
            self._conn.execute("ALTER TABLE entity_nodes ADD COLUMN pending_count INT DEFAULT 0")
        except Exception:
            pass
        # Phase 2: 共现计数（Hebbian，存储时维护）
        try:
            self._conn.execute(
                "ALTER TABLE typed_entity_relations ADD COLUMN co_activation_count INTEGER DEFAULT 1"
            )
        except Exception:
            pass
        try:
            self._conn.execute(
                "ALTER TABLE typed_entity_relations ADD COLUMN last_co_activated TEXT"
            )
        except Exception:
            pass
        # Phase 3: NetworkX in-memory graph
        self._graph = nx.Graph() if HAS_NETWORKX else None
        # Entity embedding cache for auto-dedup
        self._entity_embedding_cache = {}  # {entity_name: list[float]}
        # Loading progress tracking
        self._loading = False
        self._loading_progress = 0  # 0-100
        self._loading_total = 0
        self._loading_loaded = 0
        self._loading_cancelled = False
        self._load_graph_from_db()
        self._init_default_entities()
        logger.info(f"[graph] initialized at {db_path}")

    def _exec(self, sql: str, params=()) -> list[tuple]:
        cur = self._conn.execute(sql, params)
        return cur.fetchall()

    # Phase 3: Load graph from SQLite into memory
    def _load_graph_from_db(self):
        if self._graph is None:
            return
        try:
            rows = self._exec("SELECT from_mem, to_mem, weight FROM memory_relations")
            for from_mem, to_mem, weight in rows:
                self._graph.add_edge(from_mem, to_mem, weight=weight or 1.0)
            rows = self._exec("SELECT from_entity, to_entity, relation_type, weight FROM typed_entity_relations")
            for from_ent, to_ent, rel_type, weight in rows:
                self._graph.add_edge(from_ent, to_ent, weight=weight or 1.0, relation_type=rel_type)
            rows = self._exec("SELECT from_entity, to_entity FROM entity_relations")
            for from_ent, to_ent in rows:
                self._graph.add_edge(from_ent, to_ent)
            logger.info(f"[graph] Graph loaded with {self._graph.number_of_edges()} edges")
            # Warm up entity embedding cache
            self._warm_entity_cache()
        except Exception as e:
            logger.warning(f"[graph] _load_graph_from_db failed: {e}")

    # Phase 3: Sync edge to in-memory graph
    # 将一条边同步到内存中的 NetworkX 图：已存在则更新权重，不存在则新增
    def _sync_edge(self, from_node: str, to_node: str, weight: float = 1.0):
        if self._graph is None:
            return
        try:
            if self._graph.has_edge(from_node, to_node):
                self._graph[from_node][to_node]['weight'] = weight
            else:
                self._graph.add_edge(from_node, to_node, weight=weight)
            logger.info(f"[graph:sync_edge] synced edge: from_node={from_node[:8]}, to_node={to_node[:8]}, weight={weight}")
        except Exception as e:
            logger.warning(f"[graph] _sync_edge failed: {e}")

    def _init_default_entities(self):
        """初始化默认根实体，并建立根实体之间的互连"""
        names = []
        for name, etype in _DEFAULT_ENTITIES:
            self._exec(
                "INSERT OR IGNORE INTO entity_nodes (name, type) VALUES (?, ?)",
                (name, etype),
            )
            names.append(name)
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                self._exec(
                    "INSERT OR IGNORE INTO entity_relations (from_entity, to_entity) VALUES (?, ?)",
                    (a, b),
                )
                self._exec(
                    "INSERT OR IGNORE INTO entity_relations (from_entity, to_entity) VALUES (?, ?)",
                    (b, a),
                )
        self._conn.commit()
        logger.info(f"[graph] default entities: {names} (fully interconnected)")

    # ── 公开 API ──────────────────────────────────────────────

    def link_memory(self, mem0_id: str, text: str, link_entities: list[str] = None, root_entity: str = '用户'):
        """存储记忆节点，用传入的实体建边链接。

        link_entities 为纯实体名列表（不允许用 '-' 分隔表达重命名）。
        实体名重复或向量相似时自动 dedup 复用已有实体。
        root_entity 指定关联的根实体（用户/自己/事实/经验）。
        """
        logger.debug(f"[graph:link] mem0_id={mem0_id[:8]} link_entities={link_entities}")

        if not link_entities:
            try:
                self._exec(
                    "INSERT OR REPLACE INTO memory_nodes (mem0_id, text) VALUES (?, ?)",
                    (mem0_id, text),
                )
                self._conn.commit()
                logger.info(f"[graph:link] {mem0_id[:8]} → 0 entities (no link)")
            except Exception as e:
                self._conn.rollback()
                logger.warning(f"[graph:link] failed: {e}")
            return

        try:
            self._exec(
                "INSERT OR REPLACE INTO memory_nodes (mem0_id, text) VALUES (?, ?)",
                (mem0_id, text),
            )
            resolved_entities = []  # Track deduped entity names
            for new_entity in link_entities:
                if not new_entity:
                    continue
                new_entity = new_entity.strip()
                if not new_entity:
                    continue

                # Auto-dedup: check if a similar entity already exists
                similar = self._find_similar_entity_vector(new_entity, threshold=0.85)
                if similar and similar != new_entity:
                    logger.info(f"[graph:dedup] '{new_entity}' → reusing '{similar}'")
                    new_entity = similar
                else:
                    # New entity, insert and cache its embedding
                    self._exec(
                        "INSERT OR IGNORE INTO entity_nodes (name, type) VALUES (?, 'concept')",
                        (new_entity,),
                    )
                    try:
                        from brain_mcp.embedding import encode_texts
                        vec = encode_texts([new_entity])[0]
                        self._entity_embedding_cache[new_entity] = vec
                    except Exception:
                        pass
                self._exec(
                    "INSERT OR IGNORE INTO mentions (mem0_id, entity_name) VALUES (?, ?)",
                    (mem0_id, new_entity),
                )
                resolved_entities.append(new_entity)
                logger.info(f"[graph:link] → linked entity={new_entity!r}")
            self._conn.commit()
            # 新实体自动关联到对应的根实体
            valid_roots = {'用户', '自己', '事实', '经验'}
            if root_entity in valid_roots:
                for ent in resolved_entities:
                    if ent != root_entity:
                        self._exec(
                            "INSERT OR IGNORE INTO entity_relations (from_entity, to_entity) VALUES (?, ?)",
                            (root_entity, ent),
                        )
                        self._exec(
                            "INSERT OR IGNORE INTO entity_relations (from_entity, to_entity) VALUES (?, ?)",
                            (ent, root_entity),
                        )
            # Async LLM relation type inference for entities >= 2
            if len(resolved_entities) >= 2:
                try:
                    threading.Thread(
                        target=self._infer_and_store_typed_relations,
                        args=(mem0_id, resolved_entities, text),
                        daemon=True,
                    ).start()
                except Exception as e:
                    logger.warning(f"[graph:infer] async start failed: {e}")
            logger.info(f"[graph:link] {mem0_id[:8]} → {len(link_entities)} items")
        except Exception as e:
            self._conn.rollback()
            logger.warning(f"[graph:link] failed: {e}")

    # Phase 5: Entity similarity detection
    # 在已有实体中查找与新实体相似的实体，先尝试子串包含匹配，再用 Jaccard 相似度比较词集合
    def _find_similar_entity(self, new_entity: str, threshold: float = 0.75) -> Optional[str]:
        """Find similar entity using Jaccard similarity (fallback when embeddings unavailable)"""
        rows = self._exec('SELECT name FROM entity_nodes')
        existing = [r[0] for r in rows]
        if not existing:
            return None

        def tokens(s):
            return set(re.findall(r'\w+', s.lower()))

        new_tokens = tokens(new_entity)
        if not new_tokens:
            return None

        for ent in existing:
            if ent in new_entity or new_entity in ent:
                return ent
            ent_tokens = tokens(ent)
            intersection = len(new_tokens & ent_tokens)
            union = len(new_tokens | ent_tokens)
            jaccard = intersection / union if union > 0 else 0
            if jaccard >= threshold:
                logger.info(f"[graph:find_similar] found similar entity: new_entity={new_entity!r} → matched={ent!r}, jaccard={jaccard:.4f}")
                return ent
        return None

    def _warm_entity_cache(self):
        """Batch encode all entity names into embedding cache"""
        try:
            rows = self._exec('SELECT name FROM entity_nodes')
            names = [r[0] for r in rows]
            if not names:
                return
            from brain_mcp.embedding import encode_texts
            vectors = encode_texts(names)
            self._entity_embedding_cache = dict(zip(names, vectors))
            logger.info(f"[graph:cache] warmed {len(names)} entity embeddings")
        except Exception as e:
            logger.warning(f"[graph:cache] warm failed: {e}")

    def _find_similar_entity_vector(self, new_entity: str, threshold: float = 0.85) -> Optional[str]:
        """Find similar entity using BGE-M3 vector cosine similarity"""
        if not self._entity_embedding_cache:
            return self._find_similar_entity(new_entity, threshold=0.75)

        try:
            from brain_mcp.embedding import encode_texts
            new_vec = encode_texts([new_entity])[0]
        except Exception as e:
            logger.warning(f"[graph:dedup] encode failed, fallback to Jaccard: {e}")
            return self._find_similar_entity(new_entity, threshold=0.75)

        best_name = None
        best_score = 0.0
        for name, cached_vec in self._entity_embedding_cache.items():
            if name == new_entity:
                continue
            dot = sum(a * b for a, b in zip(new_vec, cached_vec))
            norm_a = math.sqrt(sum(a * a for a in new_vec))
            norm_b = math.sqrt(sum(b * b for b in cached_vec))
            if norm_a == 0 or norm_b == 0:
                continue
            sim = dot / (norm_a * norm_b)
            if sim > best_score:
                best_score = sim
                best_name = name

        if best_score >= threshold and best_name:
            logger.info(f"[graph:dedup] '{new_entity}' ≈ '{best_name}' (cosine={best_score:.4f})")
            return best_name
        return None

    def _infer_and_store_typed_relations(self, mem0_id: str, entity_names: list[str], memory_text: str):
        """Call LLM to infer relation types and store in typed_entity_relations (runs in background thread)"""
        try:
            try:
                from modules.brain.llm import infer_relations
            except ImportError:
                from backend.modules.brain.llm import infer_relations
            relations = infer_relations(entity_names, memory_text)
            if not relations:
                return
            for r in relations:
                self._exec(
                    'INSERT OR REPLACE INTO typed_entity_relations (from_entity, to_entity, relation_type, weight) VALUES (?, ?, ?, ?)',
                    (r['from'], r['to'], r['relation_type'], r['confidence']),
                )
                # Reverse direction too
                self._exec(
                    'INSERT OR REPLACE INTO typed_entity_relations (from_entity, to_entity, relation_type, weight) VALUES (?, ?, ?, ?)',
                    (r['to'], r['from'], r['relation_type'], r['confidence']),
                )
                # Sync to NetworkX
                if self._graph:
                    self._graph.add_edge(
                        r['from'], r['to'],
                        weight=r['confidence'],
                        relation_type=r['relation_type'],
                    )
            self._conn.commit()
            logger.info(f"[graph:infer] stored {len(relations)} typed relations for {mem0_id[:8]}")
        except Exception as e:
            logger.warning(f"[graph:infer] failed for {mem0_id[:8]}: {e}")

    # Phase 2: Link memory to memory via shared entities
    # 通过共享实体建立记忆与记忆之间的双向边：查找同一实体关联的其他记忆，互相建边并同步到内存图
    def _link_memory_to_memory(self, mem0_id: str, entity_names: list[str]):
        """Create bidirectional edges between memories sharing entities"""
        for entity in entity_names:
            related = self._exec(
                'SELECT mem0_id FROM mentions WHERE entity_name = ? AND mem0_id != ?',
                (entity, mem0_id)
            )
            for (related_id,) in related:
                self._exec(
                    'INSERT OR IGNORE INTO memory_relations (from_mem, to_mem, via_entity, weight) VALUES (?, ?, ?, 1.0)',
                    (mem0_id, related_id, entity)
                )
                logger.info(f"[graph:link_mem2mem] created edge: from_mem={mem0_id[:8]}, to_mem={related_id[:8]}, via_entity={entity!r}")
                self._exec(
                    'INSERT OR IGNORE INTO memory_relations (from_mem, to_mem, via_entity, weight) VALUES (?, ?, ?, 1.0)',
                    (related_id, mem0_id, entity)
                )
                logger.info(f"[graph:link_mem2mem] created edge: from_mem={related_id[:8]}, to_mem={mem0_id[:8]}, via_entity={entity!r}")
                self._sync_edge(mem0_id, related_id, 1.0)
        self._conn.commit()

    def link_if_no_entities(self, mem0_id: str, text: str):
        """如果该记忆在图中没有任何实体链接，自动关联到根实体'用户'"""
        rows = self._exec(
            "SELECT COUNT(*) FROM mentions WHERE mem0_id = ?",
            (mem0_id,),
        )
        if rows and rows[0][0] > 0:
            return  # 已有实体链接，跳过
        try:
            self._exec(
                "INSERT OR REPLACE INTO memory_nodes (mem0_id, text) VALUES (?, ?)",
                (mem0_id, text),
            )
            self._exec(
                "INSERT OR IGNORE INTO mentions (mem0_id, entity_name) VALUES (?, '用户')",
                (mem0_id,),
            )
            self._conn.commit()
            logger.info(f"[graph:backfill] {mem0_id[:8]} 无实体链接，自动关联→用户")
        except Exception as e:
            self._conn.rollback()
            logger.warning(f"[graph:backfill] failed: {e}")

    def list_entities(self) -> list[dict]:
        """列出所有实体"""
        rows = self._exec(
            """SELECT e.name, e.type, COUNT(mn.mem0_id) as memory_count
               FROM entity_nodes e
               LEFT JOIN mentions mn ON e.name = mn.entity_name
               GROUP BY e.name, e.type
               ORDER BY memory_count DESC, e.name"""
        )
        return [{"name": r[0], "type": r[1], "memory_count": r[2]} for r in rows]

    # Phase 4: Get neighbor memories
    # 查询指定记忆在 memory_relations 表中的邻居记忆，返回 (邻居记忆ID, 边权重) 元组列表
    def get_memory_neighbors(self, mem0_id: str, limit: int = 20) -> list[tuple]:
        """Get neighbor memories via memory_relations

        Returns:
            list of (neighbor_mem_id, weight) tuples
        """
        rows = self._exec(
            'SELECT to_mem, weight FROM memory_relations WHERE from_mem = ? LIMIT ?',
            (mem0_id, limit)
        )
        result = [(r[0], r[1]) for r in rows]
        logger.debug(f"[graph:neighbors] mem0_id={mem0_id[:8]} returned {len(result)} neighbors")
        return result

    # Phase 4: Batch get memory texts
    def get_memory_texts(self, mem_ids: list[str]) -> dict[str, str]:
        """Batch get memory texts
        
        Returns:
            dict {mem0_id: memory_text}
        """
        if not mem_ids:
            return {}
        placeholders = ','.join('?' * len(mem_ids))
        rows = self._exec(
            f'SELECT mem0_id, text FROM memory_nodes WHERE mem0_id IN ({placeholders})',
            mem_ids
        )
        return {r[0]: r[1] for r in rows}

    def search_related(self, mem0_ids: list[str], max_hops: int = 2, initial_scores: list[float] = None) -> list[dict]:
        """从向量命中的记忆出发，通过实体网络激活扩散找关联记忆

        流程：
        1. 从向量命中的 memory_ids 查 mentions 表获取关联实体
        2. 以这些实体为初始节点在 NetworkX 上做激活扩散
        3. 扩散发现的新实体通过 mentions 反查关联 memory_ids
        4. 并发调 mem0.get() 获取文本

        Args:
            mem0_ids: 初始记忆 ID 列表
            max_hops: 最大跳数
            initial_scores: 初始激活分数列表，默认全部为 1.0
        """
        if not mem0_ids:
            return []
        logger.info(f"[graph:search_related] 启动实体网络扩散 | 起始记忆数={len(mem0_ids)} | max_hops={max_hops}")

        # 1. 从 memory_ids 查关联实体
        entity_names = []
        for mid in mem0_ids:
            rows = self._exec(
                "SELECT entity_name FROM mentions WHERE mem0_id = ?", (mid,)
            )
            entity_names.extend(r[0] for r in rows)
        entity_names = list(dict.fromkeys(entity_names))  # 去重保序
        logger.info(f"[graph:search_related] 向量命中记忆关联 {len(entity_names)} 个实体 | entities={entity_names}")

        if not entity_names:
            logger.info("[graph:search_related] 无关联实体，跳过图扩展")
            return []

        # 2. 以实体为初始节点，在 NetworkX 上做激活扩散
        if self._graph and self._graph.number_of_edges() > 0:
            activations = spreading_activation(
                self._graph, entity_names, [1.0] * len(entity_names),
                decay=0.5, threshold=0.1, max_iter=100,
            )

            # 3. 排除初始实体，取扩散发现的新实体
            discovered_entities = [k for k in activations if k not in entity_names]
            if discovered_entities:
                placeholders = ','.join('?' * len(discovered_entities))
                rows = self._exec(
                    f"SELECT DISTINCT mem0_id FROM mentions WHERE entity_name IN ({placeholders})",
                    discovered_entities,
                )
                discovered_ids = list({r[0] for r in rows})  # 去重
                # 排除已在向量命中中的记忆
                original_ids = set(mem0_ids)
                discovered_ids = [mid for mid in discovered_ids if mid not in original_ids]
                if discovered_ids:
                    # 4. 并发获取记忆文本
                    from concurrent.futures import ThreadPoolExecutor
                    from modules.brain.mem0_adapter import get_mem0_client
                    client = get_mem0_client()

                    def _get_mem(mid):
                        try:
                            r = client.get(mid)
                            return {"id": mid, "text": r.get("memory", "") if r else ""}
                        except Exception:
                            return None

                    with ThreadPoolExecutor(max_workers=5) as pool:
                        mem_results = list(pool.map(_get_mem, discovered_ids))
                    result = [r for r in mem_results if r and r.get("text")]
                    # 按关联实体的激活分数排序
                    entity_act = {k: v for k, v in activations.items() if k in discovered_entities}
                    for r in result:
                        r["score"] = 0.1
                        # 取该记忆关联实体中最高的激活分数
                        rel = self._exec("SELECT entity_name FROM mentions WHERE mem0_id = ?", (r["id"],))
                        for row in rel:
                            if row[0] in entity_act:
                                r["score"] = max(r["score"], entity_act[row[0]])
                    result.sort(key=lambda x: x["score"], reverse=True)
                    logger.info(f"[graph:search_related] 实体扩散发现 {len(result)} 条关联记忆 | IDs={[r['id'][:8] for r in result]}")
                    return result[:30]

                logger.info("[graph:search_related] 扩散发现实体但无新关联记忆")
                return []

        # Fallback: SQL 递归（当 NetworkX 图无数据时启用）
        placeholders = ",".join("?" * len(mem0_ids))
        sql = f"""
            WITH RECURSIVE reachable(mem0_id, hop) AS (
                SELECT DISTINCT m2.mem0_id, 1
                FROM mentions mn1
                JOIN mentions mn2 ON mn1.entity_name = mn2.entity_name
                JOIN memory_nodes m2 ON m2.mem0_id = mn2.mem0_id
                WHERE mn1.mem0_id IN ({placeholders})
                AND m2.mem0_id NOT IN ({placeholders})
                UNION
                SELECT DISTINCT m3.mem0_id, r.hop + 1
                FROM reachable r
                JOIN mentions mn_r ON mn_r.mem0_id = r.mem0_id
                JOIN mentions mn_new ON mn_r.entity_name = mn_new.entity_name
                JOIN memory_nodes m3 ON m3.mem0_id = mn_new.mem0_id
                WHERE r.hop < ?
                AND m3.mem0_id NOT IN ({placeholders})
            )
            SELECT DISTINCT r.mem0_id, m.text FROM reachable r
            JOIN memory_nodes m ON m.mem0_id = r.mem0_id
            LIMIT 30
        """
        try:
            rows = self._exec(sql, mem0_ids + mem0_ids + [max_hops] + mem0_ids)
            result = [{"id": r[0], "text": r[1], "score": 0.5} for r in rows]
            logger.info(f"[graph:search_related] SQL fallback 完成 | 发现 {len(result)} 条关联记忆")
            return result
        except Exception as e:
            logger.warning(f"[graph:search_related] failed: {e}")
            return []

    def search_related_new(self, initial_mem_ids: list[str], initial_entities: list[str],
                           max_candidates: int = 50, generic_threshold: float = 0.05) -> list[dict]:
        """mentions 表 1跳共现召回候选记忆。

        1. 用 entity_nodes.memory_count 直接过滤泛化实体（> 5%），不走 mentions 聚合
        2. 用过滤后的具体实体，在 mentions 表查哪些记忆也提到这些实体
        3. 候选记忆按"共现实体数"排序（共现越多越相关）
        4. 返回 top max_candidates 条
        """
        if not initial_entities:
            return []

        # 总记忆数
        total_row = self._exec("SELECT COUNT(*) FROM memory_nodes")
        total = total_row[0][0] if total_row else 0
        if total == 0:
            return []

        # 查 entity_nodes 直接过滤泛化实体
        generic_entities = {
            r[0] for r in self._exec(
                "SELECT name FROM entity_nodes WHERE memory_count * 1.0 / ? > ?",
                (total, generic_threshold)
            )
        }
        # 排除泛化实体
        specific_entities = [e for e in initial_entities if e not in generic_entities]
        if not specific_entities:
            logger.info(f"[graph:search_related_new] 所有实体都是泛化实体，跳过 | generic={list(generic_entities)}")
            return []

        logger.info(f"[graph:search_related_new] 过滤泛化实体 | total={total} | generic={len(generic_entities)} | specific={len(specific_entities)} | specific_entities={specific_entities}")

        # 共现召回：在 mentions 表里找也提到这些实体的记忆
        ent_placeholders = ','.join('?' * len(specific_entities))
        mem_id_placeholders = ','.join('?' * len(initial_mem_ids))
        rows = self._exec(
            f"""SELECT m.mem0_id, m.text, COUNT(DISTINCT mn.entity_name) as co_count
                FROM mentions mn
                JOIN memory_nodes m ON m.mem0_id = mn.mem0_id
                WHERE mn.entity_name IN ({ent_placeholders})
                AND m.mem0_id NOT IN ({mem_id_placeholders})
                GROUP BY m.mem0_id
                ORDER BY co_count DESC
                LIMIT {max_candidates}""",
            specific_entities + list(initial_mem_ids)
        )
        result = [
            {"id": r[0], "text": r[1], "co_count": r[2]}
            for r in rows
        ]
        logger.info(f"[graph:search_related_new] 共现召回完成 | 候选={len(result)} 条")
        return result

    def rebuild_entity_counts(self):
        """全量重建 entity_nodes 表的 memory_count 字段，重建后清零 pending_count"""
        logger.info("[graph:rebuild_entity_counts] 开始全量重建实体计数...")
        # 从 mentions 表聚合实体计数
        rows = self._exec(
            """SELECT mn.entity_name, COUNT(DISTINCT mn.mem0_id) as cnt
               FROM mentions mn
               GROUP BY mn.entity_name"""
        )
        for name, cnt in rows:
            self._exec(
                "INSERT INTO entity_nodes (name, memory_count) VALUES (?, ?) "
                "ON CONFLICT(name) DO UPDATE SET memory_count = ?",
                (name, cnt, cnt)
            )
        # 清零所有 pending_count
        self._exec("UPDATE entity_nodes SET pending_count = 0")
        self._conn.commit()
        logger.info(f"[graph:rebuild_entity_counts] 完成 | 更新 {len(rows)} 个实体计数")

    def increment_entity_counts(self, entity_names: list[str]):
        """保存记忆时增量更新 pending_count，超过阈值自动触发全量重建"""
        if not entity_names:
            return
        for name in entity_names:
            self._exec(
                "INSERT INTO entity_nodes (name, pending_count) VALUES (?, 1) "
                "ON CONFLICT(name) DO UPDATE SET pending_count = COALESCE(pending_count, 0) + 1",
                (name,)
            )
        self._conn.commit()
        # 检查是否达到阈值
        threshold_row = self._exec(
            "SELECT SUM(pending_count) FROM entity_nodes WHERE pending_count > 0"
        )
        total_pending = threshold_row[0][0] if threshold_row and threshold_row[0][0] else 0
        if total_pending >= 20:
            logger.info(f"[graph:increment] pending_count={total_pending} >= 20，触发全量重建")
            self.rebuild_entity_counts()

    # ── Phase 2: Hebbian 共现统计（存储时维护）──────────────────────
    # 设计不变量：co_occurrence 配对用 sorted() 规范化为 (lo, hi) 单向存储。
    # 因此查询（get_related_entities）必须 UNION from/to 两个方向，否则漏一半。
    def increment_co_activation(self, entity_names: list[str]):
        """同一条记忆里的实体两两共现 → co_occurrence 关系计数 +1（存储时调用）

        配对经 sorted() 规范化后只存一行（lo, hi），避免 (A,B)/(B,A) 重复。
        """
        import datetime
        import itertools

        names = [n.strip() for n in (entity_names or []) if n and n.strip()]
        names = list(dict.fromkeys(names))  # 去重保序
        if len(names) < 2:
            return
        now = datetime.datetime.now().isoformat(timespec="seconds")
        for a, b in itertools.combinations(names, 2):
            lo, hi = sorted([a, b])  # 规范化配对顺序
            self._conn.execute(
                "INSERT INTO typed_entity_relations "
                "(from_entity, to_entity, relation_type, weight, co_activation_count, last_co_activated) "
                "VALUES (?, ?, 'co_occurrence', 1.0, 1, ?) "
                "ON CONFLICT(from_entity, to_entity, relation_type) DO UPDATE SET "
                "co_activation_count = COALESCE(co_activation_count, 1) + 1, "
                "last_co_activated = ?",
                (lo, hi, now, now),
            )
            if self._graph is not None:
                self._graph.add_edge(lo, hi, weight=1.0, relation_type="co_occurrence")
        self._conn.commit()
        logger.info(f"[graph:co_activation] +{len(list(itertools.combinations(names, 2)))} pairs from {len(names)} entities")

    def get_related_entities(self, entity_names: list[str], top_k: int = 5) -> list[tuple]:
        """返回与给定实体共现的关联实体，按 co_activation_count 降序

        Returns: [(other_entity, count), ...]
        注意：配对单向规范化存储，故必须 UNION from/to 双向查询。
        """
        names = [n for n in (entity_names or []) if n]
        if not names:
            return []
        ph = ",".join("?" * len(names))
        rows = self._exec(
            f"SELECT to_entity AS other, co_activation_count AS cnt "
            f"FROM typed_entity_relations "
            f"WHERE relation_type='co_occurrence' AND from_entity IN ({ph}) AND to_entity NOT IN ({ph}) "
            f"UNION ALL "
            f"SELECT from_entity AS other, co_activation_count AS cnt "
            f"FROM typed_entity_relations "
            f"WHERE relation_type='co_occurrence' AND to_entity IN ({ph}) AND from_entity NOT IN ({ph})",
            (*names, *names, *names, *names),
        )
        agg = {}
        for other, cnt in rows:
            agg[other] = agg.get(other, 0) + (cnt or 1)
        ranked = sorted(agg.items(), key=lambda kv: kv[1], reverse=True)
        return ranked[:top_k]

    def get_related_memories(self, entity_names: list[str], top_k: int = 5) -> list[str]:
        """返回与关联实体相关的记忆 id（经 mentions 表）

        先 get_related_entities 取关联实体，再查 mentions 得记忆 id。
        """
        related = self.get_related_entities(entity_names, top_k=top_k * 2)
        if not related:
            return []
        ent_names = [e for e, _ in related]
        ph = ",".join("?" * len(ent_names))
        rows = self._exec(
            f"SELECT DISTINCT mem0_id FROM mentions WHERE entity_name IN ({ph})",
            ent_names,
        )
        return [r[0] for r in rows][:top_k]

    def get_entities_for_memories(self, mem0_ids: list[str]) -> dict[str, list[str]]:
        """批量查询记忆关联的实体名"""
        if not mem0_ids:
            return {}
        logger.debug(f"[graph:get_entities] ids={[m[:8] for m in mem0_ids]}")
        placeholders = ",".join("?" * len(mem0_ids))
        sql = f"""
            SELECT m.mem0_id, GROUP_CONCAT(e.name, '||') as entities
            FROM memory_nodes m
            JOIN mentions mn ON m.mem0_id = mn.mem0_id
            JOIN entity_nodes e ON mn.entity_name = e.name
            WHERE m.mem0_id IN ({placeholders})
            GROUP BY m.mem0_id
        """
        try:
            rows = self._exec(sql, mem0_ids)
            result = {r[0]: r[1].split("||") if r[1] else [] for r in rows}
            logger.debug(f"[graph:get_entities] result={result}")
            return result
        except Exception as e:
            logger.warning(f"[graph:get_entities] failed: {e}")
            return {}

    def search_entity(self, name: str) -> dict:
        """查询实体是否存在，返回关联记忆和关联实体"""
        logger.info(f"[graph:search_entity] name={name!r}")
        rows = self._exec(
            "SELECT name, type FROM entity_nodes WHERE name LIKE ?",
            (f"%{name}%",),
        )
        logger.info(f"[graph:search_entity] entity_nodes query returned: {rows}")
        if not rows:
            return {"exists": False}

        entity_name = rows[0][0]
        entity_type = rows[0][1]

        mem_rows = self._exec(
            """SELECT m.mem0_id, m.text FROM memory_nodes m
               JOIN mentions mn ON m.mem0_id = mn.mem0_id
               WHERE mn.entity_name LIKE ?""",
            (f"%{name}%",),
        )
        memories = [{"mem0_id": r[0], "text": r[1]} for r in mem_rows]

        related_rows = self._exec(
            """SELECT DISTINCT e2.name, e2.type FROM mentions mn1
               JOIN mentions mn2 ON mn1.mem0_id = mn2.mem0_id
               JOIN entity_nodes e2 ON mn2.entity_name = e2.name
               WHERE mn1.entity_name LIKE ? AND e2.name NOT LIKE ?
               LIMIT 10""",
            (f"%{name}%", f"%{name}%"),
        )
        logger.info(f"[graph:search_entity] related_entities (mentions) query returned: {related_rows}")

        # 多层深度召回：双向遍历，衰减权重，限制数量
        max_depth = 3
        depth_weights = {1: 1.0, 2: 0.6, 3: 0.3}
        max_entities_per_depth = 5
        max_memories = 15
        max_related = 10
        frontier = [entity_name]
        visited = {entity_name}
        depth_results = {}

        for depth in range(1, max_depth + 1):
            next_frontier = []
            for current in frontier:
                rows = self._exec(
                    """SELECT to_entity FROM entity_relations WHERE from_entity = ?
                       UNION
                       SELECT from_entity FROM entity_relations WHERE to_entity = ?""",
                    (current, current),
                )
                for r in rows:
                    next_entity = r[0]
                    if next_entity not in visited:
                        visited.add(next_entity)
                        depth_results.setdefault(depth, []).append(next_entity)
                        next_frontier.append(next_entity)
            # 每层只保留连接数最多的 top N 实体
            if len(next_frontier) > max_entities_per_depth:
                counts = []
                for e in next_frontier:
                    c = self._exec(
                        "SELECT COUNT(*) FROM mentions WHERE entity_name = ?", (e,)
                    )
                    counts.append((e, c[0][0] if c else 0))
                counts.sort(key=lambda x: x[1], reverse=True)
                next_frontier = [e for e, _ in counts[:max_entities_per_depth]]
                depth_results[depth] = next_frontier
            frontier = next_frontier
            if not frontier:
                break

        # 全深度召回，带权重排序
        weighted_entities = []
        for d in range(1, max_depth + 1):
            for e in depth_results.get(d, []):
                weighted_entities.append((e, depth_weights.get(d, 0.1)))
        all_related_names = list(set(e for e, _ in weighted_entities))

        # 收集记忆并去重，按关联深度权重排序
        all_entity_names = [entity_name] + all_related_names
        seen_ids = set()
        if all_entity_names:
            placeholders = ','.join('?' * len(all_entity_names))
            mem_rows = self._exec(
                f"""SELECT m.mem0_id, m.text, mn.entity_name FROM memory_nodes m
                   JOIN mentions mn ON m.mem0_id = mn.mem0_id
                   WHERE mn.entity_name IN ({placeholders})""",
                all_entity_names,
            )
            entity_weight_map = {e: w for e, w in weighted_entities}
            for r in mem_rows:
                if r[0] not in seen_ids:
                    seen_ids.add(r[0])
                    w = entity_weight_map.get(r[2], 1.0) if r[2] != entity_name else 1.0
                    memories.append({"mem0_id": r[0], "text": r[1], "weight": w})
            memories.sort(key=lambda x: x.get("weight", 0), reverse=True)
            memories = memories[:max_memories]

        related = []
        if all_related_names:
            # 按权重排序，只保留 top N
            sorted_names = sorted(
                all_related_names,
                key=lambda e: entity_weight_map.get(e, 0.1),
                reverse=True,
            )[:max_related]
            placeholders = ','.join('?' * len(sorted_names))
            rel_rows = self._exec(
                f"SELECT name, type FROM entity_nodes WHERE name IN ({placeholders})",
                sorted_names,
            )
            related = [{"name": r[0], "type": r[1]} for r in rel_rows]

        logger.info(f"[graph:search_entity] depth={max_depth} results: {depth_results}")
        logger.info(f"[graph:search_entity] final memories count={len(memories)}, related_entities count={len(related)}")

        return {
            "exists": True,
            "name": entity_name,
            "type": entity_type,
            "memories": memories,
            "related_entities": related,
        }

    def link_entities(self, entity_a: str, entity_b: str) -> dict:
        """在两个已有实体之间建立双向连接（只连接，不创建新实体）

        Returns:
            success: 是否成功
            error: 错误信息（如有）
        """
        a, b = entity_a.strip(), entity_b.strip()
        if not a or not b:
            return {"success": False, "error": "两个实体名都不能为空"}
        if a == b:
            return {"success": False, "error": "不能自己连接自己"}
        try:
            # 验证两个实体都存在
            for name in [a, b]:
                rows = self._exec("SELECT 1 FROM entity_nodes WHERE name = ?", (name,))
                if not rows:
                    return {"success": False, "error": f"实体「{name}」不存在"}
            # 检查是否已连接
            exist = self._exec(
                "SELECT 1 FROM entity_relations WHERE from_entity = ? AND to_entity = ?",
                (a, b),
            )
            if exist:
                return {"success": False, "error": f"「{a}」和「{b}」已经连接"}
            # 双向插入
            self._exec(
                "INSERT OR IGNORE INTO entity_relations (from_entity, to_entity) VALUES (?, ?)",
                (a, b),
            )
            self._exec(
                "INSERT OR IGNORE INTO entity_relations (from_entity, to_entity) VALUES (?, ?)",
                (b, a),
            )
            self._conn.commit()
            logger.info(f"[graph:link_entities] {a} ↔ {b}")
            return {"success": True}
        except Exception as e:
            self._conn.rollback()
            logger.warning(f"[graph:link_entities] failed: {e}")
            return {"success": False, "error": str(e)}

    def delete_memory(self, mem0_id: str):
        """删除记忆节点及其边，同时减少关联实体的 memory_count"""
        try:
            # 先获取关联实体，用于减少计数
            entity_rows = self._exec(
                "SELECT entity_name FROM mentions WHERE mem0_id = ?", (mem0_id,)
            )
            deleted_entities = [r[0] for r in entity_rows]
            # 删除 mentions 和 memory_nodes
            self._exec("DELETE FROM mentions WHERE mem0_id = ?", (mem0_id,))
            self._exec("DELETE FROM memory_nodes WHERE mem0_id = ?", (mem0_id,))
            # 减少关联实体的 memory_count
            for name in deleted_entities:
                self._exec(
                    "UPDATE entity_nodes SET memory_count = MAX(0, memory_count - 1) WHERE name = ?",
                    (name,)
                )
            self._conn.commit()
            logger.info(f"[graph] deleted memory {mem0_id[:8]} | decremented {len(deleted_entities)} entity counts")
        except Exception as e:
            self._conn.rollback()
            logger.warning(f"[graph] delete_memory failed: {e}")

    # Phase 7: 合并实体（把 b 的 mentions 和关系迁移到 a）
    def merge_entities(self, entity_a: str, entity_b: str):
        """合并两个实体，entity_b 的所有关联都会迁移到 entity_a
        
        Args:
            entity_a: 保留的目标实体名
            entity_b: 要合并删除的实体名
        """
        try:
            self._exec(
                'UPDATE mentions SET entity_name = ? WHERE entity_name = ?',
                (entity_a, entity_b)
            )
            self._exec(
                'UPDATE typed_entity_relations SET from_entity = ? WHERE from_entity = ?',
                (entity_a, entity_b)
            )
            self._exec(
                'UPDATE typed_entity_relations SET to_entity = ? WHERE to_entity = ?',
                (entity_a, entity_b)
            )
            self._exec('DELETE FROM entity_nodes WHERE name = ?', (entity_b,))
            self._exec('DELETE FROM typed_entity_relations WHERE from_entity = to_entity')
            self._conn.commit()
            # Invalidate cache for merged entity
            self._entity_embedding_cache.pop(entity_b, None)
            logger.info(f"[graph:merge_entities] {entity_b} -> {entity_a}")
        except Exception as e:
            self._conn.rollback()
            logger.warning(f"[graph:merge_entities] failed: {e}")

    def validate_entities(self, names: list[str]) -> list[str]:
        """返回不在 entity_nodes 中的实体名列表"""
        if not names:
            return []
        missing = []
        for name in names:
            rows = self._exec("SELECT 1 FROM entity_nodes WHERE name = ?", (name,))
            if not rows:
                missing.append(name)
        return missing

    def get_stats(self) -> dict:
        """返回图中节点和边数量"""
        try:
            mem_count = self._exec("SELECT COUNT(*) FROM memory_nodes")[0][0]
            ent_count = self._exec("SELECT COUNT(*) FROM entity_nodes")[0][0]
            edge_count = self._exec("SELECT COUNT(*) FROM mentions")[0][0]
            event_count = self._exec("SELECT COUNT(*) FROM events")[0][0]
            event_mem_count = self._exec("SELECT COUNT(*) FROM event_memories")[0][0]
            event_rel_count = self._exec("SELECT COUNT(*) FROM event_relations")[0][0]
            return {
                "memory_count": mem_count,
                "entity_count": ent_count,
                "edge_count": edge_count,
                "event_count": event_count,
                "event_memory_count": event_mem_count,
                "event_relation_count": event_rel_count,
            }
        except Exception as e:
            logger.warning(f"[graph] get_stats failed: {e}")
            return {"memory_count": 0, "entity_count": 0, "edge_count": 0}

    def get_visualization_data(self) -> dict:
        """返回图谱可视化所需的节点和边数据"""
        try:
            # 节点：实体 + 关联记忆数量
            node_rows = self._exec(
                """SELECT e.name, e.type, COUNT(mn.mem0_id) as memory_count
                   FROM entity_nodes e
                   LEFT JOIN mentions mn ON e.name = mn.entity_name
                   GROUP BY e.name, e.type"""
            )
            nodes = [{"id": r[0], "label": r[0], "type": r[1], "memoryCount": r[2]} for r in node_rows]

            # 边：合并 entity_relations + typed_entity_relations（去重）
            seen_edges = set()
            edges = []
            # LLM 推断的语义关系（优先，有类型和权重）
            typed_rows = self._exec("SELECT from_entity, to_entity, relation_type, weight FROM typed_entity_relations")
            for r in typed_rows:
                key = tuple(sorted([r[0], r[1]]))
                if key not in seen_edges:
                    seen_edges.add(key)
                    edges.append({"source": r[0], "target": r[1], "relationType": r[2], "weight": r[3]})
            # 根实体关联（entity_relations 中不在 typed 中的边）
            rel_rows = self._exec("SELECT from_entity, to_entity FROM entity_relations")
            for r in rel_rows:
                key = tuple(sorted([r[0], r[1]]))
                if key not in seen_edges:
                    seen_edges.add(key)
                    edges.append({"source": r[0], "target": r[1], "relationType": "associated", "weight": 1.0})

            return {"nodes": nodes, "edges": edges}
        except Exception as e:
            logger.warning(f"[graph] get_visualization_data failed: {e}")
            return {"nodes": [], "edges": []}


def get_graph() -> GraphMemory | None:
    """全局单例，初始化失败返回 None"""
    global _INSTANCE
    if _INSTANCE is not None:
        return _INSTANCE
    try:
        os.makedirs(os.path.dirname(_GRAPH_DB_PATH), exist_ok=True)
        _INSTANCE = GraphMemory(_GRAPH_DB_PATH)
        return _INSTANCE
    except Exception as e:
        logger.warning(f"[graph] initialization failed (non-fatal): {e}")
        return None