"""Pluggable sandbox backend implementations."""

from __future__ import annotations

import io
import posixpath
import shlex
import tarfile
import time
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout

import structlog

from harness.sandbox.image import SandboxImageManager
from harness.sandbox.types import SandboxPathError, SandboxResult

logger = structlog.get_logger()


class SandboxBackend(ABC):
    """Backend interface for command, Python, and file sandbox operations."""

    name = "base"

    @abstractmethod
    def healthcheck(self) -> dict:
        """Return backend health information."""

    @abstractmethod
    def ensure_session(self, session_id: str, user_id: str, agent_id: str = "", ttl_seconds: int = 3600) -> str:
        """Create or reuse a sandbox session."""

    @abstractmethod
    def run_shell(self, session_id: str, command: str, timeout: int = 30, network_access: bool = False) -> SandboxResult:
        """Run a shell command inside the sandbox session."""

    @abstractmethod
    def run_python(self, session_id: str, code: str, timeout: int = 30, network_access: bool = False) -> SandboxResult:
        """Run Python code inside the sandbox session."""

    @abstractmethod
    def read_file(self, session_id: str, path: str) -> SandboxResult:
        """Read a file from the sandbox workspace."""

    @abstractmethod
    def write_file(self, session_id: str, path: str, content: str) -> SandboxResult:
        """Write a file into the sandbox workspace."""

    @abstractmethod
    def list_files(self, session_id: str, path: str = ".") -> SandboxResult:
        """List files inside the sandbox workspace."""

    @abstractmethod
    def close_session(self, session_id: str) -> None:
        """Close and clean up a sandbox session."""


class DisabledSandboxBackend(SandboxBackend):
    """No-op backend used when sandbox support is intentionally disabled."""

    name = "disabled"

    def healthcheck(self) -> dict:
        return {"status": "disabled", "backend": self.name}

    def ensure_session(self, session_id: str, user_id: str, agent_id: str = "", ttl_seconds: int = 3600) -> str:
        return session_id

    def run_shell(self, session_id: str, command: str, timeout: int = 30, network_access: bool = False) -> SandboxResult:
        return SandboxResult(stderr="Sandbox is disabled", exit_code=-1, backend=self.name, session_id=session_id)

    def run_python(self, session_id: str, code: str, timeout: int = 30, network_access: bool = False) -> SandboxResult:
        return SandboxResult(stderr="Sandbox is disabled", exit_code=-1, backend=self.name, session_id=session_id)

    def read_file(self, session_id: str, path: str) -> SandboxResult:
        return SandboxResult(stderr="Sandbox is disabled", exit_code=-1, backend=self.name, session_id=session_id)

    def write_file(self, session_id: str, path: str, content: str) -> SandboxResult:
        return SandboxResult(stderr="Sandbox is disabled", exit_code=-1, backend=self.name, session_id=session_id)

    def list_files(self, session_id: str, path: str = ".") -> SandboxResult:
        return SandboxResult(stderr="Sandbox is disabled", exit_code=-1, backend=self.name, session_id=session_id)

    def close_session(self, session_id: str) -> None:
        return None


class AgentScopeRemoteBackend(SandboxBackend):
    """AgentScope Runtime remote sandbox backend.

    This backend uses the AgentScope Runtime Python client when installed. It is
    intentionally lazy so local development and tests do not require the package.
    """

    name = "agentscope_remote"

    def __init__(self, base_url: str, bearer_token: str = ""):
        self.base_url = base_url
        self.bearer_token = bearer_token
        self._sessions: dict[str, object] = {}
        self._import_error: str = ""

    def healthcheck(self) -> dict:
        if not self.base_url:
            return {"status": "unavailable", "backend": self.name, "reason": "missing base_url"}
        try:
            self._load_sandbox_class()
            return {"status": "ok", "backend": self.name, "base_url": self.base_url}
        except Exception as e:
            self._import_error = str(e)
            return {"status": "unavailable", "backend": self.name, "reason": str(e)}

    def ensure_session(self, session_id: str, user_id: str, agent_id: str = "", ttl_seconds: int = 3600) -> str:
        if session_id in self._sessions:
            return session_id

        sandbox_cls = self._load_sandbox_class()
        kwargs = {"base_url": self.base_url}
        if self.bearer_token:
            kwargs["bearer_token"] = self.bearer_token

        # AgentScope Runtime has evolved; try the richer remote signature first,
        # then fall back to the minimal client constructor.
        try:
            box = sandbox_cls(session_id=session_id, user_id=user_id, **kwargs)
        except TypeError:
            box = sandbox_cls(**kwargs)

        if hasattr(box, "__enter__"):
            box = box.__enter__()
        self._sessions[session_id] = box
        return session_id

    def run_shell(self, session_id: str, command: str, timeout: int = 30, network_access: bool = False) -> SandboxResult:
        start = time.perf_counter()
        box = self._get_box(session_id)
        output = self._call_box(box, ("run_shell_command", "run_shell"), command=command, timeout=timeout)
        return SandboxResult(stdout=str(output), backend=self.name, session_id=session_id, duration_ms=_elapsed_ms(start))

    def run_python(self, session_id: str, code: str, timeout: int = 30, network_access: bool = False) -> SandboxResult:
        start = time.perf_counter()
        box = self._get_box(session_id)
        output = self._call_box(box, ("run_ipython_cell", "run_python"), code=code, timeout=timeout)
        return SandboxResult(stdout=str(output), backend=self.name, session_id=session_id, duration_ms=_elapsed_ms(start))

    def read_file(self, session_id: str, path: str) -> SandboxResult:
        start = time.perf_counter()
        box = self._get_box(session_id)
        output = self._call_box(box, ("read_file", "read"), path=path)
        return SandboxResult(stdout=str(output), backend=self.name, session_id=session_id, duration_ms=_elapsed_ms(start))

    def write_file(self, session_id: str, path: str, content: str) -> SandboxResult:
        start = time.perf_counter()
        box = self._get_box(session_id)
        self._call_box(box, ("write_file", "write"), path=path, content=content)
        return SandboxResult(stdout=f"wrote {len(content)} bytes", backend=self.name, session_id=session_id, duration_ms=_elapsed_ms(start))

    def list_files(self, session_id: str, path: str = ".") -> SandboxResult:
        start = time.perf_counter()
        box = self._get_box(session_id)
        output = self._call_box(box, ("list_files", "ls"), path=path)
        return SandboxResult(stdout=str(output), backend=self.name, session_id=session_id, duration_ms=_elapsed_ms(start))

    def close_session(self, session_id: str) -> None:
        box = self._sessions.pop(session_id, None)
        if box and hasattr(box, "__exit__"):
            box.__exit__(None, None, None)

    def _load_sandbox_class(self):
        try:
            from agentscope_runtime.sandbox import BaseSandbox
            return BaseSandbox
        except Exception as e:
            raise RuntimeError("agentscope-runtime is not installed or unavailable") from e

    def _get_box(self, session_id: str):
        if session_id not in self._sessions:
            raise RuntimeError(f"Sandbox session not initialized: {session_id}")
        return self._sessions[session_id]

    @staticmethod
    def _call_box(box, method_names: tuple[str, ...], **kwargs):
        last_error = None
        for name in method_names:
            method = getattr(box, name, None)
            if not method:
                continue
            try:
                return method(**kwargs)
            except TypeError as e:
                last_error = e
                reduced = {k: v for k, v in kwargs.items() if k in ("command", "code", "path", "content")}
                try:
                    return method(**reduced)
                except TypeError as inner:
                    last_error = inner
        raise RuntimeError(f"AgentScope sandbox does not expose any of: {', '.join(method_names)}") from last_error


class LocalDockerBackend(SandboxBackend):
    """Local Docker backend with one reusable container per sandbox session."""

    name = "local_docker"

    def __init__(
        self,
        image: str = "ai-agent-sandbox:latest",
        auto_build_image: bool = False,
        network_default: str = "deny",
        max_memory: str = "256m",
    ):
        self.image = image
        self.auto_build_image = auto_build_image
        self.network_default = network_default
        self.max_memory = max_memory
        self.workspace_dir = "/home/sandbox/workspace"
        self._client = None
        self._sessions: dict[str, object] = {}
        self._available = False
        self._init_client()

    def healthcheck(self) -> dict:
        return {
            "status": "ok" if self._available else "unavailable",
            "backend": self.name,
            "image": self.image,
            "sessions": len(self._sessions),
        }

    def ensure_session(self, session_id: str, user_id: str, agent_id: str = "", ttl_seconds: int = 3600) -> str:
        if session_id in self._sessions:
            return session_id
        if not self._available or self._client is None:
            raise RuntimeError("Docker sandbox is unavailable")

        container = self._client.containers.run(
            self.image,
            command="sh -lc 'mkdir -p /home/sandbox/workspace && sleep infinity'",
            detach=True,
            mem_limit=self.max_memory,
            network_disabled=self.network_default != "allow",
            labels={
                "ai-agent-user": user_id,
                "ai-agent-session": session_id,
                "ai-agent-id": agent_id,
                "ai-agent-type": "sandbox",
            },
            auto_remove=False,
        )
        self._sessions[session_id] = container
        return session_id

    def run_shell(self, session_id: str, command: str, timeout: int = 30, network_access: bool = False) -> SandboxResult:
        return self._exec(session_id, ["sh", "-lc", command], timeout)

    def run_python(self, session_id: str, code: str, timeout: int = 30, network_access: bool = False) -> SandboxResult:
        return self._exec(session_id, ["python", "-c", code], timeout)

    def read_file(self, session_id: str, path: str) -> SandboxResult:
        target = self._workspace_path(path)
        self._assert_within_workspace(session_id, target)
        return self._exec(session_id, ["sh", "-lc", f"cat -- {shlex.quote(target)}"], timeout=30)

    def write_file(self, session_id: str, path: str, content: str) -> SandboxResult:
        start = time.perf_counter()
        container = self._container(session_id)
        target = self._workspace_path(path)
        self._assert_within_workspace(session_id, target)
        parent = posixpath.dirname(target)
        name = posixpath.basename(target)
        self._exec(session_id, ["sh", "-lc", f"mkdir -p -- {shlex.quote(parent)}"], timeout=30)

        data = io.BytesIO()
        with tarfile.open(fileobj=data, mode="w") as tar:
            payload = content.encode("utf-8")
            info = tarfile.TarInfo(name=name)
            info.size = len(payload)
            tar.addfile(info, io.BytesIO(payload))
        data.seek(0)
        container.put_archive(parent, data.read())
        return SandboxResult(stdout=f"wrote {len(content)} bytes", backend=self.name, session_id=session_id, duration_ms=_elapsed_ms(start))

    def list_files(self, session_id: str, path: str = ".") -> SandboxResult:
        target = self._workspace_path(path)
        self._assert_within_workspace(session_id, target)
        return self._exec(session_id, ["sh", "-lc", f"find {shlex.quote(target)} -maxdepth 2 -print"], timeout=30)

    def close_session(self, session_id: str) -> None:
        container = self._sessions.pop(session_id, None)
        if container:
            try:
                container.remove(force=True)
            except Exception:
                logger.warning("sandbox_container_remove_failed", session_id=session_id, exc_info=True)

    def _init_client(self) -> None:
        try:
            import docker
            self._client = docker.from_env()
            try:
                self._client.images.get(self.image)
            except docker.errors.ImageNotFound:
                if not self.auto_build_image:
                    self._available = False
                    return
                if not SandboxImageManager(self.image).ensure_image():
                    self._available = False
                    return
            self._available = True
        except Exception as e:
            logger.warning("local_docker_sandbox_unavailable", error=str(e))
            self._available = False

    def _container(self, session_id: str):
        if session_id not in self._sessions:
            raise RuntimeError(f"Sandbox session not initialized: {session_id}")
        return self._sessions[session_id]

    def _exec(self, session_id: str, command: list[str], timeout: int = 30) -> SandboxResult:
        start = time.perf_counter()
        container = self._container(session_id)

        def _run():
            return container.exec_run(command, workdir=self.workspace_dir, demux=True)

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(_run)
            try:
                exec_result = future.result(timeout=timeout)
            except FutureTimeout:
                try:
                    container.kill()
                except Exception:
                    pass
                return SandboxResult(stderr=f"Command timed out after {timeout}s", exit_code=-1, timed_out=True, backend=self.name, session_id=session_id, duration_ms=_elapsed_ms(start))

        exit_code = getattr(exec_result, "exit_code", 0)
        output = getattr(exec_result, "output", None)
        stdout, stderr = _split_exec_output(output)
        return SandboxResult(
            stdout=stdout[:10000],
            stderr=stderr[:10000],
            exit_code=exit_code,
            backend=self.name,
            session_id=session_id,
            duration_ms=_elapsed_ms(start),
        )

    def _workspace_path(self, path: str) -> str:
        if path in ("", "."):
            return self.workspace_dir
        return posixpath.join(self.workspace_dir, path)

    def _assert_within_workspace(self, session_id: str, target: str) -> None:
        script = (
            f"workspace={shlex.quote(self.workspace_dir)}; "
            f"target=$(realpath -m -- {shlex.quote(target)}) && "
            "case \"$target\" in \"$workspace\"|\"$workspace\"/*) exit 0 ;; *) exit 70 ;; esac"
        )
        result = self._exec(session_id, ["sh", "-lc", script], timeout=30)
        if result.exit_code != 0:
            raise SandboxPathError(f"Path escapes sandbox workspace after resolving links: {target}")


def _split_exec_output(output) -> tuple[str, str]:
    if isinstance(output, tuple):
        stdout, stderr = output
    else:
        stdout, stderr = output, b""
    if isinstance(stdout, bytes):
        stdout = stdout.decode("utf-8", errors="replace")
    if isinstance(stderr, bytes):
        stderr = stderr.decode("utf-8", errors="replace")
    return stdout or "", stderr or ""


def _elapsed_ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 2)
