from .server import mcp

if __name__ == "__main__":
    try:
        import ctypes
        ctypes.windll.kernel32.SetConsoleTitleW("AiBrain BrainMCP")
    except Exception:
        pass
    mcp.run()
