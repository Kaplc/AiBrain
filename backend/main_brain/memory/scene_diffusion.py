"""
情景图扩散检索器（Scene Diffusion）— scene→anchor→scene 受控激活扩散

设计目标（见 plan/scene-memory-graph-diffusion.md 流程/检索章节）：
  - 不在在线主路径依赖 LLM 提取实体（种子来自语义命中 payload.nodes + query 锚点匹配）。
  - nodes 是扩散种子，episodic 由向量层（embedding_text 已含 what/why/result/lesson）覆盖语义。
  - affect / importance 成为扩散权重；高 importance + 正向 affect 更易被唤起（FR-004）。

扩散通道（互补，避免漏召回）：
  1. 锚点直连（1 跳）：种子锚点 + query 锚点 → 共享锚点的 scene（get_anchor_neighbors）。
  2. 边扩散（多跳）：种子 scene 沿预计算 scene_edges 传播激活（get_scene_neighbors），
     跳数上限 + 候选上限 + 每跳 frontier 上限，防止图爆炸（FR-011）。

输出每条候选带 trace（seed_nodes / hop / relation_type），满足 FR-008 可解释与 T010。
模块单例：外部经 get_scene_diffusion() 访问。
"""
import logging
import math
import threading

logger = logging.getLogger('scene_diffusion')

# 扩散控制参数（FR-011 图规模控制 + 性能 P95<300ms）
_MAX_HOPS = 2                # 最多扩散跳数
_DECAY = 0.5                 # 每跳衰减
_MAX_CANDIDATES = 40         # 最终候选上限
_MAX_FRONTIER = 12           # 每跳 frontier 上限（按激活降序保留）
_MIN_ACTIVATION = 0.05       # 低于此激活不再传播
_ACT_FLOOR = 0.05            # 候选最终激活地板分（保证有 trace 的候选可排序）

_INSTANCE = None
_INSTANCE_LOCK = threading.Lock()


class SceneDiffusion:
    """情景扩散检索器"""

    def __init__(self):
        from .scene_graph import get_scene_graph
        self._graph = get_scene_graph()

    def available(self) -> bool:
        return self._graph is not None

    # ── 主入口 ─────────────────────────────────────────────────

    def search(self, query: str, semantic_results: list[dict],
               top_k: int = 20, with_trace: bool = True) -> list[dict]:
        """情景图扩散检索

        Args:
            query: 用户查询文本
            semantic_results: 向量层语义命中（含 payload.nodes），作为扩散种子源
            top_k: 最终返回条数
            with_trace: 是否附带 trace（explain 用）

        Returns:
            [{id, text, score, source, trace:{seed_nodes,hop,relation_type}, importance, ...}]
            已排除语义命中本身；score 为扩散综合分（非语义相似度）。
        """
        if not self.available():
            logger.info("[scene_diffusion] graph unavailable, skip")
            return []

        graph = self._graph
        # 1. 种子组装：语义命中 scene（带语义分） + 种子锚点
        seed_scenes, seed_anchors, seed_scores = _assemble_seeds(semantic_results)
        # query 锚点匹配：种子锚点中出现在 query 里的优先级更高（FR-005 person/goal 锚点）
        query_anchors = [a for a in seed_anchors if a in query] if query else []

        if not seed_scenes and not seed_anchors:
            logger.info("[scene_diffusion] no seeds, skip")
            return []

        logger.info(
            f"[scene_diffusion] seeds | scenes={len(seed_scenes)} anchors={len(seed_anchors)} "
            f"query_anchors={query_anchors}"
        )

        # 2. 扩散：anchor 直连（1 跳）+ 边扩散（多跳）
        activation, trace = self._spread(seed_scenes, seed_scores, seed_anchors, query_anchors)

        if not activation:
            return []

        # 3. 候选聚合：去掉种子/语义命中本身
        seed_set = set(seed_scenes) | {m.get("id") for m in semantic_results if m.get("id")}
        candidates = [
            (sid, act) for sid, act in activation.items()
            if sid not in seed_set and act >= _MIN_ACTIVATION
        ]
        candidates.sort(key=lambda x: x[1], reverse=True)
        candidates = candidates[:_MAX_CANDIDATES]
        if not candidates:
            return []

        # 4. 从 Qdrant 补 payload（text/importance/affect/created_at）用于加权与展示
        payload_map = _fetch_payloads([sid for sid, _ in candidates])

        # 5. 加权 + 重排（importance / affect / query 锚点命中 / 时间近因）
        results = []
        for sid, act in candidates:
            pay = payload_map.get(sid, {})
            importance = _clamp(pay.get("importance", 0.3), 0.0, 1.0, 0.3)
            affect = pay.get("affect") or {}
            intensity = abs(_clamp(affect.get("intensity", 0.0), -3.0, 3.0, 0.0))
            tr = trace.get(sid, {})
            # query 锚点命中加分（为什么/目标类问题更易唤起 FR-005）
            cand_anchors = {a["name"] for a in graph.get_scene_anchors(sid)}
            query_hit = 1.0 + (0.15 * len(cand_anchors & set(query_anchors))) if query_anchors else 1.0
            recency = _recency_factor(pay.get("created_at"))
            score = act * (0.5 + importance) * (1.0 + intensity * 0.1) * query_hit * recency
            score = round(min(1.0, score), 4)
            item = {
                "id": sid,
                "text": pay.get("display_text") or pay.get("text", ""),
                "embedding_text": pay.get("embedding_text") or "",
                "score": score,
                "source": "scene_diffusion",
                "importance": importance,
            }
            if with_trace:
                item["trace"] = {
                    "seed_nodes": list(dict.fromkeys(tr.get("seeds", [])))[:6],
                    "hop": tr.get("hop", 1),
                    "relation_type": tr.get("relation", "shared_node"),
                    "activation": round(act, 4),
                }
            results.append(item)

        results.sort(key=lambda x: x["score"], reverse=True)
        logger.info(
            f"[scene_diffusion] DONE | candidates={len(results)} | "
            f"top={results[0]['id'][:8] if results else '-'} "
            f"score={results[0]['score'] if results else 0}"
        )
        return results[:top_k]

    # ── 扩散核心 ───────────────────────────────────────────────

    def _spread(self, seed_scenes, seed_scores, seed_anchors, query_anchors):
        """双通道受控激活扩散，返回 (activation, trace)

        channel A：锚点直连 — seed/query 锚点 → 共享 scene（1 跳）
        channel B：边扩散 — seed scene 沿 scene_edges 传播（多跳，frontier 限流）
        """
        graph = self._graph
        activation: dict[str, float] = {}
        trace: dict[str, dict] = {}

        def _touch(scene_id, act, hop, seeds, relation):
            sid = str(scene_id)
            if act > activation.get(sid, 0.0):
                activation[sid] = act
            prev = trace.get(sid)
            if prev is None or hop < prev.get("hop", 99):
                trace[sid] = {
                    "hop": hop,
                    "seeds": list(dict.fromkeys(seeds)),
                    "relation": relation,
                }

        # Channel A: 锚点直连（1 跳）。query_anchors 与 seed_anchors 合并，query 优先
        anchor_priorities = {a: (2.0 if a in query_anchors else 1.0) for a in seed_anchors}
        all_anchors = list(anchor_priorities.keys())
        if all_anchors:
            neighbors = graph.get_anchor_neighbors(
                all_anchors, exclude=set(seed_scenes), limit=_MAX_CANDIDATES
            )
            for sid, shared_w in neighbors:
                # 命中的种子锚点（用于 trace）
                hit_anchors = _anchors_of_scene(graph, sid, set(all_anchors))
                prior = max((anchor_priorities[a] for a in hit_anchors if a in anchor_priorities), default=1.0)
                _touch(sid, 0.6 * (shared_w or 0.5) * 0.5 * prior, 1, hit_anchors, "shared_node")

        # Channel B: 边扩散（多跳）
        frontier = [(sid, seed_scores.get(sid, 0.8)) for sid in seed_scenes]
        for hop in range(1, _MAX_HOPS + 1):
            if not frontier:
                break
            # frontier 限流
            frontier.sort(key=lambda x: x[1], reverse=True)
            frontier = frontier[:_MAX_FRONTIER]
            next_frontier = []
            for sid, act in frontier:
                if act < _MIN_ACTIVATION:
                    continue
                for nb in graph.get_scene_neighbors(sid, limit=_MAX_EDGES_LOOKUPS()):
                    nb_id = nb["scene_id"]
                    new_act = act * _DECAY * (nb["weight"] or 1.0)
                    if new_act < _MIN_ACTIVATION:
                        continue
                    seed_trace = trace.get(sid, {}).get("seeds") or [sid]
                    _touch(nb_id, new_act, hop, seed_trace, nb["relation_type"])
                    # 只把「新激活或更高激活」的邻居放入下一跳 frontier
                    if new_act >= activation.get(nb_id, 0.0) - 1e-9:
                        next_frontier.append((nb_id, new_act))
            frontier = next_frontier

        return activation, trace

    # ── 解释：返回完整扩散路径 ─────────────────────────────────

    def explain(self, query: str, semantic_results: list[dict], result_ids: list[str] | None = None) -> dict:
        """重跑扩散并返回 trace 详情（FR-008 / T010 explain 接口）

        Args:
            result_ids: 仅返回这些 id 的 trace；None 返回全部候选 trace
        """
        results = self.search(query, semantic_results, top_k=_MAX_CANDIDATES, with_trace=True)
        if result_ids:
            wanted = set(result_ids)
            results = [r for r in results if r["id"] in wanted]
        return {
            "query": query,
            "seed_count": len({m.get("id") for m in semantic_results if m.get("id")}),
            "traces": [
                {
                    "id": r["id"],
                    "text": r["text"],
                    "score": r["score"],
                    **r.get("trace", {}),
                }
                for r in results
            ],
        }


# ── 工具函数 ─────────────────────────────────────────────────


def _assemble_seeds(semantic_results: list[dict]) -> tuple[list[str], list[str], dict[str, float]]:
    """从语义命中组装扩散种子：(seed_scenes, seed_anchors, seed_scores)

    seed_scores 用语义分归一化作为种子初始激活（语义越相关 → 种子激活越高）。
    """
    seed_scenes = []
    seed_anchors = []
    seed_scores: dict[str, float] = {}
    scores = [m.get("score", 0.0) for m in semantic_results if m.get("id") and m.get("score")]
    max_score = max(scores) if scores else 1.0
    for m in semantic_results:
        sid = m.get("id")
        if not sid:
            continue
        seed_scenes.append(sid)
        norm = (m.get("score", 0.0) / max_score) if max_score > 0 else 0.8
        seed_scores[sid] = round(max(_ACT_FLOOR, norm), 4)
        # payload.nodes → 种子锚点（情景记忆才有；legacy 无 nodes 自动跳过）
        pay = m.get("payload") or {}
        for nd in pay.get("nodes") or []:
            if isinstance(nd, dict) and nd.get("name"):
                seed_anchors.append(nd["name"])
    seed_scenes = list(dict.fromkeys(seed_scenes))
    seed_anchors = list(dict.fromkeys(seed_anchors))
    return seed_scenes, seed_anchors, seed_scores


def _anchors_of_scene(graph, scene_id: str, anchor_pool: set) -> list[str]:
    """返回 scene 命中的种子锚点（用于 trace 的 seed_nodes）"""
    anchors = graph.get_scene_anchors(scene_id)
    return [a["name"] for a in anchors if a["name"] in anchor_pool]


def _fetch_payloads(scene_ids: list[str]) -> dict[str, dict]:
    """批量从 Qdrant 取 payload（text/importance/affect/created_at），失败返回空 dict"""
    if not scene_ids:
        return {}
    try:
        from modules.qdrant.store import get_qdrant_client, NEW_COLLECTION
        client = get_qdrant_client()
        points = client.retrieve(
            collection_name=NEW_COLLECTION, ids=scene_ids,
            with_payload=True, with_vectors=False,
        )
        return {str(p.id): (p.payload or {}) for p in points}
    except Exception as e:
        logger.warning(f"[scene_diffusion] fetch payloads failed: {e}")
        return {}


def _recency_factor(created_at: str | None) -> float:
    """时间近因因子：越新分越高（1.0 → 0.85），无时间返回 1.0"""
    if not created_at:
        return 1.0
    try:
        # ISO 时间字符串取年月日数值估算（避免 import datetime 受限）
        import datetime
        created = datetime.datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        days = (datetime.datetime.now(created.tzinfo) - created).days
        return max(0.85, 1.0 - days * 0.0005)
    except Exception:
        return 1.0


def _clamp(v, lo, hi, default):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, f))


def _MAX_EDGES_LOOKUPS() -> int:
    """每跳每个 scene 最多查看的边数（与 _MAX_EDGES_PER_SCENE 对齐）"""
    return 8


def get_scene_diffusion() -> "SceneDiffusion | None":
    """全局单例，图不可用时返回 None（调用方兜底）"""
    global _INSTANCE
    if _INSTANCE is not None:
        return _INSTANCE
    with _INSTANCE_LOCK:
        if _INSTANCE is None:
            try:
                inst = SceneDiffusion()
                if inst.available():
                    _INSTANCE = inst
                else:
                    logger.info("[scene_diffusion] scene graph unavailable, singleton stays None")
            except Exception as e:
                logger.warning(f"[scene_diffusion] init failed (non-fatal): {e}")
    return _INSTANCE
