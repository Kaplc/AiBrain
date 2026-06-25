"""程序记忆系统回放测试和最小集成测试（T011）

测试覆盖：
  1. 合约数据类正确序列化/反序列化
  2. Store 的 CRUD 操作
  3. 采集器从模拟运行数据提取样本
  4. 矿工从样本提炼模板
  5. 匹配器在上下文中找到最佳模板
  6. 反馈更新模板统计
  7. 生命周期管理
  8. 导出器条件检查
  9. 端到端流水线
"""

import json
import os
import tempfile
import unittest
from unittest import mock
from datetime import datetime

from main_brain.procedural_memory.contracts import (
    ProcedureTemplate, ProcedureExample, ProcedureMatch,
    ProcedureFeedback, ProcedureState, TEMPLATE_STATUS, RISK_LEVELS,
)
from main_brain.contracts import BrainRun, BrainRunContext
from main_brain.memory.procedural.store import ProcedureStore
from main_brain.memory.procedural.index import ProcedureIndex
from main_brain.memory.procedural.decay import apply_decay, check_feedback_decay
from main_brain.procedural_memory.collector import _build_example, _classify_outcome, _fetch_recent_runs
from main_brain.procedural_memory.miner import mine_procedure_templates, _build_signature, _action_sequence_sig
from main_brain.procedural_memory.matcher import match_procedure_templates, _preconditions_met
from main_brain.procedural_memory.feedback import record_procedure_feedback, promote_template, retire_template
from main_brain.procedural_memory.exporter import _check_export_eligibility
from main_brain.procedural_memory.scheduler import run_mining


# ── 测试辅助 ─────────────────────────────────────────────

def _make_example(seq: int = 0, activity: str = "reflect", outcome: str = "success",
                  mode: str = "background", tick_type: str = "medium_tick") -> ProcedureExample:
    return ProcedureExample(
        example_id=f"test_ex_{seq}",
        run_id=f"test_run_{seq}",
        mode=mode,
        tick_type=tick_type,
        context_digest={
            "activity": activity,
            "stop_reason": "ready" if outcome == "success" else "sleep",
            "cycle_count": 3,
        },
        action_sequence=[
            {"action": "recall_memory", "focus": "find relevant context", "confidence": 0.9},
            {"action": "update_state", "focus": "update current_focus", "confidence": 0.8},
            {"action": "final_reply", "focus": "summarize findings", "confidence": 0.95},
        ],
        outcome=outcome,
        reward=1.0 if outcome == "success" else 0.3,
        source_refs=[f"brain_runs:test_run_{seq}"],
    )


def _make_run_record(run_id: str = "bg_test_001", mode: str = "background",
                      activity: str = "reflect", stop_reason: str = "ready",
                      tick_type: str = "medium_tick") -> dict:
    return {
        "run_id": run_id,
        "mode": mode,
        "trigger": {"tick_type": tick_type},
        "started_at": "2026-06-24T10:00:00Z",
        "finished_at": "2026-06-24T10:00:05Z",
        "selected_activity": activity,
        "cycle_count": 3,
        "cycles": [
            {"action": "recall_memory", "focus": "find context", "confidence": 0.9,
             "thought_summary": "need to recall", "action_args": {}, "error": ""},
            {"action": "update_state", "focus": "update current_focus", "confidence": 0.8,
             "thought_summary": "update focus", "action_args": {}, "error": ""},
            {"action": "final_reply", "focus": "summarize", "confidence": 0.95,
             "thought_summary": "done", "action_args": {}, "error": ""},
        ],
        "actions": ["recall_memory", "update_state", "final_reply"],
        "stop_reason": stop_reason,
        "last_error": "",
    }


# ── 测试用例 ─────────────────────────────────────────────

class TestContracts(unittest.TestCase):
    """合约序列化/反序列化"""

    def test_template_roundtrip(self):
        t = ProcedureTemplate(template_id="proc_test_001", name="test", intent="test")
        d = t.to_dict()
        self.assertEqual(d["template_id"], "proc_test_001")
        t2 = ProcedureTemplate.from_dict(d)
        self.assertEqual(t2.template_id, t.template_id)
        self.assertEqual(t2.name, t.name)

    def test_example_roundtrip(self):
        e = _make_example(1)
        d = e.to_dict()
        self.assertEqual(d["example_id"], "test_ex_1")
        e2 = ProcedureExample.from_dict(d)
        self.assertEqual(e2.run_id, e.run_id)

    def test_state_defaults(self):
        s = ProcedureState()
        self.assertEqual(s.policy_version, "1.0")
        self.assertEqual(s.active_count, 0)

    def test_match_defaults(self):
        m = ProcedureMatch(match_id="m1", template_id="t1")
        self.assertEqual(m.score, 0.0)
        self.assertEqual(m.step_preview, [])

    def test_judge_view_includes_procedure_matches(self):
        run = BrainRun(run_id="run_view", mode="background")
        ctx = BrainRunContext(run=run, life_state={})
        ctx.procedure_matches = [
            {
                "template_id": "proc_view",
                "score": 0.88,
                "context_fit": 0.9,
                "success_fit": 0.8,
                "reason": "上下文高度匹配",
                "action_hint": "reflect",
                "step_preview": ["recall_memory", "update_state"],
            }
        ]
        view = ctx.to_judge_view()
        self.assertIn("procedure_matches", view)
        self.assertEqual(view["procedure_matches"][0]["template_id"], "proc_view")


class TestStore(unittest.TestCase):
    """存储层 CRUD"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.store = ProcedureStore(data_dir=self.tmpdir)

    def test_save_and_load(self):
        t = ProcedureTemplate(template_id="t1", name="test", intent="test")
        self.store.save_template(t)
        loaded = self.store.get_template("t1")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.name, "test")

    def test_persist_across_instances(self):
        t = ProcedureTemplate(template_id="t_persist", name="persist", intent="test")
        self.store.save_template(t)

        store2 = ProcedureStore(data_dir=self.tmpdir)
        store2.load()
        loaded = store2.get_template("t_persist")
        self.assertIsNotNone(loaded)

    def test_archive_template(self):
        t = ProcedureTemplate(template_id="t_archive", name="arch", intent="test")
        self.store.save_template(t)
        self.store.archive_template(t)

        self.assertIsNone(self.store.get_template("t_archive"))
        archive = self.store.get_archive()
        self.assertTrue(any(a["template_id"] == "t_archive" for a in archive))

    def test_append_examples(self):
        ex = _make_example(1)
        self.store.append_example(ex)
        all_ex = self.store.get_all_examples()
        self.assertEqual(len(all_ex), 1)

    def test_state_persistence(self):
        self.store.update_state(last_mined_run_id="run_abc", active_count=5)
        state = self.store.get_state()
        self.assertEqual(state.last_mined_run_id, "run_abc")
        self.assertEqual(state.active_count, 5)

    def test_counts(self):
        statuses = ["active", "active", "draft", "proposed", "active"]
        for i, s in enumerate(statuses):
            t = ProcedureTemplate(template_id=f"t_counts_{i}_{s}", name=s,
                                  intent="test", status=s)
            self.store.save_template(t)
        counts = self.store.get_counts()
        self.assertEqual(counts["active"], 3)
        self.assertEqual(counts["draft"], 1)


class TestIndex(unittest.TestCase):
    """内存索引"""

    def setUp(self):
        self.index = ProcedureIndex()
        self.templates = [
            ProcedureTemplate(template_id="t1", name="a", intent="x",
                              status="active", risk_level="low", reward_ema=0.8,
                              tags=["reflect"], confidence=0.9),
            ProcedureTemplate(template_id="t2", name="b", intent="y",
                              status="proposed", risk_level="medium", reward_ema=0.5,
                              tags=["reflect"], confidence=0.6),
            ProcedureTemplate(template_id="t3", name="c", intent="z",
                              status="draft", risk_level="high", reward_ema=0.2,
                              tags=["tool"], confidence=0.3),
        ]
        self.index.refresh(self.templates)

    def test_by_status(self):
        active = self.index.by_status("active")
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0].template_id, "t1")

    def test_by_risk(self):
        low = self.index.by_risk("low")
        self.assertEqual(len(low), 1)

    def test_by_tag(self):
        reflect = self.index.by_tag("reflect")
        self.assertEqual(len(reflect), 2)

    def test_all_valid(self):
        valid = self.index.all_valid()
        self.assertEqual(len(valid), 2)  # active + proposed

    def test_top_score(self):
        top = self.index.top_score(2)
        self.assertEqual(len(top), 2)
        self.assertEqual(top[0].template_id, "t1")  # highest reward_ema

    def test_status_counts(self):
        counts = self.index.status_counts()
        self.assertEqual(counts.get("active", 0), 1)


class TestCollector(unittest.TestCase):
    """采集器"""

    def test_classify_outcome(self):
        self.assertEqual(_classify_outcome("ready"), ("success", 1.0))
        self.assertEqual(_classify_outcome("completed"), ("success", 1.0))
        self.assertEqual(_classify_outcome("sleep"), ("partial", 0.5))
        self.assertEqual(_classify_outcome("abort"), ("fail", 0.0))
        self.assertEqual(_classify_outcome("unknown"), ("unknown", 0.3))

    def test_build_example_success(self):
        run = _make_run_record("bg_test_001", stop_reason="ready")
        ex = _build_example(run)
        self.assertIsNotNone(ex)
        self.assertEqual(ex.outcome, "success")
        self.assertEqual(ex.mode, "background")
        self.assertEqual(len(ex.action_sequence), 3)

    def test_build_example_fail(self):
        run = _make_run_record("bg_test_002", stop_reason="abort")
        ex = _build_example(run)
        self.assertIsNotNone(ex)
        self.assertEqual(ex.outcome, "fail")

    def test_build_example_empty_cycles(self):
        run = _make_run_record("bg_test_003")
        run["cycles"] = []
        ex = _build_example(run)
        self.assertIsNone(ex)

    def test_build_example_skip_wait_sleep(self):
        """纯 wait/sleep 运行不生成样本"""
        run = _make_run_record("bg_test_004")
        run["cycles"] = [
            {"action": "wait", "focus": "", "confidence": 1.0},
            {"action": "sleep", "focus": "", "confidence": 1.0},
        ]
        ex = _build_example(run)
        self.assertIsNone(ex)

    def test_fetch_recent_runs_after_checkpoint(self):
        tmp = tempfile.mkdtemp()
        log_path = os.path.join(tmp, "brain_runs.jsonl")
        records = [
            _make_run_record("bg_run_001"),
            _make_run_record("bg_run_002"),
            _make_run_record("bg_run_003"),
        ]
        with open(log_path, "w", encoding="utf-8") as f:
            for rec in records:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

        with mock.patch("main_brain.procedural_memory.collector._LOG_PATH", log_path):
            runs = _fetch_recent_runs(10, after_run_id="bg_run_002")

        self.assertEqual([r["run_id"] for r in runs], ["bg_run_003"])


class TestMiner(unittest.TestCase):
    """模式提炼器"""

    def test_mine_empty(self):
        templates = mine_procedure_templates([])
        self.assertEqual(len(templates), 0)

    def test_mine_insufficient(self):
        # 只有 2 个样本（默认 min_support=3），不应出模板
        examples = [_make_example(i) for i in range(2)]
        templates = mine_procedure_templates(examples, min_support=3)
        self.assertEqual(len(templates), 0)

    def test_mine_sufficient(self):
        examples = [_make_example(i) for i in range(5)]
        templates = mine_procedure_templates(examples, min_support=3)
        self.assertGreater(len(templates), 0)

    def test_mine_signature_consistency(self):
        """同 activity 同 action 序列应产生相同签名"""
        ex1 = _make_example(1, activity="reflect")
        ex2 = _make_example(2, activity="reflect")
        sig1 = _build_signature(ex1)
        sig2 = _build_signature(ex2)
        self.assertEqual(sig1, sig2)

    def test_mine_signature_different_activity(self):
        """不同 activity 应产生不同签名"""
        ex1 = _make_example(1, activity="reflect")
        ex2 = _make_example(2, activity="proactive_contact")
        sig1 = _build_signature(ex1)
        sig2 = _build_signature(ex2)
        self.assertNotEqual(sig1, sig2)

    def test_action_sequence_sig(self):
        sig = _action_sequence_sig([
            {"action": "recall_memory"},
            {"action": "wait"},
            {"action": "update_state"},
            {"action": "sleep"},
            {"action": "final_reply"},
        ])
        self.assertNotIn("wait", sig)
        self.assertNotIn("sleep", sig)
        self.assertIn("final_reply", sig)

    def test_mine_cap_respected(self):
        examples = [_make_example(i) for i in range(10)]
        templates = mine_procedure_templates(examples, min_support=3, max_templates=1, existing_count=0)
        self.assertLessEqual(len(templates), 1)

    def test_mine_min_success_rate(self):
        examples = [_make_example(i, outcome="fail") for i in range(5)]
        templates = mine_procedure_templates(examples, min_support=3, min_success_rate=0.7)
        self.assertEqual(len(templates), 0)


class TestMatcher(unittest.TestCase):
    """上下文匹配器"""

    def setUp(self):
        self.templates = [
            ProcedureTemplate(
                template_id="proc_reflect",
                name="bg_reflect",
                intent="background reflect",
                status="active",
                risk_level="low",
                confidence=0.85,
                success_count=10,
                failure_count=1,
                reward_ema=0.8,
                preconditions=["activity:reflect", "tick_type:medium_tick"],
                trigger_signals={"mode": "background", "activity": "reflect", "tick_types": ["medium_tick"]},
                steps=[{"action": "recall_memory"}, {"action": "update_state"}],
                tags=["reflect", "background"],
            ),
            ProcedureTemplate(
                template_id="proc_tool",
                name="bg_tool",
                intent="background tool use",
                status="active",
                risk_level="high",
                confidence=0.7,
                success_count=5,
                failure_count=3,
                reward_ema=0.4,
                preconditions=["activity:use_tool"],
                trigger_signals={"mode": "background", "activity": "use_tool", "tick_types": ["long_tick"]},
                steps=[{"action": "use_tool"}, {"action": "recall_memory"}],
                tags=["tool", "background"],
            ),
        ]

    def test_match_returns_top_k(self):
        context = {"mode": "background", "tick_type": "medium_tick",
                   "activity": "reflect"}
        matches = match_procedure_templates(context, templates=self.templates, top_k=3)
        self.assertGreater(len(matches), 0)
        self.assertLessEqual(len(matches), 3)

    def test_match_orders_by_score(self):
        context = {"mode": "background", "tick_type": "medium_tick",
                   "activity": "reflect"}
        matches = match_procedure_templates(context, templates=self.templates, top_k=3)
        if len(matches) >= 2:
            self.assertGreaterEqual(matches[0]["score"], matches[1]["score"])

    def test_match_preconditions_filter(self):
        context = {"mode": "background", "tick_type": "long_tick",
                   "activity": "organize_memory"}
        matches = match_procedure_templates(context, templates=self.templates, top_k=3)
        # "organize_memory" 不匹配任何模板的前置条件
        for m in matches:
            self.assertIn(m["template_id"], ("proc_tool",))

    def test_match_empty_context(self):
        matches = match_procedure_templates({}, templates=self.templates, top_k=3)
        self.assertIsInstance(matches, list)

    def test_preconditions_met(self):
        t = ProcedureTemplate(template_id="t", name="t", intent="t",
                              preconditions=["activity:reflect"])
        self.assertTrue(_preconditions_met(t, {"activity": "reflect"}))
        self.assertFalse(_preconditions_met(t, {"activity": "wait"}))

    def test_match_deprecated_excluded(self):
        t_dep = ProcedureTemplate(
            template_id="proc_dep", name="dep", intent="dep",
            status="deprecated", risk_level="low", preconditions=[],
            trigger_signals={"mode": "background", "activity": "reflect", "tick_types": []},
            steps=[], tags=[], confidence=0.0, success_count=0, failure_count=0, reward_ema=0.0,
        )
        context = {"mode": "background", "activity": "reflect"}
        matches = match_procedure_templates(context, templates=[t_dep], top_k=3)
        self.assertEqual(len(matches), 0)

    def test_match_min_score_filter(self):
        context = {"mode": "background", "activity": "reflect", "tick_type": "medium_tick"}
        matches = match_procedure_templates(context, templates=self.templates,
                                            top_k=3, min_score=0.3)
        self.assertGreater(len(matches), 0)

    def test_match_min_score_blocks_low_quality_matches(self):
        context = {"mode": "background", "activity": "reflect", "tick_type": "medium_tick"}
        matches = match_procedure_templates(context, templates=self.templates,
                                            top_k=3, min_score=0.95)
        self.assertEqual(matches, [])


class TestFeedback(unittest.TestCase):
    """反馈更新"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.store = ProcedureStore(data_dir=self.tmpdir)
        self.template = ProcedureTemplate(
            template_id="proc_fb_test", name="test", intent="test",
            status="active", confidence=0.5, success_count=5,
            failure_count=1, reward_ema=0.6,
        )
        self.store.save_template(self.template)

    def _patch_store(self):
        """mock get_procedure_store() to return test store"""
        patcher = mock.patch(
            "main_brain.procedural_memory.feedback.get_procedure_store",
            return_value=self.store,
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def _get(self):
        return self.store.get_template("proc_fb_test")

    def test_record_success(self):
        self._patch_store()
        record_procedure_feedback("proc_fb_test", "run_001", "success", 0.2)
        updated = self._get()
        self.assertGreater(updated.success_count, 5)
        self.assertGreater(updated.reward_ema, 0.55)

    def test_record_fail(self):
        self._patch_store()
        record_procedure_feedback("proc_fb_test", "run_002", "fail", -0.3)
        updated = self._get()
        self.assertGreater(updated.failure_count, 1)
        self.assertLess(updated.reward_ema, 0.6)

    def test_promote_template(self):
        self._patch_store()
        t = ProcedureTemplate(template_id="proc_prom", name="p", intent="p",
                              status="proposed", confidence=0.3)
        self.store.save_template(t)
        result = promote_template("proc_prom")
        self.assertTrue(result["ok"])
        self.assertEqual(self.store.get_template("proc_prom").status, "active")

    def test_retire_to_deprecated(self):
        self._patch_store()
        result = retire_template("proc_fb_test")
        self.assertTrue(result["ok"])
        self.assertEqual(self.store.get_template("proc_fb_test").status, "deprecated")

    def test_retire_to_archive(self):
        self._patch_store()
        retire_template("proc_fb_test")
        result = retire_template("proc_fb_test", reason="archive")
        self.assertTrue(result["ok"])
        self.assertIsNone(self.store.get_template("proc_fb_test"))

    def test_feedback_unknown_template(self):
        self._patch_store()
        result = record_procedure_feedback("nonexistent", "run_x", "success", 0.1)
        self.assertFalse(result["ok"])


class TestLifecycle(unittest.TestCase):
    """生命周期管理"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.store = ProcedureStore(data_dir=self.tmpdir)

    def test_high_failure_rate_deprecates(self):
        t = ProcedureTemplate(
            template_id="proc_fail", name="fail", intent="fail",
            status="active", confidence=0.8, success_count=2,
            failure_count=8, reward_ema=0.3,
        )
        self.store.save_template(t)
        check_feedback_decay(self.store, "proc_fail")
        updated = self.store.get_template("proc_fail")
        self.assertEqual(updated.status, "deprecated")

    def test_decay_old_templates(self):
        t = ProcedureTemplate(
            template_id="proc_old", name="old", intent="old",
            status="active", confidence=0.8, last_used_at="2020-01-01T00:00:00Z",
        )
        self.store.save_template(t)
        apply_decay(self.store, now="2026-06-24T00:00:00Z")
        updated = self.store.get_template("proc_old")
        self.assertLess(updated.confidence, 0.8)

    def test_decay_to_deprecated(self):
        t = ProcedureTemplate(
            template_id="proc_very_old", name="vo", intent="vo",
            status="active", confidence=0.4, last_used_at="2020-01-01T00:00:00Z",
        )
        self.store.save_template(t)
        apply_decay(self.store, now="2026-06-24T00:00:00Z")
        updated = self.store.get_template("proc_very_old")
        self.assertEqual(updated.status, "deprecated")


class TestExporter(unittest.TestCase):
    """导出器"""

    def test_eligible_checks_pass(self):
        t = ProcedureTemplate(
            template_id="proc_exp", name="exp", intent="exp",
            status="active", confidence=0.8, risk_level="low",
            source_example_ids=[f"ex_{i}" for i in range(7)],
        )
        result = _check_export_eligibility(t)
        self.assertTrue(result["eligible"])

    def test_eligible_checks_fail_confidence(self):
        t = ProcedureTemplate(
            template_id="proc_exp2", name="exp2", intent="exp2",
            status="active", confidence=0.3, risk_level="low",
            source_example_ids=[f"ex_{i}" for i in range(7)],
        )
        result = _check_export_eligibility(t)
        self.assertFalse(result["eligible"])

    def test_eligible_checks_fail_risk(self):
        t = ProcedureTemplate(
            template_id="proc_exp3", name="exp3", intent="exp3",
            status="active", confidence=0.8, risk_level="high",
            source_example_ids=[f"ex_{i}" for i in range(7)],
        )
        result = _check_export_eligibility(t)
        self.assertFalse(result["eligible"])

    def test_eligible_checks_fail_status(self):
        t = ProcedureTemplate(
            template_id="proc_exp4", name="exp4", intent="exp4",
            status="draft", confidence=0.8, risk_level="low",
            source_example_ids=[f"ex_{i}" for i in range(7)],
        )
        result = _check_export_eligibility(t)
        self.assertFalse(result["eligible"])

    def test_eligible_checks_fail_examples(self):
        t = ProcedureTemplate(
            template_id="proc_exp5", name="exp5", intent="exp5",
            status="active", confidence=0.8, risk_level="low",
            source_example_ids=["ex_0", "ex_1"],
        )
        result = _check_export_eligibility(t)
        self.assertFalse(result["eligible"])


class TestEndToEnd(unittest.TestCase):
    """端到端流水线"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.store = ProcedureStore(data_dir=self.tmpdir)

        # 批量注入模拟运行数据
        examples = []
        for i in range(7):
            ex = _make_example(i, activity="reflect", outcome="success")
            examples.append(ex)
        self.store.append_examples(examples)

    def test_collect_mine_match_cycle(self):
        # patch store for feedback calls
        patcher = mock.patch(
            "main_brain.procedural_memory.feedback.get_procedure_store",
            return_value=self.store,
        )
        patcher.start()
        self.addCleanup(patcher.stop)

        # 1. 用已有的样本提炼模板
        all_examples = self.store.get_all_examples()
        self.assertGreater(len(all_examples), 0)

        templates = mine_procedure_templates(all_examples, min_support=3)
        self.assertGreater(len(templates), 0)

        # 2. 保存模板并提升为 active（匹配器只匹配 proposed/active/cooling）
        for t in templates:
            t.status = "active"
        self.store.save_templates(templates)
        saved = self.store.get_template(templates[0].template_id)
        self.assertIsNotNone(saved)

        # 3. 匹配
        context = {"mode": "background", "tick_type": "medium_tick",
                   "activity": "reflect"}
        matches = match_procedure_templates(context, templates=templates, top_k=3)
        self.assertGreater(len(matches), 0)

        # 4. 反馈
        fb_result = record_procedure_feedback(
            template_id=templates[0].template_id,
            run_id="test_e2e_run",
            result="success",
            reward_delta=0.3,
        )
        self.assertTrue(fb_result["ok"])

        # 5. 验证更新
        updated = self.store.get_template(templates[0].template_id)
        self.assertIsNotNone(updated)
        self.assertGreater(updated.success_count, 0)


class TestScheduler(unittest.TestCase):
    """矿化调度器"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.store = ProcedureStore(data_dir=self.tmpdir)

    def test_run_mining_passes_checkpoint(self):
        with mock.patch("main_brain.procedural_memory.scheduler.get_procedure_store", return_value=self.store), \
             mock.patch("main_brain.procedural_memory.scheduler.get_last_processed_run_id", return_value="bg_run_002"), \
             mock.patch("main_brain.procedural_memory.scheduler.collect_procedure_examples", return_value=[]) as collect:
            result = run_mining(window=12, dry_run=True)

        collect.assert_called_once_with(window=12, modes=None, min_cycles=1, after_run_id="bg_run_002")
        self.assertTrue(result["ok"])


if __name__ == "__main__":
    unittest.main()
