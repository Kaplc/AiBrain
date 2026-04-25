"""Console MCP - 控制前端控制台的 MCP 服务器"""
import os
import json
import time
import threading
from pathlib import Path
from fastmcp import FastMCP

mcp = FastMCP("console_mcp")

# 命令队列文件路径
_QUEUE_FILE = os.path.join(os.path.expanduser("~"), ".aibrain", "console_queue.json")
os.makedirs(os.path.dirname(_QUEUE_FILE), exist_ok=True)


def _write_queue(commands):
    """写入命令队列"""
    with open(_QUEUE_FILE, 'w', encoding='utf-8') as f:
        json.dump({"commands": commands, "timestamp": int(time.time())}, f)


def _read_queue():
    """读取命令队列"""
    if not os.path.exists(_QUEUE_FILE):
        return []
    try:
        with open(_QUEUE_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get("commands", [])
    except Exception:
        return []


def _clear_queue():
    """清空命令队列"""
    _write_queue([])


# ── 基础控制 ──────────────────────────────────────────────

@mcp.tool()
def console_log(message: str, level: str = "info") -> str:
    """
    向前端控制台输出一条日志
    Args:
        message: 日志内容
        level: 日志级别 (info/success/warn/error/cmd)
    """
    if level not in ("info", "success", "warn", "error", "cmd"):
        level = "info"
    cmds = _read_queue()
    cmds.append({"action": "log", "message": str(message), "level": level})
    _write_queue(cmds)
    return f"[console] log: {message} ({level})"


@mcp.tool()
def console_clear() -> str:
    """清空前端控制台输出"""
    cmds = _read_queue()
    cmds.append({"action": "clear"})
    _write_queue(cmds)
    return "[console] cleared"


@mcp.tool()
def console_toggle() -> str:
    """切换前端控制台显示/隐藏"""
    cmds = _read_queue()
    cmds.append({"action": "toggle"})
    _write_queue(cmds)
    return "[console] toggled"


@mcp.tool()
def console_exec(command: str) -> str:
    """
    在前端控制台执行一条命令
    Args:
        command: 要执行的命令（如 status, time, help 等）
    """
    cmds = _read_queue()
    cmds.append({"action": "exec", "command": str(command)})
    _write_queue(cmds)
    return f"[console] exec: {command}"


# ── 系统信息 ──────────────────────────────────────────────

@mcp.tool()
def console_status() -> dict:
    """获取前端控制台状态"""
    queue = _read_queue()
    return {
        "queue_length": len(queue),
        "queue_file": _QUEUE_FILE,
        "last_updated": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


@mcp.tool()
def console_queue() -> list:
    """查看当前待执行的命令队列"""
    return _read_queue()


@mcp.tool()
def console_clear_queue() -> str:
    """清空命令队列（不执行）"""
    _clear_queue()
    return "[console] queue cleared"


if __name__ == "__main__":
    mcp.run()