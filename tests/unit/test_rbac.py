"""Unit tests for RBAC system."""

from harness.security.rbac import get_role_tool_access
from runtime.context_schema import UserRole


def test_admin_has_all_tools():
    mapping = get_role_tool_access()
    admin_tools = mapping[UserRole.ADMIN]
    assert "file_read" in admin_tools
    assert "file_write" in admin_tools
    assert "command_exec" in admin_tools
    assert len(admin_tools) == 7


def test_viewer_has_readonly_tools():
    mapping = get_role_tool_access()
    viewer_tools = mapping[UserRole.VIEWER]
    assert "file_read" in viewer_tools
    assert "file_write" not in viewer_tools
    assert "command_exec" not in viewer_tools


def test_operator_no_command_exec():
    mapping = get_role_tool_access()
    operator_tools = mapping[UserRole.OPERATOR]
    assert "command_exec" not in operator_tools
    assert "file_read" in operator_tools


def test_manager_no_command_exec():
    mapping = get_role_tool_access()
    manager_tools = mapping[UserRole.MANAGER]
    assert "command_exec" not in manager_tools
    assert "file_write" in manager_tools