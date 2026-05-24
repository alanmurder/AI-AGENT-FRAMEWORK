"""MCPServerStore — JSON file persistence for MCP server configurations."""

import json
import structlog
from pathlib import Path

from harness.mcp.types import MCPServerConfig

logger = structlog.get_logger()


class MCPServerStore:
    """Load/save MCP server configs from data/mcp_servers.json."""

    def __init__(self, project_root: Path | None = None):
        if project_root is None:
            project_root = Path(__file__).parent.parent.parent
        self._store_path = project_root / "data" / "mcp_servers.json"
        self._store_path.parent.mkdir(parents=True, exist_ok=True)

    def list_servers(self) -> list[MCPServerConfig]:
        data = self._load()
        return [self._dict_to_config(v) for v in data.values()]

    def get_server(self, name: str) -> MCPServerConfig | None:
        data = self._load()
        if name in data:
            return self._dict_to_config(data[name])
        return None

    def save_server(self, config: MCPServerConfig) -> None:
        data = self._load()
        data[config.name] = {
            "name": config.name,
            "transport": config.transport,
            "command": config.command,
            "args": config.args,
            "url": config.url,
            "enabled": config.enabled,
            "env": config.env,
        }
        self._save(data)
        logger.info("mcp_server_saved", name=config.name)

    def delete_server(self, name: str) -> bool:
        data = self._load()
        if name not in data:
            return False
        del data[name]
        self._save(data)
        logger.info("mcp_server_deleted", name=name)
        return True

    def _load(self) -> dict:
        if self._store_path.exists():
            try:
                return json.loads(self._store_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    def _save(self, data: dict) -> None:
        self._store_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    @staticmethod
    def _dict_to_config(d: dict) -> MCPServerConfig:
        return MCPServerConfig(
            name=d.get("name", ""),
            transport=d.get("transport", "stdio"),
            command=d.get("command", ""),
            args=d.get("args", []),
            url=d.get("url", ""),
            enabled=d.get("enabled", True),
            env=d.get("env", {}),
        )
