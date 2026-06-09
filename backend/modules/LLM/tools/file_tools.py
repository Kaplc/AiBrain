"""
file_tools — 文件搜索工具

封装 grep/rg 搜索，供 LLM function calling 调用。
"""
import glob as glob_mod
import logging
import os
import subprocess

from .registry import ToolDef

logger = logging.getLogger(__name__)

# 项目根目录（本文件在 backend/modules/LLM/tools/，向上 4 级到项目根）
_PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
)

# 默认搜索目录（排除无关目录）
_DEFAULT_EXCLUDE = (
    "venv312", ".venv", "__pycache__", ".git", "node_modules",
    "dist", ".claude", "logs", "qdrant/storage", "rag/lightrag_data",
    "models", ".aibrain",
)


def _grep_search_fn(
    pattern: str,
    path: str = "",
    file_pattern: str = "",
    max_results: int = 50,
    offset: int = 0,
    output_mode: str = "content",
    context: int = 0,
) -> str:
    """使用 grep 在项目文件中搜索文本"""
    search_dir = os.path.join(_PROJECT_ROOT, path) if path else _PROJECT_ROOT
    if not os.path.isdir(search_dir):
        return f"路径不存在: {search_dir}"

    exclude_args = []
    for d in _DEFAULT_EXCLUDE:
        exclude_args.extend(["--exclude-dir", d])

    include_args = []
    if file_pattern:
        include_args.extend(["--include", file_pattern])

    cmd = ["grep", "-rn", "--color=never"] + exclude_args + include_args
    if context > 0:
        cmd.extend(["-C", str(context)])
    if output_mode == "count":
        cmd.extend(["-c"])
    cmd.extend([pattern, search_dir])

    try:
        result = subprocess.run(cmd, capture_output=True, timeout=15)
        stdout = result.stdout.decode('utf-8', errors='replace')
        if result.returncode == 1 and not stdout:
            return f"没有找到匹配 '{pattern}' 的结果"

        all_lines = stdout.strip().split("\n")
        total = len(all_lines)

        if output_mode == "count":
            return f"匹配文件:\n{stdout.strip()[:2000]}"

        page = all_lines[offset:offset + max_results]
        truncated = []
        for line in page:
            if len(line) > 300:
                line = line[:300] + "..."
            truncated.append(line)

        output = "\n".join(truncated)
        summary = f"找到 {total} 个匹配，显示 {offset+1}-{min(offset+max_results, total)}：\n\n{output}"
        if offset + max_results < total:
            summary += f"\n... 还有 {total - offset - max_results} 个结果未显示（使用 offset={offset + max_results} 查看下一页）"
        return summary
    except FileNotFoundError:
        return "系统未安装 grep，请使用 ripgrep(rg) 或安装 grep"
    except subprocess.TimeoutExpired:
        return "搜索超时（15s），请缩小搜索范围"
    except Exception as e:
        return f"搜索失败: {e}"


def _rg_search_fn(
    pattern: str,
    path: str = "",
    file_pattern: str = "",
    max_results: int = 50,
    offset: int = 0,
    output_mode: str = "content",
    context: int = 0,
) -> str:
    """使用 ripgrep (rg) 在项目文件中搜索文本（更快）"""
    search_dir = os.path.join(_PROJECT_ROOT, path) if path else _PROJECT_ROOT
    if not os.path.isdir(search_dir):
        return f"路径不存在: {search_dir}"

    cmd = ["rg", "--no-heading", "--color=never", "-n"]
    for d in _DEFAULT_EXCLUDE:
        cmd.extend(["--glob", f"!{d}/**"])
    if file_pattern:
        cmd.extend(["--glob", file_pattern])
    if context > 0:
        cmd.extend(["-C", str(context)])
    if output_mode == "count":
        cmd.append("-c")
    elif output_mode == "files_only":
        cmd.append("-l")
    cmd.extend([pattern, search_dir])

    try:
        result = subprocess.run(cmd, capture_output=True, timeout=15)
        stdout = result.stdout.decode('utf-8', errors='replace')
        if result.returncode == 1:
            return f"没有找到匹配 '{pattern}' 的结果"

        all_lines = stdout.strip().split("\n")
        total = len(all_lines)

        if output_mode == "files_only":
            return f"匹配文件 ({total} 个):\n" + "\n".join(all_lines[:max_results])

        if output_mode == "count":
            return f"匹配计数:\n{stdout.strip()[:2000]}"

        page = all_lines[offset:offset + max_results]
        truncated = []
        for line in page:
            if len(line) > 300:
                line = line[:300] + "..."
            truncated.append(line)

        output = "\n".join(truncated)
        summary = f"找到 {total} 个匹配，显示 {offset+1}-{min(offset+max_results, total)}：\n\n{output}"
        if offset + max_results < total:
            summary += f"\n... 还有 {total - offset - max_results} 个结果未显示（使用 offset={offset + max_results} 查看下一页）"
        return summary
    except FileNotFoundError:
        return "系统未安装 ripgrep(rg)，请使用 grep 或安装 rg"
    except subprocess.TimeoutExpired:
        return "搜索超时（15s），请缩小搜索范围"
    except Exception as e:
        return f"搜索失败: {e}"


def _detect_search_tool() -> tuple[str, callable]:
    """自动检测使用 rg 还是 grep"""
    try:
        subprocess.run(["rg", "--version"], capture_output=True, timeout=3)
        return "ripgrep", _rg_search_fn
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return "grep", _grep_search_fn


def _build_content_search_fn():
    """包装 _file_search_fn 为 content 模式（兼容旧 _file_search_fn 签名）"""
    tool, fn = _detect_search_tool()
    def wrapper(pattern="", path="", file_pattern="", max_results=20, offset=0, output_mode="content", context=0):
        return fn(pattern=pattern, path=path, file_pattern=file_pattern, max_results=max_results, offset=offset, output_mode=output_mode, context=context)
    return wrapper


def _file_search_fn(
    pattern: str = "",
    target: str = "content",
    path: str = "",
    file_glob: str = "",
    limit: int = 50,
    offset: int = 0,
    output_mode: str = "content",
    context: int = 0,
) -> str:
    """搜索文件内容或按文件名查找

    Args:
        pattern: 内容搜索时为正则表达式，文件搜索时为 glob 模式（如 '*.py'）
        target: "content" 搜索文件内容，"files" 按文件名查找
        path: 相对项目根的搜索路径
        file_glob: 文件匹配模式（仅 content 模式），如 '*.py'
        limit: 最多返回结果数（默认 50）
        offset: 跳过前 N 个结果（分页）
        output_mode: "content" 显示匹配行, "files_only" 仅文件名, "count" 仅计数
        context: 匹配行前后各显示 N 行上下文（仅 content 模式）
    """
    if target == "files":
        return _search_by_name(pattern, path, limit, offset)

    tool_name, fn = _detect_search_tool()
    logger.info(f"[file_search] using {tool_name}, pattern={pattern!r}, path={path or '/'}")
    return fn(
        pattern=pattern, path=path, file_pattern=file_glob,
        max_results=limit, offset=offset, output_mode=output_mode, context=context,
    )


def _search_by_name(pattern: str, path: str = "", limit: int = 50, offset: int = 0) -> str:
    """按文件名搜索（glob 模式），结果按修改时间排序"""
    search_dir = os.path.join(_PROJECT_ROOT, path) if path else _PROJECT_ROOT
    if not os.path.isdir(search_dir):
        return f"路径不存在: {search_dir}"

    all_matches = []
    for fpath in glob_mod.glob(os.path.join(search_dir, "**", pattern), recursive=True):
        if not os.path.isfile(fpath):
            continue
        rel = os.path.relpath(fpath, _PROJECT_ROOT)
        if any(excl in rel.replace("\\", "/").split("/") for excl in _DEFAULT_EXCLUDE):
            continue
        try:
            mtime = os.path.getmtime(fpath)
            size = os.path.getsize(fpath)
            size_str = f"{size:,}B" if size < 1024 else f"{size/1024:.1f}KB"
            all_matches.append((mtime, rel, size_str))
        except OSError:
            all_matches.append((0, rel, "?"))

    # 按修改时间排序（最新的在前）
    all_matches.sort(key=lambda x: x[0], reverse=True)
    total = len(all_matches)
    matches = all_matches[offset:offset + limit]

    if not all_matches:
        return f"没有找到匹配 '{pattern}' 的文件"

    lines = [f"  {rel} ({size})" for _, rel, size in matches]
    output = "\n".join(lines)
    result = f"找到 {total} 个文件，显示 {offset+1}-{min(offset+limit, total)}：\n\n{output}"
    if offset + limit < total:
        result += f"\n... 还有 {total - offset - limit} 个结果"
    return result


FILE_SEARCH_TOOL = ToolDef(
    name="file_search",
    description="Search file contents or find files by name. Use this instead of grep/rg/find/ls. Ripgrep-backed, faster than shell equivalents.\n\nContent search (target='content'): Regex search inside files. Output modes: full matches with line numbers, file paths only, or match counts.\n\nFile search (target='files'): Find files by glob pattern (e.g., '*.py', '*config*'). Results sorted by modification time.",
    parameters={
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Regex pattern for content search, or glob pattern (e.g., '*.py') for file search",
            },
            "target": {
                "type": "string",
                "enum": ["content", "files"],
                "description": "'content' searches inside file contents, 'files' searches for files by name",
                "default": "content",
            },
            "path": {
                "type": "string",
                "description": "Directory to search in (default: project root)",
                "default": "",
            },
            "file_glob": {
                "type": "string",
                "description": "Filter files by pattern in content mode (e.g., '*.py' to only search Python files)",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of results to return (default: 50)",
                "default": 50,
            },
            "offset": {
                "type": "integer",
                "description": "Skip first N results for pagination (default: 0)",
                "default": 0,
            },
            "output_mode": {
                "type": "string",
                "enum": ["content", "files_only", "count"],
                "description": "Output format for content mode: 'content' shows matching lines, 'files_only' lists file paths, 'count' shows match counts per file",
                "default": "content",
            },
            "context": {
                "type": "integer",
                "description": "Number of context lines before and after each match (content mode only)",
                "default": 0,
            },
        },
        "required": ["pattern"],
    },
    fn=_file_search_fn,
)


# ════════════════════════════════════════════════════════════
# read_file — 读取文件内容
# ════════════════════════════════════════════════════════════

def _read_file_fn(path: str, max_lines: int = 0, offset: int = 0) -> str:
    """读取项目文件内容

    Args:
        path: 相对项目根的文件路径，如 'backend/modules/chat/loop.py'
        max_lines: 返回行数（0=全部，默认 0）
        offset: 起始行号（0 开头，默认 0）
    """
    full_path = os.path.join(_PROJECT_ROOT, path)
    if not os.path.isfile(full_path):
        return f"文件不存在: {path}"

    # 安全检查：禁止读取超出项目根的文件
    if not os.path.realpath(full_path).startswith(os.path.realpath(_PROJECT_ROOT)):
        return "不允许读取项目根以外的文件"

    try:
        with open(full_path, 'r', encoding='utf-8', errors='replace') as f:
            all_lines = f.readlines()
    except Exception as e:
        return f"读取失败: {e}"

    total = len(all_lines)
    if offset >= total:
        return f"起始行 {offset} 超出文件总行数 {total}"

    if max_lines <= 0:
        end = total
    else:
        end = min(offset + max_lines, total)
    lines = all_lines[offset:end]
    numbered = [f"{offset + i + 1:6d} | {l.rstrip()}" for i, l in enumerate(lines)]

    result = f"文件: {path} ({total} 行，显示 {offset+1}-{end})\n"
    result += "\n".join(numbered)
    if end < total:
        result += f"\n... 剩余 {total - end} 行，请调整 offset 继续读取"
    return result


READ_FILE_TOOL = ToolDef(
    name="read_file",
    description="读取项目文件内容。当需要查看完整的函数实现、配置文件、文档时使用。",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "相对项目根的文件路径，如 'backend/modules/chat/loop.py'、'web/src/views/ChatView.vue'",
            },
            "max_lines": {
                "type": "integer",
                "description": "返回行数（0=读取全部，默认 0）",
                "default": 0,
            },
            "offset": {
                "type": "integer",
                "description": "起始行号（0 开头，默认 0）",
                "default": 0,
            },
        },
        "required": ["path"],
    },
    fn=_read_file_fn,
)


# ════════════════════════════════════════════════════════════
# list_directory — 列出目录内容
# ════════════════════════════════════════════════════════════

def _list_directory_fn(path: str = "", max_depth: int = 1) -> str:
    """列出项目目录结构

    Args:
        path: 相对项目根的目录路径，空则列出根目录
        max_depth: 递归深度（默认 1，最大 3）
    """
    search_dir = os.path.join(_PROJECT_ROOT, path) if path else _PROJECT_ROOT
    if not os.path.isdir(search_dir):
        return f"目录不存在: {path or '/'}"

    max_depth = min(max_depth, 3)  # 限制最大深度
    lines = []
    base = search_dir.rstrip(os.sep)

    for root, dirs, files in os.walk(search_dir):
        # 跳过排除目录
        dirs[:] = [d for d in dirs if d not in _DEFAULT_EXCLUDE and not d.startswith('.')]

        rel = os.path.relpath(root, base)
        if rel == '.':
            depth = 0
        else:
            depth = rel.count(os.sep) + 1

        if depth > max_depth:
            dirs.clear()
            continue

        indent = "  " * depth
        if depth == 0:
            lines.append(f"📁 {path or '/'}")
        else:
            lines.append(f"{indent}📁 {os.path.basename(root)}/")

        for f in sorted(files):
            if f.startswith('.'):
                continue
            fpath = os.path.join(root, f)
            try:
                size = os.path.getsize(fpath)
                size_str = f"{size:,}B" if size < 1024 else f"{size/1024:.1f}KB" if size < 1024*1024 else f"{size/1024/1024:.1f}MB"
                lines.append(f"{indent}  📄 {f} ({size_str})")
            except OSError:
                lines.append(f"{indent}  📄 {f}")

    return "\n".join(lines) if len(lines) <= 200 else "\n".join(lines[:200]) + f"\n... 共 {len(lines)} 项，仅显示前 200"


LIST_DIRECTORY_TOOL = ToolDef(
    name="list_directory",
    description="列出项目目录结构。当需要了解文件布局、查找文件位置时使用。",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "相对项目根的目录路径，如 'backend/routes'、'web/src/views'，空则列出根目录",
            },
            "max_depth": {
                "type": "integer",
                "description": "递归深度（默认 1，最大 3）",
                "default": 1,
            },
        },
    },
    fn=_list_directory_fn,
)


# ════════════════════════════════════════════════════════════
# web_fetch — 获取网页内容
# ════════════════════════════════════════════════════════════

def _web_fetch_fn(url: str, max_chars: int = 5000) -> str:
    """获取网页内容

    Args:
        url: 网页 URL
        max_chars: 最多返回字符数（默认 5000）
    """
    import urllib.request
    import urllib.error

    if not url.startswith(('http://', 'https://')):
        return "只支持 http/https 协议"

    try:
        req = urllib.request.Request(
            url,
            headers={'User-Agent': 'AiBrain/1.0'},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            content = resp.read()
            # 尝试检测编码
            encoding = resp.headers.get_content_charset() or 'utf-8'
            text = content.decode(encoding, errors='replace')
    except urllib.error.HTTPError as e:
        return f"HTTP {e.code}: {e.reason}"
    except urllib.error.URLError as e:
        return f"请求失败: {e.reason}"
    except Exception as e:
        return f"获取失败: {e}"

    # 提取纯文本（简单去 HTML 标签）
    import re
    text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL)
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()

    if len(text) > max_chars:
        text = text[:max_chars] + f"\n... (仅显示前 {max_chars} 字符，共 {len(text)} 字符)"
    return text


WEB_FETCH_TOOL = ToolDef(
    name="web_fetch",
    description="获取网页内容。当需要查阅在线文档、API 参考时使用。",
    parameters={
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "网页 URL，如 'https://api-docs.deepseek.com'",
            },
            "max_chars": {
                "type": "integer",
                "description": "最多返回字符数（默认 5000）",
                "default": 5000,
            },
        },
        "required": ["url"],
    },
    fn=_web_fetch_fn,
)


def register_file_tools():
    """注册文件搜索工具到 ToolRegistry"""
    from .registry import get_tool_registry
    reg = get_tool_registry()
    reg.register(FILE_SEARCH_TOOL)
    reg.register(READ_FILE_TOOL)
    reg.register(LIST_DIRECTORY_TOOL)
    reg.register(WEB_FETCH_TOOL)
