"""Prompt 组合层单测 — PromptBlock / PromptContext / PromptComposition

覆盖 plan 第九章验收 F1/F2/F3/F4：
- F1 稳定主前缀：连续构造时 stable block 文本与指纹一致
- F2 独立上下文块：stable / dynamic 分离，每块有 name/order/source/fingerprint
- F3 块顺序固定：同样输入 → 同样的 block 顺序与数量
- F4 provider 兼容：OpenAI 多 system block / Anthropic 确定性合并
"""
import os
import sys
import unittest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from modules.chat.pipeline.composition import PromptBlock, PromptComposition
from modules.chat.pipeline.context import PromptContext


def _build_composition(persona="You are a cat."):
    """构造一个固定结构的 composition：1 stable + 2 dynamic + 历史 + user"""
    ctx = PromptContext(user_message="hello", system_persona=persona)
    ctx.add_stable("subconscious", persona + "\nRULE", title="subconscious")
    ctx.add_block("self_narrative", "mood: happy", title="self")
    ctx.add_block("brain_context", "thought: x", title="brain")

    comp = PromptComposition()
    comp.stable_blocks = list(ctx.stable_blocks)
    comp.dynamic_blocks = list(ctx.dynamic_blocks)
    comp.history_messages = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "yo"},
    ]
    comp.tool_memory_messages = []
    comp.user_message = "[2026-06-22 10:00] hello"
    return comp


class TestPromptBlock(unittest.TestCase):
    def test_fingerprint_deterministic(self):
        a = PromptBlock(name="x", content="abc")
        b = PromptBlock(name="x", content="abc")
        self.assertEqual(a.fingerprint, b.fingerprint)
        self.assertTrue(a.fingerprint)

    def test_fingerprint_differs_on_content(self):
        a = PromptBlock(name="x", content="abc")
        b = PromptBlock(name="x", content="abd")
        self.assertNotEqual(a.fingerprint, b.fingerprint)

    def test_empty_content_fingerprint_blank(self):
        self.assertEqual(PromptBlock(name="x", content="").fingerprint, "")

    def test_explicit_fingerprint_kept(self):
        b = PromptBlock(name="x", content="abc", fingerprint="CUSTOM")
        self.assertEqual(b.fingerprint, "CUSTOM")


class TestPromptContext(unittest.TestCase):
    def test_add_stable_marks_stable(self):
        ctx = PromptContext(system_persona="p")
        ctx.add_stable("subconscious", "body", title="subconscious")
        self.assertEqual(len(ctx.stable_blocks), 1)
        self.assertEqual(len(ctx.dynamic_blocks), 0)
        b = ctx.stable_blocks[0]
        self.assertTrue(b.stable)
        self.assertEqual(b.name, "subconscious")
        self.assertIn("【subconscious】", b.content)

    def test_add_block_marks_dynamic(self):
        ctx = PromptContext()
        ctx.add_block("brain_context", "body", title="brain")
        self.assertEqual(len(ctx.dynamic_blocks), 1)
        self.assertEqual(len(ctx.stable_blocks), 0)
        self.assertFalse(ctx.dynamic_blocks[0].stable)

    def test_empty_content_skipped(self):
        ctx = PromptContext()
        ctx.add_stable("x", "")
        ctx.add_block("y", "")
        self.assertEqual(ctx.stable_blocks, [])
        self.assertEqual(ctx.dynamic_blocks, [])

    def test_order_monotonic(self):
        ctx = PromptContext()
        ctx.add_stable("a", "1")
        ctx.add_block("b", "2")
        ctx.add_block("c", "3")
        orders = [ctx.stable_blocks[0].order,
                  ctx.dynamic_blocks[0].order,
                  ctx.dynamic_blocks[1].order]
        self.assertEqual(orders, sorted(orders))
        self.assertEqual(len(set(orders)), 3)


class TestRenderOpenAI(unittest.TestCase):
    """F4: OpenAI-compatible 保留多个独立 system block，顺序固定"""

    def test_order_stable_history_dynamic_user(self):
        comp = _build_composition()
        msgs = comp.render("openai")
        roles = [m["role"] for m in msgs]
        # stable system → user,assistant(history) → dynamic system → user
        self.assertEqual(roles, ["system", "user", "assistant", "system", "system", "user"])

    def test_multiple_system_blocks_preserved(self):
        comp = _build_composition()
        msgs = comp.render("openai")
        system_blocks = [m for m in msgs if m["role"] == "system"]
        self.assertEqual(len(system_blocks), 3)  # 1 stable + 2 dynamic
        # 第一个必须是稳定块
        self.assertEqual(system_blocks[0], {
            "role": "system", "content": comp.stable_blocks[0].content})

    def test_tool_memory_inserted_before_dynamic(self):
        comp = _build_composition()
        comp.tool_memory_messages = [{"role": "tool", "content": "r"}]
        msgs = comp.render("openai")
        roles = [m["role"] for m in msgs]
        # tool memory 位于 history 之后、dynamic system 之前
        self.assertEqual(roles, ["system", "user", "assistant", "tool", "system", "system", "user"])


class TestRenderAnthropic(unittest.TestCase):
    """F4: Anthropic 确定性合并所有 system 块到顶部"""

    def test_system_blocks_collapsed_into_one(self):
        comp = _build_composition()
        msgs = comp.render("anthropic")
        roles = [m["role"] for m in msgs]
        self.assertEqual(roles, ["system", "user", "assistant", "user"])
        # 合并后的 system 包含 stable + 两个 dynamic 的内容
        sys_text = msgs[0]["content"]
        self.assertIn(comp.stable_blocks[0].content, sys_text)
        self.assertIn(comp.dynamic_blocks[0].content, sys_text)
        self.assertIn(comp.dynamic_blocks[1].content, sys_text)

    def test_no_system_when_empty(self):
        comp = PromptComposition()
        comp.user_message = "hi"
        msgs = comp.render("anthropic")
        self.assertEqual([m["role"] for m in msgs], ["user"])


class TestStabilityAcrossBuilds(unittest.TestCase):
    """F1/F3: 同样输入 → stable 文本一致、dynamic 顺序一致"""

    def test_stable_identical_across_builds(self):
        a = _build_composition(persona="P1")
        b = _build_composition(persona="P1")
        self.assertEqual(a.stable_blocks[0].content, b.stable_blocks[0].content)
        self.assertEqual(a.stable_blocks[0].fingerprint, b.stable_blocks[0].fingerprint)

    def test_dynamic_order_stable(self):
        a = _build_composition()
        b = _build_composition()
        self.assertEqual([x.name for x in a.dynamic_blocks],
                         [x.name for x in b.dynamic_blocks])

    def test_persona_change_breaks_stable(self):
        a = _build_composition(persona="P1")
        b = _build_composition(persona="P2")
        self.assertNotEqual(a.stable_blocks[0].fingerprint, b.stable_blocks[0].fingerprint)


class TestPipelineIntegration(unittest.TestCase):
    """真实 PromptPipeline.build：subconscious 为唯一稳定块且跨轮一致"""

    def _build(self, persona="You are a cat."):
        from modules.chat.pipeline import PromptPipeline
        from modules.chat.pipeline.context import PromptContext
        pipe = PromptPipeline.get_instance()
        # 确保已注册（init_pipeline 幂等）
        try:
            from modules.chat.pipeline import init_pipeline
            init_pipeline()
        except Exception:
            pass
        return pipe.build(PromptContext(user_message="hi", system_persona=persona))

    def test_subconscious_is_only_stable_block(self):
        comp = self._build()
        # 恰好一个稳定块（init_pipeline 必须幂等，否则会重复注册出多个 subconscious）
        self.assertEqual(len(comp.stable_blocks), 1)
        self.assertEqual(comp.stable_blocks[0].name, "subconscious")
        self.assertTrue(comp.stable_blocks[0].stable)
        # 没有动态块被误放进 stable
        for b in comp.stable_blocks:
            self.assertTrue(b.stable)

    def test_subconscious_stable_across_builds(self):
        a = self._build()
        b = self._build()
        self.assertEqual(a.stable_blocks[0].content, b.stable_blocks[0].content)
        self.assertEqual(a.stable_blocks[0].fingerprint, b.stable_blocks[0].fingerprint)


class TestInitPipelineIdempotent(unittest.TestCase):
    """init_pipeline() 幂等：多次调用不重复注册、build 不产出重复块"""

    def test_order_does_not_grow_on_reinit(self):
        from modules.chat.pipeline import init_pipeline, PromptPipeline
        pipe = PromptPipeline.get_instance()
        init_pipeline()
        n1 = len(pipe.get_order())
        init_pipeline()
        init_pipeline()
        n2 = len(pipe.get_order())
        self.assertEqual(n1, n2, "init_pipeline() must be idempotent")

    def test_build_no_duplicate_blocks_after_reinit(self):
        from modules.chat.pipeline import init_pipeline, PromptPipeline
        from modules.chat.pipeline.context import PromptContext
        init_pipeline(); init_pipeline(); init_pipeline()
        comp = PromptPipeline.get_instance().build(
            PromptContext(user_message="hi", system_persona="cat"))
        stable_names = [b.name for b in comp.stable_blocks]
        self.assertEqual(stable_names, ["subconscious"], "no duplicate stable blocks")
        # 动态块同样不应出现同名重复
        dyn_names = [b.name for b in comp.dynamic_blocks]
        self.assertEqual(len(dyn_names), len(set(dyn_names)), "no duplicate dynamic blocks")

    def test_build_self_heals_empty_pipeline(self):
        """_order 被清空（预热未完成）时 build 应懒 init，恢复稳定前缀"""
        from modules.chat.pipeline import PromptPipeline, init_pipeline
        from modules.chat.pipeline.context import PromptContext
        init_pipeline()  # 先确保注册过一次
        pipe = PromptPipeline.get_instance()
        pipe._order.clear()
        pipe._sections.clear()
        comp = pipe.build(PromptContext(user_message="hi", system_persona="cat"))
        self.assertEqual([b.name for b in comp.stable_blocks], ["subconscious"])
        self.assertGreater(len(pipe.get_order()), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
