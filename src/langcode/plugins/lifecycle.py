"""Plugin lifecycle: install, uninstall, enable, disable, update."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langcode.core.config import Config

    from .models import Plugin


def _plugin_cache_dir(config: Config) -> Path:
    return config.global_dir / "plugins" / "cache"


def _settings_path_for_scope(config: Config, scope: str) -> Path:
    if scope == "user":
        return config.global_dir / "settings.json"
    elif scope == "local":
        for pdir in config.project_dirs:
            return pdir / "settings.local.json"
        return config.primary_project_dir / "settings.local.json"
    else:
        for pdir in config.project_dirs:
            return pdir / "settings.json"
        return config.primary_project_dir / "settings.json"


def _read_settings(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _write_settings(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


def _set_enabled_plugin(config: Config, name: str, value: bool | None, scope: str) -> None:
    path = _settings_path_for_scope(config, scope)
    data = _read_settings(path)
    enabled = data.get("enabledPlugins", {})
    if not isinstance(enabled, dict):
        enabled = {}
    if value is None:
        enabled.pop(name, None)
    else:
        enabled[name] = value
    data["enabledPlugins"] = enabled
    _write_settings(path, data)


def _is_plugin_enabled(config: Config, name: str, marketplace: str = "") -> bool:
    enabled_plugins = config.enabled_plugins
    key_full = f"{name}@{marketplace}" if marketplace else name
    if key_full in enabled_plugins:
        return enabled_plugins[key_full]
    if name in enabled_plugins:
        return enabled_plugins[name]
    return True


def install_plugin_from_path(
    config: Config,
    source_path: Path,
    scope: str = "user",
    marketplace: str = "",
) -> Plugin:
    from .loader import load_plugin

    source_path = source_path.resolve()
    plugin = load_plugin(source_path)
    if plugin.error:
        return plugin
    name = plugin.manifest.name
    cache_dir = _plugin_cache_dir(config)
    dest = cache_dir / name
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(source_path, dest, symlinks=True)
    meta_path = dest / ".claude-plugin" / "_install_meta.json"
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(
        json.dumps(
            {"source": str(source_path), "marketplace": marketplace, "scope": scope}, indent=2
        )
    )
    plugin_key = f"{name}@{marketplace}" if marketplace else name
    _set_enabled_plugin(config, plugin_key, True, scope)
    plugin = load_plugin(dest)
    plugin.source = str(source_path)
    plugin.marketplace = marketplace
    return plugin


def uninstall_plugin(config: Config, name: str, scope: str = "user") -> bool:
    cache_dir = _plugin_cache_dir(config)
    bare_name = name.split("@")[0]
    dest = cache_dir / bare_name
    if dest.exists():
        shutil.rmtree(dest)
    _set_enabled_plugin(config, name, None, scope)
    return True


def enable_plugin(config: Config, name: str, scope: str = "user") -> bool:
    _set_enabled_plugin(config, name, True, scope)
    return True


def disable_plugin(config: Config, name: str, scope: str = "user") -> bool:
    _set_enabled_plugin(config, name, False, scope)
    return True


def update_plugin(config: Config, name: str) -> Plugin | None:
    bare_name = name.split("@")[0]
    cache_dir = _plugin_cache_dir(config)
    meta_path = cache_dir / bare_name / ".claude-plugin" / "_install_meta.json"
    if not meta_path.exists():
        return None
    meta = json.loads(meta_path.read_text())
    source = meta.get("source", "")
    if not source or not Path(source).is_dir():
        return None
    return install_plugin_from_path(
        config,
        Path(source),
        scope=meta.get("scope", "user"),
        marketplace=meta.get("marketplace", ""),
    )
