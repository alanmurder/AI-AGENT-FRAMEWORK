"""External agent type definitions — endpoint config and protocol adapters."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum


class AgentProtocol(str, Enum):
    """Supported external agent/workflow API protocols."""
    OPENAI_CHAT = "openai-chat"    # OpenAI-compatible chat completions endpoint
    SIMPLE_JSON = "simple-json"    # Generic JSON in/out REST endpoint
    CUSTOM = "custom"              # Fully custom, driven by input/output mapping


@dataclass
class ExternalEndpoint:
    """Configuration for an external agent/workflow HTTP endpoint."""
    url: str
    protocol: str = "openai-chat"
    method: str = "POST"
    auth_type: str = "none"          # "none" | "bearer" | "header"
    auth_credential: str = ""        # token value or ${ENV_VAR} placeholder
    auth_header_name: str = "Authorization"
    timeout_seconds: int = 120
    headers: dict[str, str] = field(default_factory=dict)


@dataclass
class ProxyResult:
    """Result from proxying a request to an external agent."""
    content: str
    status_code: int = 200
    error: str | None = None
    metadata: dict = field(default_factory=dict)


class ExternalAgentAdapter(ABC):
    """Base class for protocol adapters that translate between platform and external formats."""

    @abstractmethod
    def build_request(
        self, message: str, user_id: str, session_id: str, endpoint: ExternalEndpoint, history: list[dict] | None = None,
    ) -> dict:
        """Build the HTTP request body for the external endpoint."""

    @abstractmethod
    def build_headers(self, endpoint: ExternalEndpoint) -> dict[str, str]:
        """Build HTTP headers including auth."""

    @abstractmethod
    def extract_response(self, response_data: dict) -> str:
        """Extract the text response from the external endpoint's reply."""

    @abstractmethod
    def extract_stream_chunk(self, chunk_data: dict) -> str | None:
        """Extract a text delta from a streaming SSE chunk. Returns None if no content."""


class OpenAICompatibleAdapter(ExternalAgentAdapter):
    """Adapter for OpenAI-compatible chat completions API."""

    def build_request(self, message, user_id, session_id, endpoint, history=None):
        messages = list(history or [])
        messages.append({"role": "user", "content": message})
        return {
            "messages": messages,
            "stream": True,
            "user": user_id,
        }

    def build_headers(self, endpoint):
        headers = {"Content-Type": "application/json"}
        if endpoint.auth_type == "bearer":
            import os
            cred = os.path.expandvars(endpoint.auth_credential) if "$" in endpoint.auth_credential else endpoint.auth_credential
            headers["Authorization"] = f"Bearer {cred}"
        elif endpoint.auth_type == "header":
            import os
            cred = os.path.expandvars(endpoint.auth_credential) if "$" in endpoint.auth_credential else endpoint.auth_credential
            headers[endpoint.auth_header_name] = cred
        headers.update(endpoint.headers)
        return headers

    def extract_response(self, response_data):
        choices = response_data.get("choices", [])
        if choices:
            msg = choices[0].get("message", {})
            return msg.get("content", "")
        return ""

    def extract_stream_chunk(self, chunk_data):
        choices = chunk_data.get("choices", [])
        if choices:
            delta = choices[0].get("delta", {})
            return delta.get("content")
        return None


class SimpleJsonAdapter(ExternalAgentAdapter):
    """Adapter for generic JSON REST endpoints (input→output)."""

    def build_request(self, message, user_id, session_id, endpoint, history=None):
        return {
            "input": message,
            "user": user_id,
            "conversation_id": session_id,
            "history": history or [],
        }

    def build_headers(self, endpoint):
        headers = {"Content-Type": "application/json"}
        if endpoint.auth_type == "bearer":
            import os
            cred = os.path.expandvars(endpoint.auth_credential) if "$" in endpoint.auth_credential else endpoint.auth_credential
            headers["Authorization"] = f"Bearer {cred}"
        elif endpoint.auth_type == "header":
            import os
            cred = os.path.expandvars(endpoint.auth_credential) if "$" in endpoint.auth_credential else endpoint.auth_credential
            headers[endpoint.auth_header_name] = cred
        headers.update(endpoint.headers)
        return headers

    def extract_response(self, response_data):
        # Try common output field names
        for key in ("output", "result", "response", "content", "reply"):
            if key in response_data:
                val = response_data[key]
                return val if isinstance(val, str) else str(val)
        return str(response_data)

    def extract_stream_chunk(self, chunk_data):
        # Simple JSON endpoints typically don't stream; return full output if present
        return self.extract_response(chunk_data)


def get_adapter(protocol: str) -> ExternalAgentAdapter:
    """Factory: return the appropriate adapter for a protocol."""
    if protocol == "openai-chat":
        return OpenAICompatibleAdapter()
    if protocol == "simple-json":
        return SimpleJsonAdapter()
    raise ValueError(f"Unsupported protocol: {protocol}")
