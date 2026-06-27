"""路径安全检查 — 防止工具越界访问文件系统

仿 Hermes tools/path_security.py。
所有文件读写工具（read_file / write_file / patch）在调用前校验路径安全。
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger("tools.path_security")

# 项目根目录（本文件在 backend/modules/LLM/tools/，向上 4 级到项目根）
_PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
)
_PROJECT_ROOT_PATH = Path(_PROJECT_ROOT).resolve()


def validate_within_project(path: str | Path) -> str | None:
    """确保路径解析后在项目根目录内。

    Returns:
        error_msg: 如果路径越界返回错误描述
        None: 路径安全
    """
    try:
        target = Path(path).expanduser().resolve()
        target.relative_to(_PROJECT_ROOT_PATH)
    except (ValueError, OSError) as e:
        return f"路径越界: {e}"
    return None


def has_traversal(path_str: str) -> bool:
    """快速检查是否包含 ``..`` 穿越。"""
    return ".." in Path(path_str).parts


def get_project_root() -> str:
    return _PROJECT_ROOT
