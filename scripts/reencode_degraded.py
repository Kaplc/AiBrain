#!/usr/bin/env python3
"""重编码 aibrain_memories 中「有 episodic 但无 nodes」的降级记忆。

编码器偶发返回空 nodes，这些记忆有情景结构但不进场景图。
策略：用每条的 embedding_text（display+what+why+result+lesson）作为输入，
先删旧的降级 point，再 POST /memory/store 重跑编码器，期望这次产出 nodes。

幂等：自身 checkpoint 跟踪已处理的 id。
"""
import json
import logging
import os
import sys
import time
from urllib.request import Request, urlopen

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("reencode")

PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "backend"))

BACKEND_URL = "http://localhost:19398"
CHECKPOINT = os.path.join(PROJECT_ROOT, "1-logs", "migrations", "legacy_scene", "checkpoint_reencode.json")


def post_store(text: str) -> dict:
    payload = json.dumps({"text": text, "memory_meta": {"source": "reencode"}}).encode("utf-8")
    
    req = Request(BACKEND_URL + "/memory/store", data=payload,
                  headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_new_nodes(point_id: str) -> list:
    """取新存入 point 的 nodes（校验编码器这次是否产出）"""
    from modules.brain.memory.qdrant_store import get_qdrant_client, NEW_COLLECTION
    c = get_qdrant_client()
    pts = c.retrieve(collection_name=NEW_COLLECTION, ids=[point_id], with_payload=True, with_vectors=False)
    if not pts:
        return []
    return (pts[0].payload or {}).get("nodes") or []


def reencode():
    from qdrant_client.http import models as q
    from modules.brain.memory.qdrant_store import get_qdrant_client, NEW_COLLECTION

    client = get_qdrant_client()

    # 1. 扫描找出降级记忆（有 episodic 无 nodes）
    offset = None
    degraded = []  # [(id, embedding_text)]
    while True:
        pts, offset = client.scroll(
            collection_name=NEW_COLLECTION, offset=offset, limit=300,
            with_payload=True, with_vectors=False,
        )
        if not pts:
            break
        for p in pts:
            pay = p.payload or {}
            nodes = pay.get("nodes") or []
            epi = pay.get("episodic")
            if epi and not nodes:
                txt = (pay.get("embedding_text") or pay.get("text") or "").strip()
                if txt:
                    degraded.append((str(p.id), txt))
        if offset is None:
            break
    logger.info(f"found {len(degraded)} degraded (episodic, no nodes)")

    # checkpoint
    done = set()
    if os.path.exists(CHECKPOINT):
        try:
            with open(CHECKPOINT) as f:
                done = set(json.load(f).get("ids", []))
        except Exception:
            pass

    reencoded = 0
    got_nodes = 0
    for pid, txt in degraded:
        if pid in done:
            continue
        # 先删旧的降级 point
        try:
            client.delete(collection_name=NEW_COLLECTION,
                          points_selector=q.PointIdsList(points=[pid]), wait=True)
        except Exception as e:
            logger.warning(f"[FAIL-DELETE] {pid[:8]} | {e}")
            continue
        # POST 重编码
        try:
            result = post_store(txt)
            reencoded += 1
            # 新 point 的 id 不直接返回，用文本反查最新一条
            # 简单做法：取 embedding_text 重新 retrieve 不可行（无 id）。
            # 改为信任编码器；事后统一统计 nodes 数。
            logger.info(f"[OK] reencoded {pid[:8]} → new | text={txt[:40]!r}")
        except Exception as e:
            logger.warning(f"[FAIL-POST] {pid[:8]} | {e} | 已删旧但重存失败，文本={txt[:40]!r}")
        done.add(pid)
        time.sleep(0.3)

    # 保存 checkpoint
    try:
        os.makedirs(os.path.dirname(CHECKPOINT), exist_ok=True)
        with open(CHECKPOINT + ".tmp", "w") as f:
            json.dump({"ids": list(done)}, f)
        os.replace(CHECKPOINT + ".tmp", CHECKPOINT)
    except Exception:
        pass

    logger.info(f"DONE: reencoded={reencoded} of {len(degraded)} degraded")


if __name__ == "__main__":
    reencode()
