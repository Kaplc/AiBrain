"""Gate 路由 - /gate/* 企业微信机器人配置接口

独立于 main_brain，配置和凭证直接由前端控制。
"""
from __future__ import annotations

import json
import os
import logging

from flask import request, jsonify
from modules.WeWork.bot_adapter import WeWorkBot

logger = logging.getLogger("routes.gate")

# 配置文件路径（用户可以访问的目录）
_CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".aibrain", "gate")
_CONFIG_PATH = os.path.join(_CONFIG_DIR, "wework.json")


def _load_config() -> dict:
    """从磁盘读取配置。"""
    try:
        if os.path.exists(_CONFIG_PATH):
            with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logger.warning("[gate] 读取配置失败: %s", e)
    return {"bot_id": "", "secret": ""}


def _save_config(bot_id: str, secret: str) -> dict:
    """保存配置到磁盘。"""
    try:
        os.makedirs(_CONFIG_DIR, exist_ok=True)
        data = {"bot_id": bot_id.strip(), "secret": secret.strip()}
        with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info("[gate] 配置已保存 bot_id=%s", data["bot_id"])
        return {"ok": True}
    except Exception as e:
        logger.error("[gate] 保存配置失败: %s", e)
        return {"ok": False, "message": str(e)}


def register(app, ready_state, logger, stats_db):
    bot = WeWorkBot.get_instance()

    # 启动时尝试加载已有配置
    cfg = _load_config()
    if cfg.get("bot_id") and cfg.get("secret"):
        bot.configure(cfg["bot_id"], cfg["secret"])
        logger.info("[gate] 启动时加载了企业微信配置 bot_id=%s", cfg["bot_id"])

    @app.route("/gate/config", methods=["GET"])
    def gate_get_config():
        """获取当前机器人配置（不返回 secret 明文）。"""
        status = bot.get_status()
        cfg = _load_config()
        return jsonify({
            "ok": True,
            "bot_id": cfg.get("bot_id", ""),
            "has_secret": bool(cfg.get("secret", "")),
            "status": status["status"],
            "connected": status["connected"],
            "last_error": status["last_error"],
        })

    @app.route("/gate/config", methods=["POST"])
    def gate_save_config():
        """保存机器人配置并更新到适配器。"""
        data = request.get_json() or {}
        bot_id = data.get("bot_id", "").strip()
        secret = data.get("secret", "").strip()

        if not bot_id or not secret:
            return jsonify({"ok": False, "message": "BotID 和 Secret 不能为空"})

        result = _save_config(bot_id, secret)
        if result.get("ok"):
            bot.configure(bot_id, secret)
        return jsonify(result)

    @app.route("/gate/connect", methods=["POST"])
    def gate_connect():
        """启动 WebSocket 连接。"""
        # 如果配置还没加载到适配器，先加载
        cfg = _load_config()
        if cfg.get("bot_id") and cfg.get("secret"):
            bot.configure(cfg["bot_id"], cfg["secret"])

        result = bot.start()
        return jsonify(result)

    @app.route("/gate/disconnect", methods=["POST"])
    def gate_disconnect():
        """断开 WebSocket 连接。"""
        result = bot.stop()
        return jsonify(result)

    @app.route("/gate/status", methods=["GET"])
    def gate_status():
        """查询连接状态。"""
        return jsonify(bot.get_status())

    @app.route("/gate/test", methods=["POST"])
    def gate_test():
        """测试配置 - 尝试连接并检查状态。"""
        data = request.get_json() or {}
        test_bot_id = data.get("bot_id", "").strip()
        test_secret = data.get("secret", "").strip()

        if not test_bot_id or not test_secret:
            return jsonify({"ok": False, "message": "请提供 BotID 和 Secret"})

        # 暂存当前配置
        old_bot_id = bot.bot_id
        old_secret = bot.secret

        # 临时配置并尝试连接
        bot.configure(test_bot_id, test_secret)
        was_running = bot._status == "connected"
        if was_running:
            bot.stop()

        result = bot.start()
        # 启动后等一会儿看是否成功
        import threading
        import time

        def _check_and_restore():
            time.sleep(3)
            current = bot.get_status()
            if current["status"] == "connected":
                logger.info("[gate] 测试连接成功")
            else:
                logger.warning("[gate] 测试连接失败: %s", current.get("last_error", ""))
            # 测试完不自动回滚——如果用户点了"保存"就是有意覆盖

        threading.Thread(target=_check_and_restore, daemon=True).start()

        return jsonify({"ok": True, "message": "正在测试连接，请查看状态"})

    @app.route("/gate/welcome", methods=["POST"])
    def gate_set_welcome():
        """配置欢迎语。"""
        data = request.get_json() or {}
        welcome_text = data.get("welcome", "").strip()
        if not welcome_text:
            return jsonify({"ok": False, "message": "欢迎语不能为空"})

        # 保存欢迎语配置
        cfg = _load_config()
        cfg["welcome"] = welcome_text
        try:
            with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2, ensure_ascii=False)
        except Exception as e:
            return jsonify({"ok": False, "message": str(e)})

        return jsonify({"ok": True})

    @app.route("/gate/welcome", methods=["GET"])
    def gate_get_welcome():
        """获取欢迎语配置。"""
        cfg = _load_config()
        return jsonify({
            "ok": True,
            "welcome": cfg.get("welcome", "欢迎来到 AiBrain！您可以向我发送消息，我会尽力为您解答。"),
        })

    # ── 企微消息处理回调 ────────────────────────────────
    def _handle_wework_message(userid: str, content: str) -> str:
        """企微消息处理：走 chat 模块发送，回复由 bot 自动发回企微。"""
        if not content.strip():
            return ""
        from modules.WeWork.bot_adapter import _wework_log as _log
        _log(f"【chat处理】compid={userid} 消息=\"{content[:100]}\" 开始调用 ChatManager.send()")

        reply = ""
        # 把企微用户 ID 带入聊天内容，让 LLM 知道是谁在说话
        enriched = f"wework:{userid} {content}"
        try:
            # 走 chat 模块发送（跟本地聊天一样的路径）
            from modules.chat import ChatManager
            mgr = ChatManager.get_instance()
            for event in mgr.send(enriched):
                if event.get('type') == 'token':
                    reply += event.get('content', '')
                elif event.get('type') == 'done':
                    break

            _log(f"【chat完成】compid={userid} 回复长度={len(reply)} 前60字=\"{reply[:60]}\"")

        except Exception as e:
            _log(f"【chat错误】compid={userid} {e}")
            logger.error("[gate] 处理企微消息异常: %s", e)

        logger.info("[gate] 企微消息处理完成 compid=%s", userid)
        return reply

    @app.route("/gate/proactive", methods=["POST"])
    def gate_proactive():
        """主动推送消息到企微（测试用）。"""
        data = request.get_json() or {}
        userid = data.get("userid", "").strip()
        content = data.get("content", "").strip()
        if not userid or not content:
            return jsonify({"ok": False, "message": "userid 和 content 不能为空"})
        bot.send_proactive(userid=userid, content=content)
        return jsonify({"ok": True, "message": f"已向 {userid} 推送消息"})

    # 注册回调到 bot
    bot.on_message = _handle_wework_message
