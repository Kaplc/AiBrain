#!/usr/bin/env python3
"""收尾迁移：基于 checkpoint_api.json 精确匹配，清掉 legacy 并补迁移。

策略（不依赖不可靠的语义相似度，用 checkpoint 精确匹配）：
  - legacy id 在 checkpoint_api（386 个）→ 已有情景副本 → 直接删 legacy 原文
  - legacy id 不在 checkpoint（~27 个）→ 未迁移 → POST /memory/store 编码 + 删 legacy

结果：legacy 清空，每条记忆只剩一条情景，搜索 0 重复。
幂等：自身 checkpoint 跟踪已处理的 legacy id，可断点续跑。
"""
import json
import logging
import os
import sys
import time
from urllib.request import Request, urlopen
from urllib.error import URLError

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("finish_migration")

PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "backend"))

BACKEND_URL = "http://localhost:19398"
CHECKPOINT_API = os.path.join(PROJECT_ROOT, "1-logs", "migrations", "legacy_scene", "checkpoint_api.json")
CHECKPOINT = os.path.join(PROJECT_ROOT, "1-logs", "migrations", "legacy_scene", "checkpoint_finish.json")


def post_store(text: str) -> dict:
    payload = json.dumps({"text": text, "memory_meta": {"source": "migration"}}).encode("utf-8")
    req = Request(BACKEND_URL + "/memory/store", data=payload,
                  headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def finish():
    from qdrant_client.http import models as q
    from modules.brain.memory.qdrant_store import get_qdrant_client, LEGACY_COLLECTION

    # 加载 API 迁移 checkpoint（已迁移的 legacy id 集合）
    migrated_set = set()
    if os.path.exists(CHECKPOINT_API):
        with open(CHECKPOINT_API) as f:
            migrated_set = set(json.load(f).get("ids", []))
    logger.info(f"API-migrated legacy ids: {len(migrated_set)}")

    # 自身 checkpoint（断点续跑）
    done = set()
    if os.path.exists(CHECKPOINT):
        try:
            with open(CHECKPOINT) as f:
                done = set(json.load(f).get("ids", []))
            logger.info(f"Resume: {len(done)} already processed")
        except Exception:
            pass

    client = get_qdrant_client()
    offset = None
    migrated_new = 0   # 本次新迁移的
    deleted_legacy = 0  # 删除的 legacy 原文

    while True:
        try:
            results, offset = client.scroll(
                LEGACY_COLLECTION, offset=offset, limit=50,
                with_payload=True, with_vectors=False,
            )
        except Exception as e:
            logger.warning(f"Scroll failed: {e}")
            break
        if not results:
            break

        for r in results:
            rid = str(r.id)
            if rid in done:
                continue
            payload = r.payload or {}
            text = (payload.get("data") or payload.get("text") or "").strip()

            if rid in migrated_set:
                # 已迁移 → 直接删 legacy 原文
                action = "delete-only"
            else:
                # 未迁移 → POST 编码
                if not text:
                    action = "delete-only"  # 空文本，直接删
                else:
                    try:
                        post_store(text)
                        migrated_new += 1
                        action = "migrated"
                    except Exception as e:
                        logger.warning(f"[FAIL-MIGRATE] {rid[:8]} | {e} | text={text[:40]!r}")
                        action = "skip"  # 迁移失败，保留 legacy 不删

            # 删除 legacy 原文（迁移失败的除外）
            if action != "skip":
                try:
                    client.delete(
                        collection_name=LEGACY_COLLECTION,
                        points_selector=q.PointIdsList(points=[rid]),
                        wait=True,
                    )
                    deleted_legacy += 1
                except Exception as e:
                    logger.warning(f"[FAIL-DELETE] {rid[:8]} | {e}")
                    action = action + "-delfail"

            done.add(rid)
            if migrated_new % 5 == 0 and migrated_new > 0:
                logger.info(f"[PROGRESS] new_migrated={migrated_new} legacy_deleted={deleted_legacy} | last={rid[:8]} {action}")

        # 保存 checkpoint
        try:
            os.makedirs(os.path.dirname(CHECKPOINT), exist_ok=True)
            with open(CHECKPOINT + ".tmp", "w") as f:
                json.dump({"ids": list(done)}, f)
            os.replace(CHECKPOINT + ".tmp", CHECKPOINT)
        except Exception as e:
            logger.warning(f"Checkpoint write failed: {e}")

        if offset is None:
            break
        time.sleep(0.2)

    logger.info(f"DONE: new_migrated={migrated_new} legacy_deleted={deleted_legacy} processed={len(done)}")


if __name__ == "__main__":
    finish()
