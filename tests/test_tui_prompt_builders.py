"""Tests for langcode.tui.prompt_builders."""

from __future__ import annotations

from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.key_binding import KeyBindings

from langcode.tui.prompt_builders import (
    _build_prompt,
    _create_keybindings,
    _fmt_tokens,
)


class TestBuildPrompt:
    def test_act_mode_default(self):
        result = _build_prompt("act")
        assert isinstance(result, FormattedText)
        text = "".join(v for _, v in result)
        assert ">" in text

    def test_plan_mode(self):
        result = _build_prompt("plan")
        assert isinstance(result, FormattedText)
        text = "".join(v for _, v in result)
        assert "plan>" in text

    def test_default_is_act(self):
        act = _build_prompt()
        plan = _build_prompt("plan")
        act_text = "".join(v for _, v in act)
        plan_text = "".join(v for _, v in plan)
        assert act_text != plan_text


class TestFmtTokens:
    def test_small_number(self):
        assert _fmt_tokens(500) == "500"

    def test_thousands(self):
        assert _fmt_tokens(1500) == "1.5K"

    def test_millions(self):
        assert _fmt_tokens(2_500_000) == "2.5M"

    def test_exact_thousand(self):
        assert _fmt_tokens(1000) == "1.0K"

    def test_zero(self):
        assert _fmt_tokens(0) == "0"


class TestCreateKeybindings:
    def test_returns_keybindings_instance(self):
        mode_state = {"mode": "act"}
        kb = _create_keybindings(mode_state)
        assert isinstance(kb, KeyBindings)

    def test_keybindings_has_bindings(self):
        mode_state = {"mode": "act"}
        kb = _create_keybindings(mode_state)
        assert len(kb.bindings) > 0
