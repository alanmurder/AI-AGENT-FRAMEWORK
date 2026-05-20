"""Unit tests for Expert Agent system — AgentProfile and AgentRegistry."""

import pytest
import tempfile
from pathlib import Path

from harness.expert.types import AgentProfile
from harness.expert.registry import AgentRegistry
from runtime.context_schema import UserContext, UserRole
from gateway.router import GatewayRouter, SessionManager
from gateway.types import ChannelType, StandardMessage


class TestAgentProfile:
    def test_profile_from_dict(self):
        p = AgentProfile(
            name="equipment_monitor",
            display_name="设备巡检专家",
            description="设备故障诊断和维护建议",
            soul_file="agents/equipment_monitor/SOUL.md",
            skill_plugin="industrial",
            model_preference="primary",
            role="operator",
        )
        assert p.name == "equipment_monitor"
        assert p.skill_plugin == "industrial"
        assert p.role == "operator"

    def test_profile_defaults(self):
        p = AgentProfile(name="test", display_name="T", description="D", soul_file="s.md")
        assert p.model_preference == "primary"
        assert p.max_context_tokens == 32000
        assert p.skill_plugin == ""
        assert p.role == "operator"


class TestAgentRegistry:
    def _make_registry_with_yaml(self, tmp_dir):
        em = tmp_dir / "agents" / "equipment_monitor"
        em.mkdir(parents=True)
        (em / "profile.yaml").write_text("""name: equipment_monitor
display_name: 设备巡检专家
description: 设备故障诊断和维护建议
soul_file: agents/equipment_monitor/SOUL.md
skill_plugin: industrial
model_preference: primary
role: operator
""", encoding="utf-8")
        (em / "SOUL.md").write_text("---\nname: equipment_monitor\n---\n# 设备巡检专家\n你是设备巡检专家。", encoding="utf-8")

        qi = tmp_dir / "agents" / "quality_inspector"
        qi.mkdir(parents=True)
        (qi / "profile.yaml").write_text("""name: quality_inspector
display_name: 质量检验专家
description: 产品质量检测和异常分析
soul_file: agents/quality_inspector/SOUL.md
skill_plugin: industrial
role: operator
""", encoding="utf-8")
        (qi / "SOUL.md").write_text("---\nname: quality_inspector\n---\n# 质量检验专家\n你是质量检验专家。", encoding="utf-8")

        return tmp_dir

    def test_scan_profiles(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._make_registry_with_yaml(Path(tmp))
            registry = AgentRegistry()
            profiles = registry.scan_profiles(root / "agents")
            assert len(profiles) == 2
            names = [p.name for p in profiles]
            assert "equipment_monitor" in names
            assert "quality_inspector" in names

    def test_get_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._make_registry_with_yaml(Path(tmp))
            registry = AgentRegistry()
            registry.scan_profiles(root / "agents")
            profile = registry.get("equipment_monitor")
            assert profile is not None
            assert profile.display_name == "设备巡检专家"

    def test_get_nonexistent(self):
        registry = AgentRegistry()
        assert registry.get("nonexistent") is None

    def test_list_profiles(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._make_registry_with_yaml(Path(tmp))
            registry = AgentRegistry()
            registry.scan_profiles(root / "agents")
            profiles = registry.list_profiles()
            assert len(profiles) == 2

    def test_register_dynamic(self):
        registry = AgentRegistry()
        profile = AgentProfile(name="custom", display_name="Custom", description="Custom agent", soul_file="custom/SOUL.md")
        name = registry.register(profile)
        assert name == "custom"
        assert registry.get("custom") is not None

    def test_generate_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._make_registry_with_yaml(Path(tmp))
            registry = AgentRegistry()
            registry.scan_profiles(root / "agents")
            manifest = registry.generate_manifest()
            assert "equipment_monitor" in manifest
            assert "设备巡检专家" in manifest

    def test_load_soul_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._make_registry_with_yaml(Path(tmp))
            registry = AgentRegistry()
            registry.scan_profiles(root / "agents")
            soul = registry.load_soul_content("equipment_monitor", root)
            assert "设备巡检专家" in soul


class TestUserContextAgentId:
    def test_default_agent_id_empty(self):
        ctx = UserContext(user_id="u1", role=UserRole.ADMIN)
        assert ctx.agent_id == ""

    def test_agent_id_set(self):
        ctx = UserContext(user_id="u1", role=UserRole.ADMIN, agent_id="equipment_monitor")
        assert ctx.agent_id == "equipment_monitor"

    def test_memory_path_with_agent_id(self):
        ctx = UserContext(user_id="u1", role=UserRole.ADMIN, agent_id="equipment_monitor")
        path = ctx.get_memory_path("/workspace")
        assert "agents/equipment_monitor" in path

    def test_memory_path_without_agent_id(self):
        ctx = UserContext(user_id="u1", role=UserRole.ADMIN)
        path = ctx.get_memory_path("/workspace")
        assert "agents" not in path


class TestExpertRouting:
    def test_route_default_when_no_agent_id(self):
        registry = AgentRegistry()
        router = GatewayRouter(registry)
        msg = StandardMessage(user_id="u1", channel=ChannelType.WEB, content="hello")
        ctx = UserContext(user_id="u1", role=UserRole.ADMIN)
        result = router.route(msg, ctx)
        assert result == "default"

    def test_route_to_expert_when_agent_id_set(self):
        registry = AgentRegistry()
        registry.register(AgentProfile(name="equipment_monitor", display_name="E", description="D", soul_file="s.md"))
        router = GatewayRouter(registry)
        msg = StandardMessage(user_id="u1", channel=ChannelType.WEB, content="hello")
        ctx = UserContext(user_id="u1", role=UserRole.ADMIN, agent_id="equipment_monitor")
        result = router.route(msg, ctx)
        assert result == "equipment_monitor"

    def test_route_to_default_when_unknown_expert(self):
        registry = AgentRegistry()
        router = GatewayRouter(registry)
        msg = StandardMessage(user_id="u1", channel=ChannelType.WEB, content="hello")
        ctx = UserContext(user_id="u1", role=UserRole.ADMIN, agent_id="nonexistent")
        result = router.route(msg, ctx)
        assert result == "default"


class TestSessionManagerExpertKey:
    def test_session_key_with_expert(self):
        sm = SessionManager()
        key = sm.create_session_key(ChannelType.WEB, "u1", expert_id="equipment_monitor")
        assert key == "agent:equipment_monitor:user:u1"

    def test_session_key_without_expert(self):
        sm = SessionManager()
        key = sm.create_session_key(ChannelType.WEB, "u1")
        assert key == "agent:user:u1"