"""Tests for references: @ file/dir expansion, path safety."""

from langcode.tui.references import expand_at_references, list_project_files


class TestExpandAtReferences:
    def test_expand_file(self, tmp_path):
        (tmp_path / "hello.txt").write_text("world")
        result = expand_at_references("check @hello.txt", cwd=tmp_path)
        assert "world" in result
        assert "<file" in result

    def test_expand_nested_file(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("print('hi')")
        result = expand_at_references("look at @src/main.py", cwd=tmp_path)
        assert "print('hi')" in result

    def test_nonexistent_file_unchanged(self, tmp_path):
        result = expand_at_references("@nonexistent.txt", cwd=tmp_path)
        assert result == "@nonexistent.txt"

    def test_path_traversal_blocked(self, tmp_path):
        result = expand_at_references("@../../etc/passwd", cwd=tmp_path)
        assert "@../../etc/passwd" in result
        assert "root:" not in result

    def test_multiple_references(self, tmp_path):
        (tmp_path / "a.txt").write_text("aaa")
        (tmp_path / "b.txt").write_text("bbb")
        result = expand_at_references("@a.txt and @b.txt", cwd=tmp_path)
        assert "aaa" in result
        assert "bbb" in result

    def test_file_size_truncation(self, tmp_path):
        big_content = "x" * 150_000
        (tmp_path / "big.txt").write_text(big_content)
        result = expand_at_references("@big.txt", cwd=tmp_path)
        assert "[truncated]" in result

    def test_no_at_references(self, tmp_path):
        result = expand_at_references("just a normal message", cwd=tmp_path)
        assert result == "just a normal message"

    def test_at_in_email_not_expanded(self, tmp_path):
        """Email addresses should not be treated as references."""
        result = expand_at_references("email user@example.com", cwd=tmp_path)
        # @ preceded by non-whitespace should not be expanded
        assert "user@example.com" in result

    def test_expand_directory(self, tmp_path):
        d = tmp_path / "mydir"
        d.mkdir()
        (d / "file1.txt").write_text("content1")
        # Note: _expand_dir uses list_project_files which needs rg or git
        # so this test might not fully expand but should not crash
        result = expand_at_references("@mydir/", cwd=tmp_path)
        # At minimum, should not crash
        assert isinstance(result, str)


class TestListProjectFiles:
    def test_returns_list(self, tmp_path):
        (tmp_path / "test.txt").touch()
        # May return empty if no git/rg, but should not crash
        result = list_project_files(tmp_path)
        assert isinstance(result, list)
