"""Activity Registry — 文件化活动定义发现与加载（取代硬编码 ACTIVITIES）

核心功能：
  1. 扫描 activities/ 目录下所有 .md 文件，解析 frontmatter
  2. 每个活动 = Markdown 文件 + YAML-like frontmatter
  3. Handler 注册：activity -> handler 函数
  4. 运行时自省：list_activities() 返回所有定义

Frontmatter 格式（标准 Markdown frontmatter）：

  ---
  name: self_learn
  description: 自主学习活动
  handler_name: run_self_learn        # 指向 registry 中注册的 handler 函数
  tick_types: [medium_tick, long_tick]
  autonomy_min: assist
  max_cycles: 5
  allowed_tools: [web_search, web_fetch, memory_search]
  conditions:
    min_idle_seconds: 180
    require_curiosity_threshold: 0.6
    require_open_loops_or_goals: true
  ---

  # 自主学习

  Body 内容用于展示 / 文档，运行时不加载。

使用方式：

  from main_brain.activities.registry import (
      get_activity, list_activities, register_handler, run_activity,
  )
  act = get_activity("self_learn")
  act.name, act.description, act.allowed_tools, act.handler
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger("main_brain.activities")

# ── 活动定义 dataclass ─────────────────────────────────────────

_ACTIVITIES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)))


@dataclass
class ActivityDef:
    """单个活动的定义（从 frontmatter 解析而来）。"""
    name: str = ""
    description: str = ""
    handler_name: str = ""            # 注册的 handler 函数名
    tick_types: list[str] = field(default_factory=lambda: ["medium_tick"])
    autonomy_min: str = "assist"      # observe / assist / autonomous / high_autonomy
    max_cycles: int = 3
    allowed_tools: list[str] = field(default_factory=list)
    conditions: dict = field(default_factory=dict)
    source_file: str = ""             # 来源文件路径，调试用

    # 运行时绑定（加载后填充）
    handler: Callable | None = None


# ── 全局注册表 ──────────────────────────────────────────────────

_activities: dict[str, ActivityDef] = {}   # name -> ActivityDef
_handlers: dict[str, Callable] = {}        # handler_name -> Callable


# ── Frontmatter 解析器（YAML-like，无外部依赖）──────────────────

def _parse_frontmatter(text: str) -> dict:
    """解析 Markdown 前端的 YAML-like frontmatter 块。

    支持：
      key: value                → 字符串
      key: [a, b, c]            → 列表
      key:
        sub: value              → 嵌套 dict
      key:
        - item                  → 列表（块格式）
      # 注释

    Returns:
        dict | None: 解析后的数据，无 frontmatter 返回空 dict
    """
    # 匹配 --- 包裹的 frontmatter 块
    m = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if not m:
        return {}
    raw = m.group(1).strip()
    return _parse_yaml_like(raw)


def _parse_yaml_like(raw: str) -> dict:
    """递归解析 YAML-like 键值对（无外部依赖）。

    支持：K: V / K: [a,b] / K: {a:b} / 缩进嵌套 K:\n  K2: V2。
    注意：block 列表格式（- item）仅支持在顶层 K: 后直接使用内联
    [a, b] 语法，不支持多行 - item 块格式（当前无此需求）。
    """
    result: dict = {}
    current: dict = result
    stack: list[dict] = []
    # 追踪块缩进（用于退出嵌套 dict）
    indent_stack: list[int] = []
    lines = raw.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            i += 1
            continue

        # K: V 对
        colon_pos = stripped.find(":")
        if colon_pos == -1:
            i += 1
            continue

        key = stripped[:colon_pos].strip()
        value_part = stripped[colon_pos + 1:].strip()

        # 退出嵌套（当前行缩进 <= 父级锁进）
        while indent_stack and _get_indent(line) <= indent_stack[-1]:
            indent_stack.pop()
            if stack:
                current = stack.pop()

        # 缩进块：K: 后跟子内容 → 进入子 dict
        if value_part == "":
            child: dict = {}
            current[key] = child
            stack.append(current)
            indent_stack.append(_get_indent(line))
            current = child
            i += 1
            continue

        # 单行值
        if value_part.startswith("["):
            current[key] = _parse_bracket_list(value_part)
        elif value_part.startswith("{"):
            current[key] = _parse_curly_dict(value_part)
        else:
            current[key] = _parse_scalar(value_part)
        i += 1

    return result


def _get_indent(line: str) -> int:
    """获取行的缩进列数（tab 算 2 空格）。"""
    s = line.lstrip()
    if not s:
        return 0
    return len(line) - len(s)


def _parse_scalar(v: str) -> Any:
    """解析标量值（字符串 / 数字 / 布尔）。"""
    v = v.strip()
    if not v:
        return ""
    if v.lower() == "true":
        return True
    if v.lower() == "false":
        return False
    if v.lower() == "null" or v.lower() == "none":
        return None
    # 整数
    try:
        if v.isdigit() or (v.startswith("-") and v[1:].isdigit()):
            return int(v)
    except ValueError:
        pass
    # 浮点数
    try:
        if "." in v:
            return float(v)
    except ValueError:
        pass
    # 去除引号
    if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
        return v[1:-1]
    return v


def _parse_bracket_list(v: str) -> list:
    """解析 [a, b, c] 格式的列表。"""
    inner = v.strip()
    if inner.startswith("[") and inner.endswith("]"):
        inner = inner[1:-1]
    if not inner.strip():
        return []
    items = []
    for item in inner.split(","):
        item = item.strip()
        if item:
            items.append(_parse_scalar(item))
    return items


def _parse_curly_dict(v: str) -> dict:
    """解析 {k: v, k2: v2} 格式的内联 dict。"""
    inner = v.strip()
    if inner.startswith("{") and inner.endswith("}"):
        inner = inner[1:-1]
    if not inner.strip():
        return {}
    result = {}
    for pair in inner.split(","):
        pair = pair.strip()
        if ":" in pair:
            k, v = pair.split(":", 1)
            result[k.strip()] = _parse_scalar(v.strip())
    return result


def _parse_inline_dict(text: str) -> dict:
    """解析单行字典字符串 'key: value'。"""
    colon = text.find(":")
    if colon == -1:
        return {}
    return {text[:colon].strip(): _parse_scalar(text[colon + 1:].strip())}


# ── 发现与加载 ──────────────────────────────────────────────────


def _discover_activity_files() -> list[str]:
    """扫描 activities/ 目录下的所有 .md 文件（不递归进入 addons 子目录）。"""
    files = []
    for entry in os.listdir(_ACTIVITIES_DIR):
        if entry.endswith(".md") and entry != "__init__.md":
            path = os.path.join(_ACTIVITIES_DIR, entry)
            if os.path.isfile(path):
                files.append(path)
    # 检查 addons/ 子目录（第三方扩展）
    addons_dir = os.path.join(_ACTIVITIES_DIR, "addons")
    if os.path.isdir(addons_dir):
        for entry in os.listdir(addons_dir):
            if entry.endswith(".md"):
                path = os.path.join(addons_dir, entry)
                if os.path.isfile(path):
                    files.append(path)
    return sorted(files)


def load_activity_file(path: str) -> ActivityDef | None:
    """加载单个活动定义文件，返回 ActivityDef。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except Exception as e:
        logger.warning(f"[registry] failed to read {path}: {e}")
        return None

    data = _parse_frontmatter(text)
    if not data:
        logger.debug(f"[registry] no frontmatter in {path}, skipping")
        return None

    name = str(data.get("name", "")).strip()
    if not name:
        logger.warning(f"[registry] activity file {path} missing 'name' in frontmatter")
        return None

    act = ActivityDef(
        name=name,
        description=str(data.get("description", ""))[:200],
        handler_name=str(data.get("handler_name", name)).strip(),
        tick_types=data.get("tick_types", ["medium_tick"]),
        autonomy_min=str(data.get("autonomy_min", "assist")).strip(),
        max_cycles=int(data.get("max_cycles", 3)),
        allowed_tools=data.get("allowed_tools", []),
        conditions=data.get("conditions", {}),
        source_file=path,
    )
    # 绑定 handler
    act.handler = _handlers.get(act.handler_name)
    return act


def reload_all() -> dict[str, ActivityDef]:
    """重新扫描并加载所有活动定义文件。"""
    discovered: dict[str, ActivityDef] = {}
    for path in _discover_activity_files():
        act = load_activity_file(path)
        if act is not None:
            if act.name in discovered:
                logger.warning(
                    f"[registry] duplicate activity name '{act.name}' "
                    f"({path} vs {discovered[act.name].source_file})"
                )
            discovered[act.name] = act

    global _activities
    _activities = discovered
    logger.info(
        f"[registry] loaded {len(discovered)} activities: "
        f"{', '.join(sorted(discovered.keys()))}"
    )
    return discovered


# ── Handler 注册 ────────────────────────────────────────────────


def register_handler(name: str, fn: Callable) -> None:
    """注册一个活动 handler 函数。

    注册前自动 ensure_loaded 确保活动定义已从 .md 文件加载。

    实际 handler 签名（由 daemon 调用时传递）：

        handler(run, tick_type, reason, tick_input, ctx, *,
                max_cycles=3, timeout=30.0, cfg=None, dry_run=False, **kwargs) -> dict

    返回 dict 必须包含字段：
        ok, stop_reason, thought_summary, actions, cycle_count,
        activity_result, learning_hints, needs_gate

    Args:
        name: handler_name（对应 frontmatter 中的 handler_name）
        fn: 处理函数
    """
    ensure_loaded()  # 确保活动定义已加载，避免先注册后加载的时序问题
    _handlers[name] = fn
    # 更新已加载的活动
    for act in _activities.values():
        if act.handler_name == name:
            act.handler = fn
    logger.debug(f"[registry] handler '{name}' registered ({fn.__name__})")


def unregister_handler(name: str) -> None:
    """取消注册 handler。"""
    _handlers.pop(name, None)
    for act in _activities.values():
        if act.handler_name == name:
            act.handler = None


# ── 校验接口 ────────────────────────────────────────────────────


def validate_handlers() -> list[str]:
    """检查所有已加载活动的 handler 是否就绪，返回缺失列表。

    在 daemon 完成全部 register_handler 调用后调用一次。
    """
    missing = []
    for name, act in _activities.items():
        if act.handler is None:
            missing.append(f"{name}(handler_name={act.handler_name})")
            logger.warning(
                f"[registry] activity '{name}' has no registered handler "
                f"'{act.handler_name}' — will fail at runtime"
            )
    if missing:
        logger.warning(f"[registry] {len(missing)} activities missing handlers: {missing}")
    else:
        logger.info(f"[registry] all {len(_activities)} activities have registered handlers")
    return missing


# ── 查询接口 ────────────────────────────────────────────────────


def get_activity(name: str) -> ActivityDef | None:
    """按名称获取活动定义。"""
    return _activities.get(name)


def list_activities() -> dict[str, ActivityDef]:
    """返回所有已加载的活动定义的快照。"""
    return dict(_activities)


def get_active_activity_names() -> list[str]:
    """返回所有可用活动名的有序列表（兼容 contracts.ACTIVITIES）。"""
    return sorted(_activities.keys())


def get_handler_for_activity(name: str) -> Callable | None:
    """获取活动对应的 handler 函数。"""
    act = _activities.get(name)
    if act is None:
        return None
    return act.handler


def run_activity(name: str, *args, **kwargs) -> Any:
    """按名称运行活动 handler。如果 handler 不存在则返回默认失败 dict。

    Args:
        name: 活动名
        args/kwargs: 透传给 handler 的参数

    Returns:
        handler 的返回值 dict，或失败 dict
    """
    act = _activities.get(name)
    if act is None:
        logger.warning(f"[registry] cannot run unknown activity '{name}'")
        return {"ok": False, "skipped": True, "reason": f"unknown activity: {name}"}
    if act.handler is None:
        logger.warning(f"[registry] activity '{name}' has no handler '{act.handler_name}'")
        return {"ok": False, "skipped": True,
                "reason": f"no handler for '{act.handler_name}'"}
    try:
        return act.handler(*args, **kwargs)
    except Exception as e:
        logger.exception(f"[registry] activity '{name}' handler failed: {e}")
        return {"ok": False, "skipped": True, "reason": str(e)}


# ── 初始化 ──────────────────────────────────────────────────────

_loaded = False


def ensure_loaded() -> dict[str, ActivityDef]:
    """确保活动定义已加载（幂等）。"""
    global _loaded
    if not _loaded:
        reload_all()
        _loaded = True
    return _activities
