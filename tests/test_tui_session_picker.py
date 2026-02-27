"""Tests for langcode.tui.session_picker."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from langcode.tui.session_picker import pick_session_tui


def _make_session(
    thread_id="abc123",
    last_query="fix the bug",
    cwd="/home/user/project",
    updated_at="2026-02-25 10:00:00",
):
    return {
        "thread_id": thread_id,
        "last_query": last_query,
        "updated_at": updated_at,
        "cwd": cwd,
    }


class TestPickSessionTuiNoSessions:
    def test_empty_sessions_returns_none(self):
        with patch("langcode.tui.session_picker.console") as mock_console:
            result = pick_session_tui([], "current-id")
        assert result is None
        mock_console.print.assert_called_once_with("no saved sessions", style="dim")


class TestPickSessionTuiGetText:
    """Test the _get_text() rendering closure without running the TUI app."""

    def _capture_get_text(self, sessions, current_thread_id):
        """Intercept the FormattedTextControl lambda before app.run() is called."""
        captured = {}

        class FakeApp:
            def __init__(self, layout, key_bindings, full_screen):
                # Extract the _get_text fn from the layout's window control
                window = layout.container.get_children()[0]
                captured["get_text"] = window.content.text

            def run(self):
                pass  # don't actually run the TUI

        with patch("langcode.tui.session_picker.Application", FakeApp):
            pick_session_tui(sessions, current_thread_id)

        return captured.get("get_text")

    def test_current_session_marked_with_asterisk(self):
        sessions = [_make_session("tid1", "first query"), _make_session("tid2", "second query")]
        get_text = self._capture_get_text(sessions, "tid1")
        if get_text is None:
            pytest.skip("could not capture get_text")
        lines = get_text()
        text = "".join(v for _, v in lines)
        assert " *" in text  # current session marker

    def test_non_current_session_no_asterisk(self):
        sessions = [_make_session("tid1", "only query")]
        get_text = self._capture_get_text(sessions, "different-id")
        if get_text is None:
            pytest.skip("could not capture get_text")
        lines = get_text()
        text = "".join(v for _, v in lines)
        assert " *" not in text

    def test_query_truncated_to_80_chars(self):
        long_query = "x" * 100
        sessions = [_make_session("tid1", long_query)]
        get_text = self._capture_get_text(sessions, "other")
        if get_text is None:
            pytest.skip("could not capture get_text")
        lines = get_text()
        text = "".join(v for _, v in lines)
        assert "x" * 81 not in text  # must be truncated

    def test_home_dir_shown_as_tilde(self):
        home = str(Path.home())
        sessions = [_make_session("tid1", "query", cwd=f"{home}/projects/myapp")]
        get_text = self._capture_get_text(sessions, "other")
        if get_text is None:
            pytest.skip("could not capture get_text")
        lines = get_text()
        text = "".join(v for _, v in lines)
        assert "~/projects/myapp" in text

    def test_invalid_cwd_shown_as_is(self):
        sessions = [_make_session("tid1", "query", cwd="/some/absolute/path")]
        get_text = self._capture_get_text(sessions, "other")
        if get_text is None:
            pytest.skip("could not capture get_text")
        lines = get_text()
        text = "".join(v for _, v in lines)
        assert "/some/absolute/path" in text

    def test_selected_item_has_arrow(self):
        sessions = [_make_session("tid1", "query")]
        get_text = self._capture_get_text(sessions, "other")
        if get_text is None:
            pytest.skip("could not capture get_text")
        lines = get_text()
        text = "".join(v for _, v in lines)
        assert ">" in text

    def test_navigation_hint_shown(self):
        sessions = [_make_session("tid1", "query")]
        get_text = self._capture_get_text(sessions, "other")
        if get_text is None:
            pytest.skip("could not capture get_text")
        lines = get_text()
        text = "".join(v for _, v in lines)
        assert "navigate" in text
        assert "select" in text
        assert "cancel" in text
