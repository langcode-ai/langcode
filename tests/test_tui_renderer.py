"""Tests for langcode.tui.renderer."""

from __future__ import annotations

from unittest.mock import MagicMock

from langcode.tui.renderer import _extract_usage, _format_tool_args


class TestExtractUsage:
    def test_dict_style(self):
        token = MagicMock()
        token.usage_metadata = {
            "input_tokens": 100,
            "output_tokens": 50,
            "input_token_details": {"cache_read": 20, "cache_creation": 5},
        }
        result = _extract_usage(token)
        assert result["input_tokens"] == 100
        assert result["output_tokens"] == 50
        assert result["cache_read"] == 20
        assert result["cache_creation"] == 5

    def test_object_style(self):
        usage = MagicMock()
        usage.input_tokens = 200
        usage.output_tokens = 75
        details = MagicMock()
        details.cache_read = 30
        details.cache_creation = 10
        usage.input_token_details = details

        token = MagicMock()
        token.usage_metadata = usage

        result = _extract_usage(token)
        assert result["input_tokens"] == 200
        assert result["output_tokens"] == 75
        assert result["cache_read"] == 30
        assert result["cache_creation"] == 10

    def test_missing_usage_returns_empty(self):
        token = MagicMock()
        token.usage_metadata = None
        result = _extract_usage(token)
        assert result == {}

    def test_dict_style_missing_details(self):
        token = MagicMock()
        token.usage_metadata = {
            "input_tokens": 10,
            "output_tokens": 5,
        }
        result = _extract_usage(token)
        assert result["cache_read"] == 0
        assert result["cache_creation"] == 0


class TestFormatToolArgs:
    def test_basic_formatting(self):
        result = _format_tool_args({"key": "value"})
        assert "key: value" in result

    def test_truncation_at_60_chars(self):
        long_val = "x" * 80
        result = _format_tool_args({"key": long_val})
        # Value should be truncated with "..."
        assert result.endswith("...")
        # After "key: ", the value part should be at most 60 chars
        val_part = result[len("key: ") :]
        assert len(val_part) <= 60

    def test_newlines_replaced(self):
        result = _format_tool_args({"key": "line1\nline2"})
        assert "\n" not in result
        assert "\\n" in result

    def test_multiple_args_joined(self):
        result = _format_tool_args({"a": "1", "b": "2"})
        assert "a: 1" in result
        assert "b: 2" in result
        assert ", " in result

    def test_empty_args(self):
        result = _format_tool_args({})
        assert result == ""
