"""Sandbox manager - session lifecycle, backend selection, and path policy."""

from __future__ import annotations

import ntpath
import posixpath
import re
import time
from dataclasses import dataclass

import structlog

from harness.sandbox.backends import (
    AgentScopeRemoteBackend,
    DisabledSandboxBackend,
    LocalDockerBackend,
    SandboxBackend,
)
from harness.sandbox.types import SandboxPathError, SandboxResult, SandboxUnavailableError
from runtime.context_schema import UserContext

logger = structlog.get_logger()


@dataclass
class _SessionState:
    user_id: str
    agent_id: str
    last_used_at: float


class SandboxManager:
    """Coordinates sandbox sessions and enforces workspace path boundaries."""

    def __init__(
        self,
        backend: SandboxBackend,
        enabled: bool = True,
        fail_closed: bool = True,
        session_ttl_seconds: int = 3600,
        network_default: str = "deny",
    ):
        self.backend = backend
        self.enabled = enabled
        self.fail_closed = fail_closed
        self.session_ttl_seconds = session_ttl_seconds
        self.network_default = network_default
        self._sessions: dict[str, _SessionState] = {}

    @classmethod
    def from_config(cls, config) -> "SandboxManager":
        backend_name = getattr(config, "sandbox_backend", "agentscope_remote")
        enabled = getattr(config, "sandbox_enabled", True)
        fail_closed = getattr(config, "sandbox_fail_closed", True)
        ttl = getattr(config, "sandbox_session_ttl_seconds", 3600)
        network_default = getattr(config, "sandbox_network_default", "deny")

        if backend_name == "agentscope_remote":
            backend = AgentScopeRemoteBackend(
                base_url=getattr(config, "sandbox_base_url", ""),
                bearer_token=getattr(config, "sandbox_bearer_token", ""),
            )
        elif backend_name == "local_docker":
            backend = LocalDockerBackend(
                image=getattr(config, "sandbox_docker_image", "ai-agent-sandbox:latest"),
                auto_build_image=getattr(config, "sandbox_auto_build_image", False),
                network_default=network_default,
                max_memory=getattr(config, "sandbox_max_memory", "256m"),
            )
        elif backend_name == "disabled":
            backend = DisabledSandboxBackend()
        else:
            logger.warning("unknown_sandbox_backend", backend=backend_name)
            backend = DisabledSandboxBackend()

        return cls(
            backend=backend,
            enabled=enabled,
            fail_closed=fail_closed,
            session_ttl_seconds=ttl,
            network_default=network_default,
        )

    def healthcheck(self) -> dict:
        if not self.enabled:
            return {"enabled": False, "status": "disabled", "backend": self.backend.name}
        info = self.backend.healthcheck()
        info["enabled"] = True
        info["fail_closed"] = self.fail_closed
        info["active_sessions"] = len(self._sessions)
        return info

    def run_shell(self, user_ctx: UserContext, command: str, timeout: int = 30) -> SandboxResult:
        session_id = self._ensure_session(user_ctx)
        result = self.backend.run_shell(session_id, command, timeout=timeout, network_access=self._network_allowed())
        self._audit(user_ctx, "command_exec", command, result)
        return result

    def run_python(self, user_ctx: UserContext, code: str, timeout: int = 30) -> SandboxResult:
        session_id = self._ensure_session(user_ctx)
        result = self.backend.run_python(session_id, code, timeout=timeout, network_access=self._network_allowed())
        self._audit(user_ctx, "python_exec", code, result)
        return result

    def read_file(self, user_ctx: UserContext, path: str) -> SandboxResult:
        safe_path = self._normalize_workspace_path(path)
        session_id = self._ensure_session(user_ctx)
        result = self.backend.read_file(session_id, safe_path)
        self._audit(user_ctx, "file_read", safe_path, result)
        return result

    def write_file(self, user_ctx: UserContext, path: str, content: str) -> SandboxResult:
        safe_path = self._normalize_workspace_path(path)
        session_id = self._ensure_session(user_ctx)
        result = self.backend.write_file(session_id, safe_path, content)
        self._audit(user_ctx, "file_write", safe_path, result)
        return result

    def list_files(self, user_ctx: UserContext, path: str = ".") -> SandboxResult:
        safe_path = self._normalize_workspace_path(path)
        session_id = self._ensure_session(user_ctx)
        result = self.backend.list_files(session_id, safe_path)
        self._audit(user_ctx, "list_files", safe_path, result)
        return result

    def close_session(self, user_ctx: UserContext) -> None:
        session_id = self._session_key(user_ctx)
        self.backend.close_session(session_id)
        self._sessions.pop(session_id, None)

    def cleanup_expired_sessions(self) -> int:
        now = time.time()
        expired = [
            sid for sid, state in self._sessions.items()
            if now - state.last_used_at >= self.session_ttl_seconds
        ]
        for sid in expired:
            self.backend.close_session(sid)
            self._sessions.pop(sid, None)
        return len(expired)

    def _ensure_session(self, user_ctx: UserContext) -> str:
        if not self.enabled:
            raise SandboxUnavailableError("Sandbox is disabled")

        health = self.backend.healthcheck()
        if health.get("status") != "ok":
            reason = health.get("reason") or health.get("status") or "unknown"
            if self.fail_closed:
                raise SandboxUnavailableError(f"Sandbox unavailable: {reason}")
            logger.warning("sandbox_unavailable_fail_open", reason=reason, backend=self.backend.name)

        session_id = self._session_key(user_ctx)
        if session_id not in self._sessions:
            self.backend.ensure_session(session_id, user_ctx.user_id, user_ctx.agent_id or "", self.session_ttl_seconds)
            self._sessions[session_id] = _SessionState(
                user_id=user_ctx.user_id,
                agent_id=user_ctx.agent_id or "",
                last_used_at=time.time(),
            )
        else:
            self._sessions[session_id].last_used_at = time.time()
        return session_id

    @staticmethod
    def _session_key(user_ctx: UserContext) -> str:
        user_id = user_ctx.user_id or "default"
        session_id = user_ctx.session_id or "default"
        agent_id = user_ctx.agent_id or "default"
        return f"{user_id}:{session_id}:{agent_id}"

    @staticmethod
    def _normalize_workspace_path(path: str) -> str:
        raw = (path or ".").replace("\\", "/").strip()
        if not raw:
            raw = "."
        if raw.startswith("/") or ntpath.isabs(path) or ":" in raw.split("/", 1)[0]:
            raise SandboxPathError(f"Absolute paths are not allowed in sandbox workspace: {path}")
        normalized = posixpath.normpath(raw)
        if normalized in ("..",) or normalized.startswith("../") or "/../" in f"/{normalized}/":
            raise SandboxPathError(f"Path escapes sandbox workspace: {path}")
        return "." if normalized == "" else normalized

    def _network_allowed(self) -> bool:
        return self.network_default == "allow"

    def _audit(self, user_ctx: UserContext, tool_name: str, summary: str, result: SandboxResult) -> None:
        logger.info(
            "sandbox_tool_call",
            user_id=user_ctx.user_id,
            session_id=user_ctx.session_id,
            agent_id=user_ctx.agent_id or "",
            tool=tool_name,
            backend=result.backend or self.backend.name,
            sandbox_session_id=result.session_id,
            exit_code=result.exit_code,
            timed_out=result.timed_out,
            duration_ms=result.duration_ms,
            summary=_redact(summary)[:200],
        )


def _redact(text: str) -> str:
    redacted = text or ""
    redacted = re.sub(r"Authorization:\s*\S+(?:\s+\S+)?", "Authorization: [REDACTED]", redacted, flags=re.IGNORECASE)
    redacted = re.sub(r"Bearer\s+[A-Za-z0-9._~+/=-]+", "Bearer [REDACTED]", redacted, flags=re.IGNORECASE)
    redacted = re.sub(
        r"\b(api[_-]?key|token|password)\b\s*[:=]\s*\S+",
        r"\1=[REDACTED]",
        redacted,
        flags=re.IGNORECASE,
    )
    return redacted
