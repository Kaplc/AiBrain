"""Wiki 工具（单例） - 供 routes/wiki_routes.py 调用"""
import json
import os
import threading
import time as _time


class WikiManager:
    _instance = None

    def __init__(self):
        pass

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def get_rag_components(self):
        from rag.lightrag_wiki.rag_engine import query_wiki_context
        from rag.lightrag_wiki.config import load_wiki_config
        from rag.lightrag_wiki.indexer import index_single_file, sync_index, scan_wiki_files
        return query_wiki_context, load_wiki_config, index_single_file, sync_index, scan_wiki_files

    def do_wiki_search(self, query: str, mode: str, logger=None):
        """执行 wiki 搜索（支持 naive/hybrid 模式，超时降级）"""
        query_wiki_context, load_wiki_config, *_ = self.get_rag_components()
        cfg = load_wiki_config()
        timeout = cfg.get("search_timeout", 60)
        t0 = _time.time()

        if mode == "naive":
            if logger:
                logger.info("[RAG→] wiki search naive 模式")
            from rag.lightrag_wiki.rag_engine import _rag_instance
            if logger:
                logger.info(f"[TRACE] RAG单例: {'已创建' if _rag_instance else 'None'}")
            result = query_wiki_context(query, mode="naive")
            total = _time.time() - t0
            return result, "naive", round(total, 1)

        # hybrid 带超时降级
        try:
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(query_wiki_context, query, mode)
                result = future.result(timeout=timeout)
                total = _time.time() - t0
                if result and result.strip():
                    return result, mode, round(total, 1)
                if logger:
                    logger.warning(f"[API⚠] wiki {mode} 返回空，降级 naive")
        except concurrent.futures.TimeoutError:
            if logger:
                logger.warning(f"[API⚠] wiki {mode} 超时 ({timeout}s)，降级 naive")
        except Exception as e:
            if logger:
                logger.warning(f"[API⚠] wiki {mode} 失败: {e}，降级 naive")

        result = query_wiki_context(query, mode="naive")
        total = _time.time() - t0
        return result, "naive(fallback)", round(total, 1)

    def get_wiki_file_list(self, project_root: str, logger=None):
        """扫描 wiki 目录，返回文件列表（含 index 状态）"""
        from rag.lightrag_wiki.indexer import _start_wiki_watcher
        _start_wiki_watcher()

        _, _, _, _, scan_wiki_files = self.get_rag_components()
        from rag.lightrag_wiki.config import get_wiki_dir, get_index_meta_path
        from rag.lightrag_wiki.indexer import _load_index_meta, _compute_file_md5

        wiki_dir = get_wiki_dir()
        if not os.path.isdir(wiki_dir):
            return [], False

        files = scan_wiki_files(wiki_dir)
        meta_path = get_index_meta_path()
        indexed = os.path.exists(meta_path)
        index_meta = _load_index_meta(meta_path) if indexed else {"files": {}}

        result = []
        for abs_path in files:
            rel_path = os.path.relpath(abs_path, wiki_dir)
            stat = os.stat(abs_path)
            try:
                with open(abs_path, "r", encoding="utf-8") as f:
                    preview = f.read(200).strip()
            except Exception:
                preview = ""
            entry = index_meta["files"].get(rel_path)
            if entry is None:
                index_status = "not_indexed"
            elif entry.get("md5") != _compute_file_md5(abs_path):
                index_status = "out_of_sync"
            else:
                index_status = "synced"
            result.append({
                "filename": rel_path,
                "abs_path": abs_path,
                "size_bytes": stat.st_size,
                "modified": os.path.getmtime(abs_path),
                "preview": preview,
                "index_status": index_status,
            })
        return result, indexed

    def start_wiki_index_background(self, logger=None):
        """在后台线程启动 wiki 索引"""
        def _run():
            try:
                _, _, _, sync_index, _ = self.get_rag_components()
                sync_index()
            except Exception as e:
                if logger:
                    logger.error(f"[wiki-index] 后台索引失败: {e}")
            finally:
                from rag.lightrag_wiki.indexer import _index_progress, _set_progress as _sp
                if _index_progress["status"] == "running":
                    _sp(_index_progress["done"], _index_progress["total"], "", "done")

        _, _, _, sync_index, _ = self.get_rag_components()
        from rag.lightrag_wiki.indexer import get_index_progress, _set_progress, _index_progress
        if _index_progress["running"]:
            return False, "索引任务正在进行中"

        _set_progress(0, 0, "", "running")
        threading.Thread(target=_run, daemon=True).start()
        return True, "已启动"

    def get_wiki_index_progress(self):
        from rag.lightrag_wiki.indexer import get_index_progress
        return get_index_progress()

    def get_wiki_index_log(self, lines: int = 20):
        from rag.lightrag_wiki.indexer import get_index_log
        return get_index_log(lines=lines)

    def get_wiki_filtered_log(self, project_root: str, keywords: list[str], lines: int = 200):
        from modules.Log.log_mod import LogManager
        _log_mgr = LogManager.get_instance()
        _, fname = _log_mgr.get_latest_log_file(project_root)
        if not fname:
            return {"lines": [], "file": None}
        result = _log_mgr.read_log_tail_filtered(os.path.join(project_root, 'logs', fname), keywords, lines)
        result["file"] = fname
        return result

    _LLM_FLAT_MAP = {
        "provider": "llm_provider",
        "model": "llm_model",
        "api_key": "llm_api_key",
        "base_url": "llm_base_url",
    }

    def get_wiki_settings(self) -> dict:
        from rag.lightrag_wiki.config import load_wiki_config
        cfg = load_wiki_config()
        llm_nested = {}
        for nested_key, flat_key in self._LLM_FLAT_MAP.items():
            val = cfg.get(flat_key, "")
            if val:
                llm_nested[nested_key] = val
        result = {k: v for k, v in cfg.items() if not k.startswith("llm_")}
        if llm_nested:
            result["llm"] = llm_nested
            if llm_nested.get("api_key"):
                result["llm"]["api_key"] = "****"
        return result

    def save_wiki_settings(self, data: dict) -> bool:
        from rag.lightrag_wiki.config import load_wiki_config, _get_config_path
        config_path = _get_config_path()
        current = load_wiki_config()
        allowed = {'wiki_dir', 'lightrag_dir', 'language', 'chunk_token_size', 'search_timeout'}
        for key in allowed:
            if key in data:
                current[key] = data[key]
        if 'llm' in data:
            new_llm = data['llm']
            for nested_key, flat_key in self._LLM_FLAT_MAP.items():
                new_val = new_llm.get(nested_key)
                if nested_key == 'api_key':
                    current[flat_key] = new_val or current.get(flat_key, "")
                elif new_val:
                    current[flat_key] = new_val
        try:
            fd, tmp_path = os.mkstemp(dir=os.path.dirname(config_path), suffix='.wiki_tmp.json')
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(current, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, config_path)
            return True
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise