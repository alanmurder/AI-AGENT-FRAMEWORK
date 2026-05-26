"""Five-level approval system (L0-L4).

L0 blacklist, L1 patterns, L2 safe commands, L3 LLM review, L4 HumanInTheLoop.
Config is loaded from config/settings.yaml (single source of truth) with hardcoded defaults as fallback.
"""

import re
import yaml
from pathlib import Path

import structlog
logger = structlog.get_logger()

from langchain_core.language_models import BaseChatModel

from harness.security.types import ApprovalLevel, ApprovalResult
from runtime.context_schema import UserContext, UserRole

# Hardcoded defaults — used when YAML config is unavailable
_DEFAULT_L0_BLACKLIST = [
    "rm -rf",
    "DROP TABLE",
    "DELETE FROM",
    "TRUNCATE",
    "sudo",
    "chmod 777",
    "passwd",
    "shadow",
    "eval(",
    "exec(",
    "__import__",
    "subprocess.call",
    "os.system",
]

_DEFAULT_L1_PATTERNS = [
    (r"\$\([^)]*\)", "command substitution $()"),
    (r"`[^`]*`", "backtick command substitution"),
    (r"\|\|", "OR pipe chain"),
    (r"&&", "AND command chain"),
    (r";\s*[a-zA-Z_]", "command separator"),
    (r">\s*/dev/", "redirect to /dev"),
    (r"wget\s+.*\s*-\s*O\s+/(?:etc|bin|usr)", "download to system directory"),
    (r"curl\s+.*\s*-\s*o\s+/(?:etc|bin|usr)", "download to system directory"),
]

_DEFAULT_L2_SAFE_COMMANDS = {
    "command_exec": [
        "ls", "cat", "head", "tail", "grep", "find", "wc", "sort", "uniq",
        "echo", "date", "pwd", "whoami", "df", "du", "ps", "top",
        "python", "python3", "pip", "node", "npm",
        "git", "docker ps",
        "jq", "awk", "sed",
    ],
    "query_database": [
        "SELECT",
    ],
}


def _load_approval_config(yaml_path: str = "config/settings.yaml") -> dict | None:
    """Load approval configuration from YAML. Returns None if file not found."""
    path = Path(yaml_path)
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _parse_l1_patterns(raw_patterns: list) -> list[tuple[str, str]]:
    """Convert YAML L1 pattern entries to (regex, description) tuples."""
    result = []
    for entry in raw_patterns:
        if isinstance(entry, dict):
            pattern = entry.get("pattern", "")
            description = entry.get("description", "")
            result.append((pattern, description))
        elif isinstance(entry, str):
            # Simple string pattern (no description)
            result.append((entry, ""))
    return result


L3_REVIEW_PROMPT = (
    "You are a security reviewer. Evaluate whether the following tool operation is safe to execute.\n"
    "Tool: {tool_name}\nContent: {content}\n\n"
    "Consider: Could this cause data loss, system damage, privilege escalation, or security breach?\n"
    "Respond with exactly one word: SAFE, UNSAFE, or UNCERTAIN.\n"
    "Then briefly explain your reasoning in one sentence."
)


class ApprovalChecker:
    """Runs L0-L4 approval chain for tool call content.

    L0-L1 always block on match. L2 can escalate to L3. L3 can approve, block,
    or escalate to L4. L4 always blocks pending human approval.
    """

    def __init__(self, yaml_path: str = "config/settings.yaml", mini_model: BaseChatModel | None = None):
        config = _load_approval_config(yaml_path)

        if config:
            approval_section = config.get("security", {}).get("approval", {})
            self.l0_blacklist = approval_section.get("l0_blacklist", _DEFAULT_L0_BLACKLIST)
            raw_l1 = approval_section.get("l1_patterns", [])
            self.l1_patterns = _parse_l1_patterns(raw_l1) if raw_l1 else _DEFAULT_L1_PATTERNS
            self.l2_safe_commands = approval_section.get("l2_safe_commands", _DEFAULT_L2_SAFE_COMMANDS)
        else:
            self.l0_blacklist = _DEFAULT_L0_BLACKLIST
            self.l1_patterns = _DEFAULT_L1_PATTERNS
            self.l2_safe_commands = _DEFAULT_L2_SAFE_COMMANDS

        self.mini_model = mini_model
        self._pending_approvals: dict[str, ApprovalResult] = {}

    def check(self, content: str, tool_name: str, user_ctx: UserContext | None) -> ApprovalResult:
        """Run full L0-L4 approval chain. Returns result at first block or final pass."""
        max_level = self._get_max_approval_level(user_ctx)

        # L0: String match — always blocks
        result = self._check_l0(content)
        if not result.approved:
            logger.warning("approval_blocked", level="L0", tool=tool_name, reason=result.reason,
                           user=getattr(user_ctx, "user_id", ""))
            return result

        # L1: Regex match — always blocks
        result = self._check_l1(content)
        if not result.approved:
            logger.warning("approval_blocked", level="L1", tool=tool_name, reason=result.reason,
                           user=getattr(user_ctx, "user_id", ""))
            return result

        # L2: Whitelist classification
        result = self._check_l2(content, tool_name, user_ctx)
        if result.approved:
            logger.debug("approval_passed", level="L2", tool=tool_name)
            return result

        # L2 blocked — check if user can escalate to L3
        if max_level == ApprovalLevel.L2:
            logger.warning("approval_blocked", level="L2", tool=tool_name, reason=result.reason,
                           user=getattr(user_ctx, "user_id", ""))
            return result

        # L3: LLM review (if mini_model available and user has L3 access)
        if self.mini_model and max_level == ApprovalLevel.L3:
            result = self._check_l3(content, tool_name)
            if result.approved:
                logger.info("approval_passed", level="L3", tool=tool_name, reason="LLM approved")
                return result
            if result.level == ApprovalLevel.L4:
                logger.info("approval_escalated", from_level="L3", to="L4", tool=tool_name, reason=result.reason)
                pass  # fall through to L4
            else:
                logger.warning("approval_blocked", level="L3", tool=tool_name, reason=result.reason,
                               user=getattr(user_ctx, "user_id", ""))
                return result

        # L4: Human-in-the-loop — always blocks pending human approval
        result = self._check_l4(content, tool_name)
        logger.info("approval_pending_l4", tool=tool_name, approval_id=result.details,
                    user=getattr(user_ctx, "user_id", ""))
        return result

    def approve_pending(self, approval_id: str) -> bool:
        """Approve a pending L4 request. Returns True if found and approved."""
        if approval_id in self._pending_approvals:
            self._pending_approvals[approval_id] = ApprovalResult(
                approved=True,
                level=ApprovalLevel.L4,
                reason="Approved by human reviewer",
            )
            return True
        return False

    def reject_pending(self, approval_id: str) -> bool:
        """Reject a pending L4 request. Returns True if found and rejected."""
        if approval_id in self._pending_approvals:
            self._pending_approvals[approval_id] = ApprovalResult(
                approved=False,
                level=ApprovalLevel.L4,
                reason="Rejected by human reviewer",
            )
            return True
        return False

    def list_pending(self) -> dict[str, ApprovalResult]:
        """List all pending L4 approvals."""
        return {k: v for k, v in self._pending_approvals.items() if not v.approved}

    def _get_max_approval_level(self, user_ctx: UserContext | None) -> ApprovalLevel:
        """Determine the maximum approval level for a user's role."""
        if user_ctx is None:
            return ApprovalLevel.L2  # Default: no user context → L2 max

        from harness.security.rbac import load_rbac_config, build_role_tool_access
        try:
            rbac_config = load_rbac_config()
            roles_section = rbac_config.get("rbac", {}).get("roles", {})
            role_data = roles_section.get(user_ctx.role.value, {})
            level_str = role_data.get("approval_level", "L2")
            return ApprovalLevel(level_str)
        except (FileNotFoundError, ValueError):
            return ApprovalLevel.L2

    def _check_l0(self, content: str) -> ApprovalResult:
        """Check for blacklist keywords."""
        for keyword in self.l0_blacklist:
            if keyword.lower() in content.lower():
                return ApprovalResult(
                    approved=False,
                    level=ApprovalLevel.L0,
                    reason=f"Blacklisted keyword detected: '{keyword}'",
                    details=f"Content contains prohibited keyword '{keyword}' which is blocked at L0 level.",
                )
        return ApprovalResult(approved=True, level=ApprovalLevel.L0)

    def _check_l1(self, content: str) -> ApprovalResult:
        """Check for dangerous patterns using regex."""
        for pattern, description in self.l1_patterns:
            if re.search(pattern, content):
                return ApprovalResult(
                    approved=False,
                    level=ApprovalLevel.L1,
                    reason=f"Dangerous pattern detected: {description}",
                    details=f"Content matches regex pattern '{pattern}' ({description}) which is blocked at L1 level.",
                )
        return ApprovalResult(approved=True, level=ApprovalLevel.L1)

    def _check_l2(self, content: str, tool_name: str, user_ctx: UserContext | None) -> ApprovalResult:
        """Check whitelist classification."""
        if tool_name == "command_exec":
            # Extract the base command
            cmd = content.strip().split()[0] if content.strip() else ""
            safe_cmds = self.l2_safe_commands.get("command_exec", [])
            if cmd not in safe_cmds:
                return ApprovalResult(
                    approved=False,
                    level=ApprovalLevel.L2,
                    reason=f"Command '{cmd}' not in safe whitelist",
                    details=f"Only safe commands are allowed: {', '.join(safe_cmds[:10])}... "
                            f"Command '{cmd}' requires higher approval level.",
                )

        elif tool_name == "query_database":
            # Only allow SELECT queries
            stripped = content.strip().upper()
            if not stripped.startswith("SELECT"):
                return ApprovalResult(
                    approved=False,
                    level=ApprovalLevel.L2,
                    reason="Only SELECT queries are allowed",
                    details="Non-SELECT SQL queries are blocked at L2 level. Only read-only database access is permitted.",
                )

        elif tool_name == "python_exec":
            return ApprovalResult(
                approved=False,
                level=ApprovalLevel.L2,
                reason="Python execution requires higher approval",
                details="Python code execution is always reviewed above L2 before sandbox execution.",
            )

        elif tool_name == "file_write":
            # Check path safety — block writing to system directories
            path = content.strip() if content.strip() else ""
            dangerous_paths = ["/etc/", "/bin/", "/usr/", "/root/", "/var/", "/sys/", "/proc/"]
            for dp in dangerous_paths:
                if dp in path:
                    return ApprovalResult(
                        approved=False,
                        level=ApprovalLevel.L2,
                        reason=f"Writing to system directory blocked: {dp}",
                        details=f"Writing to '{dp}' is blocked at L2 level for system safety.",
                    )

        return ApprovalResult(approved=True, level=ApprovalLevel.L2)

    def _check_l3(self, content: str, tool_name: str) -> ApprovalResult:
        """LLM-based security review. Uses mini_model to evaluate safety."""
        if not self.mini_model:
            return ApprovalResult(approved=False, level=ApprovalLevel.L3, reason="No LLM available for L3 review")

        prompt = L3_REVIEW_PROMPT.format(tool_name=tool_name, content=content[:2000])
        response = self.mini_model.invoke([{"role": "user", "content": prompt}])
        text = response.content.strip()

        # Parse verdict
        if text.startswith("SAFE"):
            return ApprovalResult(
                approved=True,
                level=ApprovalLevel.L3,
                reason=f"L3 approved: {text.split('\n', 1)[-1].strip() if '\n' in text else 'LLM deemed safe'}",
            )
        elif text.startswith("UNCERTAIN"):
            return ApprovalResult(
                approved=False,
                level=ApprovalLevel.L4,
                reason=f"L3 uncertain, needs human review: {text.split('\n', 1)[-1].strip() if '\n' in text else 'LLM uncertain'}",
            )
        else:  # UNSAFE or anything else
            return ApprovalResult(
                approved=False,
                level=ApprovalLevel.L3,
                reason=f"L3 blocked: {text.split('\n', 1)[-1].strip() if '\n' in text else 'LLM deemed unsafe'}",
            )

    def _check_l4(self, content: str, tool_name: str) -> ApprovalResult:
        """Human-in-the-loop: blocks operation pending human approval."""
        import uuid
        approval_id = f"L4-{uuid.uuid4().hex[:8]}"
        result = ApprovalResult(
            approved=False,
            level=ApprovalLevel.L4,
            reason=f"Requires human approval (ID: {approval_id})",
            details=f"Operation on '{tool_name}' with content '{content[:100]}...' "
                    f"requires human approval. Approval ID: {approval_id}. "
                    f"Use approve_pending('{approval_id}') to approve or reject_pending('{approval_id}') to reject.",
        )
        self._pending_approvals[approval_id] = result
        return result
