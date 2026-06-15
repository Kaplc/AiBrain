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

from .store import get_state
from . import times

logger = logging.getLogger('state.pending')

PENDING_GENERATION_THRESHOLD = 0.15  # 表达分达到此值才入队
PENDING_QUEUE_CAP = 5
SEND_MIN_INTERVAL_HOURS = 1.0
AGE_GROWTH_PER_HOUR = 0.01           # age_score = min(1.0, hours×0.01)，100h 饱和


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

        # concern 路径
        cmap = get_concerns().concern_map()
        for node_id, eff in cmap.items():
            if eff <= 0:
                continue
            path, score = self._score_for_concern(node_id)
            if score < PENDING_GENERATION_THRESHOLD:
                continue
            if refractory.is_in_refractory("interest", node_id):
                continue
            if self._create(path, node_id, score, source="concern"):
                created += 1

        # open_loop 路径
        olm = get_open_loops()
        for loop in olm.get_open():
            tension = olm.tension(loop)
            if tension < PENDING_GENERATION_THRESHOLD:
                continue
            loop_id = loop.get("id", "")
            if refractory.is_in_refractory("open_loop", loop_id):
                continue
            if self._create("open_loop", loop_id, tension, source="open_loop"):
                created += 1

        if created:
            logger.info(f"[pending] generated {created} new pending entries")
        return created

    def _create(self, type_: str, source_node_id: str, expression_score: float,
                source: str) -> bool:
        """去重入队（cap 5，超限淘汰 expression_score 最低）。成功返回 True。"""
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
                    return False  # 已存在，未新增
            pendings.append({
                "id": f"pe_{times.now_iso().replace(':', '').replace('-', '').replace('+', '')}",
                "type": type_,
                "source_node_id": source_node_id,
                "expression_score": round(float(expression_score), 4),
                "source": source,
                "created_at": times.now_iso(),
                "expressed": False,
            })
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
        hours = times.hours_since(pending.get("created_at"))
        return min(1.0, hours * AGE_GROWTH_PER_HOUR)

    def _last_send_iso(self) -> str:
        """最近一次发送时间 = expression_history 中最大的 last_expressed。"""
        hist = self._state.snapshot().get("expression_history", [])
        vals = [h.get("last_expressed", "") for h in hist if h.get("last_expressed")]
        return max(vals) if vals else ""

    def pick_to_send(self) -> dict | None:
        """选出当前应发送的 pending，或 None。

        条件：未表达 ∧ 不在冷却 ∧ 距上次发送 > 1h。
        优先级 = expression_score + age_score × 0.5，取最高。
        """
        from . import get_expression_history
        refractory = get_expression_history()

        # 距上次发送 < 1h → 不发
        last = self._last_send_iso()
        if last and times.hours_since(last) < SEND_MIN_INTERVAL_HOURS:
            return None

        best = None
        best_pri = -1.0
        for p in self.get_unexpressed():
            rtype = "open_loop" if p.get("source") == "open_loop" else "interest"
            if refractory.is_in_refractory(rtype, p.get("source_node_id", "")):
                continue
            pri = float(p.get("expression_score", 0.0)) + self._age_score(p) * 0.5
            if pri > best_pri:
                best_pri = pri
                best = p
        return best

    def mark_expressed(self, pending_id: str, content: str | None = None) -> bool:
        """标记已表达 + 记录 refractory；若给 content 则写入 output（前端可见）。

        content 由调用方（send 决策）在发送时用 LLM 实时生成，本模块不生成。
        """
        from . import get_expression_history
        refractory = get_expression_history()
        with self._state.transaction() as data:
            target = None
            for p in data.get("pending_expressions", []):
                if p.get("id") == pending_id:
                    p["expressed"] = True
                    target = p
                    break
            if target is None:
                return False
            rtype = "open_loop" if target.get("source") == "open_loop" else "interest"
            refractory.record(rtype, target.get("source_node_id", ""))
        if content:
            self._write_to_output(content)
        logger.info(f"[pending] expressed {pending_id} (rtype={rtype})")
        return True

    def _write_to_output(self, content: str) -> None:
        """写入 workmemory output.json，作为猫猫的主动消息。"""
        try:
            from modules.brain.memory.workmemory import get_work_memory
            wm = get_work_memory()
            if wm:
                wm.output_mem_write(content=content)
        except Exception as e:
            logger.warning(f"[pending] write to output failed: {e}")

    # ── 查询 ──────────────────────────────────────────────

    def get_unexpressed(self) -> list[dict]:
        data = self._state.snapshot()
        return [p for p in data.get("pending_expressions", []) if not p.get("expressed")]
