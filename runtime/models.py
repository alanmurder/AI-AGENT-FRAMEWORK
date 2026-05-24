"""Model routing using langchain init_chat_model."""

import os

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel

from runtime.config import AgentConfig

PROVIDER_MODEL_MAP = {
    "deepseek": {
        "default": "deepseek-chat",
        "mini": "deepseek-chat",
        "env_key": "DEEPSEEK_API_KEY",
        "config_key": "deepseek_api_key",
    },
    "openai": {
        "default": "gpt-4o",
        "mini": "gpt-4o-mini",
        "env_key": "OPENAI_API_KEY",
        "config_key": "openai_api_key",
    },
    "anthropic": {
        "default": "claude-sonnet-4-6",
        "mini": "claude-haiku-4-5-20251001",
        "env_key": "ANTHROPIC_API_KEY",
        "config_key": "anthropic_api_key",
    },
    "zhipu": {
        "default": "glm-4",
        "env_key": "ZHIPUAI_API_KEY",
        "config_key": "zhipu_api_key",
    },
}


def _inject_api_key(config: AgentConfig, provider: str) -> None:
    """Ensure the provider's API key is available in the environment variable expected by LangChain.

    If no API key is configured, a placeholder is injected to allow model construction.
    Actual API calls will fail with an auth error — this is intentional and allows the server
    to start for health checks, static file serving, and API docs even without a valid key.
    """
    info = PROVIDER_MODEL_MAP.get(provider, {})
    env_key = info.get("env_key")
    config_key = info.get("config_key")
    if env_key and config_key:
        key_value = getattr(config, config_key, "")
        if key_value and not os.environ.get(env_key):
            os.environ[env_key] = key_value
        elif not key_value and not os.environ.get(env_key):
            # Placeholder allows model construction; API calls will fail with auth error
            os.environ[env_key] = "sk-placeholder-missing-api-key"


def create_primary_model(config: AgentConfig) -> BaseChatModel:
    _inject_api_key(config, config.llm_primary_provider)
    return init_chat_model(
        model=config.llm_primary_model,
        model_provider=config.llm_primary_provider,
        temperature=config.llm_primary_temperature,
        max_tokens=config.llm_primary_max_tokens,
    )


def create_fallback_model(config: AgentConfig) -> BaseChatModel:
    _inject_api_key(config, config.llm_fallback_provider)
    return init_chat_model(
        model=config.llm_fallback_model,
        model_provider=config.llm_fallback_provider,
        temperature=config.llm_primary_temperature,
        max_tokens=config.llm_primary_max_tokens,
    )


def create_mini_model(config: AgentConfig) -> BaseChatModel:
    """Lightweight model for compression, evaluation, and L3 security review."""
    provider = config.llm_primary_provider
    _inject_api_key(config, provider)
    model_info = PROVIDER_MODEL_MAP.get(provider, {})
    mini_model = model_info.get("mini", config.llm_primary_model)

    return init_chat_model(
        model=mini_model,
        model_provider=provider,
        temperature=0.0,
        max_tokens=2048,
    )