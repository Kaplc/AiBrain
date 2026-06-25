"""程序记忆的 JSON/JSONL 持久化存储层

数据文件位置（由 DATA_DIR 控制，默认 main_brain/data/procedural_memory/）：
  - templates.json      : 当前所有模板（列表）
  - examples.jsonl      : 增量样本日志
  - state.json          : 模块运行状态检查点
  - archive.jsonl       : 退役模板归档

线程安全：所有写操作通过 threading.Lock 保护。
"""

import json
import logging
import os
import threading
from typing import Optional

logger = logging.getLogger("main_brain.memory.procedural.store")

from main_brain.procedural_memory.contracts import (
    ProcedureTemplate,
    ProcedureExample,
    ProcedureState,
)

DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "procedural_memory",
)

TEMPLATES_FILE = os.path.join(DATA_DIR, "templates.json")
EXAMPLES_FILE = os.path.join(DATA_DIR, "examples.jsonl")
STATE_FILE = os.path.join(DATA_DIR, "state.json")
ARCHIVE_FILE = os.path.join(DATA_DIR, "archive.jsonl")


class ProcedureStore:
    """程序记忆存储层，管理模板、样本、状态和归档"""

    def __init__(self, data_dir: str = DATA_DIR):
        self._data_dir = data_dir
        self._lock = threading.Lock()
        self._ensure_dir()

        # 内存缓存
        self._templates: dict[str, ProcedureTemplate] = {}
        self._state: ProcedureState = ProcedureState()
        self._examples: list[ProcedureExample] = []
        self._loaded = False

    # ── 初始化 ───────────────────────────────────────────

    def _ensure_dir(self):
        os.makedirs(self._data_dir, exist_ok=True)

    def _templates_path(self) -> str:
        return os.path.join(self._data_dir, "templates.json")

    def _examples_path(self) -> str:
        return os.path.join(self._data_dir, "examples.jsonl")

    def _state_path(self) -> str:
        return os.path.join(self._data_dir, "state.json")

    def _archive_path(self) -> str:
        return os.path.join(self._data_dir, "archive.jsonl")

    def load(self):
        """从磁盘加载所有数据到内存"""
        if self._loaded:
            return
        with self._lock:
            self._load_templates()
            self._load_state()
            self._load_examples()
            self._loaded = True
        logger.info(
            "[store] loaded %d templates, %d examples, state=%s",
            len(self._templates), len(self._examples),
            self._state.last_mined_run_id or "fresh",
        )

    def _load_templates(self):
        self._templates = {}
        path = self._templates_path()
        if not os.path.isfile(path):
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for item in data:
                tpl = ProcedureTemplate.from_dict(item)
                self._templates[tpl.template_id] = tpl
        except (json.JSONDecodeError, KeyError, TypeError):
            self._templates = {}

    def _load_state(self):
        path = self._state_path()
        if not os.path.isfile(path):
            self._state = ProcedureState()
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._state = ProcedureState.from_dict(data)
        except (json.JSONDecodeError, TypeError):
            self._state = ProcedureState()

    def _load_examples(self):
        self._examples = []
        path = self._examples_path()
        if not os.path.isfile(path):
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        self._examples.append(
                            ProcedureExample.from_dict(json.loads(line))
                        )
        except (json.JSONDecodeError, TypeError):
            pass

    # ── 模板操作 ─────────────────────────────────────────

    def get_template(self, template_id: str) -> Optional[ProcedureTemplate]:
        return self._templates.get(template_id)

    def get_all_templates(self) -> list[ProcedureTemplate]:
        return list(self._templates.values())

    def get_templates_by_status(self, *statuses: str) -> list[ProcedureTemplate]:
        return [t for t in self._templates.values() if t.status in statuses]

    def get_templates_by_risk(self, *levels: str) -> list[ProcedureTemplate]:
        return [t for t in self._templates.values() if t.risk_level in levels]

    def save_template(self, template: ProcedureTemplate):
        with self._lock:
            self._templates[template.template_id] = template
            self._persist_templates()
        logger.debug("[store] saved template %s (status=%s)", template.template_id, template.status)

    def save_templates(self, templates: list[ProcedureTemplate]):
        with self._lock:
            for t in templates:
                self._templates[t.template_id] = t
            self._persist_templates()
        logger.info("[store] saved %d templates", len(templates))

    def remove_template(self, template_id: str) -> bool:
        with self._lock:
            if template_id in self._templates:
                del self._templates[template_id]
                self._persist_templates()
                logger.info("[store] removed template %s", template_id)
                return True
            logger.warning("[store] remove_template %s not found", template_id)
            return False

    def archive_template(self, template: ProcedureTemplate):
        """将模板移至归档并从活动列表中移除"""
        template.status = "archive"
        with self._lock:
            self._append_archive_line(template)
            if template.template_id in self._templates:
                del self._templates[template.template_id]
            self._persist_templates()
            self._state.archive_count += 1
            self._persist_state()
        logger.info("[store] archived template %s (conf=%.2f, examples=%d)",
                     template.template_id, template.confidence, len(template.source_example_ids))

    def _persist_state(self):
        target = self._state_path()
        tmp = target + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._state.to_dict(), f, ensure_ascii=False, indent=2)
            os.replace(tmp, target)
        except OSError:
            if os.path.isfile(tmp):
                os.remove(tmp)

    def _persist_templates(self):
        data = [t.to_dict() for t in self._templates.values()]
        target = self._templates_path()
        tmp = target + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, target)
        except OSError:
            if os.path.isfile(tmp):
                os.remove(tmp)

    # ── 样本操作 ─────────────────────────────────────────

    def append_example(self, example: ProcedureExample):
        with self._lock:
            self._examples.append(example)
            self._append_example_line(example)

    def append_examples(self, examples: list[ProcedureExample]):
        with self._lock:
            for ex in examples:
                self._examples.append(ex)
                self._append_example_line(ex)

    def get_all_examples(self) -> list[ProcedureExample]:
        return list(self._examples)

    def get_recent_examples(self, n: int = 100) -> list[ProcedureExample]:
        return self._examples[-n:]

    def clear_examples(self):
        path = self._examples_path()
        with self._lock:
            self._examples = []
            if os.path.isfile(path):
                os.remove(path)

    def _append_example_line(self, example: ProcedureExample):
        path = self._examples_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(example.to_dict(), ensure_ascii=False) + "\n")

    # ── 归档操作 ─────────────────────────────────────────

    def _append_archive_line(self, template: ProcedureTemplate):
        path = self._archive_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(template.to_dict(), ensure_ascii=False) + "\n")

    def get_archive(self) -> list[dict]:
        records = []
        path = self._archive_path()
        if not os.path.isfile(path):
            return records
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        records.append(json.loads(line))
        except (json.JSONDecodeError, OSError):
            pass
        return records

    # ── 检查点状态 ───────────────────────────────────────

    def get_state(self) -> ProcedureState:
        return self._state

    def update_state(self, **kwargs):
        with self._lock:
            for k, v in kwargs.items():
                if hasattr(self._state, k):
                    setattr(self._state, k, v)
            self._persist_state()

    # ── 统计 ─────────────────────────────────────────────

    def get_counts(self) -> dict:
        active = sum(1 for t in self._templates.values() if t.status == "active")
        proposed = sum(1 for t in self._templates.values() if t.status == "proposed")
        draft = sum(1 for t in self._templates.values() if t.status == "draft")
        cooling = sum(1 for t in self._templates.values() if t.status == "cooling")
        deprecated = sum(1 for t in self._templates.values() if t.status == "deprecated")
        return {
            "active": active,
            "proposed": proposed,
            "draft": draft,
            "cooling": cooling,
            "deprecated": deprecated,
            "archive": self._state.archive_count,
            "total_active": active + proposed + cooling,
            "total_raw": len(self._templates),
            "example_count": len(self._examples),
        }


# ── 全局单例 ────────────────────────────────────────────

_INSTANCE: Optional[ProcedureStore] = None


def get_procedure_store() -> ProcedureStore:
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = ProcedureStore()
        _INSTANCE.load()
    return _INSTANCE


def reset_procedure_store():
    """测试用：重置单例"""
    global _INSTANCE
    _INSTANCE = None
