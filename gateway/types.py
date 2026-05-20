"""Gateway type definitions."""

from dataclasses import dataclass, field
from enum import Enum


class ChannelType(str, Enum):
    WEB = "web"
    DINGTALK = "dingtalk"
    FEISHU = "feishu"
    WECOM = "wecom"


@dataclass
class StandardMessage:
    user_id: str
    channel: ChannelType
    content: str
    metadata: dict = field(default_factory=dict)
    timestamp: str = ""


@dataclass
class AgentResponse:
    content: str
    tool_calls: list[dict] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)