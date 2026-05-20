"""Unit tests for Skill system."""

from pathlib import Path
from harness.skill.manager import SkillManager
from harness.skill.manifest import ManifestGenerator, parse_skill_md
from harness.skill.types import SkillManifest
from runtime.config import AgentConfig


def test_parse_skill_md(tmp_path):
    skill_dir = tmp_path / "test_skill"
    skill_dir.mkdir()
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text("""---
name: test_skill
version: 1.0.0
category: file_manager
access: all
description: A test skill
---
# Test Skill Instructions
Do something useful.""", encoding="utf-8")
    result = parse_skill_md(skill_md)
    assert result is not None
    assert result.name == "test_skill"
    assert result.category.value == "file_manager"


def test_manifest_generator():
    root = Path("D:/code/learn_project/claude_code_project/ai-agent-framework")
    gen = ManifestGenerator(
        builtin_dir=root / "skills" / "builtin",
        extension_dir=root / "skills" / "extensions",
    )
    manifest = gen.generate()
    assert len(manifest.skills) == 7
    names = [s.name for s in manifest.skills]
    assert "file_manager" in names
    assert "database_query" in names


def test_skill_manager(project_root):
    config = AgentConfig()
    sm = SkillManager(config, project_root=project_root)
    manifest = sm.get_manifest()
    assert len(manifest.skills) == 7
    assert manifest.to_text().startswith("Available Skills:")


def test_load_skill_content(project_root):
    config = AgentConfig()
    sm = SkillManager(config, project_root=project_root)
    content = sm.load_skill_content("file_manager")
    assert content is not None
    assert "file_manager" in content