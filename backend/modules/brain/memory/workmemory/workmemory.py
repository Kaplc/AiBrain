"""
WorkMemory - 工作记忆管理器（单例）
管理 data/ 目录下的 .md 文件作为工作记忆，
提供 CRUD + 滚动输入 + package 搜索接口。

外部访问：
    from modules.brain.memory.workmemory import get_work_memory
    wm = get_work_memory()
    wm.input_mem_write("新的记忆")
    entries = wm.input_mem_read()
"""
from __future__ import annotations
import logging
import os
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# 工作记忆文件存储根目录
_BASE_DIR = Path(__file__).parent / "data"

# 默认文件
DEFAULT_FILES = ["input.md", "package.md"]


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
        """扫描 data/ 下所有 .md 文件，刷新注册表"""
        self._registry.clear()
        for fpath in _BASE_DIR.glob("*.md"):
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
            name: 文件名（如 "task.md"）

        Returns:
            完整的文件路径

        Raises:
            ValueError: 路径穿越
        """
        # 补 .md 后缀
        if not name.endswith(".md"):
            name += ".md"
        # 安全拼接
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
            name: 文件名（可省略 .md）

        Returns:
            文件内容，不存在返回 None
        """
        if not name.endswith(".md"):
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
        """写入/覆盖文件。省略文件名时默认写入 input.md

        Args:
            name: 文件名（可省略 .md）。如果内容不含换行且没有 name 则当 content 处理
            content: 文件内容

        Returns:
            {"name": str, "size": int}
        """
        # 处理省略文件名的情况：write("纯文本内容") → input.md
        if not name.endswith(".md") and "\n" not in name and len(name) < 100:
            # 判断 name 是否是文件名：包含 . 或路径分隔符
            if "/" not in name and "\\" not in name and "." not in name.replace(".md", ""):
                # 没有文件名特征，当作内容写入 input.md
                content = f"{name}\n{content}" if content else name
                name = "input.md"

        if not name.endswith(".md"):
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
        if not name.endswith(".md"):
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

    # ── input.md 专用方法 ────────────────────────────────

    def input_mem_write(self, content: str) -> dict:
        """向 input.md 滚动追加条目，超过 20 条自动删除最旧

        Args:
            content: 要追加的内容

        Returns:
            {"total": 条目数, "appended": content, "removed": 删除的条目数}
        """
        fpath = _BASE_DIR / "input.md"
        text = fpath.read_text(encoding="utf-8") if fpath.exists() else ""
        entries = self._parse_entries(text)

        # 追加新条目（带时间戳）
        seq = len(entries) + 1
        from datetime import datetime
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        new_entry = f"## 条目 {seq}\n时间：{ts}\n{content}"
        entries.append(new_entry)

        # 超出 20 条，删最旧
        removed = 0
        while len(entries) > 20:
            entries.pop(0)
            removed += 1

        # 写回：用 \n---\n 连接，末尾也加 \n---
        output = "\n---\n".join(entries) + "\n---"
        fpath.write_text(output, encoding="utf-8")
        self._refresh_registry("input.md")
        logger.info(f"[workmemory] input_mem_write: total={len(entries)} removed={removed}")

        return {
            "total": len(entries),
            "appended": content,
            "removed": removed,
        }

    def input_mem_read(self) -> list[dict]:
        """读取 input.md 全部条目，返回结构化列表

        Returns:
            [{"seq": 1, "content": "...", "time": "..."}, ...]
        """
        fpath = _BASE_DIR / "input.md"
        if not fpath.exists():
            return []
        text = fpath.read_text(encoding="utf-8")
        raw_entries = self._parse_entries(text)
        result = []
        for i, entry_text in enumerate(raw_entries, 1):
            lines = entry_text.strip().split("\n")
            time_str = ""
            body_lines = []
            for line in lines:
                if line.startswith("## 条目"):
                    continue
                if line.startswith("时间："):
                    time_str = line.replace("时间：", "").strip()
                else:
                    body_lines.append(line)
            body = "\n".join(body_lines).strip()
            result.append({"seq": i, "content": body, "time": time_str})
        return result

    def _parse_entries(self, text: str) -> list[str]:
        """以 --- 分隔解析条目

        Args:
            text: input.md 全文

        Returns:
            条目字符串列表
        """
        if not text.strip():
            return []
        # 按 \n--- 分割，过滤空段
        raw = [e.strip() for e in text.split("\n---") if e.strip()]
        return raw

    # ── package.md 专用方法 ──────────────────────────────

    def package_mem_write(self, content: str) -> dict:
        """写入 package.md（覆盖）

        Args:
            content: 文件内容

        Returns:
            {"name": "package.md", "size": int}
        """
        fpath = _BASE_DIR / "package.md"
        fpath.write_text(content, encoding="utf-8")
        self._refresh_registry("package.md")
        info = self._registry.get("package.md")
        return {"name": "package.md", "size": info.size if info else 0}

    def package_mem_read(self) -> str:
        """读取 package.md 全部内容

        Returns:
            文件内容，不存在返回 ""
        """
        fpath = _BASE_DIR / "package.md"
        if not fpath.exists():
            return ""
        return fpath.read_text(encoding="utf-8")

    def handle_packagemem(self) -> dict:
        """搜索长期记忆并写入 package.md

        流程：读 input.md → 调 Agent 提取关键词和事件 → 搜索 → 写 package.md

        Returns:
            {"query": str, "result_count": int, "package_size": int, "keyword_queries": [str]}
        """
        # 1. 读 input.md 全部条目
        entries = self.input_mem_read()
        if not entries:
            logger.info("[workmemory] handle_packagemem: input.md is empty")
            return {"query": "", "result_count": 0, "package_size": 0, "keyword_queries": []}

        # 2. 调 Agent 精炼当前提问（不传历史，避免历史话题干扰搜索意图）
        query = ""
        try:
            from modules.LLM import get_agent_manager
            agent = get_agent_manager().get("memory_search")
            current = entries[-1]["content"]
            result = agent.run({"current": current})
            query = result.get("query", "")
            logger.info(f"[workmemory] agent query={query!r}")
        except Exception as e:
            logger.warning(f"[workmemory] agent call failed: {e}")

        # 3. 搜索（用 agent 返回的完整句子直接搜）
        all_results = []
        search_query = query or entries[-1]["content"]
        from modules.brain.memory.core import search_memory
        try:
            results = search_memory(search_query)
            all_results.extend(results)
            logger.info(f"[workmemory] search '{search_query[:80]}': {len(results)} results")
        except Exception as e:
            logger.warning(f"[workmemory] search failed: {e}")

        # 如果没有搜索结果，用当前消息直接搜作为兜底
        if not all_results:
            try:
                from modules.brain.memory.core import search_memory
                all_results = search_memory(entries[-1]["content"])
                logger.info(f"[workmemory] fallback search: {len(all_results)} results")
            except Exception as e:
                logger.warning(f"[workmemory] fallback search failed: {e}")

        # 去重
        seen = set()
        unique_results = []
        for r in all_results:
            rid = r.get("id", "")
            if rid and rid not in seen:
                seen.add(rid)
                unique_results.append(r)

        # 4. 格式化为 Markdown
        lines = []
        for r in unique_results:
            text = r.get("text", "") or r.get("memory", "")
            lines.append(text)
            lines.append("---")

        formatted = "\n".join(lines)

        # 5. 写入 package.md
        pw_result = self.package_mem_write(formatted)
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
        """打包读取 input + package

        TODO: 合并 input_mem_read + package_mem_read

        Returns:
            {"input": [{seq, content}], "package": str}
        """
        return {
            "input": self.input_mem_read(),
            "package": self.package_mem_read(),
        }


# ── 便利函数 ──────────────────────────────────────────

def get_work_memory() -> WorkMemoryManager:
    """获取 WorkMemoryManager 单例"""
    return WorkMemoryManager.get_instance()
