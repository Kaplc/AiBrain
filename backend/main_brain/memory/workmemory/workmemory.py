"""
WorkMemory - 工作记忆管理器（单例）
管理 data/ 目录下的 .json / .md 文件作为工作记忆。
- output.json：对话记录
- package.json：搜索结果（JSON 对象）

外部访问：
    from main_brain.memory.workmemory import get_work_memory
    wm = get_work_memory()
"""
from __future__ import annotations
import json
import logging
import os
import tempfile
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# 工作记忆文件存储根目录（统一放在 backend/main_brain/data/，上三级到 main_brain）
_BASE_DIR = Path(__file__).parent.parent.parent / "data"

# 默认文件
DEFAULT_FILES = ["output.json", "package.json"]


def _parse_time(time_str: str) -> Optional[datetime]:
    """解析 output.json 中的 time 字段，失败返回 None"""
    if not time_str:
        return None
    try:
        return datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return None


@dataclass
class FileInfo:
    """文件元数据"""
    name: str
    size: int
    created_at: float
    modified_at: float


_INSTANCE: Optional['WorkMemoryManager'] = None
_INSTANCE_LOCK = threading.Lock()


class WorkMemoryManager:
    """工作记忆管理器单例"""

    # ── 单例 ─────────────────────────────────────────────

    @classmethod
    def get_instance(cls) -> 'WorkMemoryManager':
        global _INSTANCE
        if _INSTANCE is None:
            with _INSTANCE_LOCK:
                if _INSTANCE is None:
                    _INSTANCE = cls()
        return _INSTANCE

    def __init__(self):
        self._registry: dict[str, FileInfo] = {}
        self._lock = threading.Lock()
        self._init_directory()
        self._scan_directory()

    def _init_directory(self) -> None:
        """确保 data/ 目录和默认文件存在"""
        _BASE_DIR.mkdir(parents=True, exist_ok=True)
        for fname in DEFAULT_FILES:
            fpath = _BASE_DIR / fname
            if not fpath.exists():
                fpath.write_text("", encoding="utf-8")
                logger.info(f"[workmemory] created default: {fname}")

    def _scan_directory(self) -> None:
        """扫描 data/ 下所有 .md / .json 文件，刷新注册表"""
        self._registry.clear()
        for ext in ("*.md", "*.json"):
            for fpath in _BASE_DIR.glob(ext):
                stat = fpath.stat()
                info = FileInfo(
                    name=fpath.name,
                    size=stat.st_size,
                    created_at=stat.st_ctime,
                    modified_at=stat.st_mtime,
                )
                self._registry[fpath.name] = info

    def _resolve_path(self, name: str) -> Path:
        """安全拼接路径，防止路径穿越

        Args:
            name: 文件名（如 "input.json" / "task.md"）

        Returns:
            完整的文件路径

        Raises:
            ValueError: 路径穿越
        """
        # 补后缀（.json 或 .md）
        if not name.endswith(".json") and not name.endswith(".md"):
            name += ".md"
        full = (_BASE_DIR / name).resolve()
        if not str(full).startswith(str(_BASE_DIR.resolve())):
            raise ValueError(f"路径穿越禁止: {name}")
        return full

    def _refresh_registry(self, name: str) -> None:
        """刷新单个文件的注册表信息"""
        fpath = self._resolve_path(name)
        if fpath.exists():
            stat = fpath.stat()
            self._registry[name] = FileInfo(
                name=fpath.name,
                size=stat.st_size,
                created_at=stat.st_ctime,
                modified_at=stat.st_mtime,
            )

    # ── 通用 CRUD ────────────────────────────────────────

    def list(self) -> list[dict]:
        """列出所有已注册的工作记忆文件

        Returns:
            [{name, size, created_at, modified_at}, ...]
        """
        with self._lock:
            return [
                {
                    "name": info.name,
                    "size": info.size,
                    "created_at": info.created_at,
                    "modified_at": info.modified_at,
                }
                for info in self._registry.values()
            ]

    def read(self, name: str) -> Optional[str]:
        """读取文件内容

        Args:
            name: 文件名（可省略 .md / .json）

        Returns:
            文件内容，不存在返回 None
        """
        if not name.endswith(".md") and not name.endswith(".json"):
            name += ".md"
        try:
            fpath = self._resolve_path(name)
            if not fpath.exists():
                return None
            return fpath.read_text(encoding="utf-8")
        except Exception as e:
            logger.warning(f"[workmemory] read failed: {e}")
            return None

    def write(self, name: str, content: str) -> dict:
        """写入/覆盖文件。省略后缀时默认 .md

        Args:
            name: 文件名（可省略后缀）
            content: 文件内容

        Returns:
            {"name": str, "size": int}
        """
        if not name.endswith(".json") and not name.endswith(".md"):
            name += ".md"
        fpath = self._resolve_path(name)
        fpath.write_text(content, encoding="utf-8")
        self._refresh_registry(name)
        info = self._registry.get(name)
        return {"name": name, "size": info.size if info else 0}

    def delete(self, name: str) -> bool:
        """删除文件

        Args:
            name: 文件名

        Returns:
            True 成功，False 不存在
        """
        if not name.endswith(".md") and not name.endswith(".json"):
            name += ".md"
        try:
            fpath = self._resolve_path(name)
            if not fpath.exists():
                return False
            fpath.unlink()
            self._registry.pop(name, None)
            return True
        except Exception as e:
            logger.warning(f"[workmemory] delete failed: {e}")
            return False

    def search(self, query: str) -> list[dict]:
        """关键词搜索文件名和内容

        Args:
            query: 搜索关键词

        Returns:
            [{name, matches:[], match_count}, ...]
        """
        q = query.lower()
        results = []
        with self._lock:
            for name in list(self._registry.keys()):
                try:
                    content = self.read(name)
                    if content is None:
                        continue
                    matches = []
                    # 文件名匹配
                    if q in name.lower():
                        matches.append(f"[文件名匹配] {name}")
                    # 内容行匹配
                    for line in content.split("\n"):
                        if q in line.lower():
                            matches.append(line.strip()[:120])
                    if matches:
                        results.append({
                            "name": name,
                            "matches": matches[:10],
                            "match_count": len(matches),
                        })
                except Exception:
                    continue
        return results

    # ── output.json 专用方法 ──────────────────────────────

    def output_mem_write(self, content: str, user_prompt: str = "") -> dict:
        """向 output.json 滚动追加对话记录，超过 2 天的条目自动删除
        使用临时文件 + 原子替换，防止崩溃损坏。

        Args:
            content: LLM 回复文本
            user_prompt: 用户的提问

        Returns:
            {"total": 条目数, "appended": content摘要, "removed": 删除的条目数}
        """
        fpath = _BASE_DIR / "output.json"
        entries = []
        if fpath.exists():
            try:
                raw = fpath.read_text(encoding="utf-8")
                if raw.strip():
                    entries = json.loads(raw)
            except (json.JSONDecodeError, Exception):
                entries = []
        if not isinstance(entries, list):
            entries = []

        # 计算最大序号
        max_seq = max((e.get("seq", 0) for e in entries), default=0)
        seq = max_seq + 1
        now = datetime.now()
        ts = now.strftime("%Y-%m-%d %H:%M:%S")
        entries.append({
            "seq": seq,
            "user": user_prompt,
            "assistant": content,
            "time": ts,
        })

        # 删除超过 2 天的条目
        cutoff = now - timedelta(days=2)
        removed = 0
        before = len(entries)
        kept = []
        for e in entries:
            t = _parse_time(e.get("time", ""))
            if t is not None and t >= cutoff:
                kept.append(e)
        entries = kept
        removed = before - len(entries)

        # 安全硬上限：防止时间解析异常导致无限增长
        if len(entries) > 1000:
            entries = entries[-1000:]

        # 原子写入：临时文件 + os.replace
        fd, tmp = tempfile.mkstemp(dir=str(_BASE_DIR), suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(entries, f, ensure_ascii=False, indent=2)
            os.replace(tmp, fpath)
        except Exception:
            os.unlink(tmp)
            raise

        self._refresh_registry("output.json")
        if removed:
            logger.info(f"[workmemory] output_mem_write: total={len(entries)} removed={removed} (超过2天)")

        return {
            "total": len(entries),
            "appended": content[:60],
            "removed": removed,
        }

    def output_mem_read(self) -> list[dict]:
        """读取 output.json 全部条目

        Returns:
            [{"seq": 1, "user": "...", "assistant": "...", "time": "..."}, ...]
        """
        fpath = _BASE_DIR / "output.json"
        if not fpath.exists():
            return []
        try:
            raw = fpath.read_text(encoding="utf-8")
            if not raw.strip():
                return []
            entries = json.loads(raw)
            return entries if isinstance(entries, list) else []
        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"[workmemory] output.json parse failed: {e}")
            return []

    # ── package.json 专用方法 ───────────────────────────

    def package_mem_write(self, data: dict) -> dict:
        """写入 package.json（覆盖）

        Args:
            data: JSON 可序列化对象（如 {"query": str, "results": [...]}）

        Returns:
            {"name": "package.json", "size": int}
        """
        fpath = _BASE_DIR / "package.json"
        content = json.dumps(data, ensure_ascii=False, indent=2)
        fpath.write_text(content, encoding="utf-8")
        self._refresh_registry("package.json")
        info = self._registry.get("package.json")
        return {"name": "package.json", "size": info.size if info else 0}

    def package_mem_read(self) -> dict:
        """读取 package.json

        Returns:
            dict，不存在返回空 dict {"results": [], "query": ""}
        """
        fpath = _BASE_DIR / "package.json"
        if not fpath.exists():
            return {"results": [], "query": ""}
        try:
            raw = fpath.read_text(encoding="utf-8")
            if not raw.strip():
                return {"results": [], "query": ""}
            data = json.loads(raw)
            return data if isinstance(data, dict) else {"results": [], "query": ""}
        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"[workmemory] package.json parse failed: {e}")
            return {"results": [], "query": ""}

    def handle_packagemem(self, query: str = "") -> dict:
        """搜索长期记忆并写入 package.json

        流程：直接用用户原话向量搜索 + 图扩散 → 写 package.json
        不做 LLM 判断/精炼。

        Args:
            query: 当前用户输入的文本，为空时从 output.json 取最新 user 消息

        Returns:
            {"query": str, "result_count": int, "package_size": int}
        """
        # 1. 确定搜索词
        if not query:
            outputs = self.output_mem_read()
            if outputs and outputs[-1].get("user"):
                query = outputs[-1]["user"]
            else:
                logger.info("[workmemory] handle_packagemem: no input to search")
                return {"query": "", "result_count": 0, "package_size": 0}

        search_query = query
        all_results = []
        from ..core import search_memory
        try:
            results = search_memory(search_query)
            all_results.extend(results)
            logger.info(f"[workmemory] search '{search_query[:80]}': {len(results)} results")
        except Exception as e:
            logger.warning(f"[workmemory] search failed: {e}")

        # 去重
        seen = set()
        unique_results = []
        for r in all_results:
            rid = r.get("id", "")
            if rid and rid not in seen:
                seen.add(rid)
                unique_results.append(r)

        # 2. 构建 JSON 并写入 package.json
        pkg_data = {
            "query": search_query,
            "results": [
                {
                    "id": r.get("id", ""),
                    "text": r.get("text", "") or r.get("memory", ""),
                    "score": r.get("score", 0),
                }
                for r in unique_results
            ],
        }
        pw_result = self.package_mem_write(pkg_data)
        logger.info(
            f"[workmemory] handle_packagemem: total={len(unique_results)} "
            f"written={pw_result['size']} bytes"
        )

        return {
            "query": search_query,
            "result_count": len(unique_results),
            "package_size": pw_result["size"],
        }

    # ── Agent 驱动（占位） ───────────────────────────────

    def process_instruction(self, instruction: str) -> dict:
        """通过 Agent 解析自然语言指令处理工作记忆

        TODO: 调 AgentManager.get("work_memory").run(instruction)

        Args:
            instruction: 自然语言指令

        Returns:
            {"status": str, "message": str}
        """
        logger.info(f"[workmemory] process_instruction: {instruction!r}")
        # 占位实现
        return {"status": "placeholder", "message": f"收到指令: {instruction}"}

    # ── 打包读取（占位） ─────────────────────────────────

    def get_workmem(self) -> dict:
        """打包读取 output + package

        Returns:
            {"output": [{seq, content, time}], "package": {query, results}}
        """
        return {
            "output": self.output_mem_read(),
            "package": self.package_mem_read(),
        }


# ── 便利函数 ──────────────────────────────────────────

def get_work_memory() -> WorkMemoryManager:
    """获取 WorkMemoryManager 单例"""
    return WorkMemoryManager.get_instance()


def get_base_dir() -> Path:
    """获取工作记忆数据目录路径"""
    return _BASE_DIR
