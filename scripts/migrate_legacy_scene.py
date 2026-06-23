#!/usr/bin/env python3
"""将 mem0_memories 的原文通过 store_vector 重新存入 aibrain_memories"""
import json
import logging
import os
import sys
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("migrate")

PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "backend"))

CHECKPOINT = os.path.join(PROJECT_ROOT, "1-logs", "migrations", "legacy_scene", "checkpoint.json")


def migrate(limit=None):
    from modules.brain.memory.qdrant_store import store_vector, get_qdrant_client, LEGACY_COLLECTION

    client = get_qdrant_client()
    offset = None
    total = 0
    migrated = 0

    # 尝试读取 checkpoint
    seen = set()
    if os.path.exists(CHECKPOINT):
        try:
            with open(CHECKPOINT) as f:
                cp = json.load(f)
            seen = set(cp.get("ids", []))
            offset = cp.get("offset")
            logger.info(f"Resume from checkpoint: {len(seen)} done, offset={offset}")
        except Exception:
            pass

    while True:
        results, offset = client.scroll(
            LEGACY_COLLECTION, offset=offset, limit=100,
            with_payload=True, with_vectors=False,
        )
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

            store_vector(text)
            total += 1
            migrated += 1
            seen.add(rid)

            if migrated % 50 == 0:
                logger.info(f"Progress: {migrated} migrated / {total} total")

        # 保存 checkpoint
        try:
            os.makedirs(os.path.dirname(CHECKPOINT), exist_ok=True)
            with open(CHECKPOINT + ".tmp", "w") as f:
                json.dump({"ids": list(seen), "offset": str(offset) if offset else None}, f)
            os.replace(CHECKPOINT + ".tmp", CHECKPOINT)
        except Exception as e:
            logger.warning(f"Checkpoint write failed: {e}")

        if offset is None or (limit is not None and migrated >= limit):
            break
        time.sleep(0.5)

    logger.info(f"Done: {migrated} migrated / {total} total")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int)
    args = p.parse_args()
    migrate(limit=args.limit)
