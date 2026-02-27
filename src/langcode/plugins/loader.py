"""Plugin loader: load_plugin, validate_plugin, list_plugins, load_enabled_plugins."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from rich.console import Console

from .models import Plugin, PluginComponents, PluginManifest, expand_plugin_root

if TYPE_CHECKING:
    from langcode.core.config import Config

console = Console()


def _parse_manifest(path: Path) -> PluginManifest | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    name = data.get("name", "")
    if not name:
        return None

    def _to_list(val):
        if isinstance(val, str):
            return [val] if val else []
        return list(val) if isinstance(val, list) else []

    return PluginManifest(
        name=name,
        version=data.get("version", ""),
        description=data.get("description", ""),
        author=data.get("author", {}),
        homepage=data.get("homepage", ""),
        repository=data.get("repository", ""),
        license=data.get("license", ""),
        keywords=data.get("keywords", []),
        commands=_to_list(data.get("commands", "")),
        agents=_to_list(data.get("agents", "")),
        skills=_to_list(data.get("skills", "")),
        hooks=data.get("hooks", ""),
        mcp_servers=data.get("mcpServers", ""),
        lsp_servers=data.get("lspServers", ""),
    )


def _discover_components(plugin_root: Path, manifest: PluginManifest) -> PluginComponents:
    comp = PluginComponents()
    root_str = str(plugin_root)

    default_cmd = plugin_root / "commands"
    if default_cmd.is_dir():
        comp.command_dirs.append(default_cmd)
    for custom in manifest.commands:
        p = plugin_root / custom.lstrip("./")
        if p.is_dir() or (p.is_file() and p.suffix == ".md"):
            comp.command_dirs.append(p)

    default_skills = plugin_root / "skills"
    if default_skills.is_dir():
        comp.skill_dirs.append(default_skills)
    for custom in manifest.skills:
        p = plugin_root / custom.lstrip("./")
        if p.is_dir():
            comp.skill_dirs.append(p)

    default_agents = plugin_root / "agents"
    if default_agents.is_dir():
        comp.agent_dirs.append(default_agents)
    for custom in manifest.agents:
        p = plugin_root / custom.lstrip("./")
        if p.is_dir() or (p.is_file() and p.suffix == ".md"):
            comp.agent_dirs.append(p)

    hooks_data: dict = {}
    default_hooks_json = plugin_root / "hooks" / "hooks.json"
    if default_hooks_json.exists():
        try:
            hooks_data = json.loads(default_hooks_json.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    if isinstance(manifest.hooks, dict):
        hooks_data = _deep_merge(hooks_data, manifest.hooks)
    elif isinstance(manifest.hooks, str) and manifest.hooks:
        hook_path = plugin_root / manifest.hooks.lstrip("./")
        if hook_path.exists():
            try:
                hooks_data = _deep_merge(hooks_data, json.loads(hook_path.read_text()))
            except (json.JSONDecodeError, OSError):
                pass
    if hooks_data:
        comp.hooks_config = expand_plugin_root(hooks_data, root_str)

    mcp_data: dict[str, dict] = {}
    default_mcp = plugin_root / ".mcp.json"
    if default_mcp.exists():
        try:
            raw = json.loads(default_mcp.read_text())
            mcp_data = raw.get("mcpServers", raw.get("servers", {}))
        except (json.JSONDecodeError, OSError):
            pass
    if isinstance(manifest.mcp_servers, dict):
        mcp_data.update(manifest.mcp_servers)
    elif isinstance(manifest.mcp_servers, str) and manifest.mcp_servers:
        mcp_path = plugin_root / manifest.mcp_servers.lstrip("./")
        if mcp_path.exists():
            try:
                raw = json.loads(mcp_path.read_text())
                mcp_data.update(raw.get("mcpServers", raw.get("servers", {})))
            except (json.JSONDecodeError, OSError):
                pass
    if mcp_data:
        comp.mcp_servers = expand_plugin_root(mcp_data, root_str)

    return comp


def _deep_merge(base: dict, override: dict) -> dict:
    result = dict(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        elif k in result and isinstance(result[k], list) and isinstance(v, list):
            result[k] = result[k] + v
        else:
            result[k] = v
    return result


def load_plugin(plugin_root: Path, name_override: str = "") -> Plugin:
    """Load a plugin from a directory. Returns Plugin (may have .error set)."""
    if not plugin_root.is_dir():
        return Plugin(
            name=name_override or plugin_root.name,
            root=plugin_root,
            manifest=PluginManifest(name=name_override or plugin_root.name),
            error=f"plugin directory not found: {plugin_root}",
        )
    manifest_path = plugin_root / ".claude-plugin" / "plugin.json"
    manifest = _parse_manifest(manifest_path) or PluginManifest(
        name=name_override or plugin_root.name
    )
    if name_override:
        manifest.name = name_override
    try:
        components = _discover_components(plugin_root, manifest)
    except Exception as e:
        return Plugin(name=manifest.name, root=plugin_root, manifest=manifest, error=str(e))
    return Plugin(name=manifest.name, root=plugin_root, manifest=manifest, components=components)


def validate_plugin(path: Path) -> list[str]:
    errors: list[str] = []
    if not path.is_dir():
        errors.append(f"not a directory: {path}")
        return errors
    manifest_path = path / ".claude-plugin" / "plugin.json"
    if manifest_path.exists():
        try:
            data = json.loads(manifest_path.read_text())
        except json.JSONDecodeError as e:
            errors.append(f"invalid JSON in plugin.json: {e}")
            return errors
        if "name" not in data:
            errors.append("plugin.json: missing required field 'name'")
    cp_dir = path / ".claude-plugin"
    if cp_dir.is_dir():
        for bad_dir in ("commands", "agents", "skills", "hooks"):
            if (cp_dir / bad_dir).exists():
                errors.append(f"'{bad_dir}/' found inside .claude-plugin/; move it to plugin root")
    return errors


def list_plugins(config: Config) -> list[Plugin]:
    from .lifecycle import _is_plugin_enabled, _plugin_cache_dir

    plugins: list[Plugin] = []
    cache_dir = _plugin_cache_dir(config)
    if cache_dir.is_dir():
        for d in sorted(cache_dir.iterdir()):
            if d.is_dir():
                p = load_plugin(d)
                meta_path = d / ".claude-plugin" / "_install_meta.json"
                if meta_path.exists():
                    try:
                        meta = json.loads(meta_path.read_text())
                        p.source = meta.get("source", "")
                        p.marketplace = meta.get("marketplace", "")
                    except (json.JSONDecodeError, OSError):
                        pass
                p.enabled = _is_plugin_enabled(config, p.name, p.marketplace)
                plugins.append(p)
    return plugins


def load_enabled_plugins(config: Config, extra_dirs: list[Path] | None = None) -> list[Plugin]:
    """Load all enabled plugins from cache + extra dirs."""
    from .lifecycle import _is_plugin_enabled, _plugin_cache_dir

    plugins: list[Plugin] = []
    loaded_names: set[str] = set()

    for d in extra_dirs or []:
        p = load_plugin(d.resolve())
        if p.error:
            console.print(f"  [yellow]warning: plugin {d}: {p.error}[/yellow]")
        else:
            plugins.append(p)
            loaded_names.add(p.name)

    cache_dir = _plugin_cache_dir(config)
    if cache_dir.is_dir():
        for d in sorted(cache_dir.iterdir()):
            if not d.is_dir():
                continue
            p = load_plugin(d)
            if p.name in loaded_names:
                continue
            meta_path = d / ".claude-plugin" / "_install_meta.json"
            if meta_path.exists():
                try:
                    meta = json.loads(meta_path.read_text())
                    p.marketplace = meta.get("marketplace", "")
                    p.source = meta.get("source", "")
                except (json.JSONDecodeError, OSError):
                    pass
            if not _is_plugin_enabled(config, p.name, p.marketplace):
                continue
            if p.error:
                console.print(f"  [yellow]warning: plugin {p.name}: {p.error}[/yellow]")
            else:
                plugins.append(p)
                loaded_names.add(p.name)

    return plugins
