"""Expert Agent type definitions."""

from pydantic import BaseModel


class EndpointConfig(BaseModel):
    """External agent endpoint configuration."""
    url: str
    protocol: str = "openai-chat"
    method: str = "POST"
    auth_type: str = "none"
    auth_credential: str = ""
    auth_header_name: str = "Authorization"
    timeout_seconds: int = 120
    headers: dict[str, str] = {}


class AgentProfile(BaseModel):
    name: str
    display_name: str
    description: str
    soul_file: str = ""
    skill_plugin: str = ""
    model_preference: str = "primary"
    max_context_tokens: int = 32000
    role: str = "operator"
    skills: list[str] = []
    mcp_tools: list[str] = []
    source: str = "file"
    type: str = "internal"
    endpoint: EndpointConfig | None = None
    created_by: str = ""
    created_at: str = ""
    updated_at: str = ""

    @property
    def is_external(self) -> bool:
        return self.type == "external"