""" /chat/send 路由级回归测试

锁死 plan 第九章 F4/F6：
- 多 system block（稳定前缀 + 动态上下文）能通过 /chat/send 完整送到 LLM
- SSE 事件序列（start / token / token_estimate / usage / done）与前端契约兼容
- brain_context 路径不阻断主链路（session 关闭时正常出答）
- 缺 api_key → 503，空消息 → 400

做法：真实 ChatManager + 真实 loop.send_message + 真实 PromptPipeline，
只 mock LLM 调用 / 工作记忆 / 压缩 / 设置 / brain config，捕获送给 LLM 的 msgs 做断言。
"""
import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)


def _parse_sse_types(raw: str) -> list[dict]:
    """从 SSE 原始文本里提取所有 data: {...} 的 JSON"""
    events = []
    for block in raw.split("\n\n"):
        block = block.strip()
        if block.startswith("data:"):
            try:
                events.append(json.loads(block[len("data:"):].strip()))
            except json.JSONDecodeError:
                pass
    return events


class TestChatSendSSE(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from flask import Flask
        from routes.chat_routes import register as reg_chat
        from modules.chat import ChatManager
        import logging
        cls.app = Flask(__name__)
        cls.app.testing = True
        reg_chat(cls.app, {}, logging.getLogger("test_chat"), MagicMock())
        # 真实 ChatManager 单例需要 load_config 才有 _system_persona 等属性
        ChatManager.get_instance().load_config({
            "provider": "openai", "model": "gpt-4o-mini", "api_key": "test-key",
            "base_url": "", "tools_enabled": False, "system_persona": "你是一只猫。",
        })

    def _patches(self, captured: dict):
        """返回 (patchers, client)。client 已注入所有 mock。"""
        # LLM：捕获 msgs，返回一段 token + usage
        def fake_stream(msgs, cfg):
            captured["msgs"] = msgs
            return iter([
                {"content": "你好", "usage": None, "finish_reason": None},
                {"content": "", "usage": {
                    "prompt_tokens": 42, "completion_tokens": 3,
                    "cache_hit_tokens": 0, "cache_miss_tokens": 0,
                }, "finish_reason": "stop"},
            ])

        mock_llm = MagicMock()
        mock_llm.stream_messages.side_effect = fake_stream

        # 工作记忆：空记忆，不落盘
        wm = MagicMock()
        wm.output_mem_read.return_value = []
        wm.get_workmem.return_value = {}
        wm.handle_packagemem.return_value = None
        wm.output_mem_write.return_value = None

        # 设置：带 api_key
        cfg_mgr = MagicMock()
        cfg_mgr.read_llm.return_value = {
            "api_key": "test-key", "provider": "openai", "model": "gpt-4o-mini",
        }

        # brain config：关闭 session，跳过 reactive
        brain_cfg = MagicMock()
        brain_cfg.session_enabled = False

        patchers = [
            patch("modules.chat.loop.get_llm_manager", return_value=mock_llm),
            patch("modules.brain.memory.workmemory.get_work_memory", return_value=wm),
            patch("core.settings.ConfigManager.get_instance", return_value=cfg_mgr),
            patch("main_brain.config.get_brain_config", return_value=brain_cfg),
        ]
        return patchers

    def test_blocks_reach_llm_and_sse_events(self):
        """完整链路：多 system block 送到 LLM + SSE 事件序列正确"""
        import modules.chat.loop as loop
        loop._conversation_history.clear()

        captured: dict = {}
        patchers = self._patches(captured)
        for p in patchers:
            p.start()
        try:
            with self.app.test_client() as client:
                resp = client.post("/chat/send", json={"message": "在吗"})
                raw = resp.data.decode("utf-8")
        finally:
            for p in patchers:
                p.stop()

        # ── 断言 1：送给 LLM 的 msgs 含稳定 system + 动态 system，顺序固定 ──
        msgs = captured.get("msgs")
        self.assertIsNotNone(msgs, "stream_messages 必须被调用")
        roles = [m["role"] for m in msgs]
        self.assertEqual(roles[0], "system", "首个必须是稳定 system block")
        # 首个 system 是稳定前缀（subconscious）
        self.assertIn("潜意识", msgs[0]["content"])
        # 末尾是 user
        self.assertEqual(roles[-1], "user")
        self.assertIn("在吗", msgs[-1]["content"])

        # ── 断言 2：SSE 事件序列 ──
        events = _parse_sse_types(raw)
        types = [e.get("type") for e in events]
        self.assertEqual(types[0], "start")
        self.assertIn("token", types)
        self.assertIn("token_estimate", types)
        # usage 事件带 prompt/completion
        usage_evt = next(e for e in events if e.get("type") == "usage")
        self.assertEqual(usage_evt["prompt_tokens"], 42)
        self.assertEqual(usage_evt["completion_tokens"], 3)
        self.assertEqual(types[-1], "done")

    def test_dynamic_blocks_reach_llm(self):
        """强制动态块出现，断言它们作为独立 system message 端到端送到 LLM

        用最自包含的两类动态块覆盖「section -> ctx.add_block -> render -> msgs」全链路：
        - skills_inject：临时 skills 目录逼出 skills_available（文件系统型 section）
        - self_narrative：mock store 逼出 self_narrative（brain store 型 section）
        不依赖 qdrant/graph 等重子系统。
        """
        import tempfile
        import os
        import modules.chat.loop as loop
        loop._conversation_history.clear()

        # 临时 skills 目录 → skills_inject 必然产出 skills_available 块
        tmp = tempfile.TemporaryDirectory()
        sk_dir = os.path.join(tmp.name, "fake_skill")
        os.makedirs(sk_dir)
        with open(os.path.join(sk_dir, "SKILL.md"), "w", encoding="utf-8") as f:
            f.write("---\ndescription: a fake skill for test\n---\nbody")

        # mock self_narrative store → 产出 self_narrative 块（parts 需 > 3 行）
        sn_store = MagicMock()
        sn_store.get_autobiography.return_value = {
            "current_state": {
                "mood": "happy", "thinking": "在想测试", "conversation_count": 7,
                "last_reflection_summary": "上次反思摘要",
            },
            "beliefs": ["我相信测试能锁住回归"],
        }

        captured: dict = {}
        patchers = self._patches(captured)
        patchers.append(patch(
            "modules.chat.pipeline.sections.skills_inject._SKILLS_DIR", tmp.name))
        patchers.append(patch(
            "modules.brain.memory.self_narrative.get_self_narrative", return_value=sn_store))
        for p in patchers:
            p.start()
        try:
            with self.app.test_client() as client:
                resp = client.post("/chat/send", json={"message": "在吗"})
                raw = resp.data.decode("utf-8")
        finally:
            for p in patchers:
                p.stop()
            tmp.cleanup()

        msgs = captured.get("msgs")
        self.assertIsNotNone(msgs, "stream_messages 必须被调用")
        sys_msgs = [m for m in msgs if m["role"] == "system"]

        # 至少 3 个独立 system：稳定前缀 + self_narrative + skills_available
        self.assertGreaterEqual(
            len(sys_msgs), 3,
            f"expected >=3 system blocks (stable+self_narrative+skills), got {len(sys_msgs)}: "
            f"{[m['content'][:20] for m in sys_msgs]}")
        # 首个仍是稳定前缀
        self.assertIn("潜意识", sys_msgs[0]["content"])
        # self_narrative 作为独立 system 出现
        self.assertTrue(
            any("自我叙事" in m["content"] for m in sys_msgs),
            "self_narrative dynamic block 未作为独立 system 送出")
        # skills 作为独立 system 出现
        self.assertTrue(
            any(("可用技能" in m["content"]) or ("fake_skill" in m["content"]) for m in sys_msgs),
            "skills dynamic block 未作为独立 system 送出")
        # 稳定块只有一个（幂等），其余动态块都在它之后
        self.assertEqual(
            [m["content"].startswith("【潜意识】") for m in sys_msgs].count(True), 1)
        # SSE 契约仍成立
        events = _parse_sse_types(raw)
        self.assertEqual(events[0].get("type"), "start")
        self.assertEqual(events[-1].get("type"), "done")

    def test_empty_message_returns_400(self):
        with self.app.test_client() as client:
            resp = client.post("/chat/send", json={"message": ""})
            self.assertEqual(resp.status_code, 400)

    def test_missing_apikey_returns_503(self):
        cfg_mgr = MagicMock()
        cfg_mgr.read_llm.return_value = {"api_key": "", "provider": "openai"}
        with patch("core.settings.ConfigManager.get_instance", return_value=cfg_mgr):
            with self.app.test_client() as client:
                resp = client.post("/chat/send", json={"message": "hi"})
                self.assertEqual(resp.status_code, 503)
                data = json.loads(resp.data)
                self.assertEqual(data.get("error"), "api_key_missing")


if __name__ == "__main__":
    unittest.main(verbosity=2)
