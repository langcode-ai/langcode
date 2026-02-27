"""Configuration: env, paths, model."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

from langcode.hooks import (
    HOOK_EVENTS,
    HooksConfig,
    convert_legacy_hooks,
    parse_hooks_config,
)

# Both directory names are recognised as project config dirs.
PROJECT_DIR_NAMES = (".langcode", ".claude")


@dataclass
class Config:
    api_key: str = ""
    model: str = "anthropic:claude-sonnet-4-5-20250929"
    max_tokens: int = 16384
    cwd: Path = field(default_factory=Path.cwd)
    global_dir: Path = field(default_factory=lambda: Path.home() / ".langcode")
    project_dir: Path | None = None  # explicit override; None = auto-detect from cwd
    verbose: bool = False
    hooks: HooksConfig = field(default_factory=HooksConfig)
    # plugin system
    enabled_plugins: dict[str, bool] = field(default_factory=dict)
    known_marketplaces: dict[str, dict] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if isinstance(self.hooks, dict):
            self.hooks = convert_legacy_hooks(self.hooks)

    def get_hook(self, event: str) -> str | None:
        """Look up a legacy-style hook by 'pre:tool' or 'post:tool' key."""
        if not isinstance(event, str) or ":" not in event:
            return None
        prefix, tool_name = event.split(":", 1)
        if prefix == "pre":
            rules = self.hooks.PreToolUse
        elif prefix == "post":
            rules = self.hooks.PostToolUse
        else:
            return None
        import re as _re

        for rule in rules:
            if _re.search(rule.matcher, tool_name, _re.IGNORECASE):
                for hook in rule.hooks:
                    cmd = hook.command
                    return "confirm" if cmd == "__confirm__" else cmd
        return None

    @property
    def project_dirs(self) -> list[Path]:
        if self.project_dir is not None:
            return [self.project_dir] if self.project_dir.is_dir() else []
        return [self.cwd / name for name in PROJECT_DIR_NAMES if (self.cwd / name).is_dir()]

    @property
    def primary_project_dir(self) -> Path:
        if self.project_dir is not None:
            return self.project_dir
        for name in PROJECT_DIR_NAMES:
            d = self.cwd / name
            if d.is_dir():
                return d
        return self.cwd / ".langcode"

    @property
    def plugin_cache_dir(self) -> Path:
        return self.global_dir / "plugins" / "cache"

    @property
    def marketplace_cache_dir(self) -> Path:
        return self.global_dir / "marketplaces"


def _apply_settings(config: Config, path: Path) -> None:
    """Apply a single settings.json file to config."""
    if not path.exists():
        return
    data = json.loads(path.read_text())
    if "model" in data:
        config.model = data["model"]

    if "enabledPlugins" in data and isinstance(data["enabledPlugins"], dict):
        config.enabled_plugins.update(data["enabledPlugins"])
    if "extraKnownMarketplaces" in data and isinstance(data["extraKnownMarketplaces"], dict):
        config.known_marketplaces.update(data["extraKnownMarketplaces"])

    has_event_keys = any(k in HOOK_EVENTS for k in data)
    has_legacy_hooks = "hooks" in data and isinstance(data.get("hooks"), dict)

    if has_event_keys:
        config.hooks.merge(parse_hooks_config(data))
    elif has_legacy_hooks:
        hooks_val = data["hooks"]
        if any(k in HOOK_EVENTS for k in hooks_val):
            config.hooks.merge(parse_hooks_config(hooks_val))
        else:
            config.hooks.merge(convert_legacy_hooks(hooks_val))


def load_config(
    model: str | None = None,
    verbose: bool = False,
) -> Config:
    """Load config with priority: CLI args > env > .env > settings.json > defaults."""
    load_dotenv()

    config = Config()
    config.verbose = verbose

    _apply_settings(config, config.global_dir / "settings.json")

    for pdir in config.project_dirs:
        _apply_settings(config, pdir / "settings.json")

    for pdir in config.project_dirs:
        _apply_settings(config, pdir / "settings.local.json")

    if api_key := os.getenv("ANTHROPIC_API_KEY"):
        config.api_key = api_key
    if env_model := os.getenv("LANGCODE_MODEL"):
        config.model = env_model

    if model:
        config.model = model

    return config
