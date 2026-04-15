import os
import subprocess
from fastmcp import FastMCP

from .tools import store_memory, search_memory, list_memories, delete_memory

mcp = FastMCP("Qdrant Memory Server")


def _is_process_running(process_name: str) -> bool:
    """Check if a process is running."""
    try:
        result = subprocess.run(
            f'tasklist /FI "IMAGENAME eq {process_name}"',
            shell=True,
            capture_output=True,
            text=True
        )
        return process_name in result.stdout
    except Exception:
        return False


@mcp.tool()
def store(text: str) -> str:
    """Store a memory from user input.

    Args:
        text: The memory text to store

    Returns:
        Confirmation message
    """
    return store_memory(text)


@mcp.tool()
def search(query: str) -> list[dict]:
    """Search memories by query.

    Args:
        query: The search query

    Returns:
        List of matching memories with scores
    """
    return search_memory(query)


@mcp.tool()
def list_all() -> list[dict]:
    """List all stored memories.

    Returns:
        List of all memories
    """
    return list_memories()


@mcp.tool()
def delete(memory_id: str) -> str:
    """Delete a memory by ID.

    Args:
        memory_id: The memory ID to delete

    Returns:
        Confirmation message
    """
    return delete_memory(memory_id)


@mcp.tool()
def run_bat(script_path: str) -> str:
    """Run a batch (.bat) file if not already running.

    Args:
        script_path: Relative or absolute path to the .bat file

    Returns:
        Execution result or error message
    """
    # Resolve to absolute path if relative
    if not os.path.isabs(script_path):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        script_path = os.path.join(base_dir, script_path)

    if not os.path.exists(script_path):
        return f"Error: Script not found: {script_path}"

    # Check if already running based on script type
    script_name = os.path.basename(script_path).lower()

    if "start_qdrant" in script_name or "qdrant" in script_name:
        if _is_process_running("qdrant.exe"):
            return "Qdrant is already running"
        # Kill existing qdrant if restarting
        subprocess.run('taskkill /F /IM qdrant.exe 2>NUL', shell=True)
    elif "app" in script_name:
        if _check_app_port():
            return "App is already running on port 18765"
        # Kill existing app processes
        subprocess.run('taskkill /F /IM python.exe 2>NUL', shell=True)

    import time
    time.sleep(0.3)

    try:
        result = subprocess.run(
            [script_path],
            shell=True,
            capture_output=True,
            text=True,
            timeout=60
        )
        output = result.stdout or ""
        error = result.stderr or ""
        if result.returncode != 0:
            return f"Exit code: {result.returncode}\nSTDOUT:\n{output}\nSTDERR:\n{error}"
        return f"Success\nSTDOUT:\n{output}" if output else "Success (no output)"
    except subprocess.TimeoutExpired:
        return "Error: Script timed out after 60 seconds"
    except Exception as e:
        return f"Error: {str(e)}"


@mcp.tool()
def is_app_running() -> dict:
    """Check if the application and Qdrant are running.

    Returns:
        Status of app processes
    """
    qdrant_running = _is_process_running("qdrant.exe")
    app_running = _is_process_running("python.exe") and _check_app_port()

    return {
        "qdrant": qdrant_running,
        "app": app_running,
        "status": "running" if (qdrant_running and app_running) else "not_running"
    }


def _check_app_port() -> bool:
    """Check if app is listening on its port."""
    try:
        import urllib.request
        urllib.request.urlopen('http://localhost:18765/healthz', timeout=2)
        return True
    except Exception:
        # Try status endpoint instead
        try:
            urllib.request.urlopen('http://localhost:18765/status', timeout=2)
            return True
        except Exception:
            return False
