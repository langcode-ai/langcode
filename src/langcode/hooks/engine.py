"""Hook execution engine: execute_hooks, run_command_hook, HookResult."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from typing import Any

from .models import HookDef, HooksConfig


@dataclass
class HookResult:
    """Result of executing hooks for one event."""

    permission: str = "allow"  # "allow" | "deny" | "ask"
    updated_input: dict[str, Any] | None = None
    decision: str = "approve"  # "approve" | "block"
    reason: str = ""
    messages: list[str] = field(default_factory=list)


def run_command_hook(
    hook: HookDef, variables: dict[str, str] | None = None
) -> tuple[int, str, str]:
    """Execute a command hook. Returns (exit_code, stdout, stderr)."""
    cmd = hook.command
    if variables and "CLAUDE_PLUGIN_ROOT" in variables:
        cmd = cmd.replace("${CLAUDE_PLUGIN_ROOT}", variables["CLAUDE_PLUGIN_ROOT"])
    if variables:
        for k, v in variables.items():
            cmd = cmd.replace(f"${k}", v)
    try:
        result = subprocess.run(
            cmd, shell=True, timeout=hook.timeout, capture_output=True, text=True
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "hook timed out"
    except Exception as e:
        return -1, "", str(e)


def execute_hooks(
    config: HooksConfig,
    event: str,
    match_value: str = "",
    variables: dict[str, str] | None = None,
) -> HookResult:
    """Execute all matching hooks for an event. Returns combined result."""
    result = HookResult()
    for rule in config.get_rules(event):
        if not rule.matches(match_value):
            continue
        for hook in rule.hooks:
            if hook.type == "command":
                if hook.command == "__confirm__":
                    result.permission = "ask"
                    continue
                exit_code, stdout, stderr = run_command_hook(hook, variables)
                if stdout.strip():
                    result.messages.append(stdout.strip())
                if exit_code == 2 and stderr.strip():
                    result.messages.append(stderr.strip())
                _parse_hook_output(stdout.strip(), event, result)
            elif hook.type == "prompt" and hook.prompt:
                result.messages.append(hook.prompt)
    return result


def _parse_hook_output(stdout: str, event: str, result: HookResult) -> None:
    if not stdout or not stdout.startswith("{"):
        return
    try:
        import json

        data = json.loads(stdout)
    except (json.JSONDecodeError, ValueError):
        return

    hso = data.get("hookSpecificOutput", {})
    if hso:
        if "permissionDecision" in hso:
            result.permission = hso["permissionDecision"]
        if "updatedInput" in hso:
            result.updated_input = hso["updatedInput"]

    if "decision" in data:
        result.decision = data["decision"]
    if "reason" in data:
        result.reason = data["reason"]
    if msg := data.get("systemMessage"):
        result.messages.append(msg)
