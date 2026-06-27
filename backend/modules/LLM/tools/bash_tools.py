"""bash 工具 — 执行只读 shell 命令（T032 / FR-017）

三级安全体系（仿 Hermes approval.py）：
  1. HARDLINE — 无条件禁止（rm -rf /, mkfs, shutdown, fork bomb 等）
  2. DANGEROUS — 危险命令直接拒绝（rm 递归, chmod 777, curl|sh 等）
  3. 命令白名单 — 仅允许 ALLOWED_COMMANDS 内的只读命令
     + shell 元字符检查（禁止 ; && || | ` $() 注入）
"""
from __future__ import annotations

import logging
import re
import shlex
import subprocess

logger = logging.getLogger("tools.bash")

# ── 第 1 级：无条件禁止（HARDLINE）───────────────────────────────────────
# 命中则直接拒绝，不可绕过
_HARDLINE_PATTERNS: list[tuple[str, str]] = [
    (r'\brm\s+(-[^\s]*\s+)*(/|/\*|/ \*)(\s|$)', "递归删除根目录"),
    (r'\brm\s+(-[^\s]*\s+)*(/home|/root|/etc|/usr|/var|/bin|/boot|/lib|/sbin)',
     "递归删除系统目录"),
    (r'\bmkfs(\.[a-z0-9]+)?\b', "格式化文件系统"),
    (r'\bdd\b[^\n]*\bof=/dev/', "写入块设备"),
    (r':\(\)\s*\{\s*:\s*\|\s*:&\s*\}\s*;\s*:', "fork 炸弹"),
    (r'\bshutdown\b|\breboot\b|\bhalt\b|\bpoweroff\b', "关机/重启"),
    (r'\bkill\s+(-[^\s]+\s+)*-1\b', "杀死所有进程"),
    (r'\binit\s+[06]\b', "init 0/6 关机"),
]

# ── 第 2 级：危险命令（DANGEROUS）─────────────────────────────────────────
# 命中则直接拒绝（无审批交互，比 Hermes 更严格）
_DANGEROUS_PATTERNS: list[tuple[str, str]] = [
    (r'\brm\s+(-[^\s]*\s+)*/', "删除路径下的文件"),
    (r'\brm\s+-[^\s]*r', "递归删除"),
    (r'\bchmod\s+(-[^\s]*\s+)*(-R\s+)?777', "设置 777 权限"),
    (r'\bchown\s+(-[^\s]*)?R\s+', "递归更改所有者"),
    (r'\bDROP\s+(TABLE|DATABASE)\b', "SQL DROP"),
    (r'\bDELETE\s+FROM\b(?![^\n]*\bWHERE\b)', "SQL DELETE 无 WHERE"),
    (r'\bTRUNCATE\s+(TABLE)?\s*\w', "SQL TRUNCATE"),
    (r'\bsystemctl\s+(stop|restart|disable|mask)\b', "停止/重启系统服务"),
    (r'\bpkill\s+-9\b', "强制杀死进程"),
    (r'\b(killall|pkill)\s+(-[^\s]*\s+)*-(9|KILL)', "强制杀死进程"),
    (r'\b(curl|wget)\b.*\|\s*(ba)?sh\b', "管道远程内容到 shell"),
    (r'\bbash\s+<\(curl', "通过进程替换执行远程脚本"),
    (r'\bmv\s+.*\s+/[^ ]*\b', "移动文件到系统目录"),
    (r'\bfind\s+.*-exec', "find -exec"),
    (r'\btee\s+/[^ ]*\b', "tee 写入系统文件"),
]

# ── 命令白名单（第 3 级）──────────────────────────────────────────────────
_ALLOWED_COMMANDS = frozenset({
    "curl", "wget",
    "grep", "head", "cat", "sort", "uniq", "wc",
    "echo", "ls", "ps", "date",
    # 开发工具（python -c/node -e 等危险用法由 DANGEROUS 模式保护）
    "python", "python3", "node", "git", "pip", "npm", "npx",
})

# -- shell 元字符 — 禁止命令链接/注入 ------------------------------------
# 命令链接符（; && ||）在引号外出现时视为注入
# 管道（|）允许（危险管道由 DANGEROUS 模式覆盖）
# 注入（` $() ${}）在任何位置均禁止
_SHELL_INJECT = frozenset({"`", "$(", "${"})


def _has_unquoted_linker(command: str) -> str | None:
    """检查命令字符串中是否包含未在引号内的命令链接符（; && ||）。

    shlex.split 会把 `echo a; echo b` 里的 `;` 粘在 a 上（变成 `a;`），
    导致独立 token 检查漏掉。用逐字符引号状态机精准检测。
    Returns: 匹配的符号（如 ';', '&&', '||'）或 None。
    """
    in_single = False
    in_double = False
    i = 0
    while i < len(command):
        c = command[i]
        # 转义字符跳过下一个字符
        if c == '\\' and (in_double or not in_single):
            i += 2
            continue
        if c == "'" and not in_double:
            in_single = not in_single
        elif c == '"' and not in_single:
            in_double = not in_double
        elif not in_single and not in_double:
            if c == ';':
                return ';'
            if i + 1 < len(command):
                pair = command[i:i + 2]
                if pair in ('&&', '||'):
                    return pair
        i += 1
    return None

# -- 编译正则 ---------------------------------------------------------------
_RE_FLAGS = re.IGNORECASE | re.DOTALL
_HARDLINE_COMPILED = [(re.compile(p, _RE_FLAGS), d) for p, d in _HARDLINE_PATTERNS]
_DANGEROUS_COMPILED = [(re.compile(p, _RE_FLAGS), d) for p, d in _DANGEROUS_PATTERNS]

DEFAULT_TIMEOUT = 15
MAX_OUTPUT_CHARS = 5000


# ── 安全检查 ────────────────────────────────────────────────────────────
def _check_safety(command: str) -> str | None:
    """三级安全检查。返回 None = 安全，返回 str = 拒绝原因。"""
    # 第 1 级：HARDLINE
    for pattern, desc in _HARDLINE_COMPILED:
        if pattern.search(command):
            return f"禁止执行（HARDLINE: {desc}）"
    # 第 2 级：DANGEROUS
    for pattern, desc in _DANGEROUS_COMPILED:
        if pattern.search(command):
            return f"危险命令已拒绝（DANGEROUS: {desc}）"
    return None


def _is_single_command(command: str) -> bool:
    """检查命令是否包含 shell 注入或命令链接。

    三层保护：
      1. 引号状态机检测未引用的 ; && ||（防误判 User-Agent 里的 ;）
      2. $() `` ${} 注入检查
      3. shlex.split 验证引号配对
    管道 | 允许（危险管道由 DANGEROUS 模式覆盖）。
    """
    stripped = command.strip()
    if not stripped:
        return False
    # 第 1 层：未引用的命令链接符
    linker = _has_unquoted_linker(stripped)
    if linker:
        return False
    # 第 2 层：shell 注入
    for meta in _SHELL_INJECT:
        if meta in stripped:
            return False
    # 第 3 层：shlex 验证引号配对
    try:
        tokens = shlex.split(stripped)
    except ValueError:
        return False
    return len(tokens) > 0


# ── 执行 ──────────────────────────────────────────────────────────────────
def _bash_fn(command: str, timeout: int = DEFAULT_TIMEOUT) -> str:
    """执行 shell 命令（三级安全检查 + 命令白名单）。"""
    if not command or not isinstance(command, str):
        return "错误: command 不能为空"

    # 先做行为安全检查（HARDLINE + DANGEROUS）
    safety = _check_safety(command)
    if safety:
        return f"错误: {safety}"

    if not _is_single_command(command):
        return "错误: 仅允许单一命令，禁止命令链接（; && ||）和注入（` $() $）"

    # 再做命令白名单检查
    try:
        tokens = shlex.split(command.strip())
    except ValueError as e:
        return f"错误: 命令格式错误 — {e}"
    if not tokens:
        return "错误: command 为空"
    cmd_name = tokens[0].lower()
    if cmd_name not in _ALLOWED_COMMANDS:
        return (
            f"错误: 命令 '{cmd_name}' 不在白名单中\n"
            f"允许的命令: {', '.join(sorted(_ALLOWED_COMMANDS))}"
        )

    # 执行
    try:
        result = subprocess.run(
            command, shell=True,
            capture_output=True, text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return f"错误: 命令执行超时（{timeout}s）"
    except Exception as e:
        return f"错误: 执行失败 — {e}"

    output = (result.stdout or "") + (result.stderr or "")
    if not output:
        return "(无输出)"

    if len(output) > MAX_OUTPUT_CHARS:
        output = output[:MAX_OUTPUT_CHARS] + \
            f"\n... (仅显示前 {MAX_OUTPUT_CHARS} 字符) [exit: {result.returncode}]"
    else:
        output = output.rstrip()

    if result.returncode != 0 and not output:
        return f"命令退出码: {result.returncode}（无错误输出）"

    return output


# ── ToolDef ──────────────────────────────────────────────────────────────
try:
    from .registry import ToolDef

    BASH_TOOL = ToolDef(
        name="bash",
        description=(
            "执行只读 shell 命令，带三级安全检查和命令白名单。"
            "允许的命令: curl/wget/grep/head/cat/sort/uniq/wc/echo/ls/ps/date。"
            "危险命令自动拒绝。用于搜索信息、查看环境、读取文件。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "要执行的 shell 命令。示例: 'curl -s https://example.com'",
                },
                "timeout": {
                    "type": "integer",
                    "description": f"超时秒数（默认 {DEFAULT_TIMEOUT}s，最大 30）",
                    "default": DEFAULT_TIMEOUT,
                },
            },
            "required": ["command"],
        },
        fn=_bash_fn,
    )
except ImportError as e:
    logger.warning(f"[bash_tools] ToolDef import failed: {e}")
    BASH_TOOL = None


def register_bash_tools():
    """注册 bash 工具到 ToolRegistry"""
    if BASH_TOOL is None:
        logger.error("[bash_tools] BASH_TOOL 未定义，跳过注册")
        return
    from .registry import get_tool_registry
    reg = get_tool_registry()
    reg.register(BASH_TOOL)
    logger.info("[bash_tools] 已注册 bash 工具（三级安全）")
