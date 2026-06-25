"""
重建图谱：遍历所有记忆，用新 LLM prompt 重新提取实体并写入图数据库

作为模块被 backend/core/rebuild_service.py 调用
- 函数签名：rebuild(state: dict, stop_flag, workers=5, batch_size=10, delay_between_batches=1.0)
  - state: 用于实时反馈进度的 dict（由调用方初始化）
  - stop_flag: threading.Event，set() 即终止
- 日志：复用后端 logger（角色 'memory'），不再单独写文件
"""
import os
import time
import sqlite3
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

logger = logging.getLogger('memory')

GRAPH_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "memory_graph.db"
)

# 从 .port_config 读取 Qdrant 端口
_QDRANT_PORT = None
try:
    _project_root = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
    _port_config = os.path.join(_project_root, '.port_config')
    if os.path.exists(_port_config):
        with open(_port_config, 'r') as f:
            parts = f.read().strip().split(',')
            if len(parts) >= 2:
                _QDRANT_PORT = parts[1]  # 第2个是 Qdrant
except Exception:
    pass
_QDRANT_URL = f"http://localhost:{_QDRANT_PORT or '19399'}"


def wait_for_qdrant(max_retries=30, retry_delay=2.0):
    """等待 Qdrant 就绪"""
    import urllib.request
    for i in range(max_retries):
        try:
            req = urllib.request.Request(_QDRANT_URL + "/collections")
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    logger.info(f"Qdrant 就绪 ({_QDRANT_URL})")
                    return True
        except Exception:
            pass
        time.sleep(retry_delay)
    logger.error(f"Qdrant {max_retries * retry_delay}s 后仍未就绪")
    return False


# 全局锁，保护数据库写入
_db_lock = Lock()


def get_all_memories(max_retries=5, retry_delay=5.0):
    """从 mem0 获取所有记忆，带重试"""
    from main_brain.memory import get_mem0_client
    for attempt in range(1, max_retries + 1):
        try:
            client = get_mem0_client()
            result = client.get_all(filters={"user_id": "default"}, top_k=10000)
            memories = result.get("results", [])
            logger.info(f"从 mem0 获取 {len(memories)} 条记忆")
            return memories
        except Exception as e:
            logger.warning(f"获取记忆失败 (attempt {attempt}/{max_retries}): {e}")
            if attempt < max_retries:
                time.sleep(retry_delay)
            else:
                raise


def clear_graph():
    """清空图数据库所有表"""
    conn = sqlite3.connect(GRAPH_DB_PATH)
    conn.execute("PRAGMA foreign_keys=OFF")
    for table in ['entity_relations', 'typed_entity_relations', 'mentions',
                   'memory_relations', 'memory_nodes', 'entity_nodes']:
        conn.execute(f"DELETE FROM {table}")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.commit()
    conn.close()
    logger.info("图数据库已清空")


def process_memory(mem):
    """处理单条记忆，提取实体（在线程池中执行）"""
    mem_id = mem.get("id", "")
    mem_text = mem.get("memory", "")
    if not mem_id or not mem_text:
        return None
    try:
        from main_brain.memory.llm import extract_entities_llm
        result = extract_entities_llm(mem_text)
        entities = result.get("entities", [])
        root = result.get("root", "用户")
        return {"mem_id": mem_id, "text": mem_text, "entities": entities, "root": root}
    except Exception as e:
        logger.warning(f"提取失败 {mem_id[:8]}: {e}")
        return None


def write_to_graph(data_list):
    """批量写入数据库（需要加锁）"""
    if not data_list:
        return
    with _db_lock:
        from main_brain.memory.graph import get_graph
        graph = get_graph()
        if not graph:
            return
        for data in data_list:
            graph.link_memory(data["mem_id"], data["text"],
                              link_entities=data["entities"],
                              root_entity=data["root"])


def rebuild(state: dict, stop_flag, workers: int = 5, batch_size: int = 10,
            delay_between_batches: float = 1.0):
    """遍历所有记忆，多线程提取实体，批量写入数据库

    Args:
        state: 进度状态字典（调用方负责初始化字段），函数内持续更新
        stop_flag: threading.Event，set() 时本次循环检测到后会尽快退出
        workers: 并行线程数
        batch_size: 每批处理多少条后写入一次数据库
        delay_between_batches: 每批之间的延迟秒数
    """
    state["current_phase"] = "init"
    clear_graph()
    logger.info("图数据库已清空")
    # clear_graph 把 entity_nodes（含 4 个根实体）也清空了，需要：
    # 1. 重新初始化 4 个根实体（否则 link_memory 写 entity_relations(root, ent)
    #    会触发外键约束失败）
    # 2. 清空 _entity_embedding_cache（缓存里残留的旧实体向量会导致 dedup 复用
    #    一个 entity_nodes 表里已经不存在的实体，进而触发 mentions 外键失败）
    from main_brain.memory.graph import get_graph
    _g = get_graph()
    if _g:
        _g._init_default_entities()
        _g._entity_embedding_cache.clear()
        logger.info("默认根实体已重新初始化，实体向量缓存已清空")

    # 等待 Qdrant 就绪
    if not wait_for_qdrant():
        state["status"] = "failed"
        state["error"] = "Qdrant 未就绪"
        return

    # Qdrant 就绪后等待几秒让连接稳定
    time.sleep(5)
    if stop_flag.is_set():
        state["status"] = "idle"
        return

    # 初始化图（重建默认实体）
    from main_brain.memory.graph import get_graph
    graph = get_graph()
    if not graph:
        logger.error("图初始化失败")
        state["status"] = "failed"
        state["error"] = "图初始化失败"
        return

    # 获取所有记忆
    try:
        memories = get_all_memories()
    except Exception as e:
        logger.error(f"获取记忆失败: {e}")
        state["status"] = "failed"
        state["error"] = str(e)
        return

    if not memories:
        logger.info("没有记忆需要处理")
        state["total"] = 0
        state["status"] = "completed"
        return

    total = len(memories)
    state["total"] = total
    logger.info(f"开始处理 {total} 条记忆 | 线程数={workers} | 批大小={batch_size}")

    state["current_phase"] = "first_pass"
    success = 0
    empty = 0
    failed = 0
    processed = 0
    empty_memories = []  # 收集空结果的记忆，用于最后重试

    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_mem = {executor.submit(process_memory, mem): mem for mem in memories}

        batch = []
        for future in as_completed(future_to_mem):
            if stop_flag.is_set():
                executor.shutdown(wait=False, cancel_futures=True)
                break
            processed += 1
            state["processed"] = processed
            result = future.result()
            state["llm_calls"] += 1
            if result is None:
                failed += 1
                state["failed"] = failed
                state["llm_calls_failed"] += 1
            elif not result["entities"]:
                empty += 1
                state["empty"] = empty
                empty_memories.append({"id": result["mem_id"], "text": result["text"]})
            else:
                success += 1
                state["success"] = success
                state["llm_calls_success"] += 1
                batch.append(result)

            # 达到 batch_size 就写入
            if len(batch) >= batch_size:
                write_to_graph(batch)
                batch.clear()
                logger.info(f"进度 {processed}/{total} | 成功={success} 空={empty} 失败={failed}")
                time.sleep(delay_between_batches)

        # 写入剩余的
        if batch:
            write_to_graph(batch)

    if stop_flag.is_set():
        state["status"] = "idle"
        state["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        logger.info(f"第一轮被取消 | 已处理={processed}/{total}")
        return

    logger.info(f"\n{'='*50}")
    logger.info(f"第一轮完成 | 总计={total} 成功={success} 空={empty} 失败={failed}")
    logger.info(f"{'='*50}")

    # 重试空结果（单线程、慢延迟，避免 API 限流）
    if empty_memories:
        state["current_phase"] = "retry"
        state["retry_total"] = len(empty_memories)
        state["retry_processed"] = 0
        logger.info(f"\n开始重试 {len(empty_memories)} 条空记忆（单线程，间隔 {delay_between_batches*2}s）")
        retry_success = 0
        retry_still_empty = 0

        retry_batch = []
        for i, mem in enumerate(empty_memories, 1):
            if stop_flag.is_set():
                break
            try:
                from main_brain.memory.llm import extract_entities_llm
                result = extract_entities_llm(mem["text"])
                state["llm_calls"] += 1
                entities = result.get("entities", [])
                root = result.get("root", "用户")
                if entities:
                    retry_batch.append({"mem_id": mem["id"], "text": mem["text"],
                                        "entities": entities, "root": root})
                    retry_success += 1
                    state["retry_success"] = retry_success
                    state["llm_calls_success"] += 1
                    logger.info(f"[重试 {i}/{len(empty_memories)}] {mem['id'][:8]} → 提取到 {len(entities)} 个实体")
                else:
                    retry_still_empty += 1
                    state["llm_calls_failed"] += 1
                    logger.info(f"[重试 {i}/{len(empty_memories)}] {mem['id'][:8]} → 仍为空")
            except Exception as e:
                retry_still_empty += 1
                state["llm_calls_failed"] += 1
                logger.warning(f"[重试 {i}/{len(empty_memories)}] {mem['id'][:8]} 失败: {e}")

            state["retry_processed"] = i

            # 每 5 条写入一次
            if len(retry_batch) >= 5:
                write_to_graph(retry_batch)
                retry_batch.clear()
                time.sleep(delay_between_batches * 2)

            time.sleep(delay_between_batches)

        if retry_batch:
            write_to_graph(retry_batch)

        logger.info(f"\n重试完成 | 重试成功={retry_success} 仍为空={retry_still_empty}")

    # 打印统计
    state["current_phase"] = "finished"
    try:
        stats = graph.get_stats()
        logger.info(f"\n{'='*50}")
        logger.info(f"图统计: 实体={stats['entity_count']} 记忆节点={stats['memory_count']} mentions={stats['edge_count']}")
        logger.info(f"{'='*50}")
    except Exception as e:
        logger.warning(f"读取图统计失败: {e}")
