"""
重建图谱：遍历所有记忆，用新 LLM prompt 重新提取实体并写入图数据库
用法: python -m scripts.rebuild_graph

多线程版本：并行调用 LLM，批量写入数据库
"""
import os
import sys
import time
import sqlite3
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

# 确保 backend/ 在 path 中
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(message)s',
    datefmt='%H:%M:%S',
    handlers=[
        logging.FileHandler(os.path.join(os.path.dirname(__file__), 'rebuild_graph.log'), encoding='utf-8'),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger('rebuild')

GRAPH_DB_PATH = os.path.join(os.path.expanduser("~"), ".aibrain", "data", "memory_graph.db")

# 从 .port_config 读取 Qdrant 端口
_QDRANT_PORT = None
_port_config = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', '.port_config'))
if os.path.exists(_port_config):
    with open(_port_config, 'r') as f:
        _QDRANT_PORT = f.read().strip().split(',')[1]  # 第2个是 Qdrant
_QDRANT_URL = f"http://localhost:{_QDRANT_PORT or '19399'}"

def wait_for_qdrant(max_retries=30, retry_delay=2.0):
    """等待 Qdrant 就绪"""
    import urllib.request
    import time
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
    from modules.brain.mem0_adapter import get_mem0_client
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
        from modules.brain.llm import extract_entities_llm
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
        from modules.brain.graph import get_graph
        graph = get_graph()
        if not graph:
            return
        for data in data_list:
            graph.link_memory(data["mem_id"], data["text"],
                            link_entities=data["entities"],
                            root_entity=data["root"])


def rebuild(workers=5, batch_size=10, delay_between_batches=1.0, force_clear=False):
    """遍历所有记忆，多线程提取实体，批量写入数据库

    Args:
        workers: 并行线程数（默认5）
        batch_size: 每批处理多少条后写入一次数据库（默认10）
        delay_between_batches: 每批之间的延迟秒数（默认1.0）
    """
    if force_clear:
        clear_graph()
        # 清空日志
        with open(os.path.join(os.path.dirname(__file__), 'rebuild_graph.log'), 'w', encoding='utf-8') as f:
            f.write('')
        logger.info("图数据库已清空，日志已重置")
    else:
        clear_graph()

    # 等待 Qdrant 就绪
    if not wait_for_qdrant():
        return

    # Qdrant 就绪后等待几秒让连接稳定
    time.sleep(5)

    # 初始化图（重建默认实体）
    from modules.brain.graph import get_graph
    graph = get_graph()
    if not graph:
        logger.error("图初始化失败")
        return

    # 获取所有记忆
    memories = get_all_memories()
    if not memories:
        logger.info("没有记忆需要处理")
        return

    total = len(memories)
    logger.info(f"开始处理 {total} 条记忆 | 线程数={workers} | 批大小={batch_size}")

    results = []
    success = 0
    empty = 0
    failed = 0
    processed = 0

    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_mem = {executor.submit(process_memory, mem): mem for mem in memories}

        batch = []
        for future in as_completed(future_to_mem):
            processed += 1
            result = future.result()
            if result is None:
                failed += 1
            elif not result["entities"]:
                empty += 1
            else:
                success += 1
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

    logger.info(f"\n{'='*50}")
    logger.info(f"重建完成 | 总计={total} 成功={success} 空={empty} 失败={failed}")
    logger.info(f"{'='*50}")

    # 打印统计
    stats = graph.get_stats()
    logger.info(f"图统计: 实体={stats['entity_count']} 记忆节点={stats['memory_count']} mentions={stats['edge_count']}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='重建图谱')
    parser.add_argument('-w', '--workers', type=int, default=5, help='并行线程数')
    parser.add_argument('-b', '--batch', type=int, default=10, help='每批处理条数')
    parser.add_argument('-d', '--delay', type=float, default=1.0, help='批间延迟(秒)')
    parser.add_argument('-f', '--force', action='store_true', help='清空日志和图数据库重新开始')
    args = parser.parse_args()
    rebuild(workers=args.workers, batch_size=args.batch, delay_between_batches=args.delay, force_clear=args.force)