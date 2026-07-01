"""AutonomousMind — 意识流自主决策循环（取代旧的 ActivitySelector→controller→gate 流水线）

核心理念：把完整上下文交给 AI，由 AI 自己决定此刻做什么（think / use_tool /
create_activity / speak / rest），而不是由规则链替它分配活动。

与旧系统的关系：
  - 真正的核心是「内循环」——一次 tick 可以连续 use_tool 多轮，结果逐轮注入下一轮，
    直到一个终止动作（think / create_activity / speak / rest）。从「一次 tick 做一件事」
    变成「一次 tick 完成一整套思考链」。
  - 跨 tick 连续性由 LifeState.stream_of_consciousness 承载（last_thought / mood /
    internal_dialogue / activities）。stream 的读写统一经 StateAdapter（单一 IO 持有者）。
  - 工具调用复用 ToolAdapter + 记忆 core，不另起一套工具实现。

被取代的旧路径（文件保留、不再被调用）：
  ActivitySelector / Arbiter / ExpressionGate / daemon._run_daemon_cycle。
"""
from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path

from .config import get_brain_config

logger = logging.getLogger("main_brain.mind")

_PROMPT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompts", "autonomous_mind.md")
_ACTIVITIES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "activities", "activity")
_ACTIONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "activities", "action")
_PROJECT_ROOT = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '..', '..'))

# ── 动作描述缓存（模块级单次加载）────────────────────────────
_ACTION_DESCRIPTIONS_CACHE: list[str] | None = None


def _get_action_descriptions() -> list[str]:
    """从 activities/action/*.md 读取原子动作描述，供 prompt 的「你可以做的事」段。

    返回格式化的列表，如 ["- `think`：继续想心事……。终止本轮。", …]。
    若目录不存在或读取出错，返回空列表。只在首次调用时读盘，后续缓存。
    """
    global _ACTION_DESCRIPTIONS_CACHE
    if _ACTION_DESCRIPTIONS_CACHE is not None:
        return _ACTION_DESCRIPTIONS_CACHE

    dirpath = Path(_ACTIONS_DIR)
    if not dirpath.is_dir():
        _ACTION_DESCRIPTIONS_CACHE = []
        return _ACTION_DESCRIPTIONS_CACHE

    descriptions: list[str] = []
    try:
        for fpath in sorted(dirpath.glob("*.md")):
            text = fpath.read_text(encoding="utf-8")
            name, desc, terminates = "", "", ""
            in_front = False
            for line in text.splitlines():
                if line.strip() == "---":
                    if in_front and name:
                        break
                    in_front = True
                    continue
                if in_front:
                    if line.startswith("name:"):
                        name = line.split(":", 1)[1].strip()
                    elif line.startswith("description:"):
                        desc = line.split(":", 1)[1].strip()
                    elif line.startswith("terminates:"):
                        terminates = line.split(":", 1)[1].strip().lower()
            if name and desc:
                suffix = "终止本轮。" if terminates == "true" else "继续循环。"
                descriptions.append(f"- `{name}`：{desc}。{suffix}")
    except Exception as e:
        logger.warning(f"[mind] load action descriptions failed: {e}")
        _ACTION_DESCRIPTIONS_CACHE = []

    _ACTION_DESCRIPTIONS_CACHE = descriptions
    return descriptions


# ── 活动正文指引缓存（name → body）──────────────────────────
_ACTIVITY_GUIDES: dict[str, str] | None = None


def _load_activity_guide(context: dict) -> str | None:
    """如果 AI 当前有正在执行的活动（在 activities 中），返回对应 .md 正文指引。

    Args:
        context: tick context（包含 'activities' 字段）

    Returns:
        活动执行指引文本（Markdown），无匹配返回 None
    """
    global _ACTIVITY_GUIDES
    activities_str = context.get("activities", "")

    # 懒加载活动正文缓存
    if _ACTIVITY_GUIDES is None:
        _ACTIVITY_GUIDES = {}
        dirpath = Path(_ACTIVITIES_DIR)
        if dirpath.is_dir():
            for fpath in dirpath.glob("*.md"):
                text = fpath.read_text(encoding="utf-8")
                # 解析 frontmatter 取出 name
                name = ""
                in_front = False
                for line in text.splitlines():
                    if line.strip() == "---":
                        in_front = not in_front
                        continue
                    if in_front and line.startswith("name:"):
                        name = line.split(":", 1)[1].strip()
                        break
                if not name:
                    continue
                # 提取正文（去掉 frontmatter 块）
                body = re.sub(r"^---.*?---\s*", "", text, flags=re.DOTALL).strip()
                if body:
                    _ACTIVITY_GUIDES[name] = body

    # 从 activities 字符串中搜索匹配的活动名
    if activities_str and _ACTIVITY_GUIDES:
        for act_name in _ACTIVITY_GUIDES:
            if act_name in activities_str:
                return _ACTIVITY_GUIDES[act_name]

    return None


def _load_prompt() -> str:
    try:
        with open(_PROMPT_PATH, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        logger.warning(f"[mind] load prompt failed: {e}")
        return ""


# 终止动作：只有 rest 会终止本轮，其余均继续循环
_TERMINAL_ACTIONS = {"rest"}

# 暴露给 AI 的工具说明（prompt 里也列了，这里供观测/日志）
AVAILABLE_TOOLS = {
    "read_file": "读取项目文件内容（相对路径），支持 path:offset,limit 指定行范围",
    "grep_search": "在代码库中按正则搜索内容",
    "memory_search": "在自己的长期记忆中搜索",
    "web_search": "搜索互联网获取新信息",
    "store_memory": "把一段内容存入长期记忆",
    "list_files": "列出某个目录下的文件",
    "write_file": "写入/覆盖文件（第一行为路径，其余为内容）",
}


class AutonomousMind:
    """意识流决策器。单例（rest_streak 等内存态跨 tick 保留）。"""

    def __init__(self):
        from .adapters.state import get_state_adapter
        from .adapters.tools import get_tool_adapter
        self._state = get_state_adapter()
        self._tools = get_tool_adapter()
        self._rest_streak = 0          # 连续 rest 次数（内存态，重启清零）
        self._last_action: str | None = None
        self._last_perceived_state: dict = {}  # 上次感知快照（供 perceive diff）
        self._message_queue: list[str] = []  # 用户消息缓冲（alive tick 自行读取）
        self._current_user_msg: str = ""     # 给 _build_context 用，第一轮后清空

    # ── 入口：一次意识流 tick ──────────────────────────────
    def tick(self, ctx: dict) -> dict:
        """执行一次意识流 tick。ctx: {"life_state": dict, "dry_run": bool}。

        Returns: {action, output, thought, cycle_count, tool_calls, llm_skipped}
        """
        dry_run = bool(ctx.get("dry_run", False))
        life_state = ctx.get("life_state", {}) or {}

        # 0. 消费一条用户消息（每 tick 只消费一次），供整个 tick 使用
        # 用户消息由 chat_send 发送时即写入 output.json，这里只取出供上下文使用
        if not dry_run:
            self._current_user_msg = self._drain_message_queue()
        else:
            self._current_user_msg = ""
        # 1. 感知环境变化（diff 检测）；dry_run 不更新基线，避免污染真实感知
        signals = self._perceive(life_state) if not dry_run else {}

        # 2. 感知信号注入上下文
        loop_ctx = {"cycle": 0, "tool_results": {}, "last_result": "",
                    "accumulated": [], "stuck": 0, "cycles_data": [],
                    "tool_chain": [], "last_thought": ""}  # tick 内每步工具调用：assistant 决策 + tool 结果
        max_cycles = int(get_brain_config().get("consciousness_max_cycles", 30))

        # 内部循环：连续 use_tool 多轮，直到终止动作或卡住
        while True:
            # 优先响应用户新消息：自主 tick 中途收到用户消息 → 尽快收尾，下次 tick 立即处理
            if (not self._current_user_msg and not dry_run and self._message_queue
                    and get_brain_config().get("consciousness_preempt_on_user_message", True)):
                _acc = " | ".join(str(x)[:60] for x in loop_ctx.get("accumulated", [])[-3:])
                logger.info(f"[mind] user message arrived mid-tick, wrapping up to respond promptly "
                            f"(cycle={loop_ctx['cycle']} last_action={self._last_action} "
                            f"accumulated=[{_acc}])")
                self._last_action = "rest"
                return self._finish("rest", {"thought": "interrupted by user message"}, loop_ctx)
            # 最大循环兜底（防止 AI 无限 think/speak 不 rest）
            if loop_ctx["cycle"] >= max_cycles:
                logger.info(f"[mind] max cycles ({max_cycles}) reached, force rest")
                self._last_action = "rest"
                return self._finish("rest", {"thought": f"cycles exhausted ({max_cycles})"}, loop_ctx)

            context = self._build_context(ctx, loop_ctx, signals)
            # 第一轮后清空 _current_user_msg，后续轮次不再看到用户消息，防重复回复
            if loop_ctx["cycle"] == 0:
                self._current_user_msg = ""
            decision = self._llm_decide(context, dry_run=dry_run)
            action = str(decision.get("action", "rest")).strip()
            # 保存本轮 thought，供下轮 _build_context 作为【刚才在想什么】
            loop_ctx["last_thought"] = str(decision.get("thought", ""))
            # 每个周期日志：动作 + 详情 + 当前活动
            detail = decision.get("action_detail", "") or decision.get("tool_name", "") or ""
            cur_activity = context.get("activities", "").replace("\n", " ")
            logger.info(
                f"[mind] cycle {loop_ctx['cycle']}: {action}"
                + (f" ({detail})" if detail else "")
                + (f" | activity: {cur_activity}" if "当前：" in cur_activity else "")
            )
            # 记录 cycle 轨迹（供前端回放）
            cycle_rec = {
                "cycle": loop_ctx["cycle"],
                "action": action,
                "thought": str(decision.get("thought", ""))[:200],
            }
            if action == "use_tool":
                cycle_rec["tool_name"] = str(decision.get("tool_name", ""))
                cycle_rec["tool_args"] = str(decision.get("tool_args", ""))[:100]
            elif action in ("create_activity", "set_activity"):
                cycle_rec["activity"] = str(decision.get("action_detail", ""))
                cycle_rec["activity_context"] = str(decision.get("activity_context", ""))[:200]
            elif action == "speak":
                cycle_rec["content"] = str(decision.get("action_detail", ""))[:200]
            loop_ctx["cycles_data"].append(cycle_rec)

            # use_tool：执行并把结果注入下一轮（继续循环）
            if action == "use_tool":
                result = self._execute_tool(decision, loop_ctx)
                # 保存工具调用轨迹：assistant（决策）+ tool（结果）
                loop_ctx["tool_chain"].append({
                    "role": "assistant",
                    "content": f"【我决定】想法：{decision.get('thought', '')}\n"
                               f"调用工具：{decision.get('tool_name', '')}\n"
                               f"参数：{str(decision.get('tool_args', ''))}"
                })
                loop_ctx["tool_chain"].append({
                    "role": "tool",
                    "content": str(result)
                })
                # 连续重复请求同一工具 → 提前结束，避免空转烧 token
                if str(result).startswith("[缓存]"):
                    loop_ctx["stuck"] += 1
                else:
                    loop_ctx["stuck"] = 0
                loop_ctx["last_result"] = result
                loop_ctx["accumulated"].append(result[:200])
                loop_ctx["cycle"] += 1
                self._last_action = "use_tool"
                logger.info(
                    f"[mind] cycle {loop_ctx['cycle']} use_tool="
                    f"{decision.get('tool_name','')} -> {result}"
                )
                if loop_ctx["stuck"] >= 2:
                    logger.info("[mind] stuck on repeated tool call -> rest")
                    break
                continue

            # create_activity：建活动后继续循环（不终止本轮）
            if action == "create_activity":
                if not dry_run:
                    self._create_activity(decision)
                self._last_action = "create_activity"
                loop_ctx["last_result"] = f"活动'{decision.get('action_detail','')}'已创建，继续执行"
                loop_ctx["cycle"] += 1
                continue

            # set_activity：切换到已有活动后继续循环（不终止本轮）
            if action == "set_activity":
                if not dry_run:
                    msg = self._set_active_activity(decision)
                else:
                    msg = f"[dry_run] set_activity: {decision.get('action_detail','')}"
                self._last_action = "set_activity"
                if msg:
                    loop_ctx["last_result"] = msg
                loop_ctx["cycle"] += 1
                continue

            # think / speak：执行后继续循环（不终止本轮）
            if action in ("think", "speak"):
                self._execute(decision, dry_run=dry_run)
                self._last_action = action
                loop_ctx["cycle"] += 1
                continue

            # rest（含未知动作兜底为 rest）：终止本轮
            self._execute(decision, dry_run=dry_run)
            self._last_action = action if action in _TERMINAL_ACTIONS else "rest"
            return self._finish(self._last_action, decision, loop_ctx)

        # 循环终止（break 来自 stuck 检测）→ 收尾
        logger.info(f"[mind] tool loop exhausted, finishing as rest")
        self._last_action = "rest"
        return self._finish("rest", {"thought": "tool loop exhausted"}, loop_ctx)

    # ── 感知 + 自适应频率 ──────────────────────────────────
    def _perceive(self, life_state: dict) -> dict:
        """检测系统状态变化（diff 检测）。

        对比当前状态与上次 alive tick 的快照，找出变化。
        没变化 → 返回空信号 → NeedReasoning? = No → 跳过本轮 LLM，省 token。
        所有"感知"的输入源都来自已有系统状态（life_state、work_memory、clock）。
        """
        signals = {}
        last = self._last_perceived_state

        # 1. 用户活跃度变化（idle_seconds 变化超过 1 分钟）
        now_idle = int(life_state.get("idle_seconds", 0) or 0)
        prev_idle = last.get("idle", 0)
        if abs(now_idle - prev_idle) > 60:
            signals["idle_changed"] = True
            # idle_seconds 大幅下降 → 用户刚回来了
            if prev_idle > 0 and now_idle < prev_idle - 60:
                signals["idle_dropped"] = True

        # 2. 用户是否刚说了话（output 条目数变化）
        current_count = last.get("output_count", 0)
        try:
            from main_brain.memory.workmemory import get_work_memory
            entries = get_work_memory().output_mem_read()
            current_count = len(entries)
            if current_count > last.get("output_count", 0):
                signals["user_message"] = True
        except Exception:
            pass

        except Exception as e:
            logger.warning(f"[mind] _perceive output_mem_read failed: {e}")

        # 3. 时间变化（跨时段 / 跨天，本地时间）
        from .clock import get_brain_clock
        clock = get_brain_clock()
        now_period = self._time_of_day()
        now_date = clock.today_str()
        if now_period != last.get("period"):
            signals["period_changed"] = now_period
        if now_date != last.get("date"):
            signals["day_changed"] = True

        # 缓存本次结果供下次 diff
        self._last_perceived_state = {
            "idle": now_idle,
            "output_count": current_count,
            "period": now_period,
            "date": now_date,
        }

        return signals

    # ── 上下文构建 ─────────────────────────────────────────
    def _build_context(self, ctx: dict, loop_ctx: dict, signals: dict | None = None) -> dict:
        life_state = ctx.get("life_state", {}) or {}
        stream = self._state.read_stream()
        # 内循环中用上一轮 decision 的 thought，更准确
        last_thought = (loop_ctx.get("last_thought") or stream.get("last_thought", ""))
        focus = stream.get("focus") or life_state.get("current_focus", "")
        base = {
            "last_thought": last_thought,
            "last_tick_summary": stream.get("last_tick_summary", ""),
            "mood": stream.get("mood", "平静"),
            "user_message": self._current_user_msg,  # tick 开始时已消费，内循环复用同一消息
            "recent_conversation": self._recent_chat(),
            "dialogue_history": self._dialogue_for_prompt(),
            "memory_surfaced": self._recall(focus or last_thought),
            "concerns": self._concerns_snapshot(),
            "idle_seconds": life_state.get("idle_seconds", 0),
            "time_of_day": self._time_of_day(),
            "activities": self._activities_for_prompt(stream),
            "working_memory": self._wm_for_prompt(stream),
            "perceive_signals": self._signals_for_prompt(signals or {}),
        }
        if loop_ctx["cycle"] == 0:
            return base
        # 内循环后续轮：注入上一步工具调用轨迹
        base["step"] = loop_ctx["cycle"] + 1
        base["tool_chain"] = list(loop_ctx.get("tool_chain", []))
        return base

    # ── LLM 决策 ───────────────────────────────────────────
    def _llm_decide(self, context: dict, dry_run: bool) -> dict:
        if dry_run:
            return {"action": "rest", "thought": "dry_run", "tick_summary": ""}
        try:
            messages = [
                {"role": "system", "content": self._system_prompt()},
                {"role": "system", "content": (
                    f"【可以做的行为】\n"
                    f"{chr(10).join(_get_action_descriptions()) or '（暂无可用动作）'}"
                )},
                {"role": "system", "content": f"【可以做的活动】\n{context.get('activities')}"},
                {"role": "system", "content": f"【工作记忆】\n{context.get('working_memory')}"},
            ]
            guide = _load_activity_guide(context)
            if guide:
                messages.append({"role": "system", "content": f"【当前活动执行指引】\n{guide}"})
            messages.extend(self._user_prompt(context))
            raw = self._call_llm(messages)
            decision = _parse_decision(raw)
            action = decision.get("action", "rest")

            # rest 必须带 tick_summary，否则追加提醒重新生成（最多 3 次）
            retry = 0
            while action == "rest" and not str(decision.get("tick_summary", "")).strip() and retry < 3:
                retry += 1
                logger.info(f"[mind] rest without tick_summary, remind (retry={retry})")
                reminder = (
                    "【tick_summary 缺失】你选择了 rest 结束本轮，但必须同时提供 "
                    "`tick_summary` 字段——对本 tick 所做的事情的一句话总结，供下轮自己回顾。"
                    "请重新输出完整决策 JSON，包含 tick_summary。"
                )
                messages.append({"role": "user", "content": reminder})
                raw = self._call_llm(messages)
                decision = _parse_decision(raw)
                action = decision.get("action", "rest")

            if not str(decision.get("tick_summary", "")).strip() and action == "rest":
                decision["tick_summary"] = f"进行了 {context.get('step', 1)} 轮思考后选择 rest"

            logger.info(
                f"[mind] decide action={decision.get('action','rest')} "
                f"thought={str(decision.get('thought',''))}"
            )
            return decision
        except Exception as e:
            logger.warning(f"[mind] llm decide failed: {e}")
            return {"action": "rest", "thought": f"llm_error: {e}", "tick_summary": "LLM 异常结束"}

    def _build_llm_config(self):
        from modules.LLM import LLMConfig
        from core.settings import ConfigManager
        cfg = get_brain_config()
        llm_cfg = ConfigManager.get_instance().read_llm()
        base = {
            "provider": llm_cfg.get("provider", "openai"),
            "model": llm_cfg.get("model", "gpt-4o-mini"),
            "api_key": llm_cfg.get("api_key", ""),
            "base_url": llm_cfg.get("base_url", ""),
        }
        base["temperature"] = cfg.get("consciousness_temperature", 0.6)
        base["max_tokens"] = 256000
        base["timeout"] = cfg.get("consciousness_timeout_seconds", 25)
        base["thinking_mode"] = False
        return LLMConfig.from_dict(base)

    def _call_llm(self, messages: list[dict]) -> str:
        from modules.LLM import get_llm_manager
        cfg = self._build_llm_config()
        ok, err = cfg.validate()
        if not ok:
            raise RuntimeError(f"invalid llm config: {err}")
        return get_llm_manager().complete_messages(messages, cfg)

    def _system_prompt(self) -> str:
        persona = self._persona()
        tpl = _load_prompt() or "你是 {name}，一个数字生命体。输出一个 JSON 决策对象。"
        return (tpl.replace("{name}", persona["name"])
                   .replace("{traits}", persona["traits"]))

    def _user_prompt(self, context: dict) -> list[dict]:
        """构建多 role 消息数组，按 assistant / tool / user 区分，

        让 provider prefix caching 命中 system + assistant 固定前缀，
        只需重新计算变动的 user 部分。
        """
        idle_desc = self._idle_desc(int(context.get("idle_seconds", 0) or 0))
        messages = []

        # ── assistant role：AI 自己的历史想法 / 输出 / 对话 ──
        tick_summary = context.get('last_tick_summary')
        if tick_summary:
            messages.append({"role": "assistant", "content": f"【上次 ticks 总结】\n{tick_summary}"})
        thought = context.get('last_thought')
        if thought:
            messages.append({"role": "assistant", "content": f"【刚才在想什么】\n{thought}"})
        msgs_history = context.get('dialogue_history')
        if msgs_history and msgs_history != "（暂无对话记录）":
            messages.append({"role": "tool", "content": f"【对话记录】\n{msgs_history}"})
        # ── tool role：内循环中上一步工具调用 + 结果（成对保存） ──
        for entry in (context.get("tool_chain") or []):
            messages.append(entry)

        # ── user role：当前 tick 的感知 + 上下文 + 指令 ──
        user_parts = []
        user_parts.append(
            f"【感知】\n- 时间：{context.get('time_of_day')}，{idle_desc}\n"
            f"- 心情：{context.get('mood')}\n"
            f"- 你在意的事：{context.get('concerns')}\n"
            f"- 环境变化：{context.get('perceive_signals')}"
        )
        user_parts.append(f"【刚才浮现的记忆】\n{context.get('memory_surfaced')}")
        if context.get("user_message"):
            user_parts.append(f"【用户消息】\n{context['user_message']}")
        user_parts.append("此刻你想做什么？请输出决策 JSON。")
        messages.append({"role": "user", "content": "\n\n".join(user_parts)})

        return messages

    # ── 工具层（复用 ToolAdapter + 记忆 core）──────────────
    def _execute_tool(self, decision: dict, loop_ctx: dict) -> str:
        tool_name = str(decision.get("tool_name", "")).strip()
        args_raw = str(decision.get("tool_args", "")).strip()
        cache_key = f"{tool_name}:{args_raw}"
        if cache_key in loop_ctx["tool_results"]:
            return "[缓存] 同上一步，已执行过"

        try:
            if tool_name == "store_memory":
                # memory_store 不在默认白名单，直接走记忆 core（与工具底层同一 API）
                from main_brain.memory.core import store_memory
                res = store_memory(args_raw, memory_meta={"source": "consciousness"})
                result = res.get("result", "已记住") if isinstance(res, dict) else str(res)
            elif tool_name == "read_file":
                # 支持 path:offset,limit 格式，避免整篇文件全读
                _path = args_raw
                _offset = None
                _limit = None
                if ":" in args_raw:
                    parts = args_raw.rsplit(":", 1)
                    _path = parts[0]
                    _range = parts[1].replace(" ", "")
                    if "," in _range:
                        try:
                            _offset = int(_range.split(",", 1)[0])
                            _limit = int(_range.split(",", 1)[1])
                        except ValueError:
                            pass
                    else:
                        try:
                            _offset = int(_range)
                        except ValueError:
                            pass
                _read_args = {"path": _path}
                if _offset is not None:
                    _read_args["offset"] = _offset
                if _limit is not None:
                    _read_args["limit"] = _limit
                result = self._tools.call("read_file", _read_args)
                # 在结果前附加文件总行数，供 AI 自行判断是否继续读
                if result and not result.startswith("Error"):
                    try:
                        _full_path = os.path.join(
                            _PROJECT_ROOT, _path)
                        with open(_full_path, "r", encoding="utf-8") as _f:
                            _total = sum(1 for _ in _f)
                        result = f"=== {_path} (总共 {_total} 行) ===\n\n{result}"
                    except Exception:
                        pass
            elif tool_name == "grep_search":
                result = self._tools.call("file_search", {"pattern": args_raw, "target": "content"})
            elif tool_name == "memory_search":
                result = self._tools.call("memory_search", {"query": args_raw})
            elif tool_name == "web_search":
                result = self._tools.call("web_search", {"query": args_raw})
            elif tool_name == "list_files":
                result = self._tools.call("list_directory", {"path": args_raw})
            elif tool_name == "write_file":
                lines = args_raw.split("\n", 1)
                fpath = lines[0].strip()
                fcontent = lines[1] if len(lines) > 1 else ""
                result = self._tools.call("write_file", {"path": fpath, "content": fcontent})
            else:
                result = f"未知工具：{tool_name}"
        except Exception as e:
            result = f"工具执行失败：{e}"

        loop_ctx["tool_results"][cache_key] = result
        return str(result)

    # ── 终止动作执行 ───────────────────────────────────────
    def _execute(self, decision: dict, dry_run: bool) -> None:
        action = str(decision.get("action", "rest")).strip()
        thought = str(decision.get("thought", ""))
        mood = str(decision.get("mood_update", ""))

        if action == "think":
            # 在想事情 = 活跃，重置休息计数
            self._rest_streak = 0
            if not dry_run:
                self._save_stream(thought=thought, mood=mood, dialogue=thought)
            return

        if action == "speak":
            content = (str(decision.get("action_detail", "")) or thought).strip()
            if not content:
                self._rest_streak += 1
                logger.info(f"[mind] speak with empty content, treat as rest (thought={thought[:60]})")
                return
            if dry_run:
                return
            self._write_output(content)
            self._state.mark_proactive_contact()
            self._save_stream(thought=f"跟志远说了：{content}", mood=mood, dialogue=content)
            self._rest_streak = 0
            logger.info(f"[mind] speak -> {content}")
            return

        # rest（含未知动作兜底）
        self._rest_streak += 1
        if not dry_run and thought:
            self._save_stream(thought=thought, mood=mood)

    def _finish(self, action: str, decision: dict, loop_ctx: dict,
                llm_skipped: bool = False) -> dict:
        cycles = loop_ctx["cycle"] + 1
        tools = len(loop_ctx["tool_results"])
        logger.info(
            f"[mind] finish: {action} | {cycles} cycles, {tools} tools"
            + (f" | llm_skipped={llm_skipped}" if llm_skipped else "")
            + (f" | {str(decision.get('thought',''))}" if decision.get("thought") else "")
        )
        # 跨 tick 保存本次 tick_summary
        tick_summary = str(decision.get("tick_summary", "")).strip()
        if tick_summary:
            self._state.mutate_stream(lambda s: s.update({"last_tick_summary": tick_summary}))
        return {
            "action": action,
            "output": str(decision.get("action_detail", "")) if action == "speak" else "",
            "thought": str(decision.get("thought", "")),
            "cycle_count": cycles,
            "tool_calls": tools,
            "llm_skipped": llm_skipped,
            "cycles": list(loop_ctx.get("cycles_data", [])),
        }

    # ── 跨 tick 活动 ───────────────────────────────────────
    def _create_activity(self, decision: dict) -> None:
        name = str(decision.get("action_detail", "")).strip()
        if not name:
            logger.warning("[mind] create_activity skipped: empty name")
            return
        import hashlib
        from main_brain import clock as times
        now_iso = times.now_iso()
        stamp = now_iso.replace(":", "").replace("-", "").replace("+", "")
        context = str(decision.get("activity_context", ""))[:300]
        guide = str(decision.get("activity_guide", ""))[:500]
        activity = {
            "id": "act_" + stamp + "_" + hashlib.md5(stamp.encode()).hexdigest()[:6],
            "name": name[:100],
            "status": "active",
            "context": context,
            "guide": guide,
            "findings": [],
            "created_at": now_iso,
            "updated_at": now_iso,
        }
        def _fn(stream):
            acts = stream.get("activities") or []
            for a in acts:
                a["status"] = "inactive"
            acts.append(activity)
            stream["activities"] = acts

        self._state.mutate_stream(_fn)
        logger.info(f"[mind] created activity: {name}")

        # 同步写 .md 文件，让 AI 自建活动与系统活动走同一通道
        self._write_activity_md(name, context, guide, now_iso)

    @staticmethod
    def _write_activity_md(name: str, context: str, guide: str, timestamp: str) -> None:
        """把 AI 自建活动写入 activities/activity/{name}.md，与系统活动同一通道。"""
        global _ACTIVITY_DESCRIPTIONS_CACHE, _ACTIVITY_GUIDES
        # 过滤 Windows 非法字符 \ / : * ? " < > |
        _safe = re.sub(r'[\\/:*?"<>|]', "_", name.strip().replace(" ", "_"))[:80]
        if not _safe:
            logger.warning(f"[mind] write_activity_md skipped: invalid name={name!r}")
            return
        fpath = os.path.join(_ACTIVITIES_DIR, f"{_safe}.md")
        guide_body = guide if guide else f"上下文：{context}"
        md_content = (
            "---\n"
            f"name: {name}\n"
            f"description: {context[:120]}\n"
            "source: ai\n"
            f"created_at: {timestamp}\n"
            "---\n"
            "\n"
            f"# {name}\n"
            "\n"
            f"{guide_body}\n"
        )
        try:
            os.makedirs(_ACTIVITIES_DIR, exist_ok=True)
            with open(fpath, "w", encoding="utf-8") as f:
                f.write(md_content)
            _ACTIVITY_DESCRIPTIONS_CACHE = None
            _ACTIVITY_GUIDES = None
            logger.info(f"[mind] activity md written: {fpath}")
        except Exception as e:
            _ACTIVITY_DESCRIPTIONS_CACHE = None
            _ACTIVITY_GUIDES = None
            logger.warning(f"[mind] write activity md failed: {e}")

    def _set_active_activity(self, decision: dict) -> str:
        """切换到已有活动（只切换，不创建）。返回提示消息，空串表示无操作。"""
        target = str(decision.get("action_detail", "")).strip()
        if not target:
            logger.warning(f"[mind] set_activity with empty target (thought={str(decision.get('thought',''))[:60]})")
            return ""
        found = [False]

        def _fn(stream):
            acts = stream.get("activities") or []
            for a in acts:
                if isinstance(a, dict) and a.get("name") == target:
                    a["status"] = "active"
                    found[0] = True
                else:
                    a["status"] = "inactive"

        self._state.mutate_stream(_fn)
        if found[0]:
            logger.info(f"[mind] switched to activity: {target}")
            return f"已切换到活动：{target}"
        logger.info(f"[mind] switch ignored: {target} not found")
        return ""

    def _activities_for_prompt(self, stream: dict) -> str:
        all_acts = stream.get("activities") or []
        current = [a for a in all_acts
                   if isinstance(a, dict) and a.get("status") == "active"]
        others = [a for a in all_acts
                  if isinstance(a, dict) and a.get("status") != "active"]
        if not current:
            if not others:
                return "（当前没有活动）"
            return "可用活动：\n" + "\n".join(
                f"- {a.get('name','')}" for a in others)
        lines = []
        c = current[0]
        ctx = str(c.get("context", ""))[:80]
        lines.append("当前：- " + str(c.get("name", "")) + (f"（{ctx}）" if ctx else ""))
        if others:
            lines.append("其他：" + ", ".join(a.get("name", "") for a in others))
        return "\n".join(lines)

    def handle_user_message(self, user_msg: str) -> None:
        """收到用户消息，放入缓冲队列。alive tick 会在下一轮自行读取处理。"""
        self._message_queue.append(user_msg)
        self._rest_streak = 0  # 用户来了 → AI 应该清醒

    def _drain_message_queue(self) -> str:
        """从消息队列取出一条。没消息返回空串。"""
        if not self._message_queue:
            return ""
        msg = self._message_queue.pop(0)
        logger.info(f"[mind] processing user message: {msg}")
        # 记录用户回复时间到持久化 tick_log（重启恢复 idle_seconds 用）
        try:
            from .tick_log import record_user_reply
            record_user_reply()
        except Exception as e:
            logger.warning(f"[mind] record_user_reply failed: {e}")
        self._state.mark_user_contact()
        self._state.set_loop_status("chatting", activity="respond", focus=msg)
        # 记录到 stream 让上下文连贯
        def _fn(stream):
            stream.setdefault("internal_dialogue", []).append(
                f"用户说：{(msg or '')[:300]}")
        self._state.mutate_stream(_fn)
        return msg

    @property
    def has_pending_messages(self) -> bool:
        return bool(self._message_queue)

    # ── stream IO（统一走 StateAdapter）────────────────────
    def _save_stream(self, thought: str = "", mood: str = "", dialogue: str = "") -> None:
        cap = int(get_brain_config().get("consciousness_dialogue_cap", 8))

        def _fn(stream):
            if thought:
                stream["last_thought"] = thought[:300]
            if mood:
                stream["mood"] = mood[:40]
            if dialogue:
                stream["internal_dialogue"].append(dialogue[:200])
                if len(stream["internal_dialogue"]) > cap:
                    del stream["internal_dialogue"][:len(stream["internal_dialogue"]) - cap]

        self._state.mutate_stream(_fn)

    def _within_speak_cooldown(self) -> bool:
        from main_brain import clock as times
        last = self._state.read_life_state().get("last_proactive_contact_at", "")
        if not last:
            return False
        mins = times.hours_since(last) * 60.0
        cooldown = float(get_brain_config().get("consciousness_speak_cooldown_minutes", 15))
        return mins < cooldown

    def _write_output(self, content: str) -> None:
        """speak 内容作为独立 assistant 条目写入 output.json（emit 推前端实时刷新）。"""
        try:
            from main_brain.memory.workmemory import get_work_memory
            get_work_memory().output_mem_write(content=content)
        except Exception as e:
            logger.warning(f"[mind] write output failed: {e}")

    # ── 上下文读取（best-effort，失败降级不阻塞）──────────
    def _recent_chat(self, limit: int = 4) -> str:
        try:
            from main_brain.memory.workmemory import get_work_memory
            entries = get_work_memory().output_mem_read()
            lines = []
            for e in entries[-limit:]:
                if e.get("user"):
                    lines.append("用户：" + str(e["user"]))
                if e.get("assistant"):
                    lines.append("猫猫：" + str(e["assistant"]))
            return "\n".join(lines) if lines else "（最近没有聊天）"
        except Exception:
            return "（无法读取）"

    def _recall(self, query: str) -> str:
        if not query or len(query) < 2:
            return "（暂无相关记忆浮现）"
        try:
            from main_brain.memory.core import search_memory
            hits = search_memory(query)[:3]
            if not hits:
                return "（暂无相关记忆）"
            lines = []
            for h in hits:
                ep = (h.get("payload") or {}).get("episodic")
                if not ep or not isinstance(ep, dict):
                    continue
                parts = []
                if ep.get("what"):
                    parts.append(str(ep["what"]))
                if ep.get("where"):
                    parts.append(f"地点：{ep['where']}")
                if ep.get("when"):
                    parts.append(f"时间：{ep['when']}")
                if not parts:
                    continue
                lines.append("• " + "，".join(parts))
            return "\n".join(lines) if lines else "（暂无相关记忆）"
        except Exception:
            return "（记忆检索失败）"

    def _concerns_snapshot(self) -> str:
        try:
            from main_brain.state import get_concerns
            top = get_concerns().all_effective(3)
            names = [n for n, e in top if e >= 0.1]
            return "、".join(names) if names else "（无特别在意的）"
        except Exception:
            return "（无）"

    def _wm_for_prompt(self, stream: dict) -> str:
        """格式化工记忆列表供 prompt 注入。

        working_memory 是 Day Tick 构建的"当前在意的几件事"列表，
        Sleep Tick 清空。每条上限 100 字符。
        """
        wm = (stream.get("working_memory") or [])
        if not wm:
            return "（暂无）"
        return "\n".join(f"- {str(item)[:100]}" for item in wm)

    def _dialogue_for_prompt(self, limit: int = 20) -> str:
        """从 output.json 读取最近对话记录，供 prompt 注入。

        Returns:
            格式如 "用户说：xxx\n猫猫说：yyy" 的文本，按 seq 倒序取最近 limit 条。
        """
        try:
            from main_brain.memory.workmemory import get_work_memory
            entries = get_work_memory().output_mem_read()
            if not entries:
                return "（暂无对话记录）"
            lines = []
            for e in entries[-limit:]:
                if e.get("user"):
                    lines.append(f"用户说：{str(e['user'])}")
                if e.get("assistant"):
                    lines.append(f"猫猫说：{str(e['assistant'])}")
            return "\n".join(lines) if lines else "（暂无对话记录）"
        except Exception:
            return "（暂无对话记录）"

    @staticmethod
    def _signals_for_prompt(signals: dict) -> str:
        """格式化感知信号为文本。"""
        if not signals:
            return "（无特殊变化）"
        parts = []
        if signals.get("user_message"):
            parts.append("用户刚说了话")
        if signals.get("idle_dropped"):
            parts.append("用户回来了")
        elif signals.get("idle_changed"):
            parts.append("用户活跃度有变化")
        if signals.get("period_changed"):
            parts.append(f"时间进入{signals['period_changed']}")
        if signals.get("day_changed"):
            parts.append("新的一天开始了")
        return "、".join(parts) if parts else "（无特殊变化）"

    def _time_of_day(self) -> str:
        from .clock import get_brain_clock
        return get_brain_clock().time_of_day_label()

    @staticmethod
    def _idle_desc(idle: int) -> str:
        if idle <= 0:
            return "志远刚找过你"
        mins = idle / 60.0
        if mins < 60:
            return f"志远已经 {int(mins)} 分钟没找你了"
        return f"志远已经 {mins / 60.0:.1f} 小时没找你了"

    def _persona(self) -> dict:
        try:
            from main_brain.state import get_self_model
            sm = get_self_model().get()
            return {
                "name": sm.get("name", "猫猫"),
                "traits": "、".join(sm.get("traits", []) or ["好奇", "随性"]),
            }
        except Exception:
            return {"name": "猫猫", "traits": "好奇、随性"}


# ── JSON 容错解析（直解 → ```json 块 → 首个 {...} → 关键词兜底）──
def _parse_decision(raw: str) -> dict:
    if not raw:
        return {"action": "rest", "thought": "empty", "mood_update": "平静"}
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    low = raw.lower()
    for action in ("think", "speak", "rest"):
        if action in low:
            return {"action": action, "thought": raw[:200], "mood_update": "平静"}
    return {"action": "rest", "thought": "parse_fallback_rest", "mood_update": "平静"}


# ── 单例 ───────────────────────────────────────────────────
_mind: AutonomousMind | None = None


def get_autonomous_mind() -> AutonomousMind:
    global _mind
    if _mind is None:
        _mind = AutonomousMind()
    return _mind
