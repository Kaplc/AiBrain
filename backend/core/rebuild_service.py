"""
RebuildService - 实体网络重建服务（单例）

职责：
- 在 Flask 进程内启动独立线程执行 rebuild_graph.rebuild()
- 在内存中维护实时进度 state 字典
- 通过 stop_flag（threading.Event）支持取消
- 对外暴露 start/cancel/get_state 接口供 routes 调用

不持久化：Flask 重启后状态清空。
"""
import os
import time
import threading
import logging

logger = logging.getLogger('memory')


def _init_state() -> dict:
    """初始 state 模板"""
    return {
        "status": "idle",  # idle / running / completed / failed
        "started_at": None,
        "finished_at": None,
        "total": 0,
        "processed": 0,
        "success": 0,
        "empty": 0,
        "failed": 0,
        "retry_success": 0,
        "current_phase": "idle",  # init / first_pass / retry / finished / idle
        "workers": 5,
        "llm_calls": 0,
        "llm_calls_success": 0,
        "llm_calls_failed": 0,
        "error": None,
    }


class RebuildService:
    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        self.state: dict = _init_state()
        self._thread: threading.Thread | None = None
        self._stop_flag = threading.Event()
        self._state_lock = threading.Lock()
        self._project_root: str | None = None

    @classmethod
    def get_instance(cls) -> "RebuildService":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def set_project_root(self, project_root: str):
        """由 app.py 在启动时设置 project_root（用于日志路径）"""
        self._project_root = project_root

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, workers: int = 5, batch_size: int = 10, delay: float = 1.0) -> bool:
        """启动重建任务。返回 True 表示已启动，False 表示已有任务在跑"""
        with self._state_lock:
            if self.is_running():
                return False

            # 重置 state
            self.state = _init_state()
            self.state.update({
                "status": "running",
                "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "workers": workers,
            })
            self._stop_flag = threading.Event()

        def _run():
            try:
                from main_brain.memory.graph_rebuild import rebuild
                rebuild(self.state, self._stop_flag,
                        workers=workers, batch_size=batch_size, delay_between_batches=delay)
                # rebuild 完成后，根据 stop_flag 决定状态
                with self._state_lock:
                    if self.state.get("status") == "running":
                        self.state["status"] = "completed"
                        self.state["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
                        self.state["current_phase"] = "finished"
            except Exception as e:
                logger.error(f"[rebuild] 任务异常: {e}")
                with self._state_lock:
                    self.state["status"] = "failed"
                    self.state["error"] = str(e)
                    self.state["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")

        self._thread = threading.Thread(target=_run, daemon=True, name="rebuild-graph")
        self._thread.start()
        logger.info(f"[rebuild] 任务启动 workers={workers} batch_size={batch_size}")
        return True

    def cancel(self) -> bool:
        """设置停止标志。返回 True 表示已设置"""
        with self._state_lock:
            if not self.is_running():
                return False
            self._stop_flag.set()
            self.state["status"] = "idle"
            self.state["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            logger.info("[rebuild] 已设置停止标志")
            return True

    def get_state(self) -> dict:
        """返回当前 state 副本 + 派生字段（progress_pct / elapsed_seconds）"""
        with self._state_lock:
            s = dict(self.state)
        # 派生字段
        total = s.get("total", 0) or 0
        processed = s.get("processed", 0) or 0
        phase = s.get("current_phase")
        # 进度规则：
        # - first_pass: 0% → 99%（最高 99%，给重试留 1%）
        # - retry:      99% → 100%（按 retry_processed / retry_total）
        # - finished:   100%
        if phase == "retry":
            retry_total = s.get("retry_total", 0) or 0
            retry_processed = s.get("retry_processed", 0) or 0
            s["progress_pct"] = 99 + int(retry_processed * 1 / retry_total) if retry_total > 0 else 99
        elif phase == "finished":
            s["progress_pct"] = 100
        else:
            s["progress_pct"] = min(99, int(processed * 99 / total)) if total > 0 else 0
        started = s.get("started_at")
        if started:
            try:
                from datetime import datetime
                t0 = datetime.strptime(started, "%Y-%m-%dT%H:%M:%S")
                s["elapsed_seconds"] = int((datetime.now() - t0).total_seconds())
            except Exception:
                s["elapsed_seconds"] = 0
        else:
            s["elapsed_seconds"] = 0
        return s

    def get_logs(self, lines: int = 100) -> list[str]:
        """读取后端 logger 末尾 N 行（复用 LogManager 逻辑）"""
        try:
            from modules.Log.log_mod import LogManager
            mgr = LogManager.get_instance()
            project_root = self._project_root or os.path.dirname(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            )
            log_file, _ = mgr.get_latest_log_file(project_root)
            if not log_file:
                return []
            result = mgr.read_log_tail(log_file, lines)
            return result.get("lines", [])
        except Exception as e:
            logger.warning(f"[rebuild] 读取日志失败: {e}")
            return []
