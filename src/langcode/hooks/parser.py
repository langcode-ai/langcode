"""Hook config parsing: parse_hook_def/rule/config, convert_legacy_hooks."""

from __future__ import annotations

import re

from .models import HOOK_EVENTS, HookDef, HookRule, HooksConfig


def parse_hook_def(raw: dict) -> HookDef:
    return HookDef(
        type=raw.get("type", "command"),
        command=raw.get("command", ""),
        prompt=raw.get("prompt", ""),
        timeout=raw.get("timeout", 30),
    )


def parse_hook_rule(raw: dict) -> HookRule:
    matcher = raw.get("matcher", "*")
    hooks = [parse_hook_def(h) for h in raw.get("hooks", [])]
    return HookRule(matcher=matcher, hooks=hooks)


def parse_hooks_config(data: dict) -> HooksConfig:
    """Parse a Claude Code-style hooks config dict."""
    if "hooks" in data and isinstance(data["hooks"], dict):
        inner = data["hooks"]
        if any(k in HOOK_EVENTS for k in inner):
            data = inner

    cfg = HooksConfig()
    for event in HOOK_EVENTS:
        if event in data and isinstance(data[event], list):
            rules = [parse_hook_rule(r) for r in data[event] if isinstance(r, dict)]
            setattr(cfg, event, rules)
    return cfg


def convert_legacy_hooks(legacy: dict[str, str]) -> HooksConfig:
    """Convert old-style {"pre:Write": "confirm"} dict to HooksConfig."""
    cfg = HooksConfig()
    for key, value in legacy.items():
        if ":" not in key:
            continue
        prefix, tool_name = key.split(":", 1)
        if prefix == "pre":
            hook_def = HookDef(
                type="command", command="__confirm__" if value == "confirm" else value
            )
            cfg.PreToolUse.append(HookRule(matcher=re.escape(tool_name), hooks=[hook_def]))
        elif prefix == "post":
            cfg.PostToolUse.append(
                HookRule(
                    matcher=re.escape(tool_name), hooks=[HookDef(type="command", command=value)]
                )
            )
    return cfg
