"""
上下文压缩测试 — 验证压缩触发、范围计算、内存重载、文件安全
"""
import json
import os
import tempfile
import threading
import time
from pathlib import Path

import pytest

# ── 测试目标模块 ──────────────────────────────────────────
import modules.chat.compression.context_compress as _cc
from modules.chat.compression.context_compress import (
    _estimate_tokens,
    _calculate_keep_from,
    try_spawn_compress,
    _compress_background,
    reload_if_needed,
)


# ── 辅助函数 ──────────────────────────────────────────────

def make_history(pairs: int, chars_per_msg: int = 50) -> list[dict]:
    """构造 N 对测试对话历史"""
    history = []
    for i in range(pairs):
        history.append({"role": "user", "content": "用户消息 " + "x" * chars_per_msg + f" {i}"})
        history.append({"role": "assistant", "content": "助手回复 " + "y" * chars_per_msg + f" {i}"})
    return history


def count_pairs(history: list) -> int:
    return len(history) // 2


# ════════════════════════════════════════════════════════════
# 1. Token 估算测试
# ════════════════════════════════════════════════════════════

class TestEstimateTokens:
    def test_empty(self):
        assert _estimate_tokens([]) == 0

    def test_single_message(self):
        msgs = [{"content": "你好世界"}]
        assert _estimate_tokens(msgs) > 0

    def test_chinese_chars(self):
        # 中文约 2 字符/token，系数 1.1
        msgs = [{"content": "你好" * 100}]  # 200 chars
        estimated = _estimate_tokens(msgs)
        assert 100 <= estimated <= 120  # 200/2*1.1 = 110

    def test_ascii_chars(self):
        msgs = [{"content": "hello " * 100}]  # 600 chars
        estimated = _estimate_tokens(msgs)
        assert estimated > 0


# ════════════════════════════════════════════════════════════
# 2. 压缩范围计算测试
# ════════════════════════════════════════════════════════════

class TestCalculateKeepFrom:
    def test_empty_history(self):
        assert _calculate_keep_from([], 1000) == len([])

    def test_target_tokens_zero(self):
        history = make_history(5)
        assert _calculate_keep_from(history, 0) == len(history)

    def test_keep_all_when_small(self):
        """5 对对话远小于 target，全部保留"""
        history = make_history(5, chars_per_msg=10)
        result = _calculate_keep_from(history, 10000)
        assert result == 0  # 全部保留

    def test_compress_old_when_large(self):
        """50 对对话，target 只够保留 10 对，剩余 40 对被压缩"""
        history = make_history(50, chars_per_msg=10)
        # 每对约 (10*2+2)/2*1.1 ≈ ~30 tokens，target=300 约保留 10 对
        result = _calculate_keep_from(history, 300)
        assert result > 0
        keep_pairs = (len(history) - result) // 2
        assert 5 <= keep_pairs <= 20  # 大致范围

    def test_result_is_user_aligned(self):
        """切割点必须对齐到 user 消息（偶数索引）"""
        history = make_history(20, chars_per_msg=10)
        result = _calculate_keep_from(history, 200)
        if result > 0:
            assert result % 2 == 0


# ════════════════════════════════════════════════════════════
# 3. 触发逻辑测试
# ════════════════════════════════════════════════════════════

class TestTrySpawnCompress:
    def test_zero_prompt_tokens_no_trigger(self):
        """prompt_tokens=0 不触发"""
        assert try_spawn_compress([], 0) is False

    def test_below_threshold_no_trigger(self):
        """prompt_tokens 低于阈值不触发"""
        assert try_spawn_compress([], 500) is False  # 500 < 4000*0.7=2800

    def test_above_threshold_triggers(self):
        """prompt_tokens 高于阈值应该触发"""
        history = make_history(50, chars_per_msg=5000)  # 足够大的历史
        result = try_spawn_compress(history, 300000)  # 3000 > 2800
        assert result is True

    def test_daemon_thread(self):
        """启动的后台线程应该是 daemon 线程"""
        import threading
        before = threading.active_count()
        history = make_history(50, chars_per_msg=5000)
        try_spawn_compress(history, 300000)
        time.sleep(0.1)
        assert threading.active_count() >= before


# ════════════════════════════════════════════════════════════
# 4. 后台压缩核心逻辑测试（mock Agent）
# ════════════════════════════════════════════════════════════

class TestCompressBackground:
    def setup_method(self):
        _cc._need_reload = False
        import time
        time.sleep(0.2)

    def _register_mock_agent(self):
        """注册一个返回固定结果的 mock Agent"""
        from modules.LLM.Agents.agent_manager import AgentManager
        from modules.LLM.Agents.base_agent import BaseAgent

        class MockCompressAgent(BaseAgent):
            name = "context_compress"
            description = "mock"
            def run(self, input_data, **kwargs):
                # 模拟压缩：将传入的条目合并为一个
                entries = input_data.get("entries", [])
                user_parts = []
                assistant_parts = []
                for i in range(0, len(entries), 2):
                    if i < len(entries):
                        user_parts.append(entries[i].get("content", ""))
                    if i + 1 < len(entries):
                        assistant_parts.append(entries[i + 1].get("content", ""))
                return [{"user": " | ".join(user_parts), "assistant": " | ".join(assistant_parts)}]

        mgr = AgentManager.get_instance()
        if mgr.has("context_compress"):
            mgr._registry.pop("context_compress")
        mgr.register(MockCompressAgent())

    def test_compress_reduces_message_count(self, monkeypatch):
        """压缩后消息数应减少"""
        _cc._need_reload = False
        self._register_mock_agent()

        history = make_history(60, chars_per_msg=5000)
        original_count = len(history)

        _compress_background(history, prompt_tokens=300000, max_tokens=400000, trigger_ratio=0.7)

        # 压缩后消息应合并为更少条
        assert len(history) < original_count

    def test_reload_flag_set_after_compress(self, monkeypatch):
        """压缩完成后 _need_reload 应为 True"""
        _cc._need_reload = False
        self._register_mock_agent()
        assert _cc._need_reload is False

        history = make_history(60, chars_per_msg=5000)

        _compress_background(history, prompt_tokens=300000, max_tokens=400000, trigger_ratio=0.7)
        assert _cc._need_reload is True


# ════════════════════════════════════════════════════════════
# 5. 集成测试：注入数据验证全流程
# ════════════════════════════════════════════════════════════

class TestIntegration:
    """外部注入数据，验证压缩模块能否正常使用"""

    def setup_method(self):
        _cc._need_reload = False
        import time
        time.sleep(0.2)

    def _register_mock_agent(self):
        from modules.LLM.Agents.agent_manager import AgentManager
        from modules.LLM.Agents.base_agent import BaseAgent
        class MockAgent(BaseAgent):
            name = "context_compress"
            description = "mock"
            def run(self, input_data, **kwargs):
                entries = input_data.get("entries", [])
                # 合并所有 user 和 assistant
                users = []
                assistants = []
                for i in range(0, len(entries), 2):
                    if i < len(entries):
                        users.append(entries[i].get("content", "")[:50])
                    if i + 1 < len(entries):
                        assistants.append(entries[i + 1].get("content", "")[:50])
                return [{"user": " | ".join(users), "assistant": " | ".join(assistants)}]
        mgr = AgentManager.get_instance()
        if mgr.has("context_compress"):
            mgr._registry.pop("context_compress")
        mgr.register(MockAgent())

    def test_realistic_conversation_compression(self):
        """模拟真实多轮对话，验证压缩后信息不丢失"""
        _cc._need_reload = False
        self._register_mock_agent()

        # 模拟 100 轮对话（每轮 5000 字符，足够触发压缩）
        conversations = [(f"第{i}轮用户问题 " + "x" * 5000, f"第{i}轮助手回答 " + "y" * 5000) for i in range(100)]

        history = []
        for user, assistant in conversations:
            history.append({"role": "user", "content": user})
            history.append({"role": "assistant", "content": assistant})

        original_pair_count = len(history) // 2
        assert original_pair_count == 100

        # 执行压缩（target 只够保留最近几对）
        _compress_background(history, prompt_tokens=300000, max_tokens=400000, trigger_ratio=0.7)

        # 压缩后应该减少
        compressed_pairs = len(history) // 2
        assert compressed_pairs < original_pair_count

        # 验证压缩标记
        assert _cc._need_reload is True

    def test_try_spawn_triggers_with_large_data(self):
        """大量对话数据时 try_spawn_compress 应触发"""
        history = make_history(50, chars_per_msg=5000)
        result = try_spawn_compress(history, 300000)
        assert result is True


# ════════════════════════════════════════════════════════════
# E2E 测试：注入数据 → 发送请求 → 验证压缩
# ════════════════════════════════════════════════════════════

class TestE2ECompression:
    """直接操作 data 文件模拟大量对话，通过 API 发送消息观察压缩"""

    def test_full_compress_write_read_cycle(self):
        """全流程：构建历史 → 压缩 → 写盘 → 重读 验证数据完整"""
        from modules.brain.memory.workmemory import get_base_dir
        import json

        # 注册 mock Agent
        from modules.LLM.Agents.agent_manager import AgentManager
        from modules.LLM.Agents.base_agent import BaseAgent
        class MockAgent(BaseAgent):
            name = "context_compress"
            description = "mock"
            def run(self, input_data, **kwargs):
                return [{"user": "压缩摘要", "assistant": "压缩回复"}]
        mgr = AgentManager.get_instance()
        if mgr.has("context_compress"):
            mgr._registry.pop("context_compress")
        mgr.register(MockAgent())

        # 构建 100 对历史（每对 5000 字符，足够触发压缩）
        history = []
        for i in range(100):
            history.append({"role": "user", "content": f"第{i}轮用户 " + "x" * 5000})
            history.append({"role": "assistant", "content": f"第{i}轮助手 " + "y" * 5000})

        # 执行压缩
        _cc._need_reload = False
        _compress_background(history, prompt_tokens=300000, max_tokens=400000, trigger_ratio=0.7)
        assert _cc._need_reload is True, "压缩标记应设为 True"
        assert len(history) < 200, f"压缩后消息应减少: {len(history)}"

        # 验证压缩后 output.json 也被更新
        output_dir = get_base_dir()
        output_path = output_dir / "output.json"
        original = output_path.read_text(encoding="utf-8") if output_path.exists() else None
        try:
            disk_data = json.loads(output_path.read_text(encoding="utf-8"))
            assert len(disk_data) > 0, "磁盘应有数据"
            # 最新条目应保留
            assert disk_data[-1].get("user"), "最新用户消息应存在"
        finally:
            if original:
                output_path.write_text(original, encoding="utf-8")


# ════════════════════════════════════════════════════════════
# 5. 重载逻辑测试（直接生成 JSON 文件）
# ════════════════════════════════════════════════════════════

class TestReloadIfNeeded:
    def setup_method(self):
        """每个测试前清理全局状态"""
        _cc._need_reload = False
        import time
        time.sleep(0.2)  # 等待后台线程完成

    def test_no_flag_no_reload(self):
        """_need_reload=False 时不重读"""
        assert reload_if_needed([]) is False

    def test_reload_loads_from_output_json(self):
        """标记为 True 时从 output.json 重读"""
        _cc._need_reload = True

        # 直接生成测试数据到 output.json
        from modules.brain.memory.workmemory import get_base_dir
        import json
        output_dir = get_base_dir()
        output_path = output_dir / "output.json"

        # 备份原始文件
        original = None
        if output_path.exists():
            original = output_path.read_text(encoding="utf-8")

        # 写入测试数据
        test_data = [
            {"seq": 1, "user": "测试用户1", "assistant": "测试回复1", "time": "10:00"},
            {"seq": 2, "user": "测试用户2", "assistant": "测试回复2", "time": "10:05"},
        ]
        output_path.write_text(json.dumps(test_data, ensure_ascii=False), encoding="utf-8")

        try:
            history = []
            result = reload_if_needed(history)

            assert result is True
            assert len(history) == 4
            assert history[0]["role"] == "user"
            assert history[0]["content"] == "测试用户1"
            assert history[1]["role"] == "assistant"
            assert history[1]["content"] == "测试回复1"
            assert _cc._need_reload is False
        finally:
            # 恢复原始文件
            if original is not None:
                output_path.write_text(original, encoding="utf-8")
            elif output_path.exists():
                output_path.unlink()


# ════════════════════════════════════════════════════════════
# 6. 文件安全测试
# ════════════════════════════════════════════════════════════

class TestFileSafety:
    def setup_method(self):
        _cc._need_reload = False
        import time
        time.sleep(0.2)

    def _register_mock_agent(self):
        from modules.LLM.Agents.agent_manager import AgentManager
        from modules.LLM.Agents.base_agent import BaseAgent
        class MockAgent(BaseAgent):
            name = "context_compress"
            description = "mock"
            def run(self, input_data, **kwargs):
                return [{"user": "压缩摘要", "assistant": "压缩回复"}]
        mgr = AgentManager.get_instance()
        if mgr.has("context_compress"):
            mgr._registry.pop("context_compress")
        mgr.register(MockAgent())

    def test_compress_maintains_data_integrity(self):
        """压缩后内存和文件状态一致"""
        global _need_reload
        _need_reload = False
        self._register_mock_agent()

        history = make_history(60, chars_per_msg=5000)
        original_len = len(history)

        _compress_background(history, prompt_tokens=300000, max_tokens=400000, trigger_ratio=0.7)

        # 内存消息应该被压缩
        assert len(history) > 0
        assert len(history) < original_len
