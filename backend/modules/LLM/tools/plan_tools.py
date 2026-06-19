"""
plan_tools — 计划文件管理工具

所有操作限制在 plan/ 目录下，不允许越权访问。
"""
import logging
import os
import shutil

from .registry import ToolDef

logger = logging.getLogger(__name__)

_PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
)
_PLAN_DIR = os.path.join(_PROJECT_ROOT, "plan")


def _vp(subpath: str) -> str | None:
    """验证路径，返回完整路径或 None"""
    full = os.path.normpath(os.path.join(_PLAN_DIR, subpath))
    return full if full.startswith(os.path.normpath(_PLAN_DIR)) else None


def _plan_fn(action: str = "", path: str = "", content: str = "", new_path: str = "") -> str:
    """管理 .claude/plan/ 下的文件和目录

    Args:
        action: 操作类型
        path: 相对 .claude/plan/ 的路径
        content: 写入内容（仅 write）
        new_path: 新路径（仅 rename/move）
    """
    if not action:
        return "需要指定 action 参数（list/read/write/delete/rename/mkdir/rmdir）"
    full = _vp(path) if path else _PLAN_DIR
    if full is None:
        return "错误：不允许操作 .claude/plan/ 以外的文件"

    os.makedirs(_PLAN_DIR, exist_ok=True)

    try:
        if action == "list":
            if not os.path.isdir(full):
                return f"目录不存在: .claude/plan/{path or '/'}"
            lines = []
            for fname in sorted(os.listdir(full)):
                fpath = os.path.join(full, fname)
                if os.path.isfile(fpath):
                    size = os.path.getsize(fpath)
                    size_str = f"{size:,}B" if size < 1024 else f"{size/1024:.1f}KB"
                    lines.append(f"  📄 {fname} ({size_str})")
                elif os.path.isdir(fpath):
                    lines.append(f"  📁 {fname}/")
            return "\n".join(lines) if lines else f"目录为空: .claude/plan/{path or '/'}"

        elif action == "read":
            if not os.path.isfile(full):
                return f"文件不存在: .claude/plan/{path}"
            with open(full, 'r', encoding='utf-8', errors='replace') as f:
                text = f.read()
            if len(text) > 20000:
                text = text[:20000] + "\n\n... (文件过长，仅显示前 20000 字符)"
            return text

        elif action == "write":
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, 'w', encoding='utf-8') as f:
                f.write(content)
            return f"已写入 .claude/plan/{path} ({len(content)} 字符)"

        elif action == "delete":
            if not os.path.exists(full):
                return f"不存在: .claude/plan/{path}"
            if os.path.isfile(full):
                os.remove(full)
                return f"已删除文件: .claude/plan/{path}"
            elif os.path.isdir(full):
                shutil.rmtree(full)
                return f"已删除目录: .claude/plan/{path}"

        elif action == "rename":
            new_full = _vp(new_path) if new_path else None
            if new_full is None:
                return "错误：新路径不允许在 .claude/plan/ 以外"
            if not os.path.exists(full):
                return f"不存在: .claude/plan/{path}"
            os.makedirs(os.path.dirname(new_full), exist_ok=True)
            os.rename(full, new_full)
            return f"已重命名: .claude/plan/{path} → .claude/plan/{new_path}"

        elif action == "mkdir":
            os.makedirs(full, exist_ok=True)
            return f"已创建目录: .claude/plan/{path}"

        elif action == "rmdir":
            if not os.path.isdir(full):
                return f"目录不存在: .claude/plan/{path}"
            os.rmdir(full)
            return f"已删除空目录: .claude/plan/{path}"

        else:
            return f"未知操作: {action}（支持: list/read/write/delete/rename/mkdir/rmdir）"

    except OSError as e:
        return f"操作失败: {e}"
    except Exception as e:
        return f"操作失败: {e}"


PLAN_TOOL = ToolDef(
    name="plan",
    description="管理 .claude/plan/ 下的计划文件和目录。支持 list/read/write/delete/rename/mkdir/rmdir。所有操作限制在 .claude/plan/ 内。",
    parameters={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["list", "read", "write", "delete", "rename", "mkdir", "rmdir"],
                "description": "list=列出, read=读取, write=写入, delete=删除, rename=重命名, mkdir=创建目录, rmdir=删除空目录",
            },
            "path": {
                "type": "string",
                "description": "相对 .claude/plan/ 的路径。如 'chat-tool-calling.md'、'subdir/'",
            },
            "content": {
                "type": "string",
                "description": "写入内容（仅 write 操作需要）",
            },
            "new_path": {
                "type": "string",
                "description": "新路径（仅 rename 操作需要）",
            },
        },
        "required": ["action"],
    },
    fn=_plan_fn,
)


def register_plan_tools():
    from .registry import get_tool_registry
    reg = get_tool_registry()
    reg.register(PLAN_TOOL)
