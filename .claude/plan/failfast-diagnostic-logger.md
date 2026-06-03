# 计划：Fail-Fast 独立诊断日志模块

## Context（为什么做这个改动）

**当前问题**：AiBrain 启动 Flask 时，13 个 import 发生在 `setup_logger()` 被调用之前。一旦其中任何一个失败（语法错误、import 错误、模块顶层崩溃），系统日志系统**根本不存在**——没有任何文件能记录这次失败。用户必须开终端窗口、复制 stdout/stderr 才知道哪里出问题。

**根因定位**（已验证）：
- `backend/app.py:1-49` — 13 个 stdlib + 第三方 import 全部在 `setup_logger()` 之前
- `backend/launcher/process_manager.py:68-72` — Flask 启动用 `subprocess.Popen(...)` + `stderr=subprocess.DEVNULL`，**完全屏蔽 stderr**。PM 只能通过 `proc.poll()` 非零退出码知道 Flask 死了，但不知道**为什么**。
- `backend/core/logger.py` — 没有任何 excepthook、stderr 重定向、crash log 机制
- 后果：开发者改了 `backend/modules/brain/memory.py` 写错一行 `SyntaxError` → Flask 死 → PM 看到非零退出码 → 5s 后重启 → 还是死 → 无限循环 → 用户看不到原因

**目标产物**：一个**完全不依赖 Flask** 的独立诊断模块 `backend/core/failfast.py`，在 `app.py` 第一行（甚至在 `setup_logger` 之前）就装上：
1. 捕获所有 uncaught 异常（含 import 阶段），写入 `logs/crashes/crash_<ts>_pid<n>.log`
2. 重定向 stderr 到 tee（stderr + crash 文件），把启动期间的 stderr 输出也记录下来
3. 提供 `smoke_test()` 主动扫描 `backend/**/*.py` 的 `py_compile`，改完代码先跑一遍能立刻知道哪个文件坏了
4. ProcessManager 在 Flask 死后 tail crash 日志，把原因打到 PM 自己的终端

---

## 总体架构

```
┌─────────────────────────────────────────────────────────────┐
│  启动顺序                                                    │
│                                                              │
│  1. backend/app.py 第 0-1 行                                  │
│     from core.failfast import install                        │
│     install(role='app')    ← 立刻装 excepthook + stderr tee │
│                                                              │
│  2. 后续所有 import/exec 阶段                                 │
│     - 语法错误 → SyntaxError → excepthook 捕获 → 写 crash log│
│     - ImportError → excepthook 捕获 → 写 crash log + 面包屑 │
│     - 任何 print/stderr → 同步写入终端 + crash log           │
│                                                              │
│  3. backend/app.py 第 49 行 setup_logger() 调用               │
│     - 现有 rolling log: logs/app_<ts>.log 开始生效           │
│     - 同时触发 FailFast.hand_off()                            │
│       → 关掉 stderr tee（避免影响后续业务日志）               │
│       → excepthook 改造为同时写 crash log + rolling log      │
│                                                              │
│  4. Flask 稳态运行                                            │
│     - 路由内错误仍走 Flask error handler（不变）              │
│     - uncaught 异常（罕见）→ 写两份日志                       │
│                                                              │
│  5. Flask 进程崩溃退出                                        │
│     - ProcessManager.poll() 返回非零                          │
│     - PM tail logs/crashes/crash_*.log 最后 30 行             │
│     - 打印到 PM 终端 + 设置 AIBRAIN_LAST_CRASH 环境变量       │
│     - 延迟 5s 再重启（防止语法错误的紧循环）                   │
└─────────────────────────────────────────────────────────────┘
```

---

## 关键设计决策

| 决策点 | 方案 | 理由 |
|---|---|---|
| 模块位置 | `backend/core/failfast.py` | 跟 `core/logger.py` 同目录；零依赖；纯 stdlib |
| 装入时机 | `app.py` 第 0-1 行（**最最最顶部**，sys.path 之后立刻装） | 必须早于任何可能出问题的 import |
| 兜底 | `from core.failfast import install` 包 try/except ImportError | 自身文件损坏时降级到纯 stderr |
| Crash 日志路径 | `logs/crashes/crash_<role>_<ts>_pid<n>.log` | PID 后缀避免多进程冲突；每进程一个文件，**不每异常一个** |
| stderr 处理 | 用 `_StderrTee` 包装 `sys.stderr`，启动期所有 stderr 同步到 crash log | 捕获 Flask 启动横幅、警告、未捕获 print |
| stderr 关停 | `setup_logger()` 触发 `hand_off()`，恢复原 stderr | 避免影响后续业务（transformers 进度条等） |
| 语法错误检测 | `py_compile.compile(file, doraise=True)` 在 smoke_test 中遍历 | 主动检测；不改文件就能跑 |
| import 探测 | `sys.meta_path` 装一个 finder（`_ImportBreadcrumb`）记最近 16 个 import | 出错时知道"刚才在 import 什么" |
| C 崩溃 | `faulthandler.enable(file=crash_fh, all_threads=True)` | 唯一能捕获 SIGSEGV/SIGFPE 的机制 |
| 线程安全 | 所有 crash log 写入用 `threading.Lock`；20 线程并发测试通过 | 意识流循环等多线程场景需要 |
| 抖动抑制 | 60s 内 >10 次崩溃则停止写入 + 写 `SUPPRESSED` 标记 | 防止死循环把磁盘写爆 |
| 失败模式关闭 | `AIBRAIN_FAILFAST=0` 环境变量 | 单测场景可关闭 |
| 现有 logger 兼容 | `setup_logger()` 仅在末尾加 5 行 `hand_off()`，签名不变 | 不破坏向后兼容 |
| PM 集成 | 检测 Flask 死 → tail crash log → 打印 + 设环境变量 | 现有 `restart_flask()` 加 20 行 |

---

## A. 新增/修改文件清单

### A.1 新文件

| 文件 | 作用 | 估计行数 |
|---|---|---|
| `backend/core/failfast.py` | `FailFast` 单例 + `CrashRecorder` + `_StderrTee` + `_ImportBreadcrumb` + `smoke_test()` | ~290 |
| `scripts/smoke_test.py` | CLI 入口：`python scripts/smoke_test.py [path]` | ~70 |
| `tests/test_failfast.py` | 单元测试（import 错误 / 语法错误 / 线程安全 / stderr 恢复） | ~150 |

### A.2 修改文件

| 文件 | 改动 | 行数 |
|---|---|---|
| `backend/app.py` | 第 0-1 行加 failfast import（必须在所有其他 import 之前） | +2 |
| `backend/launcher/start_flask.py` | 第 0-1 行加 failfast import（早于 `from app import app`） | +2 |
| `backend/core/logger.py` | `setup_logger()` 末尾加 `FailFast.get().hand_off(log)` 调用 | +5 |
| `backend/launcher/process_manager.py` | `restart_flask()` 失败时 tail crash log + 设 `AIBRAIN_LAST_CRASH` + 延迟 5s | +20 |

**总计**：~540 行（290 新 + 250 改）

---

## B. 三阶段保护机制

### Phase 1: Pre-Flask（`app.py` 第 0-1 行）

```python
# backend/app.py — 顶部新增 2 行
import os, sys
_BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _BASE)

try:
    from core.failfast import install as _install
    _install(role='app')
except Exception as _e:
    sys.stderr.write(f"[failfast] install skipped: {_e!r}\n")
```

`install()` 顺序：
1. 推导 `project_root`（从 `__file__` 往上找到 `backend/` 的父目录）
2. 创建 `logs/crashes/` 目录（包 try/except，权限问题不致命）
3. 打开 `crash_<role>_<ts>_pid<n>.log`，写头（PID、role、cwd、Python 版本、argv）
4. **保存并替换** `sys.excepthook` 为 `_excepthook`
5. **保存并替换** `threading.excepthook` 为 `_thread_excepthook`（Python 3.8+）
6. **包装 `sys.stderr`** 为 `_StderrTee`（可选，可通过 `enable_stderr_tee=False` 关闭）
7. **注册 meta_path finder** `_ImportBreadcrumb`，记录最近 16 次 import 尝试
8. `faulthandler.enable(file=crash_fh, all_threads=True)` 捕获 C 崩溃
9. 写 `--- PHASE -> INSTALL ---` 标记

### Phase 2: Mid-Flask（`setup_logger()` 调用时）

```python
# backend/core/logger.py — setup_logger() 末尾加 5 行
try:
    from core.failfast import FailFast
    FailFast.get().hand_off(log)
except Exception as _e:
    print(f"[logger] failfast handoff skipped: {_e}")
```

`hand_off(target_logger)` 行为：
- 恢复 `sys.stderr = self._prev_stderr`（关 tee）
- 写 `--- PHASE -> HANDOFF logger=memory ---` 标记到 crash log
- `target_logger.info("failfast: handoff complete, crash log -> ...")`
- 重新包装 excepthook，让它**同时**写 crash log 和 rolling log：
  ```python
  def _both(exc_type, exc_value, exc_tb):
      try: target_logger.critical("uncaught exception", exc_info=...)
      except Exception: pass
      prev(exc_type, exc_value, exc_tb)  # 老 hook 也写 crash log
  sys.excepthook = _both
  ```

### Phase 3: Post-Flask（稳态运行）

- `sys.excepthook` 永久保留
- 路由内错误仍走 Flask error handler（不动）
- 裸异常（极少）双写 crash log + rolling log
- 抖动抑制：60s 内 >10 次则写 `--- SUPPRESSED: too many crashes in 60s ---` 并停止

---

## C. 关键类实现要点

### C.1 `CrashRecorder`（线程安全崩溃写入器）

```python
class CrashRecorder:
    def __init__(self, project_root, role='app'):
        self.crash_dir = os.path.join(project_root, 'logs', 'crashes')
        _safe_mkdir(self.crash_dir)
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.crash_path = os.path.join(
            self.crash_dir, f'crash_{role}_{ts}_pid{os.getpid()}.log')
        self._fh = open(self.crash_path, 'a', encoding='utf-8', errors='replace')
        self._lock = threading.Lock()
        # 抖动抑制：60s 内 >10 次
        self._recent = deque()
        self._suppress_after = 10
        self._suppress_window = 60.0

    def write_crash(self, exc_type, exc_value, exc_tb) -> str:
        if self._should_suppress():
            return ""
        chain = "".join(traceback.format_exception(exc_type, exc_value, exc_tb, chain=True))
        # 提取最近 5 帧的局部变量（每帧最多 15 个，每值截 200 字符）
        locals_dump = self._extract_locals(exc_tb, depth=5)
        block = (
            "\n" + "=" * 70 + "\n"
            f"CRASH @ {self._now()}\n"
            f"Phase: {self._phase or 'UNKNOWN'}\n"
            f"Exception: {getattr(exc_type, '__name__', '?')}: {exc_value}\n"
            + "=" * 70 + "\n"
            + chain + "\n"
            + "Local variables (truncated):" + locals_dump + "\n"
        )
        self._safe_write(block)
        return self.crash_path

    def mark_phase(self, phase, **meta):
        self._phase = phase
        self._safe_write(f"\n--- PHASE -> {phase} {meta} @ {self._now()} ---\n")
```

### C.2 `_StderrTee`（stderr 复制器）

```python
class _StderrTee:
    def __init__(self, crash_fh, prefix="[stderr-tee]"):
        self._crash = crash_fh
        self._prev = sys.stderr
        self._prefix = prefix
        sys.stderr = self

    def write(self, s):
        try: self._prev.write(s)           # 终端
        except Exception: pass
        try:
            self._crash.write(f"{self._prefix} {s}")
            self._crash.flush()
        except Exception: pass
        return len(s)

    def flush(self):
        try: self._prev.flush()
        except Exception: pass
        try: self._crash.flush()
        except Exception: pass

    def __getattr__(self, name):
        # 代理 isatty() / encoding / fileno() 等
        return getattr(self._prev, name)

    def restore(self):
        sys.stderr = self._prev
```

### C.3 `smoke_test()`（主动语法检测）

```python
def smoke_test(project_root, target='backend') -> Tuple[int, List[str]]:
    import py_compile
    target_dir = os.path.join(project_root, target)
    failures = []
    files_checked = 0
    for root, _, files in os.walk(target_dir):
        if '__pycache__' in root or 'venv' in root:
            continue
        for f in files:
            if not f.endswith('.py'): continue
            path = os.path.join(root, f)
            files_checked += 1
            try:
                py_compile.compile(path, doraise=True)
            except py_compile.PyCompileError as e:
                failures.append(f"[SYNTAX] {path}: {e}")
    # 在干净子进程里尝试 import 关键模块
    import subprocess
    probe = "import core.logger, core.database, core.model, core.settings; " \
            "import routes.overview_routes, routes.memory_routes"
    try:
        r = subprocess.run(
            [sys.executable, '-c', probe],
            cwd=os.path.join(project_root, 'backend'),
            capture_output=True, text=True, timeout=30,
        )
        if r.returncode != 0:
            failures.append(f"[IMPORT] {r.stderr.strip()[:2000]}")
    except Exception as e:
        failures.append(f"[IMPORT-SUBPROCESS] {e}")
    return (0 if not failures else 1), [f"[smoke] files_checked={files_checked}"] + failures
```

---

## D. Crash 日志格式（实际效果）

```
══════════════════════════════════════════════════════════════════════
FAILFAST INSTALL @ 2026-06-04T14:23:17.951234
PID=12345  role=app  cwd=E:\Project\AiBrain
Python=3.12.4 (Windows-10-10.0.19044-SP0)
argv=['E:\\Project\\AiBrain\\backend\\app.py']
══════════════════════════════════════════════════════════════════════

--- PHASE -> INSTALL role=app pid=12345 @ 2026-06-04T14:23:17.952 ---

[stderr-tee] Flask 3.0.0
[stderr-tee] * Serving Flask app 'app'
[stderr-tee] * Debug mode: off

══════════════════════════════════════════════════════════════════════
CRASH @ 2026-06-04T14:23:18.123456
Phase: UNCAUGHT (type=ImportError)
Exception: ImportError: cannot import name 'foo' from 'werkzeug.exceptions'
══════════════════════════════════════════════════════════════════════

Traceback (most recent call last):
  File "E:\Project\AiBrain\backend\app.py", line 36, in <module>
    from flask import Flask, request, jsonify
  ...
ImportError: cannot import name 'foo' from 'werkzeug.exceptions'

Local variables (truncated):
  [frame 0] E:\Project\AiBrain\backend\app.py:36 in <module>
    __name__ = '__main__'
    _FLASK_PORT = 18765

Recent import attempts (oldest -> newest):
  2026-06-04T14:23:17.952  flask
  2026-06-04T14:23:17.953  flask_cors
  2026-06-04T14:23:17.954  core.logger
  2026-06-04T14:23:17.955  core.database
  2026-06-04T14:23:17.956  core.model
  2026-06-04T14:23:18.001  routes.overview_routes
```

---

## E. 复用现有代码

| 现有 | 复用方式 |
|---|---|
| `core/logger.py` `setup_logger()` | 仅末尾 +5 行 `hand_off()`，签名不变 |
| `process_manager.py` `restart_flask()` | +20 行：检测 `rc != 0` → tail crash log |
| `logs/archive/` 滚动归档模式 | 不复用 — crash log 是一进程一文件，PID 区分 |
| `py_compile`（stdlib） | smoke_test 直接调用 |

---

## F. 实施顺序（~3-4 小时）

1. **Step 1** (30min): 创建 `backend/core/failfast.py`（核心单例 + CrashRecorder + StderrTee + Breadcrumb + smoke_test + install）
2. **Step 2** (10min): `app.py` 第 0-1 行加 failfast；`start_flask.py` 同样处理
3. **Step 3** (15min): `core/logger.py` 末尾 +5 行 `hand_off()`
4. **Step 4** (20min): 正常启动一次，验证 `logs/crashes/crash_app_*.log` 有头 + handoff 行
5. **Step 5** (15min): 故意加一个 SyntaxError，验证 crash log 出现完整堆栈
6. **Step 6** (20min): `process_manager.py` 加 tail crash log
7. **Step 7** (30min): `scripts/smoke_test.py` + `tests/test_failfast.py`
8. **Step 8** (30min): 边界场景（线程安全、stderr 恢复、env 关闭）
9. **Step 9** (5min): `.gitignore` 确认 `logs/crashes/` 已被 `logs/` 规则覆盖

---

## G. 风险与边界

| 风险 | 缓解 |
|---|---|
| `failfast.py` 自身语法错误 | `from core.failfast import install` 包 try/except；自身用纯 stdlib |
| C 层崩溃（numpy segfault） | `faulthandler.enable(file=crash_fh, all_threads=True)` |
| 多线程并发写 crash log | 所有写入用 `threading.Lock` |
| stderr 重定向影响 transformers 进度条等 | `_StderrTee.__getattr__` 代理属性 + `enable_stderr_tee=False` 可关 + `AIBRAIN_FAILFAST=0` 完全跳过 |
| 错误风暴把磁盘写爆 | 60s 内 >10 次则停止写入 + 写 `SUPPRESSED` 标记 |
| 多进程冲突 | 文件名带 PID，天然隔离 |
| PM 重启死循环 | 检测到 SyntaxError 后延迟 5s 重启（防紧循环） |
| `hand_off` 时刻 race | `sys.excepthook` 替换是原子属性写；老 hook 也写 crash log，安全 |
| 现有 `setup_logger` API 必须不变 | 仅 +5 行，签名/返回值都不变 |
| 单测想关掉 | `AIBRAIN_FAILFAST=0` 环境变量 |

---

## H. 验证方案

### H.1 语法错误测试
```bash
echo 'def x(:' > E:/Project/AiBrain/backend/core/_broken.py
echo 'from core._broken import x' >> E:/Project/AiBrain/backend/app.py
python scripts/smoke_test.py
# 期望：exit 1，输出 [SYNTAX] E:\...\core\_broken.py: ...
python backend/app.py
# 期望：
#   - logs/crashes/crash_app_<ts>_pid<n>.log 存在 + 完整 traceback
#   - logs/app_<ts>.log 不存在（setup_logger 没被调用）
#   - 退出码非零
# 然后撤回改动
```

### H.2 ImportError 测试
```bash
echo 'raise ImportError("boom")' > E:/Project/AiBrain/backend/core/_broken.py
python backend/app.py
# 期望：
#   - stderr 终端显示 traceback（Python 默认 excepthook）
#   - crash log 包含完整堆栈 + import 面包屑
#   - 退出码非零
```

### H.3 正常通过测试
```bash
# 不改任何文件
python backend/app.py --flask-only
# 期望：
#   - logs/crashes/crash_app_*.log 仅有 header + PHASE=HANDOFF 行
#   - logs/app_<ts>.log 正常
#   - Flask 正常运行
```

### H.4 线程安全测试
```python
# tests/test_failfast.py
def test_concurrent_crashes(tmp_path):
    install(project_root=str(tmp_path), role='test')
    def boom():
        try: raise ValueError("thread boom")
        except ValueError: sys.excepthook(*sys.exc_info())
    ts = [threading.Thread(target=boom) for _ in range(20)]
    for t in ts: t.start()
    for t in ts: t.join()
    text = (tmp_path / 'logs' / 'crashes').read_text()
    assert text.count('ValueError: thread boom') <= 10
    assert 'SUPPRESSED' in text
```

### H.5 端到端 PM 集成测试
```bash
# 启动整个系统（PM + Flask + WebView）
python start.py
# 在另一个终端故意弄坏 backend 文件
echo 'def x(:' >> E:/Project/AiBrain/backend/core/_broken.py
# 触发重启
curl -X POST http://127.0.0.1:18765/overview/flask/restart
# 期望 PM 终端立刻打印：
#   [flask] Last crash log: crash_app_20260604_142318_pid12345.log
#   [flask] tail:
#     | ==========
#     | CRASH @ 2026-06-04T14:23:18.123456
#     | Phase: UNCAUGHT (type=SyntaxError)
#     | ...
```

---

## I. 关键文件速查

| 类型 | 路径 |
|---|---|
| 核心 | `backend/core/failfast.py` (新, ~290 行) |
| 核心 | `backend/app.py` (改, +2 行) |
| 核心 | `backend/launcher/start_flask.py` (改, +2 行) |
| 核心 | `backend/core/logger.py` (改, +5 行 hand_off) |
| 集成 | `backend/launcher/process_manager.py` (改, +20 行 tail crash) |
| CLI | `scripts/smoke_test.py` (新, ~70 行) |
| 测试 | `tests/test_failfast.py` (新, ~150 行) |

---

## J. 何时使用

| 场景 | 怎么用 |
|---|---|
| 改完 backend 任意 .py 文件，想立刻知道有没有坏 | `python scripts/smoke_test.py` |
| Flask 莫名死了 | 直接打开 `logs/crashes/crash_*.log` 看最后一条 |
| 改完代码想热重启 | 调 `POST /overview/flask/restart`，PM tail 完会显示原因 |
| 单测想关掉 | `set AIBRAIN_FAILFAST=0` 后启动 |
| 改 failfast 自身 | 跑 `python -m backend.core.failfast` 走自检路径 |
