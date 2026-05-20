"""Docker sandbox runner — isolated command execution in containers."""

import subprocess
import structlog

logger = structlog.get_logger()


class SandboxRunner:
    """Manages Docker container lifecycle for sandboxed command execution.

    Creates a container → runs command → captures output → destroys container.
    Falls back to subprocess if Docker is unavailable.
    """

    def __init__(self, image: str = "ai-agent-sandbox:latest"):
        self.image = image
        self._client = None
        self._docker_available = False
        self._verify_docker()

    def _verify_docker(self) -> None:
        """Check if Docker is available and the base image exists."""
        try:
            import docker
            self._client = docker.from_env()
            try:
                self._client.images.get(self.image)
                self._docker_available = True
                logger.info("sandbox_docker_available", image=self.image)
            except docker.errors.ImageNotFound:
                logger.warning("sandbox_image_not_found", image=self.image)
                self._docker_available = False
        except ImportError:
            logger.warning("docker_package_not_installed")
            self._docker_available = False
        except Exception as e:
            logger.warning("docker_unavailable", error=str(e))
            self._docker_available = False

    def is_available(self) -> bool:
        """Check if sandbox execution is available."""
        return self._docker_available and self._client is not None

    def run_command(
        self,
        command: str,
        timeout: int = 30,
        network_access: bool = False,
        max_memory: str = "256m",
        user_id: str = "default",
    ) -> dict:
        """Execute a command in a Docker sandbox container.

        Returns {"stdout": str, "stderr": str, "exit_code": int, "timed_out": bool}.
        """
        if not self.is_available():
            return self._run_on_host(command, timeout)

        try:
            container = self._client.containers.run(
                self.image,
                command=command,
                detach=True,
                mem_limit=max_memory,
                network_disabled=not network_access,
                labels={"ai-agent-user": user_id, "ai-agent-type": "sandbox"},
                auto_remove=False,
            )

            try:
                result = container.wait(timeout=timeout)
                exit_code = result.get("StatusCode", -1)
            except Exception:
                container.kill()
                container.remove(force=True)
                return {"stdout": "", "stderr": f"Command timed out after {timeout}s", "exit_code": -1, "timed_out": True}

            stdout = container.logs(stdout=True, stderr=False) or ""
            stderr = container.logs(stdout=False, stderr=True) or ""

            container.remove(force=True)

            if isinstance(stdout, bytes):
                stdout = stdout.decode("utf-8", errors="replace")
            if isinstance(stderr, bytes):
                stderr = stderr.decode("utf-8", errors="replace")

            max_chars = 10000
            stdout = stdout[:max_chars]
            stderr = stderr[:max_chars]

            return {"stdout": stdout, "stderr": stderr, "exit_code": exit_code, "timed_out": False}

        except Exception as e:
            logger.error("sandbox_execution_error", error=str(e))
            return {"stdout": "", "stderr": f"Sandbox error: {e}", "exit_code": -1, "timed_out": False}

    def _run_on_host(self, command: str, timeout: int) -> dict:
        """Fallback: run command on host using subprocess."""
        try:
            result = subprocess.run(
                command, shell=True, capture_output=True, text=True, timeout=timeout,
            )
            return {"stdout": result.stdout, "stderr": result.stderr, "exit_code": result.returncode, "timed_out": False}
        except subprocess.TimeoutExpired:
            return {"stdout": "", "stderr": f"Command timed out after {timeout}s", "exit_code": -1, "timed_out": True}