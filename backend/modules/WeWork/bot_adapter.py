"""企业微信智能机器人 — WebSocket 长连接适配器（单例）

长连接模式无需公网 IP、无需 HTTPS 回调、无需消息加解密。
通过 wss://openws.work.weixin.qq.com 与企业微信服务器保持长连接。

使用流程：
  1. 在企业微信后台创建智能机器人，获取 BotID + Secret
  2. 调用 start() 建立连接
  3. 收到文本消息后自动回调 on_message_callback
  4. 调用 send_reply() / send_markdown() 回复消息

消息格式文档：
  https://developer.work.weixin.qq.com/document/path/101463
"""
from __future__ import annotations

import json
import logging
import threading
import time
from typing import Callable

logger = logging.getLogger("modules.WeWork.bot")


def _wework_log(msg: str) -> None:
    """写企微追踪日志（统一用 logger.info 带 wework 前缀）。"""
    logger.info("[wework] %s", msg)


# 企业微信 WebSocket 长连接地址
WS_URL = "wss://openws.work.weixin.qq.com"


class WeWorkBot:
    """企业微信智能机器人客户端（单例）。"""

    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        self.bot_id: str = ""
        self.secret: str = ""
        self._ws = None
        self._running = False
        self._thread: threading.Thread | None = None
        self._heartbeat_timer: threading.Timer | None = None
        self._status: str = "stopped"  # stopped / connecting / connected / error
        self._status_lock = threading.Lock()
        self._last_error: str = ""

        # 外部注册的消息回调：callback(userid, content) -> str
        self.on_message: Callable[[str, str], str] | None = None

    @classmethod
    def get_instance(cls) -> WeWorkBot:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    # ── 状态管理 ───────────────────────────────────────────────

    def _set_status(self, s: str, err: str = "") -> None:
        with self._status_lock:
            self._status = s
            self._last_error = err
        logger.info("[WeWork] status -> %s%s", s, f" ({err})" if err else "")

    def get_status(self) -> dict:
        with self._status_lock:
            return {
                "status": self._status,
                "last_error": self._last_error,
                "bot_id": self.bot_id,
                "connected": self._status == "connected",
            }

    # ── 公共控制 ───────────────────────────────────────────────

    def configure(self, bot_id: str, secret: str) -> None:
        """更新凭证（不触发重连）"""
        self.bot_id = bot_id.strip()
        self.secret = secret.strip()
        logger.info("[WeWork] credentials updated: bot_id=%s", self.bot_id)

    def start(self) -> dict:
        """启动长连接（异步，不会阻塞）。已连接则先 stop。"""
        if self._status == "connected":
            return {"ok": True, "message": "已连接，无需重复启动"}

        if not self.bot_id or not self.secret:
            return {"ok": False, "message": "请先配置 BotID 和 Secret"}

        # 如果已有线程在跑，先停掉
        self._do_stop()

        self._running = True
        self._set_status("connecting")
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        return {"ok": True, "message": "连接中…"}

    def stop(self) -> dict:
        """断开长连接。"""
        self._do_stop()
        return {"ok": True, "message": "已断开"}

    def _do_stop(self) -> None:
        self._running = False
        self._cancel_heartbeat()
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass
            self._ws = None
        self._set_status("stopped")

    # ── 内部 WebSocket 循环（带自动重连） ─────────────────────

    def _run_loop(self) -> None:
        while self._running:
            try:
                import websocket

                self._ws = websocket.WebSocketApp(
                    WS_URL,
                    on_open=self._on_open,
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close,
                )
                self._ws.run_forever(ping_interval=None, ping_timeout=None)
            except Exception as e:
                logger.warning("[WeWork] connection error: %s", e)
                self._set_status("error", str(e))

            if not self._running:
                break

            # 指数退避重连
            for delay in [3, 5, 10, 20, 30]:
                if not self._running:
                    break
                logger.info("[WeWork] reconnecting in %ds…", delay)
                time.sleep(delay)

    def _on_open(self, ws) -> None:
        """WebSocket 打开 → 发送订阅请求。"""
        sub = {
            "cmd": "aibot_subscribe",
            "headers": {"req_id": f"sub_{int(time.time() * 1000)}"},
            "body": {"bot_id": self.bot_id, "secret": self.secret},
        }
        ws.send(json.dumps(sub))
        self._set_status("connected")
        self._start_heartbeat(ws)
        _wework_log(f"【连接】企微长连接已建立 bot_id={self.bot_id}")
        logger.info("[WeWork] 订阅请求已发送")

    def _on_message(self, ws, message: str) -> None:
        """收到消息或事件。"""
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            logger.warning("[WeWork] 收到非 JSON 消息: %s", message[:200])
            return

        cmd = data.get("cmd", "")
        headers = data.get("headers", {})
        body = data.get("body", {})
        req_id = headers.get("req_id", "")

        if cmd == "aibot_subscribe_ack":
            # 订阅确认
            code = body.get("errcode", -1)
            if code == 0:
                self._set_status("connected")
                logger.info("[WeWork] 订阅成功")
            else:
                errmsg = body.get("errmsg", "未知错误")
                self._set_status("error", f"订阅失败: {errmsg}")
                logger.error("[WeWork] 订阅失败: errcode=%s errmsg=%s", code, errmsg)

        elif cmd == "aibot_msg_callback":
            # 用户消息
            msgtype = body.get("msgtype", "")
            chatid = body.get("chatid", "")
            userid = body.get("from", {}).get("userid", "")

            if msgtype == "text":
                content = body.get("text", {}).get("content", "")
                _wework_log(f"【收到】from={userid} chatid={chatid} msg=\"{content[:200]}\"")
                logger.info("[WeWork] 收到文本消息 from=%s chatid=%s: %s", userid, chatid, content[:100])
                # 后台线程处理，不阻塞 WebSocket 线程（否则心跳 pong 无法响应导致断连）
                threading.Thread(
                    target=self._handle_text_message,
                    args=(chatid, userid, content),
                    kwargs={"req_id": req_id},
                    daemon=True,
                ).start()
            elif msgtype in ("image", "voice", "file", "video"):
                _wework_log(f"【收到{msgtype}】from={userid}（当前暂不处理）")
                logger.info("[WeWork] 收到 %s 消息 from=%s（当前暂不处理）", msgtype, userid)
            else:
                _wework_log(f"【收到未知】msgtype={msgtype} from={userid}")
                logger.info("[WeWork] 收到未知消息类型: %s", msgtype)

        elif cmd == "aibot_event_callback":
            event_type = body.get("event", {}).get("eventtype", "")
            chatid = body.get("chatid", "")
            userid = body.get("from", {}).get("userid", "")
            logger.info("[WeWork] 事件: %s from=%s", event_type, userid)

            if event_type == "enter_chat":
                # 用户首次进入会话 → 发送欢迎语
                self._send_welcome(chatid)

        elif cmd == "pong":
            # 心跳回复
            pass

        else:
            # 未处理命令（含 aibot_send_msg 响应、ack 等）
            errcode = data.get("errcode", -999)
            errmsg = data.get("errmsg", "")
            logger.info("[WeWork] 未处理命令: cmd=%s req_id=%s errcode=%s errmsg=%s body=%s",
                        cmd, req_id, errcode, errmsg, str(body)[:200])

    def _on_error(self, ws, error) -> None:
        self._set_status("error", str(error))
        self._cancel_heartbeat()

    def _on_close(self, ws, close_status_code, close_msg) -> None:
        logger.info("[WeWork] 连接关闭: code=%s msg=%s", close_status_code, close_msg)
        self._cancel_heartbeat()
        if self._running:
            self._set_status("connecting")

    # ── 心跳 ───────────────────────────────────────────────────

    def _start_heartbeat(self, ws) -> None:
        self._cancel_heartbeat()

        def _ping():
            if not self._running or not ws:
                return
            try:
                ping = {
                    "cmd": "ping",
                    "headers": {"req_id": f"ping_{int(time.time() * 1000)}"},
                }
                ws.send(json.dumps(ping))
            except Exception:
                pass
            self._heartbeat_timer = threading.Timer(30, _ping)
            self._heartbeat_timer.daemon = True
            self._heartbeat_timer.start()

        # 首次心跳在 5 秒后
        self._heartbeat_timer = threading.Timer(5, _ping)
        self._heartbeat_timer.daemon = True
        self._heartbeat_timer.start()

    def _cancel_heartbeat(self) -> None:
        if self._heartbeat_timer:
            self._heartbeat_timer.cancel()
            self._heartbeat_timer = None

    # ── 消息处理与回复 ─────────────────────────────────────────

    def _handle_text_message(self, chatid: str, userid: str, content: str, req_id: str = "") -> None:
        """处理文本消息：调用外部回调获取回复后发送。"""
        reply = None
        if self.on_message:
            try:
                _wework_log(f"【处理】compid={userid} 消息已投递到 on_message 回调")
                reply = self.on_message(userid, content)
                if reply:
                    _wework_log(f"【回复】compid={userid} 回复长度={len(reply)} 前60字=\"{reply[:60]}\"")
                    self.send_markdown(chatid, reply, req_id=req_id)
                else:
                    _wework_log(f"【警告】compid={userid} on_message 返回空回复")
            except Exception as e:
                logger.error("[WeWork] 消息处理异常: %s", e)
                _wework_log(f"【错误】compid={userid} 处理异常: {e}")
                reply = f"抱歉，处理消息时出错了: {e}"
                self.send_text(chatid, reply, req_id=req_id)
        else:
            # 无回调注册时，返回默认回复
            _wework_log(f"【未配置】compid={userid} 无 on_message 回调，使用默认回复")
            reply = "已收到您的消息，但 AiBrain 尚未配置回复逻辑。"
            self.send_text(chatid, reply, req_id=req_id)

    def _send_welcome(self, chatid: str) -> None:
        """发送欢迎语（enter_chat 事件 5 秒内有效）。"""
        welcome = "欢迎来到 AiBrain！您可以向我发送消息，我会尽力为您解答。"
        resp = {
            "cmd": "aibot_respond_welcome_msg",
            "headers": {"req_id": f"welcome_{int(time.time() * 1000)}"},
            "body": {
                "msgtype": "text",
                "text": {"content": welcome},
            },
        }
        self._safe_send(resp)
        logger.info("[WeWork] 欢迎语已发送 chatid=%s", chatid)

    def send_text(self, chatid: str, content: str, req_id: str = "") -> None:
        """回复文本消息。"""
        _wework_log(f"【发送文本】chatid={chatid} 长度={len(content)}")
        rid = req_id or f"reply_{int(time.time() * 1000)}"
        resp = {
            "cmd": "aibot_respond_msg",
            "headers": {"req_id": rid},
            "body": {
                "msgtype": "text",
                "text": {"content": content},
            },
        }
        self._safe_send(resp)

    def send_markdown(self, chatid: str, content: str, req_id: str = "") -> None:
        """回复 Markdown 消息。"""
        _wework_log(f"【发送markdown】chatid={chatid} 长度={len(content)} 前60字=\"{content[:60]}\"")
        rid = req_id or f"reply_{int(time.time() * 1000)}"
        resp = {
            "cmd": "aibot_respond_msg",
            "headers": {"req_id": rid},
            "body": {
                "msgtype": "markdown",
                "markdown": {"content": content},
            },
        }
        self._safe_send(resp)

    def send_proactive(self, userid: str, content: str, msgtype: str = "markdown") -> bool:
        """主动推送消息给用户（aibot_send_msg）。

        前提：用户必须已经在会话中给机器人发过消息。

        Args:
            userid: 企微用户 ID（单聊时 chatid 直接填 userid）
            content: 消息内容
            msgtype: 消息类型 markdown / text
        Returns:
            是否成功发送
        """
        cmd_key = "markdown" if msgtype == "markdown" else "text"
        resp = {
            "cmd": "aibot_send_msg",
            "headers": {"req_id": f"pro_{int(time.time() * 1000)}"},
            "body": {
                "chatid": userid,  # 单聊直接填 userid
                "chat_type": 1,
                "msgtype": msgtype,
                cmd_key: {"content": content},
            },
        }
        self._safe_send(resp)
        _wework_log(f"【主动推送】userid={userid} msgtype={msgtype} 长度={len(content)}")
        return True

    def _safe_send(self, data: dict) -> None:
        """安全发送 JSON 到 WebSocket。"""
        if not self._ws or self._status != "connected":
            logger.warning("[WeWork] 未连接，无法发送消息")
            return
        try:
            self._ws.send(json.dumps(data, ensure_ascii=False))
        except Exception as e:
            logger.error("[WeWork] 发送失败: %s", e)

    # ── 配置持久化 ─────────────────────────────────────────────

    def load_config(self, path: str) -> bool:
        """从 JSON 文件加载 BotID 和 Secret。"""
        try:
            import os
            if not os.path.exists(path):
                logger.info("[WeWork] 配置文件不存在: %s", path)
                return False
            with open(path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            self.bot_id = cfg.get("bot_id", "")
            self.secret = cfg.get("secret", "")
            logger.info("[WeWork] 配置已加载 bot_id=%s", self.bot_id)
            return True
        except Exception as e:
            logger.warning("[WeWork] 加载配置失败: %s", e)
            return False

    def save_config(self, path: str) -> bool:
        """保存 BotID 和 Secret 到 JSON 文件。"""
        try:
            import os
            os.makedirs(os.path.dirname(path), exist_ok=True)
            cfg = {"bot_id": self.bot_id, "secret": self.secret}
            with open(path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2, ensure_ascii=False)
            logger.info("[WeWork] 配置已保存 bot_id=%s", self.bot_id)
            return True
        except Exception as e:
            logger.warning("[WeWork] 保存配置失败: %s", e)
            return False
