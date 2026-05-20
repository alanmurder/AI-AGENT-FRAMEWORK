"""DingTalk channel adapter — integrates with DingTalk (钉钉) bot API.

DingTalk enterprise bots receive messages via webhook callbacks and send
responses via REST API calls to the DingTalk open platform.

MVP: supports outgoing message sending via DingTalk robot webhook.
Incoming message handling (callback) is configured separately in the gateway server.
"""

import hashlib
import base64
import time
import json
import hmac
import structlog
from datetime import datetime

from gateway.adapters.base import ChannelAdapter
from gateway.types import StandardMessage, AgentResponse, ChannelType

logger = structlog.get_logger()


class DingTalkAdapter(ChannelAdapter):
    """DingTalk enterprise bot adapter.

    Configuration requires:
    - app_key: DingTalk application key
    - app_secret: DingTalk application secret
    - webhook_url: Robot webhook URL for outgoing messages
    """

    channel_type = ChannelType.DINGTALK

    def __init__(self, app_key: str = "", app_secret: str = "", webhook_url: str = ""):
        self.app_key = app_key
        self.app_secret = app_secret
        self.webhook_url = webhook_url

    async def connect(self) -> bool:
        """Validate DingTalk configuration."""
        if not self.app_key or not self.app_secret:
            logger.warn("dingtalk_config_missing", detail="app_key or app_secret not set")
            return False
        logger.info("dingtalk_connected", app_key=self.app_key)
        return True

    async def receive(self) -> list[StandardMessage]:
        """DingTalk messages come via HTTP callback, not polling. Returns empty list."""
        return []

    async def send(self, user_id: str, response: AgentResponse) -> bool:
        """Send agent response to DingTalk via robot webhook."""
        if not self.webhook_url:
            logger.warn("dingtalk_webhook_missing", user_id=user_id)
            return False

        payload = self.format_response(response)

        try:
            import urllib.request
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                self.webhook_url,
                data=data,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                if result.get("errcode") == 0:
                    logger.info("dingtalk_send_success", user_id=user_id)
                    return True
                else:
                    logger.error("dingtalk_send_error", error=result)
                    return False
        except Exception as e:
            logger.error("dingtalk_send_failed", error=str(e))
            return False

    async def disconnect(self) -> bool:
        return True

    def normalize(self, raw: dict) -> StandardMessage:
        """Convert DingTalk callback message to StandardMessage.

        DingTalk callback format:
        {
            "msgtype": "text",
            "text": {"content": "user message"},
            "senderNick": "user_name",
            "senderStaffId": "user_staff_id",
            "conversationId": "conv_id",
            "conversationType": "1" (private) or "2" (group)
        }
        """
        msg_type = raw.get("msgtype", "text")
        content = ""

        if msg_type == "text":
            content = raw.get("text", {}).get("content", "")
        elif msg_type == "richText":
            # Rich text: extract plain text segments
            rich_text = raw.get("richText", {})
            content = rich_text.get("content", "")
        else:
            content = raw.get("content", "")

        sender_id = raw.get("senderStaffId", raw.get("senderId", "unknown"))
        conversation_type = raw.get("conversationType", "1")

        metadata = {
            "conversation_id": raw.get("conversationId", ""),
            "conversation_type": conversation_type,
            "sender_nick": raw.get("senderNick", ""),
            "msgtype": msg_type,
            "is_group": conversation_type == "2",
        }

        return StandardMessage(
            user_id=sender_id,
            channel=ChannelType.DINGTALK,
            content=content.strip(),
            metadata=metadata,
            timestamp=raw.get("createAt", datetime.now().isoformat()),
        )

    def format_response(self, response: AgentResponse) -> dict:
        """Convert AgentResponse to DingTalk message format.

        DingTalk robot webhook format:
        {
            "msgtype": "text",
            "text": {"content": "response text"},
            "at": {"atUserIds": ["user_id"], "isAtAll": false}
        }
        """
        content = response.content
        at_user_ids = []
        if response.metadata.get("user_id"):
            at_user_ids = [response.metadata["user_id"]]

        return {
            "msgtype": "text",
            "text": {"content": content},
            "at": {
                "atUserIds": at_user_ids,
                "isAtAll": False,
            },
        }

    def verify_callback_signature(self, timestamp: str, sign: str) -> bool:
        """Verify DingTalk callback signature for security.

        DingTalk uses HMAC-SHA256 with app_secret + timestamp to sign callbacks.
        Signature = base64(hmac_sha256(timestamp + "\n" + app_secret, app_secret))
        """
        if not self.app_secret:
            return False

        string_to_sign = f"{timestamp}\n{self.app_secret}"
        hmac_code = hmac.new(
            self.app_secret.encode("utf-8"),
            string_to_sign.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()
        expected_sign = base64.b64encode(hmac_code).decode("utf-8")
        return expected_sign == sign