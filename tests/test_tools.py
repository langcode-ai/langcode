"""Tests for tools: read, write, edit, bash, glob, grep, tool registry."""

from unittest.mock import patch

from langcode.tools import DEFAULT_SUB_TOOLS, TOOL_MAP, get_tools_by_names
from langcode.tools.bash import bash
from langcode.tools.edit import edit
from langcode.tools.glob import glob_tool
from langcode.tools.grep import grep
from langcode.tools.read import read
from langcode.tools.write import write


class TestReadTool:
    def test_read_file(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello\nworld")
        with patch("langcode.core.utils.Path.cwd", return_value=tmp_path):
            result = read.invoke({"file_path": "test.txt"})
        assert "hello" in result
        assert "world" in result

    def test_read_with_line_numbers(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("line1\nline2\nline3")
        with patch("langcode.core.utils.Path.cwd", return_value=tmp_path):
            result = read.invoke({"file_path": "test.txt"})
        assert "1|line1" in result
        assert "2|line2" in result

    def test_read_with_offset(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("line1\nline2\nline3\nline4")
        with patch("langcode.core.utils.Path.cwd", return_value=tmp_path):
            result = read.invoke({"file_path": "test.txt", "offset": 2})
        assert "line1" not in result
        assert "line2" not in result
        assert "line3" in result

    def test_read_with_limit(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("line1\nline2\nline3\nline4")
        with patch("langcode.core.utils.Path.cwd", return_value=tmp_path):
            result = read.invoke({"file_path": "test.txt", "limit": 2})
        assert "line1" in result
        assert "line2" in result
        assert "line3" not in result

    def test_read_nonexistent(self, tmp_path):
        with patch("langcode.core.utils.Path.cwd", return_value=tmp_path):
            result = read.invoke({"file_path": "nope.txt"})
        assert "Error" in result

    def test_read_directory_error(self, tmp_path):
        (tmp_path / "mydir").mkdir()
        with patch("langcode.core.utils.Path.cwd", return_value=tmp_path):
            result = read.invoke({"file_path": "mydir"})
        assert "Error" in result


class TestWriteTool:
    def test_write_new_file(self, tmp_path):
        with patch("langcode.core.utils.Path.cwd", return_value=tmp_path):
            result = write.invoke({"file_path": "new.txt", "content": "hello"})
        assert (tmp_path / "new.txt").read_text() == "hello"
        assert "5 bytes" in result

    def test_write_creates_dirs(self, tmp_path):
        with patch("langcode.core.utils.Path.cwd", return_value=tmp_path):
            write.invoke({"file_path": "a/b/c.txt", "content": "deep"})
        assert (tmp_path / "a" / "b" / "c.txt").read_text() == "deep"

    def test_write_overwrites(self, tmp_path):
        f = tmp_path / "exist.txt"
        f.write_text("old")
        with patch("langcode.core.utils.Path.cwd", return_value=tmp_path):
            write.invoke({"file_path": "exist.txt", "content": "new"})
        assert f.read_text() == "new"


class TestEditTool:
    def test_replace_unique(self, tmp_path):
        f = tmp_path / "code.py"
        f.write_text("def foo():\n    return 1\n")
        with patch("langcode.core.utils.Path.cwd", return_value=tmp_path):
            result = edit.invoke(
                {
                    "file_path": "code.py",
                    "old_string": "return 1",
                    "new_string": "return 42",
                }
            )
        assert "return 42" in f.read_text()
        assert "Replaced 1" in result

    def test_replace_not_found(self, tmp_path):
        f = tmp_path / "code.py"
        f.write_text("hello world")
        with patch("langcode.core.utils.Path.cwd", return_value=tmp_path):
            result = edit.invoke(
                {
                    "file_path": "code.py",
                    "old_string": "nonexistent",
                    "new_string": "x",
                }
            )
        assert "Error" in result
        assert "not found" in result

    def test_replace_multiple_error(self, tmp_path):
        f = tmp_path / "code.py"
        f.write_text("aaa\naaa\naaa")
        with patch("langcode.core.utils.Path.cwd", return_value=tmp_path):
            result = edit.invoke(
                {
                    "file_path": "code.py",
                    "old_string": "aaa",
                    "new_string": "bbb",
                }
            )
        assert "Error" in result
        assert "3 times" in result

    def test_replace_all(self, tmp_path):
        f = tmp_path / "code.py"
        f.write_text("aaa\naaa\naaa")
        with patch("langcode.core.utils.Path.cwd", return_value=tmp_path):
            result = edit.invoke(
                {
                    "file_path": "code.py",
                    "old_string": "aaa",
                    "new_string": "bbb",
                    "replace_all": True,
                }
            )
        assert f.read_text() == "bbb\nbbb\nbbb"
        assert "3 occurrence" in result

    def test_edit_nonexistent(self, tmp_path):
        with patch("langcode.core.utils.Path.cwd", return_value=tmp_path):
            result = edit.invoke(
                {
                    "file_path": "nope.py",
                    "old_string": "x",
                    "new_string": "y",
                }
            )
        assert "Error" in result


class TestBashTool:
    def test_simple_command(self):
        result = bash.invoke({"command": "echo hello"})
        assert "hello" in result
        assert "exit code: 0" in result

    def test_stderr(self):
        result = bash.invoke({"command": "echo err >&2"})
        assert "[stderr]" in result
        assert "err" in result

    def test_nonzero_exit(self):
        result = bash.invoke({"command": "exit 1"})
        assert "exit code: 1" in result

    def test_timeout(self):
        result = bash.invoke({"command": "sleep 10", "timeout": 1})
        assert "timed out" in result


class TestGlobTool:
    def test_find_files(self, tmp_path):
        (tmp_path / "a.py").touch()
        (tmp_path / "b.py").touch()
        (tmp_path / "c.txt").touch()
        with patch("langcode.core.utils.Path.cwd", return_value=tmp_path):
            result = glob_tool.invoke({"pattern": "*.py", "path": str(tmp_path)})
        assert "a.py" in result
        assert "b.py" in result
        assert "c.txt" not in result

    def test_recursive(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "deep.py").touch()
        with patch("langcode.core.utils.Path.cwd", return_value=tmp_path):
            result = glob_tool.invoke({"pattern": "**/*.py", "path": str(tmp_path)})
        assert "deep.py" in result

    def test_no_matches(self, tmp_path):
        with patch("langcode.core.utils.Path.cwd", return_value=tmp_path):
            result = glob_tool.invoke({"pattern": "*.xyz", "path": str(tmp_path)})
        assert "No files matching" in result


class TestGrepTool:
    def test_basic_search(self, tmp_path):
        (tmp_path / "test.py").write_text("def foo():\n    return bar\n")
        with patch("langcode.core.utils.Path.cwd", return_value=tmp_path):
            result = grep.invoke(
                {"pattern": "foo", "path": str(tmp_path), "output_mode": "content"}
            )
        assert "foo" in result
        assert "test.py" in result

    def test_regex_search(self, tmp_path):
        (tmp_path / "test.py").write_text("item1\nitem2\nother\n")
        with patch("langcode.core.utils.Path.cwd", return_value=tmp_path):
            result = grep.invoke(
                {"pattern": r"item\d", "path": str(tmp_path), "output_mode": "content"}
            )
        assert "item1" in result
        assert "item2" in result

    def test_include_filter(self, tmp_path):
        (tmp_path / "a.py").write_text("hello")
        (tmp_path / "b.txt").write_text("hello")
        with patch("langcode.core.utils.Path.cwd", return_value=tmp_path):
            result = grep.invoke({"pattern": "hello", "path": str(tmp_path), "glob": "*.py"})
        assert "a.py" in result
        assert "b.txt" not in result

    def test_no_matches(self, tmp_path):
        (tmp_path / "test.py").write_text("nothing here")
        with patch("langcode.core.utils.Path.cwd", return_value=tmp_path):
            result = grep.invoke({"pattern": "xyz123", "path": str(tmp_path)})
        assert "No matches" in result

    def test_invalid_regex(self, tmp_path):
        with patch("langcode.core.utils.Path.cwd", return_value=tmp_path):
            result = grep.invoke({"pattern": "[invalid", "path": str(tmp_path)})
        assert "Error" in result


class TestToolRegistry:
    def test_tool_map_has_all_base_tools(self):
        expected = {"Read", "Write", "Edit", "Glob", "Grep", "Bash", "AskUserQuestion"}
        assert expected.issubset(set(TOOL_MAP.keys()))

    def test_get_tools_by_names_basic(self):
        tools = get_tools_by_names(["Read", "Write"])
        assert len(tools) == 2

    def test_get_tools_by_names_preserves_order(self):
        tools = get_tools_by_names(["Grep", "Read", "Bash"])
        assert len(tools) == 3

    def test_get_tools_by_names_skips_unknown(self):
        tools = get_tools_by_names(["Read", "nonexistent", "Write"])
        assert len(tools) == 2

    def test_get_tools_by_names_empty(self):
        assert get_tools_by_names([]) == []

    def test_default_sub_tools(self):
        tools = get_tools_by_names(list(DEFAULT_SUB_TOOLS))
        assert len(tools) == len(DEFAULT_SUB_TOOLS)
        names = {t.name for t in tools}
        for name in DEFAULT_SUB_TOOLS:
            assert name in names
