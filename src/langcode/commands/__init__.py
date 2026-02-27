"""Commands: slash command dispatch, custom command loading, and project scaffolding."""

from .custom import (
    CommandResult,
    expand_custom_command,
    load_custom_commands,
    read_command_description,
)
from .handler import CommandHandler
from .scaffold import COMMANDS, INIT_PROMPT, init_project

# Compat alias used by tests
_read_command_description = read_command_description

__all__ = [
    "COMMANDS",
    "INIT_PROMPT",
    "CommandHandler",
    "CommandResult",
    "expand_custom_command",
    "init_project",
    "load_custom_commands",
    "read_command_description",
]
