"""
自我叙事 API 路由 — 提供叙事状态查看和管理接口
"""
import json
import logging

logger = logging.getLogger('narrative')


def register(app, ready_state, _logger, stats_db):
    """注册自我叙事 API 路由"""

    @app.route('/narrative/autobiography', methods=['GET'])
    def narrative_autobiography():
        """获取完整自传 JSON"""
        if not ready_state.is_set():
            return json.dumps({"error": "系统尚未就绪"}), 503, {'Content-Type': 'application/json'}

        try:
            from modules.brain.memory.self_narrative import get_self_narrative
            sn = get_self_narrative()
            if not sn:
                return json.dumps({"error": "叙事模块未初始化"}), 503, {'Content-Type': 'application/json'}
            bio = sn.get_autobiography()
            return json.dumps({"data": bio}, ensure_ascii=False), 200, {'Content-Type': 'application/json'}
        except Exception as e:
            logger.warning(f"[route] autobiography failed: {e}")
            return json.dumps({"error": str(e)}), 500, {'Content-Type': 'application/json'}

    @app.route('/narrative/state', methods=['GET'])
    def narrative_state():
        """获取当前状态 (mood, thinking 等)"""
        if not ready_state.is_set():
            return json.dumps({"error": "系统尚未就绪"}), 503, {'Content-Type': 'application/json'}

        try:
            from modules.brain.memory.self_narrative import get_self_narrative
            sn = get_self_narrative()
            if not sn:
                return json.dumps({"error": "叙事模块未初始化"}), 503, {'Content-Type': 'application/json'}
            bio = sn.get_autobiography()
            return json.dumps({"data": bio.get("current_state", {})}, ensure_ascii=False), 200, {'Content-Type': 'application/json'}
        except Exception as e:
            logger.warning(f"[route] state failed: {e}")
            return json.dumps({"error": str(e)}), 500, {'Content-Type': 'application/json'}

    @app.route('/narrative/chapters', methods=['GET'])
    def narrative_chapters():
        """获取所有人生章节"""
        if not ready_state.is_set():
            return json.dumps({"error": "系统尚未就绪"}), 503, {'Content-Type': 'application/json'}

        try:
            from modules.brain.memory.self_narrative import get_self_narrative
            sn = get_self_narrative()
            if not sn:
                return json.dumps({"error": "叙事模块未初始化"}), 503, {'Content-Type': 'application/json'}
            bio = sn.get_autobiography()
            story = bio.get("life_story", {})
            return json.dumps({
                "data": story.get("chapters", []),
                "current_index": story.get("current_chapter_index", 0),
            }, ensure_ascii=False), 200, {'Content-Type': 'application/json'}
        except Exception as e:
            logger.warning(f"[route] chapters failed: {e}")
            return json.dumps({"error": str(e)}), 500, {'Content-Type': 'application/json'}

    @app.route('/narrative/milestones', methods=['GET'])
    def narrative_milestones():
        """获取里程碑列表"""
        if not ready_state.is_set():
            return json.dumps({"error": "系统尚未就绪"}), 503, {'Content-Type': 'application/json'}

        try:
            from modules.brain.memory.self_narrative import get_self_narrative
            sn = get_self_narrative()
            if not sn:
                return json.dumps({"error": "叙事模块未初始化"}), 503, {'Content-Type': 'application/json'}
            bio = sn.get_autobiography()
            return json.dumps({"data": bio.get("milestones", [])}, ensure_ascii=False), 200, {'Content-Type': 'application/json'}
        except Exception as e:
            logger.warning(f"[route] milestones failed: {e}")
            return json.dumps({"error": str(e)}), 500, {'Content-Type': 'application/json'}

    @app.route('/narrative/core-memories', methods=['GET'])
    def narrative_core_memories():
        """获取核心记忆列表"""
        if not ready_state.is_set():
            return json.dumps({"error": "系统尚未就绪"}), 503, {'Content-Type': 'application/json'}

        try:
            from modules.brain.memory.self_narrative import get_self_narrative
            sn = get_self_narrative()
            if not sn:
                return json.dumps({"error": "叙事模块未初始化"}), 503, {'Content-Type': 'application/json'}
            cores = sn.get_core_memories()
            return json.dumps({"data": cores, "count": len(cores)}, ensure_ascii=False), 200, {'Content-Type': 'application/json'}
        except Exception as e:
            logger.warning(f"[route] core-memories failed: {e}")
            return json.dumps({"error": str(e)}), 500, {'Content-Type': 'application/json'}

    @app.route('/narrative/anchors', methods=['GET'])
    def narrative_anchors():
        """获取所有叙事锚点（分页）"""
        if not ready_state.is_set():
            return json.dumps({"error": "系统尚未就绪"}), 503, {'Content-Type': 'application/json'}

        try:
            from flask import request
            limit = int(request.args.get('limit', 200))
            offset = int(request.args.get('offset', 0))

            from modules.brain.memory.self_narrative import get_self_narrative
            sn = get_self_narrative()
            if not sn:
                return json.dumps({"error": "叙事模块未初始化"}), 503, {'Content-Type': 'application/json'}
            anchors = sn.get_all_anchors(limit=limit, offset=offset)
            return json.dumps({"data": anchors, "count": len(anchors)}, ensure_ascii=False), 200, {'Content-Type': 'application/json'}
        except Exception as e:
            logger.warning(f"[route] anchors failed: {e}")
            return json.dumps({"error": str(e)}), 500, {'Content-Type': 'application/json'}

    @app.route('/narrative/stats', methods=['GET'])
    def narrative_stats():
        """获取叙事模块统计信息"""
        if not ready_state.is_set():
            return json.dumps({"error": "系统尚未就绪"}), 503, {'Content-Type': 'application/json'}

        try:
            from modules.brain.memory.self_narrative import get_self_narrative
            sn = get_self_narrative()
            if not sn:
                return json.dumps({"error": "叙事模块未初始化"}), 503, {'Content-Type': 'application/json'}
            return json.dumps({"data": sn.get_stats()}, ensure_ascii=False), 200, {'Content-Type': 'application/json'}
        except Exception as e:
            logger.warning(f"[route] stats failed: {e}")
            return json.dumps({"error": str(e)}), 500, {'Content-Type': 'application/json'}

    @app.route('/narrative/reflect', methods=['POST'])
    def narrative_reflect():
        """手动触发反思"""
        if not ready_state.is_set():
            return json.dumps({"error": "系统尚未就绪"}), 503, {'Content-Type': 'application/json'}

        try:
            from flask import request
            body = request.get_json(silent=True) or {}
            user_msg = body.get("user_message", "")
            assistant_msg = body.get("assistant_message", "")

            if not user_msg or not assistant_msg:
                return json.dumps({"error": "需要 user_message 和 assistant_message"}), 400, {'Content-Type': 'application/json'}

            from modules.brain.memory.self_narrative import get_self_narrative
            sn = get_self_narrative()
            if not sn:
                return json.dumps({"error": "叙事模块未初始化"}), 503, {'Content-Type': 'application/json'}

            # 同步执行反思（手动触发时不用后台线程）
            sn.reflect_on_conversation(user_msg, assistant_msg)

            return json.dumps({"result": "反思完成"}, ensure_ascii=False), 200, {'Content-Type': 'application/json'}
        except Exception as e:
            logger.warning(f"[route] reflect failed: {e}")
            return json.dumps({"error": str(e)}), 500, {'Content-Type': 'application/json'}
