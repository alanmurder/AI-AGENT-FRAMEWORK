"""Sandbox base image management - build/pull the Docker image for command execution."""

import structlog
import os
import shutil
import uuid
from pathlib import Path

logger = structlog.get_logger()

SANDBOX_DOCKERFILE = """FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    bash curl jq git \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir numpy pandas

RUN useradd -m -s /bin/bash sandbox
USER sandbox
WORKDIR /home/sandbox
"""


class SandboxImageManager:
    """Builds or pulls the base sandbox Docker image."""

    def __init__(self, image_name: str = "ai-agent-sandbox:latest"):
        self.image_name = image_name

    def ensure_image(self) -> bool:
        """Ensure the sandbox image exists. Build if not found."""
        try:
            import docker
            client = docker.from_env()

            try:
                client.images.get(self.image_name)
                logger.info("sandbox_image_exists", image=self.image_name)
                return True
            except docker.errors.ImageNotFound:
                logger.info("sandbox_building_image", image=self.image_name)
                self._build_image(client)
                return True

        except ImportError:
            logger.warning("docker_package_not_installed")
            return False
        except Exception as e:
            logger.error("sandbox_image_error", error=str(e))
            return False

    def _build_image(self, client) -> None:
        """Build the sandbox image from the embedded Dockerfile."""
        tmp_root = Path.cwd() / "data" / "tmp"
        tmp_root.mkdir(parents=True, exist_ok=True)
        tmpdir = tmp_root / f"sandbox-build-{uuid.uuid4().hex[:8]}"
        tmpdir.mkdir(parents=True, exist_ok=False)
        try:
            dockerfile_path = os.path.join(str(tmpdir), "Dockerfile")
            with open(dockerfile_path, "w") as f:
                f.write(SANDBOX_DOCKERFILE)

            client.images.build(path=str(tmpdir), tag=self.image_name, rm=True)
            logger.info("sandbox_image_built", image=self.image_name)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)
