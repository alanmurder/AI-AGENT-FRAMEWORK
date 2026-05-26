"""Shared test fixtures."""

import pytest
from pathlib import Path
from runtime.config import AgentConfig
from runtime.context_schema import UserContext, UserRole


@pytest.fixture
def config():
    return AgentConfig()


@pytest.fixture
def user_ctx_admin():
    return UserContext(
        user_id="admin_test", role=UserRole.ADMIN, tenant_id="default",
        permissions=[], memory_path="", session_id="test-session",
    )


@pytest.fixture
def user_ctx_viewer():
    return UserContext(
        user_id="viewer_test", role=UserRole.VIEWER, tenant_id="default",
        permissions=[], memory_path="", session_id="test-session",
    )


@pytest.fixture
def project_root():
    return Path(__file__).resolve().parents[1]
