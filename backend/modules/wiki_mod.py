"""Wiki 路由模块：/wiki/search, /wiki/list, /wiki/index, /wiki/log

日志标记规范：
  [API→]  收到请求
  [API←]  返回响应
  [API⚠]  降级/警告
  [API✗]  错误
  [RAG→]  调用 RAG 引擎
  [RAG←]  RAG 引擎返回
"""
from flask import request, jsonify
import json
import logging
import time as _time
import os
import glob

logger = logging.getLogger(__name__)


def register(app, stats_db=None):
    """注册 wiki 相关路由到 Flask app"""

    # 延迟导入，避免启动时加载 RAG（按需初始化）
    def _get_rag_engine():
        from rag.lightrag_wiki.rag_engine import query_wiki_context
        from rag.lightrag_wiki.config import load_wiki_config
        from rag.lightrag_wiki.indexer import (
            index_single_file, sync_index, scan_wiki_files
        )
        return query_wiki_context, load_wiki_config, index_single_file, sync_index, scan_wiki_files

    @app.route('/wiki/search', methods=['POST'])
    def wiki_search():
        t0 = _time.time()
        data = request.get_json() or {}
        query = data.get('query', '').strip()
        mode = data.get('mode', 'naive')
        logger.info(f"[API→] /wiki/search | query={query[:50]} mode={mode}")
        if not query:
            logger.warning("[API⚠] /wiki/search query 为空")
            return jsonify({"error": "query 不能为空"})
        try:
            query_wiki_context, load_wiki_config, *_ = _get_rag_engine()
            cfg = load_wiki_config()
            timeout = cfg.get("search_timeout", 60)
            logger.info(f"[API ] /wiki/search | search_timeout={timeout}s")

            if mode == "naive":
                logger.info("[RAG→] /wiki/search 调用 naive 模式")
                t_rag0 = _time.time()
                # === 跟踪: RAG 引擎是否已初始化 ===
                from rag.lightrag_wiki.rag_engine import _rag_instance
                logger.info(f"[TRACE] RAG单例状态: _rag_instance={'已创建' if _rag_instance else 'None'}")
                result = query_wiki_context(query, mode="naive")
                rag_elapsed = _time.time() - t_rag0
                total = _time.time() - t0
                logger.info(
                    f"[RAG←] /wiki/search naive 完成 | "
                    f"rag_elapsed={rag_elapsed:.1f}s total={total:.1f}s result_len={len(result) if result else 0}"
                )
                return jsonify({"result": result, "mode": "naive", "elapsed": round(total, 1)})

            # hybrid 带超时降级
            logger.info(f"[RAG→] /wiki/search 调用 {mode} 模式 (timeout={timeout}s)")
            t_rag0 = _time.time()
            try:
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(query_wiki_context, query, mode)
                    result = future.result(timeout=timeout)
                    rag_elapsed = _time.time() - t_rag0
                    total = _time.time() - t0
                    if result and result.strip():
                        logger.info(
                            f"[RAG←] /wiki/search {mode} 成功 | "
                            f"rag_elapsed={rag_elapsed:.1f}s total={total:.1f}s result_len={len(result) if result else 0}"
                        )
                        return jsonify({
                            "result": result,
                            "mode": mode,
                            "elapsed": round(total, 1)
                        })
                    logger.warning(f"[API⚠] /wiki/search {mode} 返回空结果，降级 naive")
            except concurrent.futures.TimeoutError:
                elapsed = _time.time() - t_rag0
                logger.warning(f"[API⚠] /wiki/search {mode} 超时 ({timeout}s)，已耗时 {elapsed:.1f}s，取消任务并降级 naive")
                # 关键：超时后立即取消 Future 防止泄漏线程阻塞后续请求
                future.cancel()
            except Exception as e:
                elapsed = _time.time() - t_rag0
                logger.warning(f"[API⚠] /wiki/search {mode} 失败: {e}，已耗时 {elapsed:.1f}s，降级 naive")

            # 降级到 naive
            logger.info("[RAG→] /wiki/search 降级调用 naive 模式")
            t_naive0 = _time.time()
            result = query_wiki_context(query, mode="naive")
            naive_elapsed = _time.time() - t_naive0
            total = _time.time() - t0
            logger.info(
                f"[RAG←] /wiki/search naive(fallback) 完成 | "
                f"naive_elapsed={naive_elapsed:.1f}s total={total:.1f}s result_len={len(result) if result else 0}"
            )
            return jsonify({
                "result": result,
                "mode": "naive(fallback)",
                "elapsed": round(total, 1)
            })
        except Exception as e:
            logger.error(f"[API✗] /wiki/search 失败: {e}")
            return jsonify({"error": str(e)})

    @app.route('/wiki/list', methods=['GET'])
    def wiki_list():
        t0 = _time.time()
        logger.info("[API→] /wiki/list")
        try:
            _, _, _, _, scan_wiki_files = _get_rag_engine()
            from rag.lightrag_wiki.config import get_wiki_dir
            import os
            wiki_dir = get_wiki_dir()
            if not os.path.isdir(wiki_dir):
                logger.info("[API←] /wiki/list wiki_dir 不存在，返回空列表")
                return jsonify({"files": []})
            files = scan_wiki_files(wiki_dir)
            result = []
            for abs_path in files:
                rel_path = os.path.relpath(abs_path, wiki_dir)
                stat = os.stat(abs_path)
                with open(abs_path, "r", encoding="utf-8") as f:
                    preview = f.read(200).strip()
                result.append({
                    "filename": rel_path,
                    "abs_path": abs_path,
                    "size_bytes": stat.st_size,
                    "modified": os.path.getmtime(abs_path),
                    "preview": preview,
                })
            total = _time.time() - t0
            logger.info(f"[API←] /wiki/list 完成 | total={total:.1f}s files_count={len(result)}")
            return jsonify({"files": result})
        except Exception as e:
            logger.error(f"[API✗] /wiki/list 失败: {e}")
            return jsonify({"error": str(e)})

    @app.route('/wiki/index', methods=['POST'])
    def wiki_index():
        t0 = _time.time()
        logger.info("[API→] /wiki/index")
        try:
            _, _, _, sync_index, _ = _get_rag_engine()
            result = sync_index()
            total = _time.time() - t0
            logger.info(
                f"[API←] /wiki/index 完成 | total={total:.1f}s "
                f"added={len(result.get('added',[]))} "
                f"updated={len(result.get('updated',[]))} "
                f"deleted={len(result.get('deleted',[]))} "
                f"unchanged={result.get('unchanged',0)}"
            )
            return jsonify(result)
        except Exception as e:
            logger.error(f"[API✗] /wiki/index 失败: {e}")
            return jsonify({"error": str(e)})

    @app.route('/wiki/log', methods=['GET'])
    def wiki_log():
        """读取后端日志文件，返回最近的 wiki 相关日志行"""
        try:
            # 找到最新的日志文件
            project_root = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
            log_dir = os.path.join(project_root, 'logs')
            files = []
            for pat in ('app_*.log', 'flask_*.log', 'ui_*.log'):
                files.extend(glob.glob(os.path.join(log_dir, pat)))
            if not files:
                return jsonify({"lines": [], "file": None})

            # 取最新的日志文件
            log_file = max(files, key=os.path.getmtime)

            # 读取最后 N 行（默认 200）
            lines_param = request.args.get('lines', '200', type=int)
            lines_param = min(max(lines_param, 10), 500)

            with open(log_file, 'r', encoding='utf-8', errors='replace') as f:
                all_lines = f.readlines()

            # 只返回包含 wiki/RAG/搜索相关关键词的行
            keywords = ['wiki', 'RAG', 'lightrag', 'index', 'search', 'embed']
            relevant = []
            for line in all_lines:
                stripped = line.strip()
                if any(kw.lower() in stripped.lower() for kw in keywords):
                    relevant.append(stripped)

            tail = relevant[-lines_param:] if len(relevant) > lines_param else relevant
            return jsonify({
                "lines": tail,
                "file": os.path.basename(log_file),
                "total_relevant": len(relevant),
                "returned": len(tail),
            })
        except Exception as e:
            logger.error(f"[API✗] /wiki/log 失败: {e}")
            return jsonify({"error": str(e), "lines": []})

    # 扁平 <-> 嵌套 LLM 字段映射
    _LLM_FLAT_MAP = {
        "provider": "llm_provider",
        "model": "llm_model",
        "api_key": "llm_api_key",
        "base_url": "llm_base_url",
    }

    @app.route('/wiki/settings', methods=['GET', 'POST'])
    def wiki_settings():
        """读取/保存 Wiki 配置。存储使用扁平格式，API 使用嵌套格式兼容前端"""
        try:
            from rag.lightrag_wiki.config import load_wiki_config, _get_config_path

            if request.method == 'GET':
                cfg = load_wiki_config()
                # 扁平存储 → 嵌套返回给前端
                llm_nested = {}
                for nested_key, flat_key in _LLM_FLAT_MAP.items():
                    val = cfg.get(flat_key, "")
                    if val:
                        llm_nested[nested_key] = val
                result = {k: v for k, v in cfg.items() if not k.startswith("llm_")}
                if llm_nested:
                    result["llm"] = llm_nested
                    if llm_nested.get("api_key"):
                        result["llm"]["api_key"] = "****"
                return jsonify(result)

            if request.method == 'POST':
                data = request.get_json() or {}
                config_path = _get_config_path()
                current = load_wiki_config()

                # 只允许更新特定字段
                allowed = {'wiki_dir', 'lightrag_dir', 'language',
                           'chunk_token_size', 'search_timeout'}
                for key in allowed:
                    if key in data:
                        current[key] = data[key]

                # LLM 配置：接收嵌套格式 → 转扁平存储
                if 'llm' in data:
                    new_llm = data['llm']
                    for nested_key, flat_key in _LLM_FLAT_MAP.items():
                        new_val = new_llm.get(nested_key)
                        if nested_key == 'api_key':
                            # api_key 为空时保留原值
                            current[flat_key] = new_val or current.get(flat_key, "")
                        elif new_val:
                            current[flat_key] = new_val

                import tempfile
                fd, tmp_path = tempfile.mkstemp(
                    dir=os.path.dirname(config_path),
                    suffix='.wiki_tmp.json',
                )
                try:
                    with os.fdopen(fd, 'w', encoding='utf-8') as f:
                        json.dump(current, f, indent=2, ensure_ascii=False)
                    os.replace(tmp_path, config_path)
                except Exception:
                    os.unlink(tmp_path)
                    raise

                logger.info("[API←] /wiki/settings 已保存")
                return jsonify({"ok": True})

        except Exception as e:
            logger.error(f"[API✗] /wiki/settings 失败: {e}")
            return jsonify({"error": str(e)}), 500
