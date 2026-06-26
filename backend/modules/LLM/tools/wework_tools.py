"""
wework_tools — 企业微信主动推送工具

封装 WeWorkBot.send_proactive，供 LLM function calling 调用。
Agent 可通过 use_tool action 主动向企微用户推送消息。
"""
import logging

from .registry import ToolDef

logger = logging.getLogger(__name__)


def _wework_send_fn(userid: str, content: str, msgtype: str = "markdown") -> str:
    """向企业微信用户主动推送消息

    Args:
        userid: 企微用户 ID
        content: 消息内容（支持 markdown 格式）
        msgtype: 消息类型 markdown / text，默认 markdown

    Returns:
        执行结果描述
    """
    from modules.WeWork.bot_adapter import WeWorkBot

    bot = WeWorkBot.get_instance()
    status = bot.get_status()

    if not status.get("bot_id"):
        return "错误：企业微信机器人未配置，请在企微网关页面配置 BotID 和 Secret"

    if not status.get("connected"):
        return "错误：企业微信未连接，请在企微网关页面点击「连接」"

    if msgtype not in ("markdown", "text"):
        msgtype = "markdown"

    try:
        bot.send_proactive(userid=userid, content=content, msgtype=msgtype)
        return f"已向 {userid} 主动推送 {msgtype} 消息（{len(content)} 字符）"
    except Exception as e:
        logger.warning(f"[wework_tools] send_proactive failed: {e}")
        return f"错误：推送失败 — {e}"


WEWORK_SEND_TOOL = ToolDef(
    name="wework_send",
    description=(
        "向企业微信用户主动推送消息。"
        "当用户通过企微联系你且你有重要信息需要主动告知时使用。"
        "注意：目标用户必须先给机器人发过至少一条消息才能收到主动推送。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "userid": {
                "type": "string",
                "description": "企业微信用户 ID（从对话上下文中获取）",
            },
            "content": {
                "type": "string",
                "description": "消息内容，支持 Markdown 格式",
            },
            "msgtype": {
                "type": "string",
                "description": "消息类型：markdown 或 text，默认 markdown",
                "enum": ["markdown", "text"],
            },
        },
        "required": ["userid", "content"],
    },
    fn=_wework_send_fn,
)


def register_wework_tools():
    """注册所有企微工具到 ToolRegistry（在 _preload 中调用）"""
    from .registry import get_tool_registry
    reg = get_tool_registry()
    reg.register(WEWORK_SEND_TOOL)
