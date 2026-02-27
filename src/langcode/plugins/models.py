"""Plugin data models: PluginManifest, PluginComponents, Plugin."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class PluginManifest:
    """Parsed from .claude-plugin/plugin.json."""

    name: str
    version: str = ""
    description: str = ""
    author: dict[str, str] = field(default_factory=dict)
    homepage: str = ""
    repository: str = ""
    license: str = ""
    keywords: list[str] = field(default_factory=list)
    commands: list[str] = field(default_factory=list)
    agents: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    hooks: str | dict | list = ""
    mcp_servers: str | dict | list = ""
    lsp_servers: str | dict | list = ""


@dataclass
class PluginComponents:
    """Resolved component paths/data from a loaded plugin."""

    command_dirs: list[Path] = field(default_factory=list)
    skill_dirs: list[Path] = field(default_factory=list)
    agent_dirs: list[Path] = field(default_factory=list)
    hooks_config: dict = field(default_factory=dict)
    mcp_servers: dict[str, dict] = field(default_factory=dict)


@dataclass
class Plugin:
    """A loaded plugin with all resolved components."""

    name: str
    root: Path
    manifest: PluginManifest
    components: PluginComponents = field(default_factory=PluginComponents)
    source: str = ""
    marketplace: str = ""
    enabled: bool = True
    error: str = ""


def expand_plugin_root(value: Any, plugin_root: str) -> Any:
    """Recursively substitute ${CLAUDE_PLUGIN_ROOT} in strings/dicts/lists."""
    if isinstance(value, str):
        return value.replace("${CLAUDE_PLUGIN_ROOT}", plugin_root)
    if isinstance(value, dict):
        return {k: expand_plugin_root(v, plugin_root) for k, v in value.items()}
    if isinstance(value, list):
        return [expand_plugin_root(v, plugin_root) for v in value]
    return value
