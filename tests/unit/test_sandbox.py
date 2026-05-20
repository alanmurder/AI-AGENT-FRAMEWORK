"""Unit tests for Docker Sandbox system — mock-based, no Docker dependency required."""

import pytest
import subprocess
from unittest.mock import MagicMock, patch
from pathlib import Path

from harness.sandbox.runner import SandboxRunner
from harness.sandbox.image import SandboxImageManager
from harness.skill.types import SkillInfo, SkillCategory, SkillAccess
from harness.skill.manifest import parse_skill_md


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

    def test_parse_skill_md_with_runtime(self, tmp_path):
        skill_dir = tmp_path / "analysis_skill"
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

    def test_parse_skill_md_runtime_yes_network(self, tmp_path):
        skill_dir = tmp_path / "web_skill"
        skill_dir.mkdir()
        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text(
            "---\nname: web_skill\nruntime: sandbox\nnetwork: yes\n---\nWeb skill.",
            encoding="utf-8",
        )

        result = parse_skill_md(skill_md)
        assert result is not None
        assert result.network_access

    def test_parse_skill_md_without_runtime(self, tmp_path):
        skill_dir = tmp_path / "basic_skill"
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