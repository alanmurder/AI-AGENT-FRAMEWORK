"""Import MCP server configurations from uploaded JSON or YAML files."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import yaml

from harness.mcp.types import MCPServerConfig


class MCPImportError(ValueError):
    """Raised when an uploaded MCP configuration is invalid."""


@dataclass
class MCPImportResult:
    """Result returned after importing MCP server configurations."""

    imported: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


def parse_mcp_server_configs(content: bytes, filename: str = "mcp.yaml") -> list[MCPServerConfig]:
    """Parse JSON/YAML MCP config uploads into server configs."""
    raw = content.decode("utf-8")
    data = json.loads(raw) if filename.lower().endswith(".json") else yaml.safe_load(raw)
    if data is None:
        raise MCPImportError("MCP config is empty")

    entries = _extract_server_entries(data)
    if not entries:
        raise MCPImportError("MCP config must contain at least one server")
    return [_dict_to_config(entry) for entry in entries]


def _extract_server_entries(data) -> list[dict]:
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        raise MCPImportError("MCP config must be an object or list")
    if "servers" in data:
        servers = data["servers"]
        if isinstance(servers, list):
            return servers
        if isinstance(servers, dict):
            return [_with_default_name(name, value) for name, value in servers.items()]
        raise MCPImportError("servers must be a list or object")
    if "mcpServers" in data:
        servers = data["mcpServers"]
        if isinstance(servers, dict):
            return [_with_default_name(name, value) for name, value in servers.items()]
        raise MCPImportError("mcpServers must be an object")
    if "name" in data:
        return [data]
    return [_with_default_name(name, value) for name, value in data.items()]


def _with_default_name(name: str, value) -> dict:
    if not isinstance(value, dict):
        raise MCPImportError(f"MCP server '{name}' must be an object")
    merged = dict(value)
    merged.setdefault("name", name)
    return merged


def _dict_to_config(data: dict) -> MCPServerConfig:
    if not isinstance(data, dict):
        raise MCPImportError("MCP server entry must be an object")
    name = str(data.get("name", "")).strip()
    if not name:
        raise MCPImportError("MCP server name is required")
    if "/" in name or "\\" in name or ":" in name:
        raise MCPImportError(f"Invalid MCP server name: {name}")

    transport = str(data.get("transport", "stdio")).strip()
    if transport not in ("stdio", "sse"):
        raise MCPImportError("MCP server transport must be 'stdio' or 'sse'")

    args = data.get("args", [])
    if isinstance(args, str):
        args = [a for a in args.split() if a]
    if not isinstance(args, list):
        raise MCPImportError("MCP server args must be a list or string")

    env = data.get("env", {})
    if env is None:
        env = {}
    if not isinstance(env, dict):
        raise MCPImportError("MCP server env must be an object")

    command = str(data.get("command", "")).strip()
    url = str(data.get("url", "")).strip()
    if transport == "stdio" and not command:
        raise MCPImportError(f"MCP server '{name}' requires command for stdio transport")
    if transport == "sse" and not url:
        raise MCPImportError(f"MCP server '{name}' requires url for sse transport")

    return MCPServerConfig(
        name=name,
        transport=transport,
        command=command,
        args=[str(arg) for arg in args],
        url=url,
        enabled=bool(data.get("enabled", True)),
        env={str(k): str(v) for k, v in env.items()},
    )
