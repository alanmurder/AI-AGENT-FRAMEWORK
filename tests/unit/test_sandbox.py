"""Unit tests for Docker Sandbox system — mock-based, no Docker dependency required."""

import pytest
import subprocess
import uuid
from unittest.mock import MagicMock, patch
from pathlib import Path

from harness.sandbox.runner import SandboxRunner
from harness.sandbox.image import SandboxImageManager
from harness.skill.types import SkillInfo, SkillCategory, SkillAccess
from harness.skill.manifest import parse_skill_md
from runtime.context_schema import UserContext, UserRole


def _make_tmp_dir() -> Path:
    path = Path("data") / "test_sandbox_tmp" / uuid.uuid4().hex
    path.mkdir(parents=True, exist_ok=False)
    return path


class TestSandboxRunner:
    def test_sandbox_unavailable_when_no_docker(self):
        # When docker SDK is not installed, _verify_docker catches ImportError
        # and sets _docker_available=False automatically
        runner = SandboxRunner.__new__(SandboxRunner)
        runner.image = "ai-agent-sandbox:latest"
        runner._docker_available = False
        runner._client = None
        assert not runner.is_available()

    def test_fallback_to_host_when_docker_unavailable(self):
        runner = SandboxRunner.__new__(SandboxRunner)
        runner.image = "ai-agent-sandbox:latest"
        runner._docker_available = False
        runner._client = None

        result = runner._run_on_host("echo hello", timeout=5)
        assert result["exit_code"] == 0
        assert "hello" in result["stdout"]

    def test_host_timeout(self):
        runner = SandboxRunner.__new__(SandboxRunner)
        runner.image = "ai-agent-sandbox:latest"
        runner._docker_available = False
        runner._client = None

        # subprocess.run(shell=True, timeout) doesn't reliably kill child process tree on Windows,
        # so mock TimeoutExpired instead of testing real subprocess timeout
        with patch("harness.sandbox.runner.subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="sleep 999", timeout=1)):
            result = runner._run_on_host("sleep 999", timeout=1)
            assert result["timed_out"]
            assert result["exit_code"] == -1

    def test_run_command_in_container(self):
        # Direct mock injection — no need for @patch("docker.from_env") since docker is optional
        mock_client = MagicMock()
        mock_container = MagicMock()
        mock_container.wait.return_value = {"StatusCode": 0}
        mock_container.logs.side_effect = [b"hello output", b""]
        mock_client.containers.run.return_value = mock_container

        runner = SandboxRunner.__new__(SandboxRunner)
        runner.image = "ai-agent-sandbox:latest"
        runner._docker_available = True
        runner._client = mock_client

        result = runner.run_command("echo hello", timeout=30, user_id="test_user")
        assert result["stdout"] == "hello output"
        assert result["exit_code"] == 0
        assert not result["timed_out"]

        mock_container.remove.assert_called_once_with(force=True)

    def test_timeout_kills_container(self):
        mock_client = MagicMock()
        mock_container = MagicMock()
        mock_container.wait.side_effect = Exception("timeout")
        mock_client.containers.run.return_value = mock_container

        runner = SandboxRunner.__new__(SandboxRunner)
        runner.image = "ai-agent-sandbox:latest"
        runner._docker_available = True
        runner._client = mock_client

        result = runner.run_command("sleep 999", timeout=5, user_id="test_user")
        assert result["timed_out"]
        mock_container.kill.assert_called_once()
        mock_container.remove.assert_called_once_with(force=True)

    def test_nonzero_exit_code(self):
        mock_client = MagicMock()
        mock_container = MagicMock()
        mock_container.wait.return_value = {"StatusCode": 1}
        mock_container.logs.side_effect = [b"", b"error output"]
        mock_client.containers.run.return_value = mock_container

        runner = SandboxRunner.__new__(SandboxRunner)
        runner.image = "ai-agent-sandbox:latest"
        runner._docker_available = True
        runner._client = mock_client

        result = runner.run_command("false", timeout=30)
        assert result["exit_code"] == 1
        assert result["stderr"] == "error output"


class TestSandboxImageManager:
    def test_ensure_image_no_docker(self):
        # docker package is not installed in dev environment — ensure_image returns False
        mgr = SandboxImageManager()
        result = mgr.ensure_image()
        assert result is False

    def test_ensure_image_with_mock_client(self):
        # Simulate docker package available, image exists
        mock_docker = MagicMock()
        mock_client = MagicMock()
        mock_docker.from_env.return_value = mock_client
        mock_docker.errors.ImageNotFound = Exception  # Use generic Exception for mock

        with patch.dict("sys.modules", {"docker": mock_docker}):
            mgr = SandboxImageManager()
            result = mgr.ensure_image()
            assert result is True

    def test_ensure_image_build_when_missing(self):
        # Simulate docker package available, image not found — triggers build
        mock_docker = MagicMock()
        mock_client = MagicMock()
        mock_docker.from_env.return_value = mock_client
        mock_docker.errors.ImageNotFound = type("ImageNotFound", (Exception,), {})

        # First call: image not found; second call: after build
        mock_client.images.get.side_effect = mock_docker.errors.ImageNotFound("not found")

        with patch.dict("sys.modules", {"docker": mock_docker}):
            mgr = SandboxImageManager()
            result = mgr.ensure_image()
            assert result is True
            mock_client.images.build.assert_called_once()


class FakeSandboxBackend:
    name = "fake"

    def __init__(self, available: bool = True):
        self.available = available
        self.ensure_calls = []
        self.shell_calls = []
        self.python_calls = []
        self.read_calls = []
        self.write_calls = []

    def healthcheck(self):
        return {"status": "ok" if self.available else "unavailable", "backend": self.name}

    def ensure_session(self, session_id, user_id, agent_id="", ttl_seconds=3600):
        self.ensure_calls.append((session_id, user_id, agent_id, ttl_seconds))
        return session_id

    def run_shell(self, session_id, command, timeout=30, network_access=False):
        from harness.sandbox.types import SandboxResult

        self.shell_calls.append((session_id, command, timeout, network_access))
        return SandboxResult(stdout="shell ok", backend=self.name, session_id=session_id)

    def run_python(self, session_id, code, timeout=30, network_access=False):
        from harness.sandbox.types import SandboxResult

        self.python_calls.append((session_id, code, timeout, network_access))
        return SandboxResult(stdout="python ok", backend=self.name, session_id=session_id)

    def read_file(self, session_id, path):
        from harness.sandbox.types import SandboxResult

        self.read_calls.append((session_id, path))
        return SandboxResult(stdout="file contents", backend=self.name, session_id=session_id)

    def write_file(self, session_id, path, content):
        from harness.sandbox.types import SandboxResult

        self.write_calls.append((session_id, path, content))
        return SandboxResult(stdout=f"wrote {len(content)} bytes", backend=self.name, session_id=session_id)

    def list_files(self, session_id, path="."):
        from harness.sandbox.types import SandboxResult

        return SandboxResult(stdout="[]", backend=self.name, session_id=session_id)

    def close_session(self, session_id):
        return None


class TestSandboxManager:
    def test_reuses_session_key_by_user_session_and_agent(self):
        from harness.sandbox.manager import SandboxManager

        backend = FakeSandboxBackend()
        manager = SandboxManager(backend=backend, enabled=True, fail_closed=True, session_ttl_seconds=900)
        ctx = UserContext(user_id="u1", role=UserRole.ADMIN, session_id="s1", agent_id="expert_a")

        first = manager.run_shell(ctx, "echo hello")
        second = manager.write_file(ctx, "notes.txt", "hello")

        assert first.session_id == second.session_id
        assert first.session_id == "u1:s1:expert_a"
        assert backend.ensure_calls == [
            ("u1:s1:expert_a", "u1", "expert_a", 900),
        ]

    @pytest.mark.parametrize("bad_path", ["../secret.txt", "a/../../secret.txt", "/etc/passwd", "C:\\Windows\\win.ini"])
    def test_rejects_paths_that_escape_workspace(self, bad_path):
        from harness.sandbox.manager import SandboxManager
        from harness.sandbox.types import SandboxPathError

        manager = SandboxManager(backend=FakeSandboxBackend(), enabled=True, fail_closed=True)
        ctx = UserContext(user_id="u1", role=UserRole.ADMIN, session_id="s1")

        with pytest.raises(SandboxPathError):
            manager.read_file(ctx, bad_path)

    def test_fail_closed_blocks_when_backend_unavailable(self):
        from harness.sandbox.manager import SandboxManager
        from harness.sandbox.types import SandboxUnavailableError

        manager = SandboxManager(backend=FakeSandboxBackend(available=False), enabled=True, fail_closed=True)
        ctx = UserContext(user_id="u1", role=UserRole.ADMIN, session_id="s1")

        with pytest.raises(SandboxUnavailableError):
            manager.run_shell(ctx, "echo should-not-run")


class TestLocalDockerBackend:
    def _backend_with_exec_code(self, exit_code: int):
        from harness.sandbox.backends import LocalDockerBackend
        from harness.sandbox.types import SandboxResult

        backend = object.__new__(LocalDockerBackend)
        backend.workspace_dir = "/home/sandbox/workspace"
        backend._exec = lambda session_id, command, timeout=30: SandboxResult(exit_code=exit_code)
        return backend

    def test_rejects_resolved_path_escape(self):
        from harness.sandbox.types import SandboxPathError

        backend = self._backend_with_exec_code(70)

        with pytest.raises(SandboxPathError):
            backend._assert_within_workspace("sid", "/etc/passwd")

    def test_allows_resolved_workspace_path(self):
        backend = self._backend_with_exec_code(0)

        backend._assert_within_workspace("sid", "/home/sandbox/workspace/notes.txt")


class TestSandboxMiddleware:
    def _request(self, name, args):
        request = MagicMock()
        request.tool_call = {"id": "tc1", "name": name, "args": args}
        request.runtime = MagicMock()
        request.runtime.context = UserContext(user_id="u1", role=UserRole.ADMIN, session_id="s1")
        return request

    def test_routes_file_read_to_sandbox(self):
        from harness.middleware.sandbox import SandboxMiddleware
        from harness.sandbox.manager import SandboxManager

        backend = FakeSandboxBackend()
        middleware = SandboxMiddleware(SandboxManager(backend=backend, enabled=True, fail_closed=True))
        handler = MagicMock()

        msg = middleware.wrap_tool_call(self._request("file_read", {"path": "notes.txt"}), handler)

        assert msg.content == "file contents"
        assert backend.read_calls == [("u1:s1:default", "notes.txt")]
        handler.assert_not_called()

    def test_routes_command_and_python_to_sandbox(self):
        from harness.middleware.sandbox import SandboxMiddleware
        from harness.sandbox.manager import SandboxManager

        backend = FakeSandboxBackend()
        middleware = SandboxMiddleware(SandboxManager(backend=backend, enabled=True, fail_closed=True))

        shell_msg = middleware.wrap_tool_call(self._request("command_exec", {"command": "echo hi"}), MagicMock())
        python_msg = middleware.wrap_tool_call(self._request("python_exec", {"code": "print('hi')"}), MagicMock())

        assert shell_msg.content == "[sandbox:fake] shell ok"
        assert python_msg.content == "[sandbox:fake] python ok"
        assert backend.shell_calls[0][1] == "echo hi"
        assert backend.python_calls[0][1] == "print('hi')"

    def test_fail_closed_returns_tool_error_without_calling_host_handler(self):
        from harness.middleware.sandbox import SandboxMiddleware
        from harness.sandbox.manager import SandboxManager

        middleware = SandboxMiddleware(SandboxManager(backend=FakeSandboxBackend(available=False), enabled=True, fail_closed=True))
        handler = MagicMock()

        msg = middleware.wrap_tool_call(self._request("command_exec", {"command": "echo unsafe"}), handler)

        assert "Sandbox unavailable" in msg.content
        handler.assert_not_called()


class TestSkillRuntimeFields:
    def test_skill_info_default_runtime(self):
        info = SkillInfo(
            name="test_skill", description="test",
            category=SkillCategory.FILE_MANAGER, access=SkillAccess.ALL, location="/test",
        )
        assert info.runtime == "host"
        assert info.timeout == 30
        assert not info.network_access
        assert info.max_memory == "256m"
        assert info.dependencies == []

    def test_skill_info_sandbox_runtime(self):
        info = SkillInfo(
            name="data_analysis", description="test",
            category=SkillCategory.DATA_ANALYSIS, access=SkillAccess.ALL, location="/test",
            runtime="sandbox",
            dependencies=["python3", "numpy"],
            timeout=60,
            network_access=False,
            max_memory="512m",
        )
        assert info.runtime == "sandbox"
        assert info.dependencies == ["python3", "numpy"]
        assert info.timeout == 60
        assert info.max_memory == "512m"

    def test_parse_skill_md_with_runtime(self):
        skill_dir = _make_tmp_dir() / "analysis_skill"
        skill_dir.mkdir()
        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text(
            "---\nname: analysis_skill\nversion: 1.0.0\ncategory: data_analysis\n"
            "access: all\nruntime: sandbox\ndependencies: python3,numpy,pandas\n"
            "timeout: 60\nnetwork: no\nmax_memory: 512m\n---\n"
            "# Analysis Skill\nRun Python data analysis.",
            encoding="utf-8",
        )

        result = parse_skill_md(skill_md)
        assert result is not None
        assert result.runtime == "sandbox"
        assert result.dependencies == ["python3", "numpy", "pandas"]
        assert result.timeout == 60
        assert result.max_memory == "512m"
        assert not result.network_access

    def test_parse_skill_md_runtime_yes_network(self):
        skill_dir = _make_tmp_dir() / "web_skill"
        skill_dir.mkdir()
        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text(
            "---\nname: web_skill\nruntime: sandbox\nnetwork: yes\n---\nWeb skill.",
            encoding="utf-8",
        )

        result = parse_skill_md(skill_md)
        assert result is not None
        assert result.network_access

    def test_parse_skill_md_without_runtime(self):
        skill_dir = _make_tmp_dir() / "basic_skill"
        skill_dir.mkdir()
        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text(
            "---\nname: basic_skill\nversion: 1.0.0\ncategory: file_manager\n---\nBasic skill.",
            encoding="utf-8",
        )

        result = parse_skill_md(skill_md)
        assert result is not None
        assert result.runtime == "host"
        assert result.timeout == 30
