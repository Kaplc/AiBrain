#!/usr/bin/env python3
"""将 mem0_memories 的原文通过完整 store 管线（含 encoder）重新存入 aibrain_memories。

每次调用 store_memory(text) 触发完整的 store 流水线：
  episodic_merge（去重合并）→ encoder（LLM 提取 display_text/episodic/nodes/affect/importance）
  → vector_store（写入 Qdrant）→ entity_extract → graph_link → scene_link（建情景图索引）

幂等：checkpoint 记录已处理的 legacy_id，可中断后断点续跑。
"""
import json
import logging
import os
import sys
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("migrate_episodic")

PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "backend"))

CHECKPOINT = os.path.join(
    PROJECT_ROOT, "1-logs", "migrations", "legacy_scene", "checkpoint_episodic.json"
)


def migrate(limit: int | None = None):
    # 初始化流水线引擎（注册 store/search 步骤），否则 store_memory 降级为跳过 encoder 的 legacy 路径
    try:
        from modules.brain.memory.pipeline import init_pipelines
        init_pipelines()

        from modules.brain.memory.pipeline.engine import PipelineEngine
        engine = PipelineEngine.get_instance()
        # 迁移期间跳过 entity_extract 和 graph_link（旧实体图，~7s/条），迁移结束后可重跑 graph_link
        # 保留 encoder + scene_link 以构建情景图（核心目标）
        engine.set_pipeline("store", [
            {"name": "episodic_merge", "enabled": True, "required": False},
            {"name": "encoder", "enabled": True, "required": False},
            {"name": "vector_store", "enabled": True, "required": True},
            {"name": "entity_extract", "enabled": False, "required": False},
            {"name": "graph_link", "enabled": False, "required": False},
            {"name": "scene_link", "enabled": True, "required": False},
        ])
        logger.info("Pipeline engine initialized (entity_extract+graph_link DISABLED for speed)")
    except Exception as e:
        logger.warning(f"Pipeline engine init failed (will fallback to legacy path): {e}")

    from modules.brain.memory.qdrant_store import get_qdrant_client, LEGACY_COLLECTION
    from modules.brain.memory import store_memory

    client = get_qdrant_client()
    offset = None
    total = 0
    migrated = 0

    # 读取 checkpoint（幂等恢复）
    seen = set()
    if os.path.exists(CHECKPOINT):
        try:
            with open(CHECKPOINT) as f:
                cp = json.load(f)
            seen = set(cp.get("ids", []))
            offset = cp.get("offset")
            logger.info(f"Resume from checkpoint: {len(seen)} done, offset={offset}")
        except Exception as e:
            logger.warning(f"Checkpoint read failed: {e}")

    while True:
        try:
            results, offset = client.scroll(
                LEGACY_COLLECTION, offset=offset, limit=30,
                with_payload=True, with_vectors=False,
            )
        except Exception as e:
            logger.warning(f"Scroll failed: {e}")
            break
        if not results:
            break

        for r in results:
            if limit is not None and migrated >= limit:
                break
            rid = str(r.id)
            if rid in seen:
                total += 1
                continue
            payload = r.payload or {}
            text = (payload.get("data") or payload.get("text") or "").strip()
            if not text:
                total += 1
                continue

            try:
                # store_memory 触发完整管线：encoder(LLM) → vector_store → scene_link
                store_memory(text, {"source": "migration"})
                total += 1
                migrated += 1
                seen.add(rid)
                logger.info(f"[OK] {rid[:8]} | text={text[:50]!r}")
            except Exception as e:
                logger.warning(f"[FAIL] {rid[:8]} store_memory failed: {e}")

            if migrated > 0 and migrated % 10 == 0:
                logger.info(f"Progress: {migrated} migrated / {total} total")

        # 保存 checkpoint
        try:
            os.makedirs(os.path.dirname(CHECKPOINT), exist_ok=True)
            with open(CHECKPOINT + ".tmp", "w") as f:
                json.dump({
                    "ids": list(seen),
                    "offset": str(offset) if offset else None,
                }, f)
            os.replace(CHECKPOINT + ".tmp", CHECKPOINT)
        except Exception as e:
            logger.warning(f"Checkpoint write failed: {e}")

        if offset is None or (limit is not None and migrated >= limit):
            break

    logger.info(f"Done: {migrated} migrated / {total} total")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="将 legacy 记忆编码为情景记忆并存入 aibrain_memories")
    p.add_argument("--limit", type=int, help="限制处理条数（测试用）")
    args = p.parse_args()
    migrate(limit=args.limit)
