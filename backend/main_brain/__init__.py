"""main_brain — BrainLoop 常驻数字生命循环

在现有 AiBrain chat 能力之上构建常驻数字主体：
  - Reactive BrainSession：用户消息触发，内部多轮思考后回复。
  - LifeLoopDaemon：用户无输入时维持自己的节奏（思考/整理/表达）。
  - BrainJudge：每轮由 LLM 输出结构化控制信号，Python adapter 执行副作用。

设计原则（plan 第六节关键决策）：
  - adapter 只包装现有能力边界，不复制 memory/state/tool manager。
  - LLM 只判断与建议，副作用由 adapter 执行。
  - 全程可观测：run_id / mode / cycle / action / latency / stop_reason / error。
  - 兼容可回滚：session/life/proactive 各自可独立开关，关闭即回旧链路。

外部访问统一经模块转发：
    from main_brain import get_brain_session, get_life_loop_daemon
"""
from __future__ import annotations

from .config import BrainConfig, get_brain_config


# ── 懒加载单例（避免 import 时触碰 IO / state）──────────────
_brain_session = None
_life_daemon = None


def get_brain_session():
    """获取 Reactive BrainSession 单例。"""
    global _brain_session
    if _brain_session is None:
        from .session import BrainSession
        _brain_session = BrainSession()
    return _brain_session


def get_life_loop_daemon():
    """获取 LifeLoopDaemon 单例。"""
    global _life_daemon
    if _life_daemon is None:
        from .daemon import LifeLoopDaemon
        _life_daemon = LifeLoopDaemon()
    return _life_daemon


__all__ = [
    "BrainConfig",
    "get_brain_config",
    "get_brain_session",
    "get_life_loop_daemon",
]
