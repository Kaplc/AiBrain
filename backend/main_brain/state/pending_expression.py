"""Pending Expression — 表达意图（存意图不存内容）

核心改造（plan 模块 5 / 决策 #6）：
  - 【不存 content】：发送时由 LLM 按当前上下文实时生成，保证内容反映最新状态。
    这里只存 source_node_id + expression_score 快照 + 路径类型。
  - 双路径（取 max）：
      recent_interest     = effective × drive
      resurfacing_interest = effective × dormancy × drive
      expression_score    = max(recent, resurfacing)
    dormancy = min(1.0, hours_since_last_activated / 24)
  - expression_score 生成时【快照】，后续检查不重算（否则队列顺序漂移）。

发送（plan 模块 7 / 决策 #10）：
  - 优先级 = expression_score + age_score × 0.5（age_score 运行时算，不快照）
  - 条件：未表达 ∧ 不在冷却 ∧ 距上次发送 > 1h
  - recent_interest 冷却【不】阻断 open_loop（refractory type 区分 interest/open_loop）

注：旧版的 age_importance() 存在 hours×0.0001 的双缩放 bug，新版用 age_score
运行时计算，该 bug 随之消失。
"""
import logging
import threading

from .store import get_state
from .. import clock

logger = logging.getLogger('state.pending')

PENDING_GENERATION_THRESHOLD = 0.15  # 表达分达到此值才入队
PENDING_QUEUE_CAP = 5
SEND_MIN_INTERVAL_HOURS = 1.0
AGE_GROWTH_PER_HOUR = 0.01           # age_score = min(1.0, hours×0.01)，100h 饱和

# 主动消息生成的 LLM system prompt
_PROACTIVE_SYSTEM = """你是{name}，一个数字生命体。
性格：{traits}。
{relationship}"""

_SEND_LOCK = threading.Lock()  # 确保同一时间只有一个线程执行 proactive_send


class PendingExpressionManager:
    """表达意图管理器。"""

    def __init__(self, state=None):
        self._state = state or get_state()

    # ── 双路径评分（只读）─────────────────────────────────

    def _score_for_concern(self, node_id: str) -> tuple[str, float]:
        """对 concern 节点算双路径表达分。Returns (path_type, score)。"""
        from . import get_concerns
        from . import get_drives
        concerns = get_concerns()
        eff = concerns.get_effective(node_id)
        if eff <= 0:
            return ("recent_interest", 0.0)
        drive = get_drives().drive_for_node(node_id)
        dormancy = concerns.get_dormancy(node_id)

        recent = eff * drive
        resurfacing = eff * dormancy * drive
        if resurfacing >= recent and dormancy > 0:
            return ("resurfacing_interest", round(resurfacing, 4))
        return ("recent_interest", round(recent, 4))

    # ── 生成（扫描 + 入队）────────────────────────────────

    def evaluate_and_generate(self) -> int:
        """扫描所有 concern + open_loop，为达标的生成 pending。

        尊重 refractory（在冷却内的不入队）+ 去重。Returns: 新生成数量。
        """
        from . import get_concerns
        from . import get_open_loops
        from . import get_expression_history
        refractory = get_expression_history()
        created = 0
        blocked_refractory = 0
        below_threshold = 0

        # concern 路径
        cmap = get_concerns().concern_map()
        for node_id, eff in cmap.items():
            if eff <= 0:
                continue
            path, score = self._score_for_concern(node_id)
            if score < PENDING_GENERATION_THRESHOLD:
                below_threshold += 1
                continue
            if refractory.is_in_refractory("interest", node_id):
                blocked_refractory += 1
                continue
            if self._create(path, node_id, score, source="concern"):
                created += 1

        # open_loop 路径
        olm = get_open_loops()
        open_loop_count = 0
        for loop in olm.get_open():
            open_loop_count += 1
            tension = olm.tension(loop)
            if tension < PENDING_GENERATION_THRESHOLD:
                below_threshold += 1
                continue
            loop_id = loop.get("id", "")
            if refractory.is_in_refractory("open_loop", loop_id):
                blocked_refractory += 1
                continue
            if self._create("open_loop", loop_id, tension, source="open_loop"):
                created += 1

        logger.info(
            f"[pending] evaluate: {len(cmap)} concerns, {open_loop_count} open_loops, "
            f"below_threshold={below_threshold}, refractory_blocked={blocked_refractory}, "
            f"created={created}"
        )
        return created

    def _create(self, type_: str, source_node_id: str, expression_score: float,
                source: str, note: str = "") -> bool:
        """去重入队（cap 5，超限淘汰 expression_score 最低）。成功返回 True。

        note: BrainJudge 想说的话或理由 hint，proactive_send 生成时参考。
        """
        if not source_node_id:
            return False
        with self._state.transaction() as data:
            pendings = data.setdefault("pending_expressions", [])
            # 去重：同 source + source_node_id 已有未表达 → 更新分数，不新增
            for p in pendings:
                if (not p.get("expressed")
                        and p.get("source") == source
                        and p.get("source_node_id") == source_node_id):
                    p["expression_score"] = max(float(p.get("expression_score", 0.0)), expression_score)
                    p["type"] = type_
                    if note:
                        p["note"] = note
                    return False  # 已存在，未新增
            entry = {
                "id": f"pe_{clock.now_iso().replace(':', '').replace('-', '').replace('+', '')}",
                "type": type_,
                "source_node_id": source_node_id,
                "expression_score": round(float(expression_score), 4),
                "source": source,
                "created_at": clock.now_iso(),
                "expressed": False,
            }
            if note:
                entry["note"] = note
            pendings.append(entry)
            # 超 cap：淘汰未表达里 expression_score 最低的
            unexpressed = [p for p in pendings if not p.get("expressed")]
            if len(unexpressed) > PENDING_QUEUE_CAP:
                victim = min(unexpressed, key=lambda p: p.get("expression_score", 0.0))
                pendings.remove(victim)
                logger.info(f"[pending] queue cap {PENDING_QUEUE_CAP}, dropped lowest")
        logger.info(
            f"[pending] created {type_} for {source_node_id!r} score={expression_score:.3f}"
        )
        return True

    # ── 发送决策 ──────────────────────────────────────────

    def _age_score(self, pending: dict) -> float:
        """运行时 age_score = min(1.0, hours_since_created × 0.01)。"""
        hours = clock.hours_since(pending.get("created_at"))
        return min(1.0, hours * AGE_GROWTH_PER_HOUR)

    def _last_send_iso(self) -> str:
        """最近一次发送时间 = expression_history 中最大的 last_expressed。"""
        hist = self._state.snapshot().get("expression_history", [])
        vals = [h.get("last_expressed", "") for h in hist if h.get("last_expressed")]
        return max(vals) if vals else ""

    @staticmethod
    def _topic_recently_expressed(topic: str) -> bool:
        """检查 topic 是否在 output.json 最近 N 条 assistant 中出现过。

        用于 proactive_send 发送前判断同一话题是否已被表达过，
        避免因上游异常（mark_expressed 失败等）导致同一内容重复发送。
        检查最近 10 条而非仅最新 1 条，减少重复表达同一话题的概率。
        """
        if not topic:
            return False
        try:
            from main_brain.memory.workmemory import get_work_memory
            entries = get_work_memory().output_mem_read()
            if not entries:
                return False
            # 检查最近 10 条 assistant 回复，任一出现 topic 即视为已表达
            target = topic.strip()
            if not target:
                return False
            for entry in entries[-10:]:
                assistant = entry.get("assistant", "")
                if assistant and target in assistant:
                    return True
            return False
        except Exception as e:
            logger.debug(f"[pending] topic_recently_expressed check failed: {e}")
            return False

    def pick_to_send(self) -> dict | None:
        """选出当前应发送的 pending，或 None。

        条件：未表达 ∧ 不在冷却 ∧ 距上次发送 > 1h。
        优先级 = expression_score + age_score × 0.5，取最高。
        """
        from . import get_expression_history
        refractory = get_expression_history()

        # 距上次发送 < 1h → 不发
        last = self._last_send_iso()
        if last and clock.hours_since(last) < SEND_MIN_INTERVAL_HOURS:
            hours_left = SEND_MIN_INTERVAL_HOURS - clock.hours_since(last)
            logger.info(f"[pending] pick_to_send: cooldown active, {hours_left:.1f}h remaining")
            return None

        unexpressed = self.get_unexpressed()
        if not unexpressed:
            logger.info("[pending] pick_to_send: no unexpressed entries")
            return None

        best = None
        best_pri = -1.0
        blocked = 0
        for p in unexpressed:
            rtype = "open_loop" if p.get("source") == "open_loop" else "interest"
            snid = p.get("source_node_id", "")
            if refractory.is_in_refractory(rtype, snid):
                blocked += 1
                continue
            pri = float(p.get("expression_score", 0.0)) + self._age_score(p) * 0.5
            if pri > best_pri:
                best_pri = pri
                best = p
        if best:
            logger.info(
                f"[pending] pick_to_send: selected {best.get('id','')} "
                f"({best.get('source','')}/{best.get('source_node_id','')}) "
                f"pri={best_pri:.3f} (unexpressed={len(unexpressed)}, "
                f"refractory_blocked={blocked})"
            )
        else:
            logger.info(
                f"[pending] pick_to_send: all {len(unexpressed)} entries in refractory, none selected"
            )
        return best

    def _pick_unexpressed_top(self) -> dict | None:
        """绕过冷却，直接拿最高 expression_score 的未表达 pending（手动强制用）。"""
        pendings = self.get_unexpressed()
        if not pendings:
            logger.info("[pending] _pick_unexpressed_top: no unexpressed entries")
            return None
        best = max(pendings, key=lambda p: float(p.get("expression_score", 0.0)))
        logger.info(
            f"[pending] _pick_unexpressed_top: selected {best.get('id','')} "
            f"score={best.get('expression_score',0):.3f} "
            f"(candidates={len(pendings)})"
        )
        return best

    def mark_expressed(self, pending_id: str, content: str | None = None) -> bool:
        """标记已表达 + 记录 refractory + 移除条目；若给 content 则写入 output。

        content 由调用方（send 决策）在发送时用 LLM 实时生成，本模块不生成。
        表达后直接【移除】条目而非只标记 expressed=True，避免重复 topic 重入队列
        时被同 source+source_node_id 的旧 expressed 条目占位，也避免 LLM 下次选
        到同类 pending 时生成相似内容。
        """
        from . import get_expression_history
        refractory = get_expression_history()
        with self._state.transaction() as data:
            pendings = data.get("pending_expressions", [])
            target_idx = None
            target = None
            for i, p in enumerate(pendings):
                if p.get("id") == pending_id:
                    target_idx = i
                    target = p
                    break
            if target is None:
                return False
            rtype = "open_loop" if target.get("source") == "open_loop" else "interest"
            refractory.record(rtype, target.get("source_node_id", ""))
            # 移除已表达条目（不保留 expressed=True 占位）
            pendings.pop(target_idx)
            data["pending_expressions"] = pendings
        if content:
            self._write_to_output(content)
            logger.info(f"[pending] expressed {pending_id} (rtype={rtype}, content='{content[:60]}')")
        else:
            logger.info(f"[pending] expressed {pending_id} (rtype={rtype}, no content)")
        return True

    def _write_to_output(self, content: str) -> None:
        """写入 workmemory output.json，作为猫猫的主动消息。"""
        try:
            from main_brain.memory.workmemory import get_work_memory
            wm = get_work_memory()
            if wm:
                wm.output_mem_write(content=content)
        except Exception as e:
            logger.warning(f"[pending] write to output failed: {e}")

    # ── 真人化主动消息：状态 + 记忆 + 情绪 综合 ──────────────

    def _recall_vivid_memory(self, query_text: str, top_k: int = 5) -> dict | None:
        """语义召回一条最鲜活的具体记忆。

        query_text: 当前状态的语义查询（concern/open_loop/thinking 拼成）。
        用语义向量搜索（非图共现），按 affect 烈度 + importance 选最鲜活的。
        返回 {display, what, affect_desc} 或 None。
        """
        if not query_text:
            return None
        try:
            from modules.qdrant.search import search_new_collection
            hits = search_new_collection(query_text, top_k=top_k, threshold=0.3)
        except Exception as e:
            logger.warning(f"[pending] semantic recall failed for {query_text!r}: {e}")
            return None
        if not hits:
            logger.info(f"[pending] recall_vivid: no hits for {query_text!r}")
            return None

        best = None
        best_score = -1.0
        for h in hits:
            payload = h.get("payload") or {}
            affect = payload.get("affect") or {}
            intensity = abs(float(affect.get("intensity", 0) or 0))
            importance = float(payload.get("importance", 0) or 0)
            score = intensity + importance  # 鲜活度 = 情绪烈度 + 重要性
            if score > best_score:
                best_score = score
                best = payload
        if not best:
            best = hits[0].get("payload") or {}
        affect = best.get("affect") or {}
        affect_dims = {k: v for k, v in affect.items() if k != "intensity" and isinstance(v, (int, float))}
        top_dim = max(affect_dims, key=affect_dims.get) if affect_dims else None
        affect_desc = f"{top_dim}({affect_dims[top_dim]:.1f})" if top_dim else "平静"
        epi = best.get("episodic") or {}
        _what = epi.get("what", "") or best.get("display_text", "") or best.get("text", "")
        logger.info(
            f"[pending] recall_vivid: query={query_text!r} hits={len(hits)} "
            f"selected={_what[:60]} affect={affect_desc} vivacity={best_score:.2f}"
        )
        return {
            "display": best.get("display_text", ""),
            "what": _what,
            "affect_desc": affect_desc,
            "intensity": float(affect.get("intensity", 0) or 0),
        }

    def _current_mood(self) -> str:
        """从 self_narrative 拿当前心情。"""
        try:
            from main_brain.narrative import get_self_narrative
            sn = get_self_narrative()
            if sn:
                bio = sn.get_autobiography()
                mood = (bio.get("current_state") or {}).get("mood", "")
                thinking = (bio.get("current_state") or {}).get("thinking", "")
                if mood and thinking:
                    return f"{mood}，在想：{thinking}"
                return mood or "平静"
        except Exception:
            pass
        return "平静"

    def _build_persona(self) -> str:
        """综合人格：self_model（轻量）+ self_narrative 身份。"""
        parts = []
        try:
            from .self_model import get_self_model
            sm = get_self_model().get()
            name = sm.get("name", "猫猫")
            traits = "、".join(sm.get("traits", []))
            rel = sm.get("relationship", {})
            rel_str = "。".join(f"{k}是我的{v}" for k, v in rel.items())
            parts.append(f"你是{name}，性格{traits}")
            if rel_str:
                parts.append(rel_str)
        except Exception:
            parts.append("你是猫猫")
        return "。".join(parts)


    # ── 主动消息缓存（先缓存、空闲再写 output）───────────

    # 内存缓存：proactive_send 生成内容但不写 output，等空闲时 flush 一起写
    _proactive_buffer: list[dict] = []

    def proactive_send(self, force: bool = False) -> str | None:
        """生成一条主动消息 → 缓存（不写 output）→ 记冷却。

        Args:
            force: True 时绕过 1h 冷却和 refractory 检查（手动按钮用），
                   直接拿最高分未表达 pending。写入冷却仍会做（防定时器重复）。
        Returns: 生成的文本，或 None（没有待发送的 pending）。

        线程安全：用 _SEND_LOCK 保证同一时间只有一个线程执行完整
        pick→LLM→mark_expressed 流程，防止多线程同时选中不同 pending 发送。
        """
        with _SEND_LOCK:
            pick = self.pick_to_send() if not force else self._pick_unexpressed_top()
            if pick is None:
                return None

            logger.info(
                f"[pending] proactive_send start: force={force} "
                f"pick=({pick.get('source','')}/{pick.get('source_node_id','')}) "
                f"score={pick.get('expression_score',0):.3f}"
            )

            # ── 发送前检查：output 最近是否已表达过同类话题 ─────
            _snid = pick.get("source_node_id", "")
            if not force and _snid and self._topic_recently_expressed(_snid):
                logger.info(
                    f"[pending] skip send: topic '{_snid}' already in recent output"
                )
                self.mark_expressed(pick["id"])
                return None

            # ── 综合状态 + 语义召回记忆 + LLM loop 反复查找 → 主动发起 ──
            _trigger = pick.get("source", "")
            try:
                from .concerns import get_concerns
                from .open_loops import get_open_loops
            except Exception:
                get_concerns = get_open_loops = None

            # 1. 当前状态文本（concern + open_loop）
            _state_lines = []
            _query_parts = []
            if get_concerns:
                try:
                    _top = get_concerns().all_effective(3)
                    _names = [n for n, e in _top if e >= 0.1]
                    if _names:
                        _query_parts.extend(_names)
                        _state_lines.append("最近在意：" + "、".join(_names))
                except Exception:
                    pass
            if get_open_loops:
                try:
                    _loops = get_open_loops().get_open()
                    if _loops:
                        _lc = _loops[0].get("content", "")
                        if _lc:
                            _query_parts.append(_lc)
                            _state_lines.append("没想明白：" + _lc)
                except Exception:
                    pass
            if _trigger == "concern" and _snid:
                _query_parts.append(_snid)

            # 1.5 最近聊天上下文（最新 4 轮对话）
            _chat_lines = []
            try:
                from main_brain.memory.workmemory import get_work_memory
                _wm = get_work_memory()
                if _wm:
                    _entries = _wm.output_mem_read()
                    _recent = _entries[-4:] if len(_entries) >= 4 else _entries
                    if _recent:
                        _chat_lines.append("最近聊天：")
                        for _e in _recent:
                            if _e.get("user"):
                                _chat_lines.append("用户：" + str(_e["user"])[:120])
                            if _e.get("assistant"):
                                _chat_lines.append("猫猫：" + str(_e["assistant"])[:120])
                        _chat_lines.append("")
                    logger.info(
                        f"[pending] chat_history: {len(_entries)} total, "
                        f"{len(_recent)} injected into prompt"
                    )
            except Exception as exc:
                logger.warning(f"[pending] chat_history read failed: {exc}")

            # 2. 初始语义召回一条鲜活记忆
            _mem_lines = []
            _first = self._recall_vivid_memory(" ".join(_query_parts[:5])) if _query_parts else None
            if _first:
                _mem_lines.append("- " + _first["what"] + "（感受：" + _first["affect_desc"] + "）")
            _query_preview = " ".join(_query_parts[:5])
            logger.info(
                f"[pending] initial recall: query='{_query_preview}' "
                f"found={'yes' if _first else 'no'}"
            )

            # 3. LLM loop：可反复 SEARCH 新关键词查记忆，直到想好要说的话（最多 3 轮）
            _persona = self._build_persona()
            _mood = self._current_mood()
            _NL = chr(10)
            content = None
            for _round in range(3):
                _mem_block = _NL.join(_mem_lines) if _mem_lines else "（暂无相关记忆）"
                _state_block = "；".join(_state_lines) if _state_lines else "（无特别在意的）"
                _chat_block = _NL.join(_chat_lines) + _NL if _chat_lines else ""
                _hint = pick.get("note", "")
                _hint_line = f"\n思路提示（可参考但不必局限）：{_hint}" if _hint else ""
                _system = (
                    _persona + "。此刻心情：" + _mood + "。"
                    "你要主动发起一个话题和用户聊天。"
                    "如果有相关记忆帮你想起具体内容，就基于它自然开口；"
                    "如果觉得记忆不够、想再回忆更多，回复一行：SEARCH: 关键词（只写关键词）；"
                    "如果已经想好，直接回复那句话（口语自然，30字以内，像真人随口开口）。"
                    + _hint_line
                )
                _user = (
                    _chat_block
                    + "当前状态：" + _NL + _state_block + _NL + _NL
                    + "相关记忆：" + _NL + _mem_block + _NL + _NL
                    + "现在主动开口吧——想聊什么？（需要更多回忆就回复 SEARCH: 关键词）"
                )
                logger.info(
                    f"[pending] LLM round {_round}: system={len(_system)}chars "
                    f"user={len(_user)}chars, "
                    f"state={_state_block[:80]}, memories={len(_mem_lines)} items"
                )
                try:
                    from main_brain.memory.llm import call_llm
                    reply = call_llm(_system, _user, timeout=20).strip()
                except Exception as e:
                    logger.warning(f"[pending] proactive LLM round {_round} failed: {e}")
                    break
                if reply.upper().startswith("SEARCH:"):
                    _kw = reply.split(":", 1)[1].strip().strip(chr(34)).strip(chr(39))
                    if _kw:
                        _more = self._recall_vivid_memory(_kw)
                        if _more:
                            _mem_lines.append("- " + _more["what"] + "（感受：" + _more["affect_desc"] + "）")
                        logger.info(f"[pending] round {_round} SEARCH: {_kw} -> {'found' if _more else 'none'}")
                    else:
                        logger.info(f"[pending] round {_round} SEARCH: empty keyword, skipped")
                    continue
                content = reply.strip().strip(chr(34)).strip(chr(39))
                logger.info(f"[pending] LLM round {_round} done: content={content[:80]}")
                break

            if not content:
                content = ("突然想起，" + _first["what"][:18] + "……") if _first else f"突然想到{_snid}……"
                logger.info(f"[pending] fallback content (LLM exhausted): {content[:60]}")
            content = content[:120]
            self._proactive_buffer.append({
                "content": content,
                "source": _trigger,
                "source_node_id": _snid,
            })
            self.mark_expressed(pick["id"])
            logger.info(f"[pending] proactive_send done: cached='{content[:60]}'")
            return content

    def flush_proactive_buffer(self) -> int:
        """空闲时将缓存中的主动消息写入 output.json。Returns: 写入条数。"""
        if not self._proactive_buffer:
            return 0
        entries = list(self._proactive_buffer)
        self._proactive_buffer.clear()
        written = 0
        for e in entries:
            try:
                c = e.get("content", "")
                self._write_to_output(c)
                written += 1
                logger.info(f"[pending] flush: written '{c[:60]}' (source={e.get('source','')})")
            except Exception as ex:
                logger.warning(f"[pending] flush failed: {ex}")
        if written:
            logger.info(f"[pending] flush complete: {written}/{len(entries)} written")
        return written

    # ── 查询 ──────────────────────────────────────────────

    def get_unexpressed(self) -> list[dict]:
        data = self._state.snapshot()
        return [p for p in data.get("pending_expressions", []) if not p.get("expressed")]
