# mcp_servers/ — 扩展 MCP 服务器

## 概览
4 个独立的 FastMCP 服务器，提供外部工具能力。除 wiki_mcp 注册在 `.mcp.json` 外，其余为独立可选的 MCP 服务。

## 服务器清单

### wiki_mcp/ — Wiki 知识库 MCP
- **框架**: FastMCP | **通信**: HTTP → Flask `/wiki/*` API
- **工具**: `wiki_search(query, mode)` / `wiki_list()` / `wiki_index()`
- **搜索模式**: naive / local / global / hybrid / mix
- **日志标记**: `[MCP→]`, `[MCP←]`, `[MCP⚠]`, `[MCP✗]`

### computer_mcp/ — 计算机控制 MCP
- **依赖**: pyautogui / pyperclip / PyGetWindow / psutil
- **工具**: 鼠标控制 (move/click/scroll/drag) / 键盘控制 (press/hotkey/type)
- **扩展**: 剪贴板操作 / 文件列表/读/写 / 窗口管理 / 系统信息
- **安全**: `pag.PAUSE = 0.1`

### console_mcp/ — 前端控制台 MCP
- **通信**: JSON 队列文件 `~/.aibrain/console_queue.json`
- **工具**: `console_log` / `console_clear` / `console_toggle`
- **功能**: 向 Web 前端控制台写入命令队列

### eye_mcp/ — 屏幕截图 MCP
- **依赖**: PIL.ImageGrab
- **工具**: `capture_screen()` — 截图并返回 base64

## 注册配置 (`.mcp.json`)
```json
{
  "brain": "python -m brain_mcp",
  "wiki": "python -m mcp_servers.wiki_mcp.server"
}
```
