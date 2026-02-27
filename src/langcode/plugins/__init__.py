"""Plugins: plugin manifest, component discovery, lifecycle management."""

from .lifecycle import (
    disable_plugin,
    enable_plugin,
    install_plugin_from_path,
    uninstall_plugin,
    update_plugin,
)
from .loader import list_plugins, load_enabled_plugins, load_plugin, validate_plugin
from .models import Plugin, PluginComponents, PluginManifest, expand_plugin_root

__all__ = [
    "Plugin",
    "PluginComponents",
    "PluginManifest",
    "disable_plugin",
    "enable_plugin",
    "expand_plugin_root",
    "install_plugin_from_path",
    "list_plugins",
    "load_enabled_plugins",
    "load_plugin",
    "uninstall_plugin",
    "update_plugin",
    "validate_plugin",
]
