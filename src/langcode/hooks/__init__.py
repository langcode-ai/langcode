"""Hooks: Claude Code-compatible hook system."""

from .engine import HookResult, execute_hooks, run_command_hook
from .models import HOOK_EVENTS, HookDef, HookRule, HooksConfig
from .parser import convert_legacy_hooks, parse_hook_def, parse_hook_rule, parse_hooks_config

__all__ = [
    "HOOK_EVENTS",
    "HookDef",
    "HookRule",
    "HooksConfig",
    "HookResult",
    "convert_legacy_hooks",
    "execute_hooks",
    "parse_hook_def",
    "parse_hook_rule",
    "parse_hooks_config",
    "run_command_hook",
]
