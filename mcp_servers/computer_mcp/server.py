"""Computer MCP - 计算机控制 MCP 服务器（键盘、鼠标、文件、系统操作）"""
import os
import subprocess
from pathlib import Path
import pyperclip
import pyautogui as pag
import psutil
import platform
from fastmcp import FastMCP

mcp = FastMCP("computer_mcp")

# 安全设置：pyautogui 的安全模式（防误操作）
pag.PAUSE = 0.1  # 每个操作后暂停 100ms

# ── 鼠标控制 ──────────────────────────────────────────────

@mcp.tool()
def mouse_move(x: int, y: int) -> str:
    """移动鼠标到指定坐标"""
    pag.moveTo(x, y, duration=0.2)
    return f"鼠标已移动到 ({x}, {y})"


@mcp.tool()
def mouse_click(button: str = "left") -> str:
    """鼠标点击 (left / right / middle)"""
    btn = button.lower()
    if btn == "left":
        pag.click()
    elif btn == "right":
        pag.rightClick()
    elif btn == "middle":
        pag.middleClick()
    else:
        return f"错误: 不支持的按钮 '{button}'，支持 left/right/middle"
    return f"鼠标已{btn}点击"


@mcp.tool()
def mouse_double_click() -> str:
    """鼠标左键双击"""
    pag.doubleClick()
    return "鼠标已双击"


@mcp.tool()
def mouse_scroll(dx: int = 0, dy: int = 0) -> str:
    """
    鼠标滚轮滚动
    Args:
        dx: 水平滚动量（正=右，负=左）
        dy: 垂直滚动量（正=上，负=下），每单位约 1 行
    """
    if dy != 0:
        pag.scroll(clicks=dy)
    if dx != 0:
        pag.hscroll(clicks=dx)
    return f"鼠标已滚动 dx={dx}, dy={dy}"


@mcp.tool()
def get_mouse_position() -> dict:
    """获取当前鼠标位置"""
    x, y = pag.position()
    return {"x": x, "y": y}


# ── 键盘控制 ──────────────────────────────────────────────

@mcp.tool()
def key_press(key: str) -> str:
    """
    按下并释放单个按键
    Args:
        key: 按键名，如 enter, space, tab, escape, a-z, f1-f12 等
        完整列表见 https://pyautogui.readthedocs.io/en/latest/keyboard.html
    """
    pag.press(key)
    return f"按键: {key}"


@mcp.tool()
def key_down(key: str) -> str:
    """按下按键不放"""
    pag.keyDown(key)
    return f"按键按下: {key}"


@mcp.tool()
def key_up(key: str) -> str:
    """释放按键"""
    pag.keyUp(key)
    return f"按键释放: {key}"


@mcp.tool()
def hotkey(key_combo: str) -> str:
    """
    按下组合键（如 ctrl+s, alt+f4）
    Args:
        key_combo: 组合键字符串，用 + 分隔，如 "ctrl+alt+delete"
    """
    keys = [k.strip() for k in key_combo.split("+")]
    pag.hotkey(*keys)
    return f"组合键: {'+'.join(keys)}"


@mcp.tool()
def type_text(text: str, interval: float = 0.05) -> str:
    """
    输入文本
    Args:
        text: 要输入的文本内容
        interval: 每字符间隔时间（秒）
    """
    pag.typewrite(text, interval=interval)
    return f"已输入文本 ({len(text)} 字符)"


@mcp.tool()
def type_paste(text: str) -> str:
    """通过剪贴板粘贴文本（适合中文/特殊字符）"""
    pyperclip.copy(text)
    pag.hotkey("ctrl", "v")
    return f"已粘贴文本 ({len(text)} 字符)"


# ── 剪贴板 ────────────────────────────────────────────────

@mcp.tool()
def get_clipboard() -> str:
    """获取剪贴板文本内容"""
    try:
        data = pyperclip.paste()
        return data if isinstance(data, str) else ""
    except Exception as e:
        return f"错误: {e}"


@mcp.tool()
def set_clipboard(text: str) -> str:
    """设置剪贴板文本内容"""
    try:
        pyperclip.copy(text)
        return f"已写入剪贴板 ({len(text)} 字符)"
    except Exception as e:
        return f"错误: {e}"


# ── 文件/目录操作 ─────────────────────────────────────────

@mcp.tool()
def list_dir(path: str = ".") -> list[dict]:
    """
    列出目录内容
    Args:
        path: 目录路径，默认当前工作目录
    Returns:
        list[dict]: 文件/目录列表，包含名称、类型、大小等
    """
    p = Path(path)
    if not p.exists():
        return [{"error": f"路径不存在: {path}"}]
    if not p.is_dir():
        return [{"error": f"不是目录: {path}"}]

    result = []
    for item in sorted(p.iterdir()):
        info = {
            "name": item.name,
            "type": "directory" if item.is_dir() else "file",
        }
        if item.is_file():
            try:
                info["size"] = item.stat().st_size
            except Exception:
                pass
        result.append(info)
    return result


@mcp.tool()
def read_file(file_path: str, max_size: int = 50000) -> str:
    """
    读取文件内容（文本文件）
    Args:
        file_path: 文件路径
        max_size: 最大读取字节数，防止过大
    Returns:
        str: 文件内容或错误信息
    """
    p = Path(file_path)
    if not p.exists():
        return f"错误: 文件不存在: {file_path}"
    if p.stat().st_size > max_size:
        return f"错误: 文件过大 ({p.stat().st_size} bytes)，超过限制 {max_size}"
    try:
        encodings = ["utf-8", "gbk", "latin-1"]
        for enc in encodings:
            try:
                content = p.read_text(encoding=enc)
                return content
            except UnicodeDecodeError:
                continue
        return "错误: 无法识别文件编码"
    except Exception as e:
        return f"错误: 读取失败 - {e}"


@mcp.tool()
def write_file(file_path: str, content: str) -> str:
    """写入文本文件"""
    p = Path(file_path)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"已写入: {file_path} ({len(content)} 字符)"
    except Exception as e:
        return f"错误: 写入失败 - {e}"


@mcp.tool()
def delete_file(file_path: str) -> str:
    """此操作已禁用，出于安全考虑不允许通过 MCP 删除文件"""
    return f"错误: 出于安全考虑，MCP 禁止删除文件: {file_path}"


# ── 窗口控制 ─────────────────────────────────────────────

@mcp.tool()
def list_windows() -> list[dict]:
    """列出所有可见窗口"""
    import pygetwindow as gw
    windows = []
    for w in gw.getAllWindows():
        try:
            title = w.title or ""
            if not title.strip():
                continue
            rect = w.getRect() if hasattr(w, 'getRect') else (0, 0, 400, 300)
            windows.append({
                "title": title[:80],
                "left": rect[0],
                "top": rect[1],
                "width": rect[2] - rect[0] if len(rect) >= 4 else 0,
                "height": rect[3] - rect[1] if len(rect) >= 4 else 0,
            })
        except Exception:
            continue
    return windows


@mcp.tool()
def activate_window(title_contains: str) -> str:
    """
    激活包含指定文字的窗口（将其置于前台）
    Args:
        title_contains: 窗口标题包含的文字（模糊匹配）
    """
    import pygetwindow as gw
    matches = gw.getWindowsWithTitle(title_contains)
    if not matches:
        return f"错误: 未找到包含 '{title_contains}' 的窗口"
    try:
        matches[0].activate()
        matches[0].maximize()
        matches[0].restore()
        return f"已激活窗口: {matches[0].title[:50]}"
    except Exception as e:
        return f"激活窗口失败: {e}"


# ── 系统命令 ──────────────────────────────────────────────

@mcp.tool()
def run_command(command: str, timeout: int = 30) -> dict:
    """
    执行系统命令（cmd）
    Args:
        command: 要执行的命令
        timeout: 超时时间（秒）
    Returns:
        dict: 包含 stdout、stderr、returncode 的字典
    """
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=os.getcwd(),
        )
        return {
            "returncode": result.returncode,
            "stdout": result.stdout[-5000:] if len(result.stdout) > 5000 else result.stdout,
            "stderr": result.stderr[-2000:] if len(result.stderr) > 2000 else result.stderr,
        }
    except subprocess.TimeoutExpired:
        return {"returncode": -1, "stdout": "", "stderr": f"命令超时 ({timeout}s)"}
    except Exception as e:
        return {"returncode": -1, "stdout": "", "stderr": str(e)}


@mcp.tool()
def open_file_or_url(path: str) -> str:
    """用默认程序打开文件或 URL"""
    try:
        os.startfile(path)
        return f"已打开: {path}"
    except Exception as e:
        return f"错误: 打开失败 - {e}"


@mcp.tool()
def get_system_info() -> dict:
    """获取系统基本信息"""
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    cpu_percent = psutil.cpu_percent(interval=0.5)

    return {
        "os": platform.system(),
        "os_version": platform.version(),
        "hostname": platform.node(),
        "arch": platform.machine(),
        "python": platform.python_version(),
        "cpu_usage": round(cpu_percent, 1),
        "memory_total": mem.total,
        "memory_used": mem.used,
        "memory_percent": mem.percent,
        "disk_total": disk.total,
        "disk_free": disk.free,
        "disk_percent": round(disk.percent, 1),
    }


@mcp.tool()
def get_system_time() -> dict:
    """获取当前系统日期和时间"""
    from datetime import datetime
    now = datetime.now()
    return {
        "datetime": now.strftime("%Y-%m-%d %H:%M:%S"),
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "weekday_cn": ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][now.weekday()],
        "weekday_en": now.strftime("%A"),
        "timestamp": int(now.timestamp()),
    }


if __name__ == "__main__":
    mcp.run()
