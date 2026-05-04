"""Wiki 路由 - /wiki/*（纯转发）
Wiki 搜索、文件列表、索引管理、设置读写"""
from flask import request, jsonify
from modules.Wiki.wiki_mod import WikiManager

_wiki_mgr = WikiManager.get_instance()


def register(app, ready_state, logger, stats_db):
    project_root = app.config.get('_PROJECT_ROOT', '')

    @app.route('/wiki/search', methods=['POST'])
    def wiki_search():
        """Wiki 全文搜索（支持 naive/hybrid 等模式）"""
        data = request.get_json() or {}
        query = data.get('query', '').strip()
        mode = data.get('mode', 'naive')
        logger.info(f"[API→] /wiki/search | query={query[:50]} mode={mode}")
        if not query:
            logger.warning("[API⚠] /wiki/search query 为空")
            return jsonify({"error": "query 不能为空"})
        try:
            result, mode_used, elapsed = _wiki_mgr.do_wiki_search(query, mode, logger)
            return jsonify({"result": result, "mode": mode_used, "elapsed": elapsed})
        except Exception as e:
            logger.error(f"[API✗] /wiki/search 失败: {e}")
            return jsonify({"error": str(e)})

    @app.route('/wiki/list', methods=['GET'])
    def wiki_list():
        """获取 Wiki 文件列表和索引状态"""
        t0 = __import__('time').time()
        try:
            files, indexed = _wiki_mgr.get_wiki_file_list(project_root, logger)
            elapsed = __import__('time').time() - t0
            logger.info(f"[API←] /wiki/list | {len(files)} files, indexed={indexed}, elapsed={elapsed:.1f}s")
            return jsonify({"files": files, "indexed": indexed})
        except Exception as e:
            logger.error(f"[API✗] /wiki/list 失败: {e}")
            return jsonify({"error": str(e)})

    @app.route('/wiki/index', methods=['POST'])
    def wiki_index():
        """后台启动 Wiki 索引重建"""
        ok, msg = _wiki_mgr.start_wiki_index_background(logger)
        if not ok:
            return jsonify({"error": msg}), 409
        return jsonify({"status": "started", "started_at": 0})

    @app.route('/wiki/index-progress', methods=['GET'])
    def wiki_index_progress():
        """获取 Wiki 索引进度"""
        return jsonify(_wiki_mgr.get_wiki_index_progress())

    @app.route('/wiki/index-log', methods=['GET'])
    def wiki_index_log():
        """获取 Wiki 索引日志"""
        lines = request.args.get('lines', 20, type=int)
        return jsonify(_wiki_mgr.get_wiki_index_log(lines=lines))

    @app.route('/wiki/log', methods=['GET'])
    def wiki_log():
        """获取 Wiki 相关日志（过滤关键字）"""
        lines = request.args.get('lines', 200, type=int)
        lines = min(max(int(lines), 10), 500)
        keywords = ['wiki', 'RAG', 'lightrag', 'index', 'search', 'embed', 'ERROR', 'WARNING', 'WARN', 'error', 'warning', 'warn', 'fail', 'failed', 'exception']
        result = _wiki_mgr.get_wiki_filtered_log(project_root, keywords, lines)
        return jsonify(result)

    @app.route('/wiki/settings', methods=['GET', 'POST'])
    def wiki_settings():
        """读写 Wiki 配置（Llm 模型、API 配置等）"""
        if request.method == 'GET':
            return jsonify(_wiki_mgr.get_wiki_settings())
        try:
            data = request.get_json() or {}
            _wiki_mgr.save_wiki_settings(data)
            logger.info("[API←] /wiki/settings 已保存")
            return jsonify({"ok": True})
        except Exception as e:
            logger.error(f"[API✗] /wiki/settings 失败: {e}")
            return jsonify({"error": str(e)}), 500