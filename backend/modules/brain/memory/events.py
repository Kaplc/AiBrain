"""
事件记忆召回 - EventStore 单例
管理事件的提取、存储、链推断、时间衰减和召回
通过 graph._exec() 复用 memory_graph.db 连接
"""
import json
import logging
import math
import re
import uuid
from datetime import datetime

logger = logging.getLogger('events')

_INSTANCE = None


def get_event_store():
    """获取 EventStore 单例，初始化失败返回 None"""
    global _INSTANCE
    if _INSTANCE is not None:
        return _INSTANCE
    try:
        from modules.brain.graph import get_graph
        graph = get_graph()
        if graph is None:
            return None
        _INSTANCE = EventStore(graph)
        logger.info("[events] EventStore initialized")
        return _INSTANCE
    except Exception as e:
        logger.warning(f"[events] EventStore init failed (non-fatal): {e}")
        return None


# ── JSON 解析工具 ──────────────────────────────────────────

def _parse_json(raw: str):
    """从 LLM 响应中提取 JSON，支持 code block 包裹"""
    if not raw:
        return None
    raw = raw.strip()
    # 直接解析
    try:
        return json.loads(raw)
    except Exception:
        pass
    # 尝试提取 ```json ... ```
    m = re.search(r'```(?:json)?\s*([\s\S]*?)```', raw)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except Exception:
            pass
    # 尝试提取第一个 {...} 或 [...]
    for pattern in (r'\{[\s\S]*\}', r'\[[\s\S]*\]'):
        m = re.search(pattern, raw)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
    return None


class EventStore:
    """事件存储与召回，复用 GraphMemory 的 SQLite 连接"""

    # 合法的 relation_type 值
    VALID_RELATION_TYPES = {"cause_of", "effect_of", "next_in_sequence"}
    # 合法的 emotion 值
    VALID_EMOTIONS = {"positive", "negative", "neutral", "shock", "warm", "sad", "excited"}

    def __init__(self, graph):
        self._graph = graph
        self._exec = graph._exec  # 复用 graph 的 _exec 方法
        self._conn = graph._conn  # 直接引用连接（用于 commit）

    # ── 事件提取 ──────────────────────────────────────────

    def extract_events_from_memory(self, memory_id: str, memory_text: str) -> list[str]:
        """从记忆文本中提取事件并存入 events + event_memories 表

        Returns:
            成功创建的 event_id 列表
        """
        if not memory_text or not memory_text.strip():
            return []

        from modules.brain.memory.prompts import EVENT_EXTRACT_PROMPT
        from modules.brain.llm import call_llm

        for attempt in range(1, 4):  # max_retries=3
            try:
                raw = call_llm(EVENT_EXTRACT_PROMPT, f"文本：{memory_text}", timeout=20)
                parsed = _parse_json(raw)
                if not parsed:
                    logger.warning(f"[events] extract parse failed ({attempt}/3)")
                    continue

                # 概念/事实 → 不建事件
                if parsed.get("type") != "event" or not parsed.get("event"):
                    logger.info(f"[events] not an event, skip | text={memory_text[:50]}")
                    return []

                ev = parsed["event"]
                event_id = str(uuid.uuid4())

                # 清洗字段
                subject = str(ev.get("subject", "")).strip()[:50]
                action = str(ev.get("action", "")).strip()[:50]
                if not subject or not action:
                    logger.warning(f"[events] extract missing subject/action, skip")
                    continue

                obj = ev.get("object")
                obj = str(obj).strip()[:50] if obj else None
                context = ev.get("context")
                context = str(context).strip()[:200] if context else None
                time_expr = ev.get("time_expr")
                time_expr = str(time_expr).strip()[:50] if time_expr else None
                summary = str(ev.get("summary", "")).strip()[:300]
                if not summary:
                    summary = f"{subject}{action}"
                emotion = ev.get("emotion", "neutral")
                if emotion not in self.VALID_EMOTIONS:
                    emotion = "neutral"
                emotion_intensity = float(ev.get("emotion_intensity", 0.5))
                emotion_intensity = max(0.0, min(1.0, emotion_intensity))
                importance = float(ev.get("importance", 0.5))
                importance = max(0.0, min(1.0, importance))
                is_first = bool(ev.get("is_first_occurrence", False))

                # 写入 events 表
                self._exec(
                    """INSERT INTO events
                       (id, subject, action, object, context, time_expr, summary,
                        emotion, emotion_intensity, importance, is_first_occurrence, memory_count)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
                    (event_id, subject, action, obj, context, time_expr, summary,
                     emotion, emotion_intensity, importance, is_first)
                )
                # 写入 event_memories 关联
                self._exec(
                    "INSERT OR IGNORE INTO event_memories (event_id, memory_id) VALUES (?, ?)",
                    (event_id, memory_id)
                )
                self._conn.commit()
                logger.info(
                    f"[events] extracted event {event_id[:8]} | "
                    f"{subject}→{action} | emotion={emotion} importance={importance:.2f}"
                )
                return [event_id]

            except Exception as e:
                logger.warning(f"[events] extract failed ({attempt}/3): {e}")

        logger.warning(f"[events] extract all 3 attempts failed | mem={memory_id[:8]}")
        return []

    # ── 事件查询 ──────────────────────────────────────────

    def get_events_for_memories(self, memory_ids: list[str]) -> dict[str, list[dict]]:
        """反查：给定 memory_id 列表，返回每条记忆关联的事件

        Returns:
            {memory_id: [event_dict, ...]}
        """
        if not memory_ids:
            return {}
        try:
            placeholders = ",".join("?" * len(memory_ids))
            rows = self._exec(
                f"""SELECT em.memory_id, e.id, e.subject, e.action, e.object,
                           e.context, e.time_expr, e.summary, e.emotion,
                           e.emotion_intensity, e.importance, e.is_first_occurrence, e.created_at
                    FROM events e
                    JOIN event_memories em ON e.id = em.event_id
                    WHERE em.memory_id IN ({placeholders})""",
                tuple(memory_ids)
            )
            result: dict[str, list[dict]] = {mid: [] for mid in memory_ids}
            for r in rows:
                mid = r[0]
                if mid in result:
                    result[mid].append(self._row_to_event(r[1:]))
            return result
        except Exception as e:
            logger.warning(f"[events] get_events_for_memories failed: {e}")
            return {}

    def get_memories_for_events(self, event_ids: list[str]) -> list[str]:
        """反查：给定 event_id 列表，返回关联的 memory_id 列表（去重）"""
        if not event_ids:
            return []
        try:
            placeholders = ",".join("?" * len(event_ids))
            rows = self._exec(
                f"SELECT DISTINCT memory_id FROM event_memories WHERE event_id IN ({placeholders})",
                tuple(event_ids)
            )
            return [r[0] for r in rows]
        except Exception as e:
            logger.warning(f"[events] get_memories_for_events failed: {e}")
            return []

    def get_recent_events(self, limit: int = 50, offset: int = 0) -> list[dict]:
        """获取最近事件，按 created_at 倒序"""
        try:
            rows = self._exec(
                """SELECT id, subject, action, object, context, time_expr, summary,
                          emotion, emotion_intensity, importance, is_first_occurrence, created_at
                   FROM events ORDER BY created_at DESC LIMIT ? OFFSET ?""",
                (limit, offset)
            )
            return [self._row_to_event(r) for r in rows]
        except Exception as e:
            logger.warning(f"[events] get_recent_events failed: {e}")
            return []

    def get_event_by_id(self, event_id: str) -> dict | None:
        """根据 ID 获取单个事件"""
        try:
            rows = self._exec(
                """SELECT id, subject, action, object, context, time_expr, summary,
                          emotion, emotion_intensity, importance, is_first_occurrence, created_at
                   FROM events WHERE id = ?""",
                (event_id,)
            )
            return self._row_to_event(rows[0]) if rows else None
        except Exception as e:
            logger.warning(f"[events] get_event_by_id failed: {e}")
            return None

    # ── 事件搜索 ──────────────────────────────────────────

    def search_events_by_query(self, query: str, events_pool: list[dict] = None,
                                max_results: int = 15) -> list[dict]:
        """用 LLM 匹配查询与事件摘要

        Args:
            query: 用户搜索词
            events_pool: 候选事件列表，None 则从 DB 加载最近 200 条
            max_results: 最大返回数
        """
        if events_pool is None:
            events_pool = self.get_recent_events(limit=200)
        if not events_pool:
            return []

        # 事件太少时直接用子串匹配
        if len(events_pool) < 3:
            return self._substring_search(query, events_pool, max_results)

        try:
            from modules.brain.memory.prompts import EVENT_MATCH_PROMPT
            from modules.brain.llm import call_llm

            # 构建事件列表文本
            lines = []
            for i, ev in enumerate(events_pool):
                lines.append(
                    f"[{i}] {ev['subject']} {ev['action']}"
                    + (f" {ev['object']}" if ev.get('object') else "")
                    + f" | {ev['summary']}"
                )
            user_prompt = f"查询：{query}\n\n事件列表：\n" + "\n".join(lines)

            raw = call_llm(EVENT_MATCH_PROMPT, user_prompt, timeout=15)
            parsed = _parse_json(raw)
            if not parsed or "matched_indices" not in parsed:
                # LLM 失败，回退子串匹配
                return self._substring_search(query, events_pool, max_results)

            matched = []
            for idx in parsed["matched_indices"]:
                if isinstance(idx, int) and 0 <= idx < len(events_pool):
                    matched.append(events_pool[idx])
                if len(matched) >= max_results:
                    break
            return matched

        except Exception as e:
            logger.warning(f"[events] search_events_by_query LLM failed, fallback: {e}")
            return self._substring_search(query, events_pool, max_results)

    def _substring_search(self, query: str, events: list[dict], max_results: int) -> list[dict]:
        """子串匹配回退方案"""
        q_lower = query.lower()
        matched = []
        for ev in events:
            text = f"{ev.get('subject','')} {ev.get('action','')} {ev.get('object','')} {ev.get('summary','')}"
            if q_lower in text.lower():
                matched.append(ev)
        return matched[:max_results]

    # ── 事件链 ──────────────────────────────────────────

    def get_chain_for_event(self, event_id: str, max_depth: int = 3) -> list[dict]:
        """BFS 遍历 event_relations，获取事件链中所有关联事件

        Returns:
            关联事件列表（不含起始事件），每条带 depth 和 relation_type 字段
        """
        try:
            visited = {event_id}
            result = []
            current_level = [event_id]

            for depth in range(1, max_depth + 1):
                if not current_level:
                    break
                placeholders = ",".join("?" * len(current_level))
                # 查双向关系
                rows = self._exec(
                    f"""SELECT source_event_id, target_event_id, relation_type
                        FROM event_relations
                        WHERE source_event_id IN ({placeholders})
                           OR target_event_id IN ({placeholders})""",
                    tuple(current_level) * 2
                )
                next_level = []
                for r in rows:
                    src, tgt, rel_type = r[0], r[1], r[2]
                    neighbor = tgt if src in visited else src
                    if neighbor not in visited:
                        visited.add(neighbor)
                        ev = self.get_event_by_id(neighbor)
                        if ev:
                            ev["depth"] = depth
                            ev["relation_type"] = rel_type
                            result.append(ev)
                            next_level.append(neighbor)
                current_level = next_level

            return result
        except Exception as e:
            logger.warning(f"[events] get_chain_for_event failed: {e}")
            return []

    def infer_event_chains(self, new_event_ids: list[str]):
        """LLM 推断新事件与近期事件的因果/时序关系

        Args:
            new_event_ids: 新创建的事件 ID 列表
        """
        if not new_event_ids:
            return

        try:
            from modules.brain.memory.prompts import CHAIN_INFER_PROMPT
            from modules.brain.llm import call_llm

            # 取新事件 + 最近 20 条事件作为上下文
            new_events = []
            for eid in new_event_ids:
                ev = self.get_event_by_id(eid)
                if ev:
                    new_events.append(ev)
            if not new_events:
                return

            recent = self.get_recent_events(limit=20)
            # 排除新事件自身（按 id 去重）
            new_ids_set = set(new_event_ids)
            context_events = [e for e in recent if e["id"] not in new_ids_set]

            # 如果没有历史事件，无法建链
            if not context_events:
                logger.info("[events] no context events for chain inference")
                return

            # 合并：历史在前（索引 0..N-1），新事件在后
            all_events = context_events + new_events
            new_start_idx = len(context_events)

            # 构建 prompt
            lines = []
            for i, ev in enumerate(all_events):
                tag = " [新]" if i >= new_start_idx else ""
                lines.append(
                    f"[{i}] {ev['subject']} {ev['action']}"
                    + (f" → {ev['object']}" if ev.get('object') else "")
                    + f" | {ev['summary']}{tag}"
                )
            user_prompt = "事件列表：\n" + "\n".join(lines)

            raw = call_llm(CHAIN_INFER_PROMPT, user_prompt, timeout=20)
            parsed = _parse_json(raw)
            if not parsed or not isinstance(parsed, list):
                logger.info("[events] chain inference returned no relations")
                return

            # 写入 event_relations
            inserted = 0
            for rel in parsed:
                try:
                    src_idx = rel.get("source_idx")
                    tgt_idx = rel.get("target_idx")
                    rel_type = rel.get("relation_type", "")
                    confidence = float(rel.get("confidence", 0.5))

                    if not isinstance(src_idx, int) or not isinstance(tgt_idx, int):
                        continue
                    if src_idx < 0 or src_idx >= len(all_events):
                        continue
                    if tgt_idx < 0 or tgt_idx >= len(all_events):
                        continue
                    if rel_type not in self.VALID_RELATION_TYPES:
                        continue
                    if confidence < 0.5:
                        continue

                    src_id = all_events[src_idx]["id"]
                    tgt_id = all_events[tgt_idx]["id"]

                    self._exec(
                        """INSERT OR IGNORE INTO event_relations
                           (source_event_id, target_event_id, relation_type, confidence)
                           VALUES (?, ?, ?, ?)""",
                        (src_id, tgt_id, rel_type, confidence)
                    )
                    inserted += 1
                except Exception as e:
                    logger.warning(f"[events] insert relation failed: {e}")

            self._conn.commit()
            if inserted > 0:
                logger.info(f"[events] chain inference: {inserted} relations created")

        except Exception as e:
            logger.warning(f"[events] infer_event_chains failed: {e}")

    # ── 时间衰减算法 ─────────────────────────────────────

    def compute_decay_score(self, raw_score: float, event: dict, hours_elapsed: float) -> float:
        """计算时间衰减后的分数

        公式：decayed_score = raw_score × decay(t) × emotion_boost × importance_boost
        - decay(t) = e^(-λ×t), λ = 0.01 / (importance + 0.2)
        - 近因加成: t < 1天时 decay += 0.1×(1-t)
        - 首因豁免: is_first_occurrence → decay = 1.0
        - emotion_boost = 1 + (emotion_intensity - 0.5) × 0.4
        - importance_boost = 1 + (importance - 0.5) × 0.3
        """
        importance = event.get("importance", 0.5)
        emotion_intensity = event.get("emotion_intensity", 0.5)
        is_first = event.get("is_first_occurrence", False)

        # 首因豁免：永不衰减
        if is_first:
            decay_t = 1.0
        else:
            lam = 0.01 / (importance + 0.2)
            days_elapsed = hours_elapsed / 24.0
            decay_t = math.exp(-lam * days_elapsed)
            # 近因加成：平滑过渡
            if days_elapsed < 1.0:
                decay_t += 0.1 * (1.0 - days_elapsed)

        emotion_boost = 1.0 + (emotion_intensity - 0.5) * 0.4
        importance_boost = 1.0 + (importance - 0.5) * 0.3

        return raw_score * decay_t * emotion_boost * importance_boost

    def apply_decay_to_results(self, memories: list[dict], event_map: dict[str, list[dict]]) -> list[dict]:
        """对搜索结果应用时间衰减加权

        Args:
            memories: 搜索结果列表 [{id, text, score, ...}]
            event_map: {memory_id: [event_dict, ...]}，来自 get_events_for_memories

        Returns:
            按 decayed_score 降序重排后的 memories（原地修改 score 字段）
        """
        if not event_map:
            return memories

        now = datetime.utcnow()

        for m in memories:
            mid = m.get("id", "")
            events = event_map.get(mid, [])
            if not events:
                continue

            # 取所有关联事件中最高的 decay_score
            max_decayed = m.get("score", 0.5)
            for ev in events:
                try:
                    created = ev.get("created_at", "")
                    if created:
                        dt = datetime.fromisoformat(created.replace("Z", "+00:00").replace("+00:00", ""))
                        hours = max(0.0, (now - dt).total_seconds() / 3600)
                    else:
                        hours = 0.0
                    decayed = self.compute_decay_score(m.get("score", 0.5), ev, hours)
                    if decayed > max_decayed:
                        max_decayed = decayed
                except Exception:
                    pass

            m["score"] = round(max_decayed, 4)

        memories.sort(key=lambda x: x.get("score", 0), reverse=True)
        return memories

    # ── 统计 ──────────────────────────────────────────

    def get_event_stats(self) -> dict:
        """返回事件系统统计信息"""
        try:
            event_count = self._exec("SELECT COUNT(*) FROM events")[0][0]
            event_mem_count = self._exec("SELECT COUNT(*) FROM event_memories")[0][0]
            event_rel_count = self._exec("SELECT COUNT(*) FROM event_relations")[0][0]

            # 带链的事件数
            chained = self._exec(
                """SELECT COUNT(DISTINCT e.id) FROM events e
                   WHERE EXISTS (SELECT 1 FROM event_relations er WHERE er.source_event_id = e.id)
                      OR EXISTS (SELECT 1 FROM event_relations er WHERE er.target_event_id = e.id)"""
            )[0][0]

            # 情感分布
            emotion_rows = self._exec(
                "SELECT emotion, COUNT(*) FROM events GROUP BY emotion"
            )
            emotions = {r[0] or "neutral": r[1] for r in emotion_rows}

            return {
                "total_events": event_count,
                "event_memory_links": event_mem_count,
                "event_relations": event_rel_count,
                "chained_events": chained,
                "orphan_events": event_count - chained,
                "emotions": emotions,
            }
        except Exception as e:
            logger.warning(f"[events] get_event_stats failed: {e}")
            return {
                "total_events": 0, "event_memory_links": 0,
                "event_relations": 0, "chained_events": 0,
                "orphan_events": 0, "emotions": {},
            }

    # ── 回溯处理旧记忆 ─────────────────────────────────────

    def reprocess_memories(self, limit: int = 100, skip_existing: bool = True) -> dict:
        """从已有记忆中回溯提取事件（用于填充初始数据）

        Args:
            limit: 最多处理多少条记忆
            skip_existing: 是否跳过已有事件关联的记忆

        Returns:
            {"processed": N, "events_created": M, "skipped_concepts": K, "errors": E}
        """
        try:
            # 获取还没有事件关联的记忆
            if skip_existing:
                rows = self._exec(
                    """SELECT m.mem0_id, m.text FROM memory_nodes m
                       WHERE m.mem0_id NOT IN (SELECT DISTINCT memory_id FROM event_memories)
                       LIMIT ?""",
                    (limit,)
                )
            else:
                rows = self._exec(
                    "SELECT mem0_id, text FROM memory_nodes LIMIT ?",
                    (limit,)
                )

            processed = 0
            events_created = 0
            skipped = 0
            errors = 0

            for mem_id, text in rows:
                processed += 1
                try:
                    new_ids = self.extract_events_from_memory(mem_id, text or "")
                    if new_ids:
                        events_created += len(new_ids)
                    else:
                        skipped += 1
                except Exception as e:
                    errors += 1
                    logger.warning(f"[events] reprocess failed for {mem_id[:8]}: {e}")

            # 对所有新事件做一次批量链推断
            if events_created > 0:
                try:
                    all_events = self.get_recent_events(limit=events_created + 20)
                    new_ids = [e["id"] for e in all_events[:events_created]]
                    self.infer_event_chains(new_ids)
                except Exception as e:
                    logger.warning(f"[events] reprocess chain inference failed: {e}")

            return {
                "processed": processed,
                "events_created": events_created,
                "skipped_concepts": skipped,
                "errors": errors,
            }
        except Exception as e:
            logger.warning(f"[events] reprocess_memories failed: {e}")
            return {"processed": 0, "events_created": 0, "skipped_concepts": 0, "errors": 1}

    # ── 内部工具 ────────────────────────────────────────

    def _row_to_event(self, row) -> dict:
        """将 SQL 行转为事件字典"""
        return {
            "id": row[0],
            "subject": row[1],
            "action": row[2],
            "object": row[3],
            "context": row[4],
            "time_expr": row[5],
            "summary": row[6],
            "emotion": row[7],
            "emotion_intensity": row[8],
            "importance": row[9],
            "is_first_occurrence": bool(row[10]),
            "created_at": row[11],
        }
