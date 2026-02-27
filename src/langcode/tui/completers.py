"""Prompt-toolkit completers for slash commands and @file references."""

from __future__ import annotations

import time
from pathlib import Path

from prompt_toolkit.completion import Completer, Completion

from ..commands import COMMANDS
from .references import list_project_files


class _SlashCompleter(Completer):
    """Autocomplete slash commands (built-in + custom)."""

    def __init__(self, cmd_handler=None):
        self._handler = cmd_handler

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor.lstrip()
        if not text.startswith("/"):
            return
        for cmd, desc in COMMANDS.items():
            if cmd.startswith(text):
                yield Completion(cmd, start_position=-len(text), display_meta=desc)
        # custom commands from project dirs
        if self._handler:
            for cmd, path in self._handler.custom_commands.items():
                if cmd.startswith(text):
                    from ..commands import _read_command_description

                    desc = _read_command_description(path)
                    yield Completion(cmd, start_position=-len(text), display_meta=desc)


class _FileCompleter(Completer):
    """Autocomplete file/directory paths triggered by @."""

    _DEBOUNCE = 0.3

    def __init__(self, cwd: Path):
        self.cwd = cwd
        self._files: list[str] = []
        self._last_query_time: float = 0

    def _refresh(self):
        now = time.time()
        if now - self._last_query_time < self._DEBOUNCE:
            return
        self._last_query_time = now
        self._files = list_project_files(self.cwd)

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        at_pos = text.rfind("@")
        if at_pos < 0:
            return
        if at_pos > 0 and not text[at_pos - 1].isspace():
            return
        partial = text[at_pos + 1 :]
        if " " in partial:
            return

        self._refresh()

        partial_lower = partial.lower()
        seen_dirs: set[str] = set()
        count = 0

        # directories first
        for fp in self._files:
            parts = fp.split("/")
            for i in range(1, len(parts)):
                d = "/".join(parts[:i]) + "/"
                if d in seen_dirs:
                    continue
                seen_dirs.add(d)
                if partial_lower and partial_lower not in d.lower():
                    continue
                if count >= 50:
                    break
                count += 1
                yield Completion(d, start_position=-len(partial), display_meta="dir")

        # then files
        for fp in self._files:
            if count >= 50:
                break
            if partial_lower and partial_lower not in fp.lower():
                continue
            count += 1
            yield Completion(fp, start_position=-len(partial))
