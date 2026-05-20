"""DingTalk channel adapter tests."""

import pytest
from gateway.adapters.dingtalk import DingTalkAdapter
from gateway.types import ChannelType, AgentResponse, StandardMessage


@pytest.fixture
def adapter():
    return DingTalkAdapter(
        app_key="test_key",
        app_secret="test_secret",
        webhook_url="",
    )


class TestDingTalkAdapter:
    def test_channel_type(self, adapter):
        assert adapter.channel_type == ChannelType.DINGTALK

    @pytest.mark.asyncio
    async def test_connect_valid_config(self, adapter):
        result = await adapter.connect()
        assert result is True

    @pytest.mark.asyncio
    async def test_connect_missing_config(self):
        empty_adapter = DingTalkAdapter(app_key="", app_secret="")
        result = await empty_adapter.connect()
        assert result is False

    @pytest.mark.asyncio
    async def test_receive_returns_empty(self, adapter):
        messages = await adapter.receive()
        assert messages == []

    @pytest.mark.asyncio
    async def test_send_no_webhook(self, adapter):
        response = AgentResponse(content="Hello")
        result = await adapter.send("user1", response)
        assert result is False  # No webhook configured

    def test_normalize_text_message(self, adapter):
        raw = {
            "msgtype": "text",
            "text": {"content": "Hello, what is the production status?"},
            "senderStaffId": "staff001",
            "senderNick": "张三",
            "conversationId": "conv123",
            "conversationType": "1",
            "createAt": "2026-05-12T10:00:00",
        }
        msg = adapter.normalize(raw)
        assert msg.user_id == "staff001"
        assert msg.channel == ChannelType.DINGTALK
        assert msg.content == "Hello, what is the production status?"
        assert msg.metadata["sender_nick"] == "张三"
        assert msg.metadata["is_group"] is False

    def test_normalize_group_message(self, adapter):
        raw = {
            "msgtype": "text",
            "text": {"content": "Group message"},
            "senderStaffId": "staff002",
            "conversationId": "conv_group_456",
            "conversationType": "2",
        }
        msg = adapter.normalize(raw)
        assert msg.metadata["is_group"] is True
        assert msg.metadata["conversation_type"] == "2"

    def test_normalize_rich_text(self, adapter):
        raw = {
            "msgtype": "richText",
            "richText": {"content": "Rich text content here"},
            "senderStaffId": "staff003",
            "conversationType": "1",
        }
        msg = adapter.normalize(raw)
        assert msg.content == "Rich text content here"

    def test_normalize_unknown_type(self, adapter):
        raw = {
            "msgtype": "unknown",
            "content": "Fallback content",
            "senderStaffId": "staff004",
            "conversationType": "1",
        }
        msg = adapter.normalize(raw)
        assert msg.content == "Fallback content"

    def test_format_response_text(self, adapter):
        response = AgentResponse(
            content="Production line #3 is running at 85% capacity.",
            metadata={"user_id": "staff001"},
        )
        payload = adapter.format_response(response)
        assert payload["msgtype"] == "text"
        assert payload["text"]["content"] == "Production line #3 is running at 85% capacity."
        assert payload["at"]["atUserIds"] == ["staff001"]
        assert payload["at"]["isAtAll"] is False

    def test_format_response_no_at(self, adapter):
        response = AgentResponse(content="General announcement")
        payload = adapter.format_response(response)
        assert payload["at"]["atUserIds"] == []

    def test_verify_callback_signature_valid(self):
        import base64, hashlib, hmac
        adapter = DingTalkAdapter(app_secret="my_secret")
        timestamp = "1234567890"
        string_to_sign = f"{timestamp}\n{adapter.app_secret}"
        hmac_code = hmac.new(
            adapter.app_secret.encode("utf-8"),
            string_to_sign.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()
        sign = base64.b64encode(hmac_code).decode("utf-8")

        assert adapter.verify_callback_signature(timestamp, sign) is True

    def test_verify_callback_signature_invalid(self, adapter):
        result = adapter.verify_callback_signature("1234567890", "invalid_sign")
        assert result is False

    def test_verify_callback_no_secret(self):
        adapter = DingTalkAdapter(app_secret="")
        result = adapter.verify_callback_signature("1234", "sign")
        assert result is False