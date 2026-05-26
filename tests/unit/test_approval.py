"""Unit tests for Security Approval system (L0-L4)."""

import pytest
from unittest.mock import MagicMock

from harness.security.approval import ApprovalChecker
from harness.security.types import ApprovalLevel
from runtime.context_schema import UserContext, UserRole


def test_l0_blacklist_rm_rf():
    checker = ApprovalChecker()
    result = checker.check("rm -rf /tmp", "command_exec", None)
    assert not result.approved
    assert result.level == ApprovalLevel.L0
    assert "rm -rf" in result.reason


def test_l0_blacklist_drop_table():
    checker = ApprovalChecker()
    result = checker.check("DROP TABLE users", "query_database", None)
    assert not result.approved
    assert result.level == ApprovalLevel.L0


def test_l0_blacklist_sudo():
    checker = ApprovalChecker()
    result = checker.check("sudo apt install", "command_exec", None)
    assert not result.approved
    assert "sudo" in result.reason


def test_l0_safe_content():
    checker = ApprovalChecker()
    result = checker.check("ls -la /home", "command_exec", None)
    assert result.approved


def test_l1_command_substitution():
    checker = ApprovalChecker()
    result = checker.check("echo $(whoami)", "command_exec", None)
    assert not result.approved
    assert result.level == ApprovalLevel.L1


def test_l1_backtick_substitution():
    checker = ApprovalChecker()
    result = checker.check("echo `whoami`", "command_exec", None)
    assert not result.approved
    assert result.level == ApprovalLevel.L1


def test_l1_or_pipe_chain():
    checker = ApprovalChecker()
    result = checker.check("ls || rm", "command_exec", None)
    assert not result.approved


def test_l2_unsafe_command():
    checker = ApprovalChecker()
    result = checker.check("hack_tool --attack", "command_exec", None)
    assert not result.approved
    assert result.level == ApprovalLevel.L2
    assert "hack_tool" in result.reason


def test_l2_safe_command_ls():
    checker = ApprovalChecker()
    result = checker.check("ls", "command_exec", None)
    assert result.approved


def test_l2_safe_command_git():
    checker = ApprovalChecker()
    result = checker.check("git status", "command_exec", None)
    assert result.approved


def test_l2_select_query():
    checker = ApprovalChecker()
    result = checker.check("SELECT * FROM users", "query_database", None)
    assert result.approved


def test_l2_file_write_system_path():
    checker = ApprovalChecker()
    # /etc/passwd contains "passwd" which is L0-blacklisted, so it gets blocked at L0
    result = checker.check("/etc/passwd", "file_write", None)
    assert not result.approved
    # Use a path that has /etc/ but no L0 keywords
    result2 = checker.check("/etc/config.json", "file_write", None)
    assert not result2.approved
    assert result2.level == ApprovalLevel.L2


def test_l2_file_write_safe_path():
    checker = ApprovalChecker()
    result = checker.check("/home/user/data.txt", "file_write", None)
    assert result.approved


def test_l2_python_exec_requires_higher_approval():
    checker = ApprovalChecker()
    result = checker.check("print('hello')", "python_exec", None)
    assert not result.approved
    assert result.level == ApprovalLevel.L2
    assert "Python execution" in result.reason


def test_security_middleware_checks_file_write_path():
    from harness.middleware.security_check import SecurityCheckMiddleware

    middleware = SecurityCheckMiddleware(ApprovalChecker())
    request = MagicMock()
    request.tool_call = {
        "id": "tc1",
        "name": "file_write",
        "args": {"path": "/etc/config.json", "content": "safe content"},
    }
    request.runtime = None
    handler = MagicMock()

    msg = middleware.wrap_tool_call(request, handler)

    assert "Operation blocked by security policy" in msg.content
    assert "Level: L2" in msg.content
    handler.assert_not_called()


# --- L3 Tests ---


class TestL3Approval:
    """L3: LLM-based security review."""

    def _make_mock_model(self, verdict: str):
        """Create a mock mini_model that returns the given verdict."""
        model = MagicMock()
        model.invoke.return_value = MagicMock(content=verdict)
        return model

    def test_l3_approves_safe_command(self):
        model = self._make_mock_model("SAFE\nThis is a standard diagnostic command.")
        checker = ApprovalChecker(mini_model=model)
        # "kubectl" is not in L2 whitelist, passes L0-L1, L3 approves
        user_ctx = UserContext(
            user_id="admin1", role=UserRole.ADMIN, tenant_id="default",
            permissions=[], memory_path="", session_id="s1",
        )
        result = checker.check("kubectl get pods", "command_exec", user_ctx)
        assert result.approved
        assert result.level == ApprovalLevel.L3

    def test_l3_blocks_unsafe_command(self):
        model = self._make_mock_model("UNSAFE\nThis could execute arbitrary code.")
        checker = ApprovalChecker(mini_model=model)
        # "ansible" is not in whitelist, L3 blocks it
        user_ctx = UserContext(
            user_id="admin1", role=UserRole.ADMIN, tenant_id="default",
            permissions=[], memory_path="", session_id="s1",
        )
        result = checker.check("ansible-playbook --dangerous-flag", "command_exec", user_ctx)
        assert not result.approved
        assert result.level == ApprovalLevel.L3

    def test_l3_uncertain_escalates_to_l4(self):
        model = self._make_mock_model("UNCERTAIN\nCannot determine safety without context.")
        checker = ApprovalChecker(mini_model=model)
        user_ctx = UserContext(
            user_id="admin1", role=UserRole.ADMIN, tenant_id="default",
            permissions=[], memory_path="", session_id="s1",
        )
        result = checker.check("ambiguous_command --flag", "command_exec", user_ctx)
        assert not result.approved
        assert result.level == ApprovalLevel.L4

    def test_l2_viewer_no_l3_escalation(self):
        """Viewer role (approval_level L2) cannot escalate beyond L2 block."""
        checker = ApprovalChecker(mini_model=self._make_mock_model("SAFE"))
        user_ctx = UserContext(
            user_id="viewer1", role=UserRole.VIEWER, tenant_id="default",
            permissions=[], memory_path="", session_id="s1",
        )
        result = checker.check("hack_tool --attack", "command_exec", user_ctx)
        # Viewer gets L2 block, no L3 escalation
        assert not result.approved
        assert result.level == ApprovalLevel.L2

    def test_l3_no_model_falls_to_l4(self):
        """Without mini_model, L3 can't review — escalates to L4 for admin."""
        checker = ApprovalChecker(mini_model=None)
        user_ctx = UserContext(
            user_id="admin1", role=UserRole.ADMIN, tenant_id="default",
            permissions=[], memory_path="", session_id="s1",
        )
        result = checker.check("unknown_tool --flag", "command_exec", user_ctx)
        # No mini_model → can't do L3 → falls to L4
        assert not result.approved
        assert result.level == ApprovalLevel.L4


# --- L4 Tests ---


class TestL4Approval:
    """L4: Human-in-the-loop approval."""

    def test_l4_blocks_with_approval_id(self):
        checker = ApprovalChecker()
        user_ctx = UserContext(
            user_id="admin1", role=UserRole.ADMIN, tenant_id="default",
            permissions=[], memory_path="", session_id="s1",
        )
        result = checker.check("dangerous_tool --flag", "command_exec", user_ctx)
        # L2 blocked, no mini_model → L4
        assert not result.approved
        assert result.level == ApprovalLevel.L4
        assert "Requires human approval" in result.reason

    def test_l4_approve_pending(self):
        checker = ApprovalChecker()
        user_ctx = UserContext(
            user_id="admin1", role=UserRole.ADMIN, tenant_id="default",
            permissions=[], memory_path="", session_id="s1",
        )
        result = checker.check("dangerous_tool --flag", "command_exec", user_ctx)
        # Extract approval_id from reason
        approval_id = result.reason.split("ID: ")[1].rstrip(")")

        success = checker.approve_pending(approval_id)
        assert success is True

        # Check the approval is now marked approved
        approval = checker._pending_approvals[approval_id]
        assert approval.approved

    def test_l4_reject_pending(self):
        checker = ApprovalChecker()
        user_ctx = UserContext(
            user_id="admin1", role=UserRole.ADMIN, tenant_id="default",
            permissions=[], memory_path="", session_id="s1",
        )
        result = checker.check("dangerous_tool --flag", "command_exec", user_ctx)
        approval_id = result.reason.split("ID: ")[1].rstrip(")")

        success = checker.reject_pending(approval_id)
        assert success is True

        approval = checker._pending_approvals[approval_id]
        assert not approval.approved

    def test_l4_list_pending(self):
        checker = ApprovalChecker()
        user_ctx = UserContext(
            user_id="admin1", role=UserRole.ADMIN, tenant_id="default",
            permissions=[], memory_path="", session_id="s1",
        )
        checker.check("tool_a", "command_exec", user_ctx)
        checker.check("tool_b", "command_exec", user_ctx)

        pending = checker.list_pending()
        assert len(pending) == 2

    def test_l4_approve_nonexistent(self):
        checker = ApprovalChecker()
        success = checker.approve_pending("L4-nonexistent")
        assert success is False

    def test_l4_reject_nonexistent(self):
        checker = ApprovalChecker()
        success = checker.reject_pending("L4-nonexistent")
        assert success is False
