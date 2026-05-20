"""Expert Agent type definitions."""

from pydantic import BaseModel


class AgentProfile(BaseModel):
    name: str
    display_name: str
    description: str
    soul_file: str
    skill_plugin: str = ""
    model_preference: str = "primary"
    max_context_tokens: int = 32000
    role: str = "operator"