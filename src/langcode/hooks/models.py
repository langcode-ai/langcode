"""Hook data models: HookDef, HookRule, HooksConfig, HOOK_EVENTS."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

HOOK_EVENTS = (
    "PreToolUse",
    "PostToolUse",
    "Stop",
    "SubagentStop",
    "SessionStart",
    "SessionEnd",
    "UserPromptSubmit",
    "PreCompact",
    "Notification",
)


@dataclass
class HookDef:
    """A single hook action — either a shell command or a prompt message."""

    type: str  # "command" or "prompt"
    command: str = ""
    prompt: str = ""
    timeout: int = 30


@dataclass
class HookRule:
    """A matcher + list of hooks that fire when the matcher matches."""

    matcher: str  # regex pattern, or "*" for match-all
    hooks: list[HookDef] = field(default_factory=list)

    _pattern: re.Pattern | None = field(default=None, init=False, repr=False)

    def matches(self, value: str) -> bool:
        if self.matcher == "*":
            return True
        if self._pattern is None:
            try:
                self._pattern = re.compile(self.matcher)
            except re.error:
                return self.matcher == value
        return self._pattern.search(value) is not None


@dataclass
class HooksConfig:
    """All hook rules grouped by event type."""

    PreToolUse: list[HookRule] = field(default_factory=list)
    PostToolUse: list[HookRule] = field(default_factory=list)
    Stop: list[HookRule] = field(default_factory=list)
    SubagentStop: list[HookRule] = field(default_factory=list)
    SessionStart: list[HookRule] = field(default_factory=list)
    SessionEnd: list[HookRule] = field(default_factory=list)
    UserPromptSubmit: list[HookRule] = field(default_factory=list)
    PreCompact: list[HookRule] = field(default_factory=list)
    Notification: list[HookRule] = field(default_factory=list)

    def get_rules(self, event: str) -> list[HookRule]:
        return getattr(self, event, [])

    def merge(self, other: HooksConfig) -> None:
        for event in HOOK_EVENTS:
            getattr(self, event).extend(getattr(other, event))

    def is_empty(self) -> bool:
        return all(len(getattr(self, e)) == 0 for e in HOOK_EVENTS)
