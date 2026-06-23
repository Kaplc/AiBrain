"""Usage 归一化单测 — UsageNormalizer

覆盖 plan 第九章验收 F5：兼容三类缓存字段来源并补齐推导
- prompt_cache_hit_tokens / prompt_cache_miss_tokens   (DeepSeek)
- prompt_tokens_details.cached_tokens                  (OpenAI 官方)
- cached_tokens / cache_read_input_tokens              (OpenAI 顶层 / Anthropic)
- 缺失字段记 0；只有 hit 无 miss 时按 prompt-hit 推导
"""
import os
import sys
import unittest
from types import SimpleNamespace

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from modules.LLM.usage import UsageNormalizer, UsageMetrics


class TestDeepSeekFields(unittest.TestCase):
    def test_hit_and_miss(self):
        m = UsageNormalizer.normalize({
            "prompt_tokens": 1000, "completion_tokens": 50,
            "prompt_cache_hit_tokens": 800, "prompt_cache_miss_tokens": 200,
        }, "deepseek")
        self.assertEqual(m.cache_hit_tokens, 800)
        self.assertEqual(m.cache_miss_tokens, 200)
        self.assertEqual(m.prompt_tokens, 1000)

    def test_to_dict_flat(self):
        m = UsageNormalizer.normalize({
            "prompt_tokens": 10, "completion_tokens": 5,
            "prompt_cache_hit_tokens": 3,
        }, "deepseek")
        d = m.to_dict()
        self.assertEqual(set(d.keys()),
                         {"prompt_tokens", "completion_tokens", "cache_hit_tokens", "cache_miss_tokens"})
        self.assertEqual(d["cache_hit_tokens"], 3)


class TestOpenAIDetailsField(unittest.TestCase):
    """prompt_tokens_details.cached_tokens"""

    def test_details_cached_tokens_and_derivation(self):
        m = UsageNormalizer.normalize({
            "prompt_tokens": 1000, "completion_tokens": 50,
            "prompt_tokens_details": {"cached_tokens": 700},
        }, "openai")
        self.assertEqual(m.cache_hit_tokens, 700)
        # 只有 hit、无 miss、prompt 已知 → miss = 1000-700
        self.assertEqual(m.cache_miss_tokens, 300)

    def test_details_as_object(self):
        """SDK 对象形态的 prompt_tokens_details"""
        details = SimpleNamespace(cached_tokens=250)
        m = UsageNormalizer.normalize(SimpleNamespace(
            prompt_tokens=1000, completion_tokens=10,
            prompt_tokens_details=details), "openai")
        self.assertEqual(m.cache_hit_tokens, 250)
        self.assertEqual(m.cache_miss_tokens, 750)


class TestTopLevelCachedTokens(unittest.TestCase):
    def test_top_level_cached(self):
        m = UsageNormalizer.normalize({
            "prompt_tokens": 500, "completion_tokens": 10, "cached_tokens": 400,
        }, "openai")
        self.assertEqual(m.cache_hit_tokens, 400)
        self.assertEqual(m.cache_miss_tokens, 100)


class TestAnthropicFields(unittest.TestCase):
    def test_cache_read_and_creation(self):
        m = UsageNormalizer.normalize({
            "input_tokens": 1000, "output_tokens": 50,
            "cache_read_input_tokens": 600, "cache_creation_input_tokens": 100,
        }, "anthropic")
        self.assertEqual(m.prompt_tokens, 1000)
        self.assertEqual(m.completion_tokens, 50)
        self.assertEqual(m.cache_hit_tokens, 600)
        self.assertEqual(m.cache_miss_tokens, 100)


class TestDerivationRules(unittest.TestCase):
    def test_hit_without_prompt_no_derivation(self):
        m = UsageNormalizer.normalize({"prompt_cache_hit_tokens": 300}, "deepseek")
        self.assertEqual(m.cache_hit_tokens, 300)
        self.assertEqual(m.cache_miss_tokens, 0)

    def test_negative_derivation_not_applied(self):
        """hit > prompt 时推导结果为负，不应写入"""
        m = UsageNormalizer.normalize({
            "prompt_tokens": 100, "prompt_cache_hit_tokens": 300,
        }, "deepseek")
        self.assertEqual(m.cache_hit_tokens, 300)
        self.assertEqual(m.cache_miss_tokens, 0)  # 100-300 < 0 → 不推导


class TestMissingAndRaw(unittest.TestCase):
    def test_none_input(self):
        m = UsageNormalizer.normalize(None, "openai")
        self.assertIsInstance(m, UsageMetrics)
        self.assertEqual((m.prompt_tokens, m.completion_tokens,
                          m.cache_hit_tokens, m.cache_miss_tokens), (0, 0, 0, 0))

    def test_no_cache_fields(self):
        m = UsageNormalizer.normalize({"prompt_tokens": 10, "completion_tokens": 5}, "openai")
        self.assertEqual(m.cache_hit_tokens, 0)
        self.assertEqual(m.cache_miss_tokens, 0)

    def test_raw_usage_preserved(self):
        raw = {"prompt_tokens": 10, "completion_tokens": 5, "extra": "x"}
        m = UsageNormalizer.normalize(raw, "openai")
        self.assertEqual(m.raw_usage.get("extra"), "x")


class TestObjectInput(unittest.TestCase):
    """SDK usage 对象（带 model_dump / model_extra）也能正确归一化"""

    def test_pydantic_like_object(self):
        class FakeUsage:
            def model_dump(self):
                return {"prompt_tokens": 1000, "completion_tokens": 20}
            # model_extra 模拟 DeepSeek 扩展字段
            model_extra = {"prompt_cache_hit_tokens": 900, "prompt_cache_miss_tokens": 100}

        m = UsageNormalizer.normalize(FakeUsage(), "deepseek")
        self.assertEqual(m.prompt_tokens, 1000)
        self.assertEqual(m.cache_hit_tokens, 900)
        self.assertEqual(m.cache_miss_tokens, 100)


if __name__ == "__main__":
    unittest.main(verbosity=2)
