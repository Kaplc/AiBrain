"""LLM 模块单元测试

LLM 模块只做基本请求/响应 —— 不测 prompt 构造（那是调用方的事）。

跑测试：
    cd backend && python -m unittest discover -s ../tests -p "test_llm_module.py" -v
"""
import sys
import os

# 把 backend/ 加进 path
_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

import unittest
from unittest.mock import patch, MagicMock

from modules.LLM import (
    LLMConfig,
    LLMManager,
    get_llm_manager,
    call_llm_stream,
    call_llm_sync,
    SUPPORTED_PROVIDERS,
)


class TestLLMConfig(unittest.TestCase):
    def test_default(self):
        c = LLMConfig()
        self.assertEqual(c.provider, "openai")
        self.assertEqual(c.model, "gpt-4o-mini")
        self.assertEqual(c.temperature, 0.7)
        self.assertEqual(c.max_tokens, 1024)

    def test_from_dict_full(self):
        c = LLMConfig.from_dict({
            "provider": "deepseek",
            "model": "deepseek-reasoner",
            "api_key": "sk-1234",
            "base_url": "https://api.deepseek.com/v1",
            "temperature": 0.3,
            "max_tokens": 2048,
        })
        self.assertEqual(c.provider, "deepseek")
        self.assertEqual(c.model, "deepseek-reasoner")
        self.assertEqual(c.api_key, "sk-1234")
        self.assertEqual(c.temperature, 0.3)

    def test_from_dict_missing_model_fills_default(self):
        c = LLMConfig.from_dict({"provider": "ollama"})
        self.assertEqual(c.provider, "ollama")
        self.assertEqual(c.model, "qwen2.5:7b")
        self.assertEqual(c.base_url, "http://localhost:11434/v1")

    def test_from_dict_accepts_llm_provider_alias(self):
        c = LLMConfig.from_dict({
            "llm_provider": "anthropic",
            "llm_model": "claude-opus-4-7",
            "api_key": "sk-ant-xxx",
        })
        self.assertEqual(c.provider, "anthropic")
        self.assertEqual(c.model, "claude-opus-4-7")

    def test_validate_ok(self):
        c = LLMConfig(provider="openai", model="gpt-4o", api_key="sk-123")
        ok, err = c.validate()
        self.assertTrue(ok, err)

    def test_validate_ollama_no_key_ok(self):
        c = LLMConfig(provider="ollama", model="qwen2.5:7b", api_key="", base_url="http://localhost:11434/v1")
        ok, err = c.validate()
        self.assertTrue(ok, err)

    def test_validate_openai_no_key_fail(self):
        c = LLMConfig(provider="openai", model="gpt-4o", api_key="")
        ok, err = c.validate()
        self.assertFalse(ok)
        self.assertIn("api_key", err)

    def test_validate_unknown_provider(self):
        c = LLMConfig(provider="fake-llm", model="x", api_key="k")
        ok, err = c.validate()
        self.assertFalse(ok)
        self.assertIn("unsupported", err)

    def test_validate_bad_temperature(self):
        c = LLMConfig(provider="ollama", model="q", api_key="k", temperature=5.0)
        ok, err = c.validate()
        self.assertFalse(ok)
        self.assertIn("temperature", err)

    def test_to_safe_dict_masks_key(self):
        c = LLMConfig(provider="openai", model="gpt-4o", api_key="sk-1234567890abcdef")
        d = c.to_safe_dict()
        self.assertNotIn("sk-1234567890abcdef", d["api_key"])
        self.assertIn("***", d["api_key"])

    def test_to_safe_dict_short_key(self):
        c = LLMConfig(provider="openai", model="gpt-4o", api_key="sk")
        d = c.to_safe_dict()
        self.assertEqual(d["api_key"], "***")

    def test_frozen(self):
        c = LLMConfig()
        with self.assertRaises(Exception):  # FrozenInstanceError
            c.provider = "anthropic"


class TestStreamRouting(unittest.TestCase):
    """测试 call_llm_stream 的 provider 路由（不真发请求）"""

    def test_openai_compatible_routes_to_openai(self):
        cfg = LLMConfig(provider="ollama", model="qwen", api_key="dummy", base_url="http://localhost:11434/v1")
        with patch("modules.LLM.stream._openai_compatible_stream") as mock_stream:
            mock_stream.return_value = iter([{"content": "hi", "usage": None, "finish_reason": None}])
            list(call_llm_stream("sys", "user", cfg))
            mock_stream.assert_called_once()

    def test_anthropic_routes_to_anthropic(self):
        cfg = LLMConfig(provider="anthropic", model="claude-sonnet-4-20250514", api_key="sk-ant-x")
        with patch("modules.LLM.stream._anthropic_stream") as mock_stream:
            mock_stream.return_value = iter([{"content": "hi", "usage": None, "finish_reason": None}])
            list(call_llm_stream("sys", "user", cfg))
            mock_stream.assert_called_once()

    def test_unknown_provider_raises(self):
        # frozen dataclass：用 dataclasses.replace 绕过校验
        import dataclasses
        cfg = LLMConfig(provider="ollama", model="q", api_key="k", base_url="http://x")
        cfg = dataclasses.replace(cfg, provider="fake")
        with self.assertRaises(ValueError):
            list(call_llm_stream("sys", "user", cfg))

    def test_invalid_config_raises_before_call(self):
        cfg = LLMConfig(provider="openai", model="gpt-4o", api_key="")  # no key
        with self.assertRaises(ValueError):
            list(call_llm_stream("sys", "user", cfg))

    def test_call_llm_sync_concatenates_content(self):
        cfg = LLMConfig(provider="ollama", model="q", api_key="dummy", base_url="http://localhost:11434/v1")
        with patch("modules.LLM.stream._openai_compatible_stream") as mock_stream:
            mock_stream.return_value = iter([
                {"content": "你", "usage": None, "finish_reason": None},
                {"content": "好", "usage": None, "finish_reason": None},
                {"content": "！", "usage": None, "finish_reason": "stop"},
            ])
            result = call_llm_sync("sys", "user", cfg)
            self.assertEqual(result, "你好！")

    def test_does_not_touch_prompts(self):
        """LLM 模块是透传的：system_prompt / user_prompt 原样传给底层函数"""
        cfg = LLMConfig(provider="ollama", model="q", api_key="dummy", base_url="http://localhost:11434/v1")
        with patch("modules.LLM.stream._openai_compatible_stream") as mock_stream:
            mock_stream.return_value = iter([])
            list(call_llm_stream("RAW_SYSTEM", "RAW_USER", cfg))
            # 验证两个参数原样透传
            args, kwargs = mock_stream.call_args
            self.assertEqual(args[0], "RAW_SYSTEM")
            self.assertEqual(args[1], "RAW_USER")


class TestLLMManager(unittest.TestCase):
    def test_singleton(self):
        a = LLMManager.get_instance()
        b = LLMManager.get_instance()
        self.assertIs(a, b)

    def test_get_llm_manager_helper(self):
        a = get_llm_manager()
        b = LLMManager.get_instance()
        self.assertIs(a, b)

    def test_supported_providers(self):
        providers = LLMManager.supported_providers()
        self.assertIn("openai", providers)
        self.assertIn("anthropic", providers)
        self.assertIn("ollama", providers)
        self.assertGreater(len(providers), 5)

    def test_no_prompt_methods(self):
        """LLMManager 不暴露 prompt 构造方法（职责单一）"""
        mgr = get_llm_manager()
        for name in ('build_chat_system_prompt', 'build_idle_system_prompt',
                     'safe_inject_memory', 'get_random_idle_cue', 'idle_cues'):
            self.assertFalse(
                hasattr(mgr, name),
                f"LLMManager 不应该有 {name}（属于调用方/feature 模块）"
            )

    def test_stream_method_passes_through(self):
        mgr = get_llm_manager()
        cfg = LLMConfig(provider="ollama", model="q", api_key="dummy", base_url="http://localhost:11434/v1")
        with patch("modules.LLM.stream._openai_compatible_stream") as mock_stream:
            mock_stream.return_value = iter([{"content": "x", "usage": None, "finish_reason": None}])
            chunks = list(mgr.stream("sys", "user", cfg))
            self.assertEqual(len(chunks), 1)
            self.assertEqual(chunks[0]["content"], "x")

    def test_complete_method(self):
        mgr = get_llm_manager()
        cfg = LLMConfig(provider="ollama", model="q", api_key="dummy", base_url="http://localhost:11434/v1")
        with patch("modules.LLM.stream._openai_compatible_stream") as mock_stream:
            mock_stream.return_value = iter([
                {"content": "A", "usage": None, "finish_reason": None},
                {"content": "B", "usage": None, "finish_reason": "stop"},
            ])
            self.assertEqual(mgr.complete("s", "u", cfg), "AB")


class TestIntegrationWithOpenAISDK(unittest.TestCase):
    """集成测试：mock OpenAI SDK 走完一遍解析流程"""

    def test_openai_stream_parses_delta_and_usage(self):
        cfg = LLMConfig(provider="openai", model="gpt-4o-mini", api_key="sk-test")

        def fake_chunk(content, finish_reason=None, usage=None):
            c = MagicMock()
            c.choices = [MagicMock()]
            c.choices[0].delta = MagicMock()
            c.choices[0].delta.content = content
            c.choices[0].finish_reason = finish_reason
            c.usage = usage
            return c

        chunks = [
            fake_chunk("你"),
            fake_chunk("好"),
            fake_chunk("", finish_reason="stop", usage=MagicMock(prompt_tokens=10, completion_tokens=5)),
        ]

        with patch("openai.OpenAI") as MockOpenAI:
            mock_client = MockOpenAI.return_value
            mock_client.chat.completions.create.return_value = iter(chunks)

            from modules.LLM.stream import _openai_compatible_stream
            results = list(_openai_compatible_stream("sys", "user", cfg))

        self.assertEqual("".join(r["content"] for r in results), "你好")
        last = results[-1]
        self.assertEqual(last["usage"], {"prompt_tokens": 10, "completion_tokens": 5})
        self.assertEqual(last["finish_reason"], "stop")


if __name__ == "__main__":
    unittest.main(verbosity=2)
