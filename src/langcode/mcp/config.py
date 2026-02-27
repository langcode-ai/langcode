"""MCP config file helpers: read/write/list/add/remove servers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langcode.core.config import Config


def mcp_config_path(config: Config, scope: str = "project") -> Path:
    if scope == "user":
        return config.global_dir / "mcp.json"
    return config.cwd / ".mcp.json"


def read_mcp_file(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}
    return dict(data.get("mcpServers", data.get("servers", {})))


def write_mcp_file(path: Path, servers: dict[str, dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"mcpServers": servers}, indent=2) + "\n")


def mcp_list_servers(config: Config) -> dict[str, dict]:
    """List all configured MCP servers from all sources."""
    result: dict[str, dict] = {}

    user_path = config.global_dir / "mcp.json"
    for name, cfg in read_mcp_file(user_path).items():
        result[name] = {**cfg, "_source": str(user_path)}

    project_path = config.cwd / ".mcp.json"
    for name, cfg in read_mcp_file(project_path).items():
        result[name] = {**cfg, "_source": str(project_path)}

    for pdir in config.project_dirs:
        ppath = pdir / "mcp.json"
        for name, cfg in read_mcp_file(ppath).items():
            if name not in result:
                result[name] = {**cfg, "_source": str(ppath)}

    return result


def mcp_add_server(config: Config, name: str, server_config: dict, scope: str = "project") -> Path:
    path = mcp_config_path(config, scope)
    servers = read_mcp_file(path)
    servers[name] = server_config
    write_mcp_file(path, servers)
    return path


def mcp_remove_server(config: Config, name: str, scope: str = "project") -> bool:
    path = mcp_config_path(config, scope)
    servers = read_mcp_file(path)
    if name not in servers:
        return False
    del servers[name]
    write_mcp_file(path, servers)
    return True


def mcp_get_server(config: Config, name: str) -> dict | None:
    return mcp_list_servers(config).get(name)
