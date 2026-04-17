"""Eye MCP - 屏幕截图与视觉分析 MCP 服务器"""
import base64
import tempfile
from fastmcp import FastMCP
from PIL import ImageGrab

mcp = FastMCP("eye_mcp")


@mcp.tool()
def capture_screen() -> dict:
    """
    截取当前屏幕，返回截图信息（base64 编码的图片数据）

    Returns:
        dict: 包含图片格式、尺寸和 base64 数据的字典
    """
    screenshot = ImageGrab.grab()
    width, height = screenshot.size

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        temp_path = f.name
        screenshot.save(temp_path, "PNG")

    with open(temp_path, "rb") as f:
        image_data = base64.b64encode(f.read()).decode("utf-8")

    return {
        "format": "PNG",
        "width": width,
        "height": height,
        "data": image_data,
        "path": temp_path,
    }


@mcp.tool()
def capture_region(x: int, y: int, width: int, height: int) -> dict:
    """
    截取屏幕指定区域

    Args:
        x: 区域左上角 X 坐标
        y: 区域左上角 Y 坐标
        width: 区域宽度
        height: 区域高度

    Returns:
        dict: 包含截图信息的字典
    """
    bbox = (x, y, x + width, y + height)
    screenshot = ImageGrab.grab(bbox=bbox)

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        temp_path = f.name
        screenshot.save(temp_path, "PNG")

    with open(temp_path, "rb") as f:
        image_data = base64.b64encode(f.read()).decode("utf-8")

    return {
        "format": "PNG",
        "width": width,
        "height": height,
        "data": image_data,
        "bbox": {"x": x, "y": y, "width": width, "height": height},
        "path": temp_path,
    }


@mcp.tool()
def get_screen_size() -> dict:
    """获取当前屏幕分辨率"""
    img = ImageGrab.grab()
    w, h = img.size
    del img
    return {"width": w, "height": h}


@mcp.tool()
def list_windows() -> list[dict]:
    """
    列出当前系统中的窗口信息

    Returns:
        list[dict]: 窗口列表，每个包含标题、位置、大小等信息
    """
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    EnumWindows = user32.EnumWindows
    GetWindowTextW = user32.GetWindowTextW
    GetWindowRect = user32.GetWindowRect
    IsWindowVisible = user32.IsWindowVisible

    windows = []
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

    def _enum_callback(hwnd, lparam):
        if not IsWindowVisible(hwnd):
            return True
        length = GetWindowTextW(hwnd, None, 0)
        if length == 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value
        if not title.strip():
            return True

        rect = ctypes.wintypes.RECT()
        GetWindowRect(hwnd, ctypes.byref(rect))
        windows.append({
            "title": title[:100],
            "hwnd": hwnd,
            "left": rect.left,
            "top": rect.top,
            "right": rect.right,
            "bottom": rect.bottom,
            "width": rect.right - rect.left,
            "height": rect.bottom - rect.top,
        })
        return True

    EnumWindows(WNDENUMPROC(_enum_callback), 0)
    return windows


if __name__ == "__main__":
    mcp.run()
