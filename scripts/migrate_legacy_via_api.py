#!/usr/bin/env python3
"""通过 POST /memory/store API 将 mem0_memories 的原文经完整管线（含 encoder）重新存入。

每次 POST 触发后端 full store pipeline：episodic_merge → encoder(LLM) → vector_store → scene_link
（entity_extract/graph_link 按服务器端配置运行，在此不做干预）

幂等：checkpoint 跟踪 legacy_id，支持断点续跑。
"""
import json
import logging
import os
import sys
import time
from urllib.request import Request, urlopen
from urllib.error import URLError

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("migrate_via_api")

PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "backend"))

BACKEND_URL = os.environ.get("MIGRATE_BACKEND_URL", "http://localhost:18980")
CHECKPOINT = os.path.join(
    PROJECT_ROOT, "1-logs", "migrations", "legacy_scene", "checkpoint_api.json"
)

# 清除之前通过 store_vector 写入的检验点，因为这次要经编码器重写
# 已有 checkpoint 则读取（幂等恢复）
_RESUME_CLEAR = False  # 清理旧 checkpoint 以全量重跑（设为 False 则断点续跑）


def post_store(text: str) -> dict:
    """POST /memory/store → 返回 JSON"""
    payload = json.dumps({"text": text, "memory_meta": {"source": "migration"}}).encode("utf-8")
    req = Request(
        BACKEND_URL + "/memory/store",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except URLError as e:
        raise RuntimeError(f"API error: {e}")


def migrate(limit: int | None = None):
    from modules.qdrant.store import get_qdrant_client, LEGACY_COLLECTION

    client = get_qdrant_client()
    offset = None
    total = 0
    migrated = 0

    # 清理旧 checkpoint（如果 _RESUME_CLEAR 为 True）
    if _RESUME_CLEAR and os.path.exists(CHECKPOINT):
        os.remove(CHECKPOINT)
        logger.info("_RESUME_CLEAR=True, cleared old checkpoint for full re-run")

    # 读取 checkpoint
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
                result = post_store(text)
                total += 1
                migrated += 1
                seen.add(rid)
                # 每 5 条打印简洁进度
                if migrated % 5 == 0:
                    logger.info(f"[OK] #{migrated} | id={rid[:8]} | text={text[:45]!r} | added={result.get('added_count', 0)}")
                else:
                    logger.debug(f"[OK] {rid[:8]} | text={text[:40]!r}")
            except Exception as e:
                logger.warning(f"[FAIL] {rid[:8]} | {e} | text={text[:40]!r}")

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
        time.sleep(0.3)  # 轻微限速

    logger.info(f"Done: {migrated} migrated / {total} total")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, help="限制处理条数（测试用）")
    args = p.parse_args()
    migrate(limit=args.limit)
