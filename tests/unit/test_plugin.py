"""Unit tests for PluginManager — mock-based filesystem tests."""

import pytest
import tempfile
from pathlib import Path

from harness.skill.plugin import PluginManager, PluginInfo
from harness.skill.manager import SkillManager
from runtime.config import AgentConfig


@pytest.fixture
def tmp_root():
    """Create a temporary directory structure for testing."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        # Create builtin skills
        builtin = root / "skills" / "builtin"
        builtin.mkdir(parents=True)

        # Create plugins directory
        plugins = root / "skills" / "plugins"
        plugins.mkdir(parents=True)

        # Create industrial plugin
        industrial = plugins / "industrial"
        industrial.mkdir()
        (industrial / "PLUGIN.md").write_text("""---
name: industrial
description: Industrial production skills
---

# Plugin: Industrial

Industrial production skills.

## Skills
  - equipment_monitor
  - process_control
""", encoding="utf-8")

        # Create enterprise plugin
        enterprise = plugins / "enterprise"
        enterprise.mkdir()
        (enterprise / "PLUGIN.md").write_text("""---
name: enterprise
description: Enterprise management skills
---

# Plugin: Enterprise

Enterprise management skills.

## Skills
  - hr_management
  - finance_report
""", encoding="utf-8")

        yield root


@pytest.fixture
def config(tmp_root):
    c = AgentConfig()
    c.project_root = str(tmp_root)
    return c


@pytest.fixture
def skill_manager(config):
    return SkillManager(config, project_root=Path(config.project_root))


@pytest.fixture
def plugin_manager(skill_manager):
    return PluginManager(skill_manager)


class TestPluginScan:
    """scan_plugins directory scanning."""

    def test_scan_finds_plugins(self, plugin_manager, tmp_root):
        plugins = plugin_manager.scan_plugins(tmp_root)
        assert len(plugins) == 2

    def test_scan_plugin_names(self, plugin_manager, tmp_root):
        plugins = plugin_manager.scan_plugins(tmp_root)
        names = [p.name for p in plugins]
        assert "industrial" in names
        assert "enterprise" in names

    def test_scan_empty_directory(self, plugin_manager):
        empty_root = Path(tempfile.mkdtemp())
        plugins = plugin_manager.scan_plugins(empty_root)
        assert len(plugins) == 0


class TestPluginManifest:
    """generate_plugin_manifest for prompt injection."""

    def test_manifest_generated_when_more_than_3_plugins(self, plugin_manager, tmp_root):
        # Add more plugins to exceed threshold
        extra = tmp_root / "skills" / "plugins" / "analytics"
        extra.mkdir()
        (extra / "PLUGIN.md").write_text("""---
name: analytics
description: Data analytics skills
---

# Plugin: Analytics

Data analytics skills.

## Skills
  - data_analysis
""", encoding="utf-8")

        fourth = tmp_root / "skills" / "plugins" / "monitoring"
        fourth.mkdir()
        (fourth / "PLUGIN.md").write_text("""---
name: monitoring
description: System monitoring skills
---

# Plugin: Monitoring

System monitoring skills.

## Skills
  - system_check
""", encoding="utf-8")

        manifest = plugin_manager.generate_plugin_manifest(tmp_root)
        assert "Available Plugins:" in manifest
        assert "industrial" in manifest

    def test_manifest_empty_when_less_than_3_plugins(self, plugin_manager, tmp_root):
        # Only 2 plugins exist, manifest should be empty
        manifest = plugin_manager.generate_plugin_manifest(tmp_root)
        assert manifest == ""


class TestPluginLoad:
    """load_plugin by name."""

    def test_load_existing_plugin(self, plugin_manager, tmp_root):
        plugin = plugin_manager.load_plugin("industrial", tmp_root)
        assert plugin is not None
        assert plugin.name == "industrial"
        assert "equipment_monitor" in plugin.skills

    def test_load_nonexistent_plugin(self, plugin_manager, tmp_root):
        plugin = plugin_manager.load_plugin("nonexistent", tmp_root)
        assert plugin is None


class TestPluginCreate:
    """create_plugin creates new plugin directory."""

    def test_create_plugin(self, plugin_manager, tmp_root):
        info = plugin_manager.create_plugin(
            name="new_plugin",
            description="A brand new plugin",
            skills=["skill_a", "skill_b"],
            root=tmp_root,
        )
        assert info.name == "new_plugin"
        assert info.skills == ["skill_a", "skill_b"]

        # Verify PLUGIN.md was written
        plugin_dir = tmp_root / "skills" / "plugins" / "new_plugin"
        assert plugin_dir.exists()
        assert (plugin_dir / "PLUGIN.md").exists()

    def test_created_plugin_scannable(self, plugin_manager, tmp_root):
        plugin_manager.create_plugin("test_plugin", "Test", ["t1"], tmp_root)
        plugins = plugin_manager.scan_plugins(tmp_root)
        names = [p.name for p in plugins]
        assert "test_plugin" in names


class TestPluginInfo:
    """PluginInfo Pydantic model."""

    def test_default_values(self):
        info = PluginInfo(name="test", description="test desc")
        assert info.skills == []
        assert info.location == ""

    def test_with_skills(self):
        info = PluginInfo(name="test", description="test desc", skills=["s1", "s2"])
        assert len(info.skills) == 2