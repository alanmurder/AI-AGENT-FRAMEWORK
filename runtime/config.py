"""Agent runtime configuration."""

import os
from pathlib import Path
from typing import Optional, Tuple, Type

from pydantic_settings import BaseSettings, SettingsConfigDict, YamlConfigSettingsSource


class AgentConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AI_AGENT_",
        env_file=".env",
        env_file_encoding="utf-8",
        yaml_file="config/settings.yaml",
        extra="ignore",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: Type[BaseSettings],
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ) -> Tuple:
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            YamlConfigSettingsSource(settings_cls),
            file_secret_settings,
        )

    # LLM
    llm_primary_provider: str = "deepseek"
    llm_primary_model: str = "deepseek-v3"
    llm_primary_temperature: float = 0.1
    llm_primary_max_tokens: int = 4096
    llm_fallback_provider: str = "openai"
    llm_fallback_model: str = "gpt-4o"

    # API Keys
    deepseek_api_key: str = ""
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    zhipu_api_key: str = ""

    # Gateway
    gateway_host: str = "0.0.0.0"
    gateway_port: int = 8000
    gateway_workers: int = 1

    # Memory
    memory_base_dir: str = "data/workspace"
    project_root: str = ""
    max_memory_tokens: int = 2000

    # Context
    max_context_tokens: int = 64000
    compression_threshold: int = 4000
    flush_threshold: int = 60000
    max_flush_per_session: int = 1
    placeholder_threshold: int = 2000
    keep_recent_messages: int = 20

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Security
    jwt_secret: str = "change-this-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 480

    # Logging
    log_level: str = "INFO"

    # Scheduler
    heartbeat_interval: int = 30  # minutes

    # PostgreSQL (Phase 2 - Medium-term Memory)
    pg_host: str = "localhost"
    pg_port: int = 5432
    pg_database: str = "ai_agent_platform"
    pg_user: str = "ai_agent"
    pg_password: str = ""
    pg_pool_min_size: int = 2
    pg_pool_max_size: int = 10
    mid_term_retention_days: int = 30
    mid_term_search_top_k: int = 5

    # Production
    serve_static: bool = False
    static_dir: str = "web/dist"
    static_url_path: str = "/"

    # Sandbox (Phase 2+)
    sandbox_enabled: bool = True
    sandbox_backend: str = "agentscope_remote"  # agentscope_remote | local_docker | disabled
    sandbox_fail_closed: bool = True
    sandbox_base_url: str = "http://sandbox-runtime:8000"
    sandbox_bearer_token: str = ""
    sandbox_network_default: str = "deny"
    sandbox_session_ttl_seconds: int = 3600
    sandbox_auto_build_image: bool = False
    sandbox_docker_image: str = "ai-agent-sandbox:latest"
    sandbox_timeout_seconds: int = 30
    sandbox_max_memory: str = "256m"

    # Evolution (Phase 3)
    evolution_enabled: bool = True
    auto_evolve_enabled: bool = False
    gepa_max_candidates: int = 3
    three_agent_max_rounds: int = 3
    subagent_timeout: int = 120
    background_max_concurrent: int = 3

    # Expert & Team (Phase 4)
    expert_enabled: bool = True
    team_enabled: bool = True
    member_idle_timeout: int = 300
    team_max_members: int = 5
    task_board_max_tasks: int = 20

    def get_memory_base_dir(self) -> Path:
        # Resolve relative paths against project_root, fallback to cwd
        p = Path(self.memory_base_dir)
        if not p.is_absolute():
            root = Path(self.project_root) if self.project_root else Path.cwd()
            p = root / p
        p.mkdir(parents=True, exist_ok=True)
        return p
