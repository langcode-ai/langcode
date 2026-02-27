"""Tests for langcode.tui.completers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from prompt_toolkit.document import Document

from langcode.tui.completers import _FileCompleter, _SlashCompleter


class TestSlashCompleter:
    def _completions(self, text, cmd_handler=None):
        completer = _SlashCompleter(cmd_handler)
        doc = Document(text, len(text))
        return list(completer.get_completions(doc, None))

    def test_slash_trigger_returns_builtin_commands(self):
        completions = self._completions("/")
        texts = [c.text for c in completions]
        assert any(t.startswith("/") for t in texts)

    def test_no_slash_returns_nothing(self):
        completions = self._completions("hello")
        assert completions == []

    def test_partial_slash_filters_commands(self):
        completions = self._completions("/hel")
        for c in completions:
            assert c.text.startswith("/hel")

    def test_custom_commands_included(self):
        cmd_handler = MagicMock()
        cmd_handler.custom_commands = {"/mycmd": Path("/fake/path")}
        with patch("langcode.commands._read_command_description", return_value="my desc"):
            completions = self._completions("/my", cmd_handler)
        texts = [c.text for c in completions]
        assert "/mycmd" in texts

    def test_no_custom_commands_without_handler(self):
        completions = self._completions("/")
        # Should still work — no crash
        assert isinstance(completions, list)


class TestFileCompleter:
    def _completions(self, text, files=None):
        completer = _FileCompleter(Path("/fake/cwd"))
        completer._files = files or ["src/main.py", "src/utils.py", "README.md"]
        completer._last_query_time = float("inf")  # skip refresh
        doc = Document(text, len(text))
        return list(completer.get_completions(doc, None))

    def test_at_trigger_returns_files(self):
        completions = self._completions("@")
        assert len(completions) > 0

    def test_no_at_returns_nothing(self):
        completions = self._completions("hello")
        assert completions == []

    def test_at_not_preceded_by_space_ignored(self):
        completions = self._completions("foo@bar")
        assert completions == []

    def test_partial_filter(self):
        completions = self._completions("@main")
        texts = [c.text for c in completions]
        assert all("main" in t.lower() for t in texts)

    def test_50_item_limit(self):
        files = [f"file{i}.py" for i in range(100)]
        completions = self._completions("@", files=files)
        assert len(completions) <= 50

    def test_dirs_listed_before_files(self):
        files = ["src/main.py", "src/utils.py", "README.md"]
        completions = self._completions("@src", files=files)
        types = [c.display_meta for c in completions]
        # First completion with display_meta="dir" should appear before plain files
        dir_indices = [i for i, m in enumerate(types) if m and "dir" in str(m)]
        file_indices = [i for i, m in enumerate(types) if not m or "dir" not in str(m)]
        if dir_indices and file_indices:
            assert min(dir_indices) < min(file_indices)
