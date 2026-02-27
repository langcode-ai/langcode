"""Tests for utils: safe_path, format_lines, truncate, human_size."""

import pytest

from langcode.core.utils import format_lines, human_size, safe_path, truncate


class TestSafePath:
    def test_resolves_relative(self, tmp_path):
        (tmp_path / "foo.txt").touch()
        result = safe_path("foo.txt", cwd=tmp_path)
        assert result == (tmp_path / "foo.txt").resolve()

    def test_resolves_nested(self, tmp_path):
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "bar.txt").touch()
        result = safe_path("sub/bar.txt", cwd=tmp_path)
        assert result == (tmp_path / "sub" / "bar.txt").resolve()

    def test_blocks_traversal(self, tmp_path):
        with pytest.raises(ValueError, match="traversal"):
            safe_path("../../etc/passwd", cwd=tmp_path)

    def test_blocks_absolute_outside(self, tmp_path):
        with pytest.raises(ValueError, match="traversal"):
            safe_path("/etc/passwd", cwd=tmp_path)

    def test_allows_cwd_itself(self, tmp_path):
        result = safe_path(".", cwd=tmp_path)
        assert result == tmp_path.resolve()

    def test_dot_dot_within_cwd(self, tmp_path):
        """sub/../foo.txt should resolve to foo.txt within cwd."""
        (tmp_path / "sub").mkdir()
        (tmp_path / "foo.txt").touch()
        result = safe_path("sub/../foo.txt", cwd=tmp_path)
        assert result == (tmp_path / "foo.txt").resolve()


class TestFormatLines:
    def test_basic(self):
        result = format_lines("hello\nworld")
        assert result == "1|hello\n2|world"

    def test_offset(self):
        result = format_lines("a\nb\nc", offset=10)
        assert result.startswith("11|a")
        assert "12|b" in result
        assert "13|c" in result

    def test_single_line(self):
        result = format_lines("only")
        assert result == "1|only"

    def test_empty(self):
        result = format_lines("")
        assert result == "1|"

    def test_width_alignment(self):
        lines = "\n".join(str(i) for i in range(100))
        result = format_lines(lines)
        # line 1 should be padded to width 3
        assert result.startswith("  1|0")


class TestTruncate:
    def test_short_text_unchanged(self):
        assert truncate("hello") == "hello"

    def test_truncates_large_text(self):
        big = "x" * 200_000
        result = truncate(big, max_bytes=1000)
        assert len(result.encode()) < 2000
        assert "[truncated" in result

    def test_custom_max_bytes(self):
        text = "a" * 500
        result = truncate(text, max_bytes=100)
        assert "[truncated" in result

    def test_exact_boundary(self):
        text = "a" * 100
        result = truncate(text, max_bytes=100)
        assert result == text

    def test_multibyte_chars(self):
        text = "你好" * 100
        result = truncate(text, max_bytes=50)
        assert "[truncated" in result


class TestHumanSize:
    def test_bytes(self):
        assert human_size(0) == "0B"
        assert human_size(512) == "512B"

    def test_kb(self):
        result = human_size(1024)
        assert "KB" in result

    def test_mb(self):
        result = human_size(1024 * 1024)
        assert "MB" in result

    def test_gb(self):
        result = human_size(1024**3)
        assert "GB" in result
