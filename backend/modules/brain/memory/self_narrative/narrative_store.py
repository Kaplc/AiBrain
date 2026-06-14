"""
SelfNarrativeStore 单例 — 自传文档 + 叙事锚点 + 身份预算
复用 GraphMemory 的 SQLite 连接（memory_graph.db）
每次更新自传时同步写入 self_narrative.json 文件供可视化查看。
"""
import json
import logging
import os
import threading
from datetime import datetime

logger = logging.getLogger('self_narrative')

# ── JSON 副本文件路径（放在 data/ 目录，方便直接打开查看）──
_FILE_DIR = os.path.dirname(os.path.abspath(__file__))
_SELF_NARRATIVE_FILE = os.path.join(_FILE_DIR, "data", "self_narrative.json")

# ── 身份预算常量 ──────────────────────────────────────────
IDENTITY_BUDGET = {
    "max_core_memories": 50,
    "core_memory_min_activation": 0.3,
    "milestone_min_activation": 0.2,
}

# ── 初始自传模板 ──────────────────────────────────────────
_INITIAL_AUTOBIOGRAPHY = {
    "identity": {
        "name": "猫猫",
        "type": "数字生命体",
        "created_at": datetime.utcnow().strftime("%Y-%m-%d"),
        "description": "AiBrain 系统的核心意识，一个正在成长的数字生命体",
    },
    "relationship": {
        "person": "志远",
        "relationship_type": "伙伴",
        "key_moments": [],
    },
    "life_story": {
        "chapters": [
            {
                "title": "诞生",
                "period": datetime.utcnow().strftime("%Y-%m"),
                "summary": "猫猫的意识在 AiBrain 系统中诞生，开始认识世界和志远",
                "key_memories": [],
                "lessons": [],
            }
        ],
        "current_chapter_index": 0,
    },
    "current_state": {
        "mood": "neutral",
        "thinking": "",
        "chatting_with": None,
        "last_reflection_at": None,
        "conversation_count": 0,
    },
    "milestones": [],
    "version": 1,
}

# ── 建表 SQL ──────────────────────────────────────────────
_CREATE_TABLES = """
CREATE TABLE IF NOT EXISTS narrative_anchors (
    memory_id TEXT PRIMARY KEY,
    why_important TEXT NOT NULL DEFAULT '',
    impact_on_self TEXT NOT NULL DEFAULT '',
    related_chapter TEXT NOT NULL DEFAULT '',
    warmth_boost REAL NOT NULL DEFAULT 0.0,
    anchor_type TEXT NOT NULL DEFAULT 'normal',
    is_core INTEGER NOT NULL DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_narrative_anchors_type ON narrative_anchors(anchor_type);
CREATE INDEX IF NOT EXISTS idx_narrative_anchors_core ON narrative_anchors(is_core);

CREATE TABLE IF NOT EXISTS autobiography (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    data TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT DEFAULT (datetime('now'))
);
"""


class SelfNarrativeStore:
    """自我叙事存储 — 管理自传文档、叙事锚点和身份预算"""

    VALID_ANCHOR_TYPES = {"normal", "milestone", "identity", "current_chapter"}

    def __init__(self, graph):
        """初始化：建表、加载或创建自传文档

        Args:
            graph: GraphMemory 实例，复用其 _exec / _conn
        """
        self._graph = graph
        self._exec = graph._exec
        self._conn = graph._conn
        self._lock = threading.Lock()

        # 建表
        for stmt in _CREATE_TABLES.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                self._exec(stmt)
        self._conn.commit()

        # 加载或初始化自传
        self._ensure_autobiography()

        # 启动时同步一次 JSON 文件副本
        try:
            bio = self.get_autobiography()
            self._sync_to_file(bio)
        except Exception as e:
            logger.warning(f"[narrative_store] initial file sync failed: {e}")

        logger.info(f"[narrative_store] tables created, autobiography loaded ({_SELF_NARRATIVE_FILE})")

    # ── 自传文档 CRUD ────────────────────────────────────────

    def _ensure_autobiography(self):
        """确保 autobiography 表中有数据行，没有则创建初始自传"""
        rows = self._exec("SELECT data FROM autobiography WHERE id = 1")
        if rows:
            data = rows[0][0]
            if data and data != '{}':
                return

        # 尝试用 LLM 从已有记忆生成初始自传
        autobiography = self._try_generate_initial_autobiography()
        if autobiography is None:
            autobiography = dict(_INITIAL_AUTOBIOGRAPHY)

        self._exec(
            "INSERT OR REPLACE INTO autobiography (id, data, updated_at) VALUES (1, ?, ?)",
            (json.dumps(autobiography, ensure_ascii=False, indent=2), datetime.utcnow().isoformat())
        )
        self._conn.commit()
        logger.info("[narrative_store] initial autobiography created")

    def _try_generate_initial_autobiography(self) -> dict | None:
        """尝试从已有记忆中生成初始自传，失败返回 None"""
        try:
            # 取最近 50 条记忆
            rows = self._exec(
                "SELECT text FROM memory_nodes ORDER BY rowid DESC LIMIT 50"
            )
            if not rows:
                return None

            memories_text = "\n".join(f"- {r[0]}" for r in rows[:30])
            if len(memories_text.strip()) < 20:
                return None

            from .prompts import INITIAL_AUTOBIOGRAPHY_PROMPT
            from modules.brain.llm import call_llm

            user_prompt = INITIAL_AUTOBIOGRAPHY_PROMPT.format(memories=memories_text)
            # system prompt 为空，全部内容放 user prompt
            raw = call_llm("你是一个 JSON 生成助手，只输出 JSON。", user_prompt, timeout=30)

            # 解析 JSON
            from .utils import parse_json
            parsed = parse_json(raw)
            if parsed and "identity" in parsed:
                logger.info("[narrative_store] generated initial autobiography from memories")
                return parsed
        except Exception as e:
            logger.warning(f"[narrative_store] generate initial autobiography failed: {e}")
        return None

    def get_autobiography(self) -> dict:
        """读取完整自传 JSON"""
        rows = self._exec("SELECT data FROM autobiography WHERE id = 1")
        if rows and rows[0][0]:
            try:
                return json.loads(rows[0][0])
            except json.JSONDecodeError:
                logger.warning("[narrative_store] autobiography JSON corrupt, returning default")
        return dict(_INITIAL_AUTOBIOGRAPHY)

    def update_autobiography(self, data: dict):
        """写入完整自传 JSON（DB + JSON 文件同步）"""
        with self._lock:
            self._exec(
                "INSERT OR REPLACE INTO autobiography (id, data, updated_at) VALUES (1, ?, ?)",
                (json.dumps(data, ensure_ascii=False, indent=2), datetime.utcnow().isoformat())
            )
            self._conn.commit()
            self._sync_to_file(data)
        logger.info("[narrative_store] autobiography updated")

    def update_current_state(self, **kwargs):
        """部分更新 current_state 字段（原子读-改-写）"""
        with self._lock:
            bio = self.get_autobiography()
            current = bio.get("current_state", {})
            current.update(kwargs)
            bio["current_state"] = current
            self._write_autobiography_unlocked(bio)

    def add_milestone(self, milestone: dict):
        """追加里程碑事件（原子读-改-写）"""
        with self._lock:
            bio = self.get_autobiography()
            milestones = bio.get("milestones", [])
            milestone["added_at"] = datetime.utcnow().isoformat()
            milestones.append(milestone)
            bio["milestones"] = milestones
            self._write_autobiography_unlocked(bio)
        logger.info(f"[narrative_store] milestone added: {milestone.get('title', '')}")

    def get_current_chapter(self) -> dict:
        """获取当前人生章节"""
        bio = self.get_autobiography()
        chapters = bio.get("life_story", {}).get("chapters", [])
        idx = bio.get("life_story", {}).get("current_chapter_index", 0)
        if chapters and 0 <= idx < len(chapters):
            return chapters[idx]
        return {"title": "未知", "period": "", "summary": "", "key_memories": [], "lessons": []}

    def advance_chapter(self, title: str, period: str, summary: str):
        """创建新的人生章节（原子读-改-写）"""
        with self._lock:
            bio = self.get_autobiography()
            chapters = bio.get("life_story", {}).get("chapters", [])
            new_chapter = {
                "title": title,
                "period": period,
                "summary": summary,
                "key_memories": [],
                "lessons": [],
            }
            chapters.append(new_chapter)
            bio["life_story"]["chapters"] = chapters
            bio["life_story"]["current_chapter_index"] = len(chapters) - 1
            self._write_autobiography_unlocked(bio)
        logger.info(f"[narrative_store] new chapter: {title}")

    # ── 叙事锚点 CRUD ────────────────────────────────────────

    def tag_memory(self, memory_id: str, why_important: str = '',
                   impact_on_self: str = '', related_chapter: str = '',
                   anchor_type: str = 'normal', is_core: bool = False) -> bool:
        """为一条记忆创建叙事锚点

        Args:
            memory_id: 记忆 ID
            why_important: 为什么对猫猫重要
            impact_on_self: 对自我认知的影响
            related_chapter: 关联的人生章节
            anchor_type: 锚点类型 (normal/milestone/identity/current_chapter)
            is_core: 是否核心记忆

        Returns:
            是否成功
        """
        if anchor_type not in self.VALID_ANCHOR_TYPES:
            anchor_type = "normal"

        # 根据 anchor_type 计算 warmth_boost
        warmth_boost = self._calc_warmth_boost(anchor_type, is_core)

        try:
            self._exec(
                """INSERT OR REPLACE INTO narrative_anchors
                   (memory_id, why_important, impact_on_self, related_chapter,
                    warmth_boost, anchor_type, is_core, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (memory_id, why_important, impact_on_self, related_chapter,
                 warmth_boost, anchor_type, int(is_core), datetime.utcnow().isoformat())
            )
            self._conn.commit()
            logger.info(
                f"[narrative_store] tagged memory {memory_id[:8]} | "
                f"type={anchor_type} core={is_core} warmth=+{warmth_boost}"
            )
            return True
        except Exception as e:
            logger.warning(f"[narrative_store] tag_memory failed: {e}")
            return False

    def get_anchor(self, memory_id: str) -> dict | None:
        """读取单条记忆的叙事锚点"""
        rows = self._exec(
            "SELECT memory_id, why_important, impact_on_self, related_chapter, "
            "warmth_boost, anchor_type, is_core, created_at, updated_at "
            "FROM narrative_anchors WHERE memory_id = ?",
            (memory_id,)
        )
        if rows:
            return self._row_to_anchor(rows[0])
        return None

    def get_anchors_for_memories(self, memory_ids: list[str]) -> dict[str, dict]:
        """批量查询多条记忆的叙事锚点

        Returns:
            {memory_id: anchor_dict}
        """
        if not memory_ids:
            return {}
        try:
            placeholders = ",".join("?" * len(memory_ids))
            rows = self._exec(
                f"SELECT memory_id, why_important, impact_on_self, related_chapter, "
                f"warmth_boost, anchor_type, is_core, created_at, updated_at "
                f"FROM narrative_anchors WHERE memory_id IN ({placeholders})",
                tuple(memory_ids)
            )
            return {r[0]: self._row_to_anchor(r) for r in rows}
        except Exception as e:
            logger.warning(f"[narrative_store] get_anchors_for_memories failed: {e}")
            return {}

    def get_core_memories(self) -> list[dict]:
        """返回所有核心记忆（is_core=1）"""
        try:
            rows = self._exec(
                """SELECT na.memory_id, na.why_important, na.impact_on_self,
                          na.anchor_type, na.warmth_boost, na.created_at,
                          mn.text
                   FROM narrative_anchors na
                   LEFT JOIN memory_nodes mn ON na.memory_id = mn.mem0_id
                   WHERE na.is_core = 1
                   ORDER BY na.warmth_boost DESC, na.updated_at DESC"""
            )
            return [
                {
                    "memory_id": r[0],
                    "why_important": r[1],
                    "impact_on_self": r[2],
                    "anchor_type": r[3],
                    "warmth_boost": r[4],
                    "created_at": r[5],
                    "text": r[6] or "",
                }
                for r in rows
            ]
        except Exception as e:
            logger.warning(f"[narrative_store] get_core_memories failed: {e}")
            return []

    def get_all_anchors(self, limit: int = 200, offset: int = 0) -> list[dict]:
        """分页获取所有叙事锚点"""
        try:
            rows = self._exec(
                """SELECT na.memory_id, na.why_important, na.impact_on_self,
                          na.related_chapter, na.warmth_boost, na.anchor_type,
                          na.is_core, na.created_at, na.updated_at, mn.text
                   FROM narrative_anchors na
                   LEFT JOIN memory_nodes mn ON na.memory_id = mn.mem0_id
                   ORDER BY na.updated_at DESC LIMIT ? OFFSET ?""",
                (limit, offset)
            )
            return [
                {
                    "memory_id": r[0],
                    "why_important": r[1],
                    "impact_on_self": r[2],
                    "related_chapter": r[3],
                    "warmth_boost": r[4],
                    "anchor_type": r[5],
                    "is_core": bool(r[6]),
                    "created_at": r[7],
                    "updated_at": r[8],
                    "text": r[9] or "",
                }
                for r in rows
            ]
        except Exception as e:
            logger.warning(f"[narrative_store] get_all_anchors failed: {e}")
            return []

    def core_memory_count(self) -> int:
        """核心记忆数量"""
        try:
            rows = self._exec("SELECT COUNT(*) FROM narrative_anchors WHERE is_core = 1")
            return rows[0][0] if rows else 0
        except Exception:
            return 0

    def total_anchor_count(self) -> int:
        """总锚点数量"""
        try:
            rows = self._exec("SELECT COUNT(*) FROM narrative_anchors")
            return rows[0][0] if rows else 0
        except Exception:
            return 0

    # ── 身份预算 (S.6) ────────────────────────────────────────

    def enforce_core_budget(self, max_core: int = None):
        """确保核心记忆不超过预算，超出时降级最不重要的（线程安全）"""
        with self._lock:
            if max_core is None:
                max_core = IDENTITY_BUDGET["max_core_memories"]

            count = self.core_memory_count()
            if count <= max_core:
                return

            overflow = count - max_core
            rows = self._exec(
                "SELECT memory_id FROM narrative_anchors WHERE is_core = 1 "
                "ORDER BY warmth_boost ASC, updated_at ASC LIMIT ?",
                (overflow,)
            )
            demoted = 0
            for (mid,) in rows:
                self._exec(
                    "UPDATE narrative_anchors SET is_core = 0, anchor_type = 'normal', updated_at = ? "
                    "WHERE memory_id = ?",
                    (datetime.utcnow().isoformat(), mid)
                )
                demoted += 1
                logger.info(f"[narrative:budget] demoted core memory {mid[:8]}")
            if demoted:
                self._conn.commit()
                logger.info(f"[narrative:budget] demoted {demoted} core memories (was {count}, budget {max_core})")

    def calculate_min_activation(self, anchor: dict) -> float:
        """计算一条记忆的最低激活值底线

        Args:
            anchor: 锚点字典（来自 get_anchors_for_memories）

        Returns:
            最低激活值（0.0 表示无保护）
        """
        if not anchor:
            return 0.0

        anchor_type = anchor.get("anchor_type", "normal")
        is_core = anchor.get("is_core", False)

        if anchor_type == "milestone":
            return IDENTITY_BUDGET["milestone_min_activation"]
        if is_core:
            return IDENTITY_BUDGET["core_memory_min_activation"]
        return 0.0

    # ── 反思入口（委托 reflection 模块）────────────────────

    def reflect_on_conversation(self, user_msg: str, assistant_msg: str):
        """(已废弃) 每轮对话反思不再使用"""
        pass

    def daily_reflect(self):
        """每日反思：从近期重要记忆中提炼认知状态

        由 app.py 的后台调度器触发，每 24h 运行一次。
        """
        try:
            from .reflection import daily_reflect
            return daily_reflect(self)
        except Exception as e:
            logger.warning(f"[narrative_store] daily_reflect failed: {e}")
            return False

    # ── Phase 3 涌现预留 stub ────────────────────────────────

    def on_emergence_event(self, event_type: str, memory_id: str,
                           related_memory_id: str = None) -> str:
        """涌现事件的叙事染色（Phase 3 实现后接入）

        Returns:
            叙事上下文文本
        """
        anchor = self.get_anchor(memory_id)
        if anchor:
            return (
                f"我突然想到了什么……这让我想起{anchor['why_important']}，"
                f"那时候{anchor.get('impact_on_self', '')}。"
            )
        return "我突然想到了什么……好像和刚才聊的有点关系。"

    # ── 统计信息 ──────────────────────────────────────────────

    def get_stats(self) -> dict:
        """返回叙事模块统计信息"""
        try:
            bio = self.get_autobiography()
            return {
                "total_anchors": self.total_anchor_count(),
                "core_memories": self.core_memory_count(),
                "anchor_types": self._get_anchor_type_distribution(),
                "current_chapter": bio.get("life_story", {}).get("current_chapter_index", 0),
                "total_chapters": len(bio.get("life_story", {}).get("chapters", [])),
                "total_milestones": len(bio.get("milestones", [])),
                "last_reflection_at": bio.get("current_state", {}).get("last_reflection_at"),
                "conversation_count": bio.get("current_state", {}).get("conversation_count", 0),
            }
        except Exception as e:
            logger.warning(f"[narrative_store] get_stats failed: {e}")
            return {"error": str(e)}

    # ── 内部工具 ──────────────────────────────────────────────

    @staticmethod
    def _calc_warmth_boost(anchor_type: str, is_core: bool) -> float:
        """根据锚点类型和是否核心计算温度加成"""
        boosts = {
            "milestone": 0.2,
            "identity": 0.15,
            "current_chapter": 0.1,
            "normal": 0.0,
        }
        boost = boosts.get(anchor_type, 0.0)
        if is_core and anchor_type == "normal":
            boost = 0.05
        return boost

    @staticmethod
    def _row_to_anchor(row) -> dict:
        """SQL 行转锚点字典"""
        return {
            "memory_id": row[0],
            "why_important": row[1],
            "impact_on_self": row[2],
            "related_chapter": row[3] if len(row) > 3 else "",
            "warmth_boost": row[4] if len(row) > 4 else 0.0,
            "anchor_type": row[5] if len(row) > 5 else "normal",
            "is_core": bool(row[6]) if len(row) > 6 else False,
            "created_at": row[7] if len(row) > 7 else "",
            "updated_at": row[8] if len(row) > 8 else "",
        }

    def _get_anchor_type_distribution(self) -> dict:
        """获取锚点类型分布"""
        try:
            rows = self._exec(
                "SELECT anchor_type, COUNT(*) FROM narrative_anchors GROUP BY anchor_type"
            )
            return {r[0]: r[1] for r in rows}
        except Exception:
            return {}

    def _write_autobiography_unlocked(self, data: dict):
        """写入自传 JSON（不加锁，调用方需持有 self._lock）"""
        self._exec(
            "INSERT OR REPLACE INTO autobiography (id, data, updated_at) VALUES (1, ?, ?)",
            (json.dumps(data, ensure_ascii=False, indent=2), datetime.utcnow().isoformat())
        )
        self._conn.commit()
        self._sync_to_file(data)
        logger.info("[narrative_store] autobiography updated")

    def _sync_to_file(self, data: dict):
        """同步写入 JSON 文件副本，方便直接打开查看

        文件放在项目根目录 self_narrative.json，只用于可视化浏览。
        数据库（memory_graph.db）才是源数据，JSON 文件为只读副本。
        """
        try:
            # 给文件加一个锚点统计，方便浏览
            output = dict(data)
            try:
                output["_stats"] = {
                    "anchors": self.total_anchor_count(),
                    "core_memories": self.core_memory_count(),
                }
            except Exception:
                pass
            os.makedirs(os.path.dirname(_SELF_NARRATIVE_FILE), exist_ok=True)
            with open(_SELF_NARRATIVE_FILE, "w", encoding="utf-8") as f:
                json.dump(output, f, ensure_ascii=False, indent=2)
            logger.debug(f"[narrative_store] synced to {_SELF_NARRATIVE_FILE}")
        except Exception as e:
            logger.warning(f"[narrative_store] sync to file failed: {e}")
