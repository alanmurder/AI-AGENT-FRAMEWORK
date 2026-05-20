"""Channel adapter base class."""

from abc import ABC, abstractmethod
from gateway.types import StandardMessage, AgentResponse, ChannelType


class ChannelAdapter(ABC):
    """Base class for all channel adapters. Each channel implements this interface."""

    channel_type: ChannelType

    @abstractmethod
    async def connect(self) -> bool:
        """Establish connection to the channel platform."""

    @abstractmethod
    async def receive(self) -> list[StandardMessage]:
        """Receive messages from the channel."""

    @abstractmethod
    async def send(self, user_id: str, response: AgentResponse) -> bool:
        """Send agent response to a specific user on this channel."""

    @abstractmethod
    async def disconnect(self) -> bool:
        """Disconnect from the channel platform."""

    @abstractmethod
    def normalize(self, raw: dict) -> StandardMessage:
        """Convert raw platform message to StandardMessage format."""

    @abstractmethod
    def format_response(self, response: AgentResponse) -> dict:
        """Convert AgentResponse to platform-specific format."""