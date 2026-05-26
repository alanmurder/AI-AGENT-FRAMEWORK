"""Unit tests for Skill and MCP configuration imports."""

import io
import json
import uuid
import zipfile
from pathlib import Path

import pytest


def _make_tmp_dir() -> Path:
    path = Path("data") / "test_import_tmp" / uuid.uuid4().hex
    path.mkdir(parents=True, exist_ok=False)
    return path


def _zip_bytes(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


def _skill_md(name: str = "quality_check") -> str:
    return f"""---
name: {name}
version: 1.0.0
category: data_analysis
access: production
---
# Quality Check
Run quality checks against uploaded data.
"""


def test_import_skill_zip_writes_valid_skill():
    from harness.skill.importer import import_skill_zip

    target = _make_tmp_dir() / "skills" / "extensions"
    result = import_skill_zip(
        _zip_bytes({"quality_check/SKILL.md": _skill_md(), "quality_check/examples/readme.md": "demo"}),
        target,
    )

    assert result.imported == ["quality_check"]
    assert (target / "quality_check" / "SKILL.md").exists()
    assert (target / "quality_check" / "examples" / "readme.md").read_text(encoding="utf-8") == "demo"


def test_import_skill_zip_rejects_path_traversal():
    from harness.skill.importer import SkillImportError, import_skill_zip

    target = _make_tmp_dir() / "skills" / "extensions"

    with pytest.raises(SkillImportError, match="unsafe zip path"):
        import_skill_zip(_zip_bytes({"../evil/SKILL.md": _skill_md("evil")}), target)


def test_import_skill_zip_rejects_windows_drive_segments():
    from harness.skill.importer import SkillImportError, import_skill_zip

    target = _make_tmp_dir() / "skills" / "extensions"

    with pytest.raises(SkillImportError, match="unsafe zip path"):
        import_skill_zip(_zip_bytes({"safe/C:/evil.txt": "nope", "safe/SKILL.md": _skill_md("safe")}), target)


def test_import_skill_zip_rejects_missing_skill_md():
    from harness.skill.importer import SkillImportError, import_skill_zip

    target = _make_tmp_dir() / "skills" / "extensions"

    with pytest.raises(SkillImportError, match="SKILL.md"):
        import_skill_zip(_zip_bytes({"notes/readme.md": "not a skill"}), target)


def test_parse_mcp_import_json_servers_list():
    from harness.mcp.importer import parse_mcp_server_configs

    payload = json.dumps({
        "servers": [
            {
                "name": "filesystem",
                "transport": "stdio",
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-filesystem"],
                "env": {"API_TOKEN": "${MCP_TOKEN}"},
            }
        ]
    }).encode("utf-8")

    configs = parse_mcp_server_configs(payload, "mcp.json")

    assert len(configs) == 1
    assert configs[0].name == "filesystem"
    assert configs[0].transport == "stdio"
    assert configs[0].args == ["-y", "@modelcontextprotocol/server-filesystem"]
    assert configs[0].env == {"API_TOKEN": "${MCP_TOKEN}"}


def test_parse_mcp_import_rejects_invalid_transport():
    from harness.mcp.importer import MCPImportError, parse_mcp_server_configs

    payload = b'{"servers":[{"name":"bad","transport":"websocket"}]}'

    with pytest.raises(MCPImportError, match="transport"):
        parse_mcp_server_configs(payload, "mcp.json")
