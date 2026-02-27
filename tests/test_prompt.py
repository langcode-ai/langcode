"""Tests for prompt: system prompt assembly."""

from langcode.agents.prompt import build_prompt
from langcode.core.config import Config


class TestBuildPrompt:
    def test_contains_role(self):
        config = Config()
        result = build_prompt(config)
        assert "LangCode" in result
        assert "coding agent" in result

    def test_contains_tool_guidelines(self):
        config = Config()
        result = build_prompt(config)
        assert "Read" in result
        assert "Edit" in result
        assert "Write" in result
        assert "Bash" in result
        assert "Glob" in result
        assert "Grep" in result
        assert "Task" in result
        assert "Ask" in result

    def test_contains_environment_info(self, tmp_path):
        config = Config(cwd=tmp_path)
        result = build_prompt(config)
        assert str(tmp_path) in result
        assert "OS:" in result

    def test_includes_skills_content(self):
        config = Config()
        result = build_prompt(config, skills_content="# My Project Rules\nUse strict types.")
        assert "Project Context" in result
        assert "My Project Rules" in result
        assert "Use strict types" in result

    def test_no_skills_no_project_context(self):
        config = Config()
        result = build_prompt(config, skills_content="")
        assert "Project Context" not in result

    def test_prompt_structure(self):
        """Verify prompt has proper sections."""
        config = Config()
        result = build_prompt(config, skills_content="test")
        assert "## Tool Usage Guidelines" in result
        assert "## Project Context" in result
        assert "## Environment" in result
