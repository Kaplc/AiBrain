"""execute_code — 沙箱执行 Python 代码（T034 / FR-017）

参考 Hermes tools/code_execution_tool.py 模式，轻量子进程沙箱：
  1. 写临时 .py 文件 → 子进程运行
  2. 环境变量清洗（过滤 KEY/TOKEN/SECRET/PASSWORD）
  3. 超时 + 输出截断
  4. 临时目录隔离，不访问项目文件

注：Hermes 的 UDS RPC 沙箱（子进程调父进程工具）暂未实现，后续可按需加。
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import tempfile

logger = logging.getLogger("tools.execute_code")

DEFAULT_TIMEOUT = 30
MAX_OUTPUT_CHARS = 5000

# 环境变量清洗规则（仿 Hermes _SAFE_ENV_PREFIXES / _SECRET_SUBSTRINGS）
_SAFE_ENV_PREFIXES = (
    "PATH", "HOME", "USER", "LANG", "LC_", "TERM",
    "TMPDIR", "TMP", "TEMP", "SHELL", "LOGNAME",
    "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "PATHEXT",
    "OS", "PROCESSOR_", "NUMBER_OF_PROCESSORS",
)
_SECRET_SUBSTRINGS = ("KEY", "TOKEN", "SECRET", "PASSWORD", "PASSWD", "AUTH", "CREDENTIAL")


def _sanitize_env() -> dict[str, str]:
    """清洗环境变量：只保留安全前缀，去除含敏感子串的变量。"""
    clean = {}
    for k, v in os.environ.items():
        if any(secret in k.upper() for secret in _SECRET_SUBSTRINGS):
            continue
        if any(k.startswith(prefix) for prefix in _SAFE_ENV_PREFIXES):
            clean[k] = v
    return clean


def _execute_code_fn(code: str, timeout: int = DEFAULT_TIMEOUT) -> str:
    """在临时目录子进程执行 Python 代码，返回 stdout/stderr。"""
    if not code or not isinstance(code, str):
        return "错误: code 不能为空"

    # 基本安全检查：禁止危险系统调用
    dangerous_imports = ("shutil.rmtree", "os.remove", "os.unlink", "os.rmdir",
                         "subprocess", "ctypes", "multiprocessing")
    for di in dangerous_imports:
        if di in code:
            return f"错误: 代码中包含危险调用 '{di}'（已禁止）"

    try:
        with tempfile.TemporaryDirectory(prefix="exec_") as tmpdir:
            script_path = os.path.join(tmpdir, "_exec.py")
            with open(script_path, "w", encoding="utf-8") as f:
                f.write(code)

            env = _sanitize_env()
            result = subprocess.run(
                [sys.executable, script_path],
                capture_output=True, text=True,
                timeout=timeout,
                cwd=tmpdir,
                env=env,
            )
    except subprocess.TimeoutExpired:
        return f"错误: 代码执行超时（{timeout}s）"
    except Exception as e:
        return f"错误: 执行失败 — {e}"

    output = (result.stdout or "") + (result.stderr or "")
    if not output:
        return f"(代码执行成功，无输出) [exit: {result.returncode}]"

    if len(output) > MAX_OUTPUT_CHARS:
        output = output[:MAX_OUTPUT_CHARS] + \
            f"\n... (仅显示前 {MAX_OUTPUT_CHARS} 字符) [exit: {result.returncode}]"
    else:
        output = output.rstrip()

    return output


# ToolDef 定义
try:
    from .registry import ToolDef

    EXECUTE_CODE_TOOL = ToolDef(
        name="execute_code",
        description="在沙箱中执行 Python 代码。用于数据处理、计算、算法验证。环境变量经过清洗（过滤密钥），超时限制，临时目录隔离。",
        parameters={
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "要执行的 Python 代码（标准库可用，禁止危险系统调用）",
                },
                "timeout": {
                    "type": "integer",
                    "description": f"超时秒数（默认 {DEFAULT_TIMEOUT}s）",
                    "default": DEFAULT_TIMEOUT,
                },
            },
            "required": ["code"],
        },
        fn=_execute_code_fn,
    )
except ImportError as e:
    logger.warning(f"[execute_code_tools] ToolDef import failed: {e}")
    EXECUTE_CODE_TOOL = None


def register_execute_code_tools():
    """注册 execute_code 工具到 ToolRegistry"""
    if EXECUTE_CODE_TOOL is None:
        logger.error("[execute_code_tools] EXECUTE_CODE_TOOL 未定义，跳过注册")
        return
    from .registry import get_tool_registry
    reg = get_tool_registry()
    reg.register(EXECUTE_CODE_TOOL)
    logger.info("[execute_code_tools] 已注册 execute_code 工具")
