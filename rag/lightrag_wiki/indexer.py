"""
Wiki 索引管理 - MD 文件扫描、MD5 变化检测、增量索引
"""
import os
import json
import hashlib
import logging
import sys
import io
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# 索引进度全局状态
_index_progress = {
    "running": False,
    "done": 0,
    "total": 0,
    "current_file": "",
    "status": "idle",  # idle / running / done / error
    "result": None,
}

# 索引日志内存缓冲区（最多保留 20 条）
_INDEX_LOG_BUFFER = []
_INDEX_LOG_MAX = 20


def _log_buffer_write(msg):
    """写入索引日志缓冲区，线程安全（单线程 indexer）"""
    from datetime import datetime as _dt
    ts = _dt.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    _INDEX_LOG_BUFFER.append(line)
    if len(_INDEX_LOG_BUFFER) > _INDEX_LOG_MAX:
        del _INDEX_LOG_BUFFER[:len(_INDEX_LOG_BUFFER) - _INDEX_LOG_MAX]


def get_index_log(lines=50):
    """获取最近的索引日志行"""
    tail = _INDEX_LOG_BUFFER[-lines:] if len(_INDEX_LOG_BUFFER) > lines else list(_INDEX_LOG_BUFFER)
    return {"lines": tail, "total": len(_INDEX_LOG_BUFFER)}


def clear_index_log():
    """清空日志缓冲区"""
    global _INDEX_LOG_BUFFER
    _INDEX_LOG_BUFFER = []


def _set_progress(done, total, current_file, status="running"):
    # done 是已完成的文件数，显示时用 done+1 表示当前正在处理第几个
    _index_progress["running"] = (status == "running")
    _index_progress["done"] = done
    _index_progress["total"] = total
    _index_progress["current_file"] = current_file
    _index_progress["status"] = status
    logger.info(f"[indexer→progress] done={done} total={total} current={current_file} status={status}")


def get_index_progress():
    return _index_progress


def _compute_file_md5(file_path: str) -> str:
    """计算文件的 MD5 哈希值"""
    h = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_index_meta(meta_path: str) -> dict:
    """加载索引元数据"""
    if os.path.exists(meta_path):
        with open(meta_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"files": {}}


def _save_index_meta(meta_path: str, meta: dict):
    """保存索引元数据"""
    os.makedirs(os.path.dirname(meta_path), exist_ok=True)
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)


def scan_wiki_files(wiki_dir: str) -> list[str]:
    """扫描 wiki 目录下所有 .md 文件

    Args:
        wiki_dir: wiki 目录的绝对路径

    Returns:
        .md 文件的绝对路径列表
    """
    if not os.path.isdir(wiki_dir):
        logger.warning(f"Wiki 目录不存在: {wiki_dir}")
        return []

    md_files = []
    for root, _dirs, files in os.walk(wiki_dir):
        for f in sorted(files):
            if f.lower().endswith(".md"):
                md_files.append(os.path.join(root, f))
    return md_files


def sync_index() -> dict:
    """增量同步索引：检测 wiki 目录变化并更新 LightRAG 索引

    Returns:
        {added: [...], updated: [...], deleted: [...], unchanged: int, errors: [...]}
    """
    from .config import get_wiki_dir, get_index_meta_path
    from .rag_engine import insert_document

    logger.info("[indexer] sync_index() 开始")
    wiki_dir = get_wiki_dir()
    meta_path = get_index_meta_path()
    _set_progress(0, 1, "扫描目录...", "running")

    # 确保 wiki 目录存在
    os.makedirs(wiki_dir, exist_ok=True)

    meta = _load_index_meta(meta_path)
    current_files = scan_wiki_files(wiki_dir)

    # 用相对路径作为 key（相对于 wiki_dir）
    current_map = {}
    for abs_path in current_files:
        rel = os.path.relpath(abs_path, wiki_dir)
        current_map[rel] = abs_path

    indexed_files = meta.get("files", {})
    result = {"added": [], "updated": [], "deleted": [], "unchanged": 0, "errors": []}

    # 第一遍：扫描所有文件，计算MD5，分类哪些需要处理
    _set_progress(0, 1, "扫描文件...", "running")
    to_process = []
    items = list(current_map.items())
    for rel_path, abs_path in items:
        md5 = _compute_file_md5(abs_path)
        old_entry = indexed_files.get(rel_path)
        if old_entry is None:
            to_process.append((rel_path, abs_path, md5, "added"))
        elif old_entry.get("md5") != md5:
            to_process.append((rel_path, abs_path, md5, "updated"))
        else:
            result["unchanged"] += 1
            logger.info(f"[indexer→] 跳过（MD5未变）| rel_path={rel_path} md5={md5}")

    total = len(to_process)
    if total == 0:
        _set_progress(0, 0, "无需处理", "done")
        _index_progress["result"] = result
        logger.info("索引同步完成: 全部已是最新")
        return result

    done = 0
    # 第二遍：仅遍历需要处理的文件，实时更新进度
    for i, (rel_path, abs_path, md5, action) in enumerate(to_process):
        logger.info(f"[indexer→sync] 开始处理文件 {i+1}/{total}: {rel_path} (action={action})")
        _set_progress(done, total, rel_path)
        try:
            # 重定向 stdout 捕获 LightRAG 的 print 输出
            old_stdout = sys.stdout
            captured = io.StringIO()
            sys.stdout = captured
            try:
                verified = _index_file(abs_path, rel_path)
            finally:
                sys.stdout = old_stdout
                output = captured.getvalue().strip()
                if output:
                    for line in output.split('\n'):
                        line = line.strip()
                        if line:
                            _log_buffer_write(line)

            if verified:
                indexed_files[rel_path] = {
                    "md5": md5,
                    "indexed_at": datetime.now(timezone.utc).isoformat(),
                }
                logger.info(f"[indexer✓] meta 更新成功 | rel_path={rel_path} md5={md5}")
                result[action].append(rel_path)
                logger.info(f"{'索引新文件' if action == 'added' else '重新索引'}: {rel_path}")
                meta["files"] = indexed_files
                _save_index_meta(meta_path, meta)
            else:
                result["errors"].append(f"{rel_path}: 向量验证失败")
                logger.warning(f"[indexer✗] 向量验证未通过，跳过 meta 更新 | rel_path={rel_path}")
        except Exception as e:
            result["errors"].append(f"{rel_path}: {e}")
            logger.error(f"索引失败 {rel_path}: {e}")

        # 无论成功或失败，都推进进度
        done += 1
        _set_progress(done, total, rel_path)
        logger.info(f"[indexer→sync] 文件 {i+1}/{total} 处理完毕: {rel_path}")

    # 检测已删除的文件
    for rel_path in list(indexed_files.keys()):
        if rel_path not in current_map:
            del indexed_files[rel_path]
            result["deleted"].append(rel_path)
            logger.info(f"文件已删除，移除索引: {rel_path}")

    # 完成后写盘（保存删除操作）
    meta["files"] = indexed_files
    _save_index_meta(meta_path, meta)
    logger.info(f"[indexer✓] meta 已保存 | path={meta_path} files_count={len(indexed_files)}")

    _set_progress(total, total, "", "done")
    _index_progress["result"] = result
    logger.info(
        f"索引同步完成: 新增 {len(result['added'])}, "
        f"更新 {len(result['updated'])}, 删除 {len(result['deleted'])}, "
        f"未变 {result['unchanged']}"
    )
    return result


def index_single_file(filename: str) -> str:
    """索引单个文件（写入后自动调用）

    Args:
        filename: 相对于 wiki_dir 的文件名

    Returns:
        索引结果描述
    """
    from .config import get_wiki_dir, get_index_meta_path

    wiki_dir = get_wiki_dir()
    abs_path = os.path.join(wiki_dir, filename)

    if not os.path.exists(abs_path):
        return f"文件不存在: {filename}"

    meta_path = get_index_meta_path()
    meta = _load_index_meta(meta_path)

    try:
        verified = _index_file(abs_path, filename)
        if not verified:
            return f"向量验证失败: {filename}"
        md5 = _compute_file_md5(abs_path)
        meta.setdefault("files", {})[filename] = {
            "md5": md5,
            "indexed_at": datetime.now(timezone.utc).isoformat(),
        }
        _save_index_meta(meta_path, meta)
        return f"已索引: {filename}"
    except Exception as e:
        return f"索引失败 {filename}: {e}"


def _index_file(abs_path: str, rel_path: str) -> bool:
    """将单个 MD 文件内容插入 LightRAG，并通过 aget_docs_by_track_id 验证处理完成

    insert_document() 为异步接口，将任务入队后立即返回。
    本函数轮询 doc_status 直到 status=processed 或超时。

    Returns:
        True: 插入并验证成功
        False: 插入失败或验证超时
    """
    from .rag_engine import insert_document, _verify_vector_inserted

    logger.info(f"[indexer→] _index_file 开始 | rel_path={rel_path}")
    with open(abs_path, "r", encoding="utf-8") as f:
        content = f.read()

    if not content.strip():
        logger.warning(f"[indexer] 跳过空文件: {rel_path}")
        return True

    track_id = insert_document(content, file_path=rel_path)
    logger.info(f"[indexer] insert 入队 | rel_path={rel_path} track_id={track_id}")

    # 验证文档处理完成（轮询 aget_docs_by_track_id 直到 status=processed）
    if not _verify_vector_inserted(rel_path, track_id, timeout=30):
        logger.error(f"[indexer✗] 向量验证失败 | rel_path={rel_path}")
        return False

    logger.info(f"[indexer←] _index_file 完成 | rel_path={rel_path}")
    return True


# ── 文件变化自动监听（单例）───────────────────────────────────────────────
_wiki_watcher = None


def _start_wiki_watcher():
    """启动 wiki 目录监听，文件变化时自动增量索引"""
    global _wiki_watcher
    if _wiki_watcher is not None:
        return  # 避免重复启动

    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler, FileModifiedEvent
    except ImportError:
        logger.warning("[wiki-watcher] watchdog 未安装，无法自动监听文件变化")
        return

    from .config import get_wiki_dir
    wiki_dir = get_wiki_dir()
    if not os.path.isdir(wiki_dir):
        logger.warning(f"[wiki-watcher] wiki_dir 不存在，跳过监听: {wiki_dir}")
        return

    class _WikiChangeHandler(FileSystemEventHandler):
        def on_modified(self, event):
            if isinstance(event, FileModifiedEvent) and event.src_path.lower().endswith('.md'):
                rel = os.path.relpath(event.src_path, wiki_dir)
                logger.info(f"[wiki-watcher] 检测到文件变化: {rel}")
                index_single_file(rel)

        def on_created(self, event):
            if not event.is_directory and event.src_path.lower().endswith('.md'):
                rel = os.path.relpath(event.src_path, wiki_dir)
                logger.info(f"[wiki-watcher] 检测到新文件: {rel}")
                index_single_file(rel)

        def on_deleted(self, event):
            if not event.is_directory and event.src_path.lower().endswith('.md'):
                rel = os.path.relpath(event.src_path, wiki_dir)
                logger.info(f"[wiki-watcher] 检测到文件删除: {rel}（请手动重建索引清理残留向量）")

    observer = Observer()
    observer.schedule(_WikiChangeHandler(), wiki_dir, recursive=True)
    observer.daemon = True
    observer.start()
    _wiki_watcher = observer
    logger.info(f"[wiki-watcher] 已启动，监听目录: {wiki_dir}")
