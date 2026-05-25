"""External agent integration — HTTP proxy forwarding for pre-built domain agents/workflows."""

from harness.external_agent.types import (
    ExternalEndpoint, ProxyResult, AgentProtocol,
    ExternalAgentAdapter, OpenAICompatibleAdapter, SimpleJsonAdapter, get_adapter,
)
from harness.external_agent.proxy import AgentProxyHandler

__all__ = [
    "ExternalEndpoint", "ProxyResult", "AgentProtocol",
    "ExternalAgentAdapter", "OpenAICompatibleAdapter", "SimpleJsonAdapter", "get_adapter",
    "AgentProxyHandler",
]
