"""
记忆去重模块 - 基于 Embedding 相似度的流式去重分组
支持分批处理、实时 yield 组、暂停/恢复/停止控制
"""
import logging
import threading
import time
import numpy as np

from brain_mcp.embedding import encode_texts

logger = logging.getLogger(__name__)

# 相似度阈值档位
THRESHOLD_STRICT = 0.90
THRESHOLD_MEDIUM = 0.85
THRESHOLD_LOOSE = 0.80

# 全局暂停/停止标志
_dedup_pause_flag = threading.Event()
_dedup_stop_flag = threading.Event()


def _get_all_memories(client, user_id: str):
    """从 mem0 获取全部记忆"""
    result = client.get_all(filters={"user_id": user_id}, top_k=100000)
    memories = result.get("results", [])
    memories.sort(key=lambda m: m.get("created_at", ""), reverse=True)
    return [
        {"id": m["id"], "text": m["memory"], "timestamp": m.get("created_at")}
        for m in memories
    ]


def _union_find_cluster(sim_matrix, threshold):
    """并查集聚类：相似度 >= threshold 的记忆归为同一组"""
    n = len(sim_matrix)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for i in range(n):
        for j in range(i + 1, n):
            if sim_matrix[i][j] >= threshold:
                union(i, j)

    groups = {}
    for i in range(n):
        root = find(i)
        groups.setdefault(root, []).append(i)

    return [indices for indices in groups.values() if len(indices) >= 2]


def dedup_memories(threshold=THRESHOLD_MEDIUM):
    """全量记忆去重分组（同步版本，保留向后兼容）"""
    from modules.brain.mem0_adapter import get_mem0_client
    from modules.brain.memory import DEFAULT_USER_ID

    client = get_mem0_client()
    all_memories = _get_all_memories(client, DEFAULT_USER_ID)

    if not all_memories:
        return {"groups": [], "total_memories": 0, "grouped_count": 0, "ungrouped_count": 0}

    n = len(all_memories)
    logger.info(f"[dedup] 开始去重，共 {n} 条记忆，阈值={threshold}")

    texts = [m["text"] for m in all_memories]
    vectors = encode_texts(texts)

    mat = np.array(vectors, dtype=np.float32)
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    mat = mat / np.maximum(norms, 1e-8)

    sim_matrix = mat @ mat.T
    cluster_indices = _union_find_cluster(sim_matrix, threshold)

    groups = []
    grouped_indices = set()
    for indices in cluster_indices:
        grouped_indices.update(indices)
        if len(indices) > 1:
            pairs = [(indices[a], indices[b]) for a in range(len(indices)) for b in range(a + 1, len(indices))]
            avg_sim = float(np.mean([sim_matrix[i][j] for i, j in pairs]))
        else:
            avg_sim = 1.0

        groups.append({
            "group_id": len(groups),
            "memories": [
                {
                    "id": all_memories[i]["id"],
                    "text": all_memories[i]["text"],
                    "timestamp": all_memories[i].get("timestamp"),
                }
                for i in indices
            ],
            "similarity": round(avg_sim, 4),
        })

    groups.sort(key=lambda g: g["similarity"], reverse=True)
    for i, g in enumerate(groups):
        g["group_id"] = i

    grouped_count = len(grouped_indices)
    logger.info(f"[dedup] 完成：{len(groups)} 组相似记忆，{grouped_count} 条参与去重")

    return {
        "groups": groups,
        "total_memories": n,
        "grouped_count": grouped_count,
        "ungrouped_count": n - grouped_count,
    }


def dedup_memories_iter(threshold=THRESHOLD_MEDIUM, batch_size=30, pause_flag=None, stop_flag=None):
    """流式去重生成器，分批处理记忆，发现新组时 yield

    Yields:
        {"type": "batch", "found": N, "total": T, "groups": [...]} 定期发送当前已发现组
        {"type": "done", "total": N, "grouped": M, "ungrouped": K, "groups": [...]} 扫描完成
        {"type": "stopped", "found": N, "groups": [...]} 中途停止
    """
    if pause_flag is None:
        pause_flag = _dedup_pause_flag
    if stop_flag is None:
        stop_flag = _dedup_stop_flag

    from modules.brain.mem0_adapter import get_mem0_client
    from modules.brain.memory import DEFAULT_USER_ID

    client = get_mem0_client()
    all_memories = _get_all_memories(client, DEFAULT_USER_ID)

    if not all_memories:
        yield {"type": "done", "total": 0, "grouped": 0, "ungrouped": 0, "groups": []}
        return

    n = len(all_memories)
    logger.info(f"[dedup:iter] 开始流式去重，共 {n} 条记忆，阈值={threshold}，batch_size={batch_size}")

    texts = [m["text"] for m in all_memories]

    # Union-Find 并查集
    uf_parent = list(range(n))
    uf_rank = [0] * n

    def uf_find(x):
        while uf_parent[x] != x:
            uf_parent[x] = uf_parent[uf_parent[x]]
            x = uf_parent[x]
        return x

    def uf_union(a, b):
        ra, rb = uf_find(a), uf_find(b)
        if ra != rb:
            if uf_rank[ra] < uf_rank[rb]:
                ra, rb = rb, ra
            uf_parent[rb] = ra
            if uf_rank[ra] == uf_rank[rb]:
                uf_rank[ra] += 1

    # 累积编码向量和对应的 index
    all_vectors = []
    all_indices = []
    # 已yield出去的组id集合（用于去重）
    yielded_ids = set()

    for batch_start in range(0, n, batch_size):
        if stop_flag is not None and stop_flag.is_set():
            logger.info("[dedup:iter] 检测到停止信号")
            found = _collect_groups(uf_parent, all_memories, all_vectors, all_indices, threshold)
            yield {"type": "stopped", "found": len(found), "groups": found}
            return

        if pause_flag is not None:
            while pause_flag.is_set() and not (stop_flag is not None and stop_flag.is_set()):
                time.sleep(0.1)
            if stop_flag is not None and stop_flag.is_set():
                logger.info("[dedup:iter] 暂停状态下收到停止信号")
                found = _collect_groups(uf_parent, all_memories, all_vectors, all_indices, threshold)
                yield {"type": "stopped", "found": len(found), "groups": found}
                return

        batch_end = min(batch_start + batch_size, n)
        batch_texts = texts[batch_start:batch_end]

        batch_vecs = encode_texts(batch_texts)
        batch_mat = np.array(batch_vecs, dtype=np.float32)
        batch_norms = np.linalg.norm(batch_mat, axis=1, keepdims=True)
        batch_mat = batch_mat / np.maximum(batch_norms, 1e-8)

        # 批次内部两两比较
        bs = batch_end - batch_start
        if bs > 1:
            sim_batch = batch_mat @ batch_mat.T
            np.fill_diagonal(sim_batch, 0)
            for i in range(bs):
                for j in range(i + 1, bs):
                    if sim_batch[i, j] >= threshold:
                        uf_union(batch_start + i, batch_start + j)

        # 当前批次与历史已编码记忆比较
        if all_vectors:
            hist_mat = np.array(all_vectors, dtype=np.float32)
            sim_cross = batch_mat @ hist_mat.T
            for bi in range(bs):
                for hi in range(len(all_vectors)):
                    if sim_cross[bi, hi] >= threshold:
                        uf_union(batch_start + bi, all_indices[hi])

        # 追加到历史
        for bi in range(bs):
            all_vectors.append(batch_mat[bi])
            all_indices.append(batch_start + bi)

        # 每批处理完发送新增的组（仅发送本批中新形成的组）
        found_groups = _collect_groups(uf_parent, all_memories, all_vectors, all_indices, threshold)
        new_groups = [g for g in found_groups
                      if not any(m["id"] in yielded_ids for m in g["memories"])]
        if new_groups:
            # 分配临时 group_id（按发现顺序）
            for i, g in enumerate(new_groups):
                g["group_id"] = len(yielded_ids) + i
            for g in new_groups:
                yielded_ids.update(m["id"] for m in g["memories"])
            yield {
                "type": "batch",
                "found": len(new_groups),
                "total": n,
                "groups": new_groups,
            }

    # 全量处理完毕，计算精确相似度
    final_groups = _collect_groups(uf_parent, all_memories, all_vectors, all_indices, threshold)
    final_groups.sort(key=lambda g: g["similarity"], reverse=True)
    for i, g in enumerate(final_groups):
        g["group_id"] = i

    grouped_ids = set()
    for g in final_groups:
        for m in g["memories"]:
            grouped_ids.add(m["id"])

    logger.info(f"[dedup:iter] 完成：{len(final_groups)} 组，{len(grouped_ids)} 条参与去重")

    yield {
        "type": "done",
        "total": n,
        "grouped": len(grouped_ids),
        "ungrouped": n - len(grouped_ids),
        "groups": final_groups,
    }


def _collect_groups(uf_parent, all_memories, all_vectors, all_indices, threshold):
    """从 Union-Find 结构收集已确认的重复组"""
    index_to_mem = {all_indices[i]: i for i in range(len(all_indices))}

    root_map = {}
    for idx in range(len(all_memories)):
        root = idx
        while uf_parent[root] != root:
            root = uf_parent[root]
        root_map.setdefault(root, []).append(idx)

    groups = []
    for indices in root_map.values():
        if len(indices) < 2:
            continue

        # 过滤出在 all_indices 中的 index
        valid_indices = [idx for idx in indices if idx in index_to_mem]
        if len(valid_indices) < 2:
            continue

        vec_indices = [index_to_mem[idx] for idx in valid_indices]
        vecs = np.array([all_vectors[vi] for vi in vec_indices], dtype=np.float32)
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        vecs_norm = vecs / np.maximum(norms, 1e-8)
        sim_mat = vecs_norm @ vecs_norm.T
        np.fill_diagonal(sim_mat, 0)
        avg_sim = float(np.mean(sim_mat)) if sim_mat.size > 0 else 0.85

        groups.append({
            "group_id": len(groups),
            "memories": [
                {
                    "id": all_memories[i]["id"],
                    "text": all_memories[i]["text"],
                    "timestamp": all_memories[i].get("timestamp"),
                }
                for i in valid_indices
            ],
            "similarity": round(avg_sim, 4),
        })

    groups.sort(key=lambda g: g["similarity"], reverse=True)
    return groups
