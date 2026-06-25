"""
PipelineEngine - 流水线引擎单例
统一编排步骤执行，管理上下文传递，支持异常容错和超时控制
"""
import logging
import threading
import time
import concurrent.futures
from typing import Any, Optional

from .context import PipelineContext, StepDef

logger = logging.getLogger('memory.pipeline')


class PipelineEngine:
    """流水线引擎：注册步骤、管理拓扑、执行流水线

    线程安全：配置读写通过 threading.Lock 保护
    """

    _instance: Optional['PipelineEngine'] = None
    _lock = threading.Lock()

    def __init__(self):
        self._registry: dict[str, StepDef] = {}  # name -> StepDef
        self._pipelines: dict[str, list[dict]] = {}  # "store"/"search" -> [{name, enabled, required}]
        self._config_lock = threading.Lock()
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)

    @classmethod
    def get_instance(cls) -> 'PipelineEngine':
        """获取引擎单例"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    # ── 步骤注册 ──────────────────────────────────────────────

    def register_step(self, step: StepDef) -> None:
        """注册一个步骤到引擎

        Args:
            step: 步骤定义对象
        """
        self._registry[step.name] = step
        logger.info(f"[pipeline] registered step: {step.name} ({step.pipeline}) required={step.required}")

    def get_step(self, name: str) -> Optional[StepDef]:
        """获取已注册的步骤"""
        return self._registry.get(name)

    # ── 流水线拓扑管理 ────────────────────────────────────────

    def set_pipeline(self, name: str, steps: list[dict]) -> None:
        """设置流水线拓扑（仅内存，重启后恢复为 DEFAULT_CONFIG）

        Args:
            name: "store" 或 "search"
            steps: [{name, enabled, required}, ...]
        """
        with self._config_lock:
            self._pipelines[name] = steps
        logger.info(f"[pipeline] set_pipeline({name}): {[s['name'] for s in steps]}")

    def get_pipeline(self, name: str) -> list[dict]:
        """获取流水线拓扑（从内存读取）

        Args:
            name: "store" 或 "search"

        Returns:
            步骤配置列表
        """
        with self._config_lock:
            return list(self._pipelines.get(name, []))

    def get_all_pipelines(self) -> dict:
        """获取所有流水线配置"""
        with self._config_lock:
            return {k: list(v) for k, v in self._pipelines.items()}

    def set_all_pipelines(self, pipelines: dict) -> None:
        """设置所有流水线配置（仅内存）"""
        with self._config_lock:
            self._pipelines = {k: v for k, v in pipelines.items()}

    # ── 执行引擎 ──────────────────────────────────────────────

    def run(self, ctx: PipelineContext, pipeline: str) -> Any:
        """执行一条流水线

        Args:
            ctx: 流水线上下文
            pipeline: "store" 或 "search"

        Returns:
            ctx.output

        Raises:
            RuntimeError: required 步骤失败时
        """
        steps_config = self.get_pipeline(pipeline)
        if not steps_config:
            logger.warning(f"[pipeline] no steps configured for '{pipeline}'")
            return ctx.output

        logger.info(f"[pipeline] RUN {pipeline} | steps={[s['name'] for s in steps_config]}")

        for step_cfg in steps_config:
            if ctx.aborted:
                logger.info(f"[pipeline] aborted, skipping remaining steps")
                break

            step_name = step_cfg["name"]
            is_enabled = step_cfg.get("enabled", True)
            is_required = step_cfg.get("required", False)

            # 跳过禁用步骤
            if not is_enabled:
                logger.debug(f"[pipeline] SKIP {step_name} (disabled)")
                continue

            # 查找步骤定义
            step_def = self._registry.get(step_name)
            if step_def is None:
                logger.error(f"[pipeline] step '{step_name}' not registered, skipping")
                continue

            # 执行步骤（带超时和异常处理）
            self._run_step(ctx, step_def, is_required)

        logger.info(
            f"[pipeline] DONE {pipeline} | "
            f"results={list(ctx.step_results.keys())} | "
            f"aborted={ctx.aborted}"
        )
        return ctx.output

    def _run_step(self, ctx: PipelineContext, step: StepDef, is_required: bool) -> None:
        """执行单个步骤，带超时控制和异常处理

        Args:
            ctx: 流水线上下文
            step: 步骤定义
            is_required: 是否为强制步骤
        """
        step_name = step.name
        start_time = time.monotonic()

        # 触发 on_start 钩子
        if step.on_start:
            try:
                step.on_start(ctx)
            except Exception as e:
                logger.warning(f"[pipeline] {step_name}.on_start error: {e}")

        try:
            # 使用线程池执行，支持超时控制
            future = self._executor.submit(step.execute, ctx)
            try:
                future.result(timeout=step.timeout)
            except concurrent.futures.TimeoutError:
                raise TimeoutError(f"Step '{step_name}' timed out after {step.timeout}s")

            duration = time.monotonic() - start_time
            ctx.step_results[step_name] = {
                "duration": round(duration, 4),
                "status": "success",
                "error": None,
            }
            logger.info(f"[pipeline] {step_name} OK ({duration:.3f}s)")

            # 触发 on_finish 钩子
            if step.on_finish:
                try:
                    step.on_finish(ctx)
                except Exception as e:
                    logger.warning(f"[pipeline] {step_name}.on_finish error: {e}")

        except Exception as e:
            duration = time.monotonic() - start_time
            ctx.step_results[step_name] = {
                "duration": round(duration, 4),
                "status": "error",
                "error": str(e),
            }

            # 触发 on_error 钩子
            if step.on_error:
                try:
                    step.on_error(ctx, e)
                except Exception as hook_err:
                    logger.warning(f"[pipeline] {step_name}.on_error error: {hook_err}")

            if is_required:
                logger.error(f"[pipeline] {step_name} FAILED (required): {e}")
                ctx.aborted = True
                raise RuntimeError(f"Required step '{step_name}' failed: {e}") from e
            else:
                logger.warning(f"[pipeline] {step_name} FAILED (non-required, skip): {e}")
