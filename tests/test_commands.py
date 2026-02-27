"""Tests for commands: built-in + custom commands from commands/*.md."""

import json

import pytest

from langcode.commands import (
    COMMANDS,
    CommandHandler,
    CommandResult,
    expand_custom_command,
    init_project,
    load_custom_commands,
)
from langcode.core.config import Config


@pytest.fixture
def handler():
    config = Config()
    h = CommandHandler(config)
    h.messages = [{"role": "user", "content": "hello"}]
    return h


class TestIsCommand:
    def test_slash_is_command(self, handler):
        assert handler.is_command("/help") is True

    def test_with_spaces(self, handler):
        assert handler.is_command("  /help") is True

    def test_not_command(self, handler):
        assert handler.is_command("hello") is False

    def test_empty(self, handler):
        assert handler.is_command("") is False


class TestHandleHelp:
    def test_shows_all_commands(self, handler):
        result = handler.handle("/help")
        for cmd in COMMANDS:
            assert cmd in result


class TestHandleQuit:
    def test_returns_quit(self, handler):
        assert handler.handle("/quit") == "quit"


class TestHandleClear:
    def test_clears_messages(self, handler):
        assert len(handler.messages) > 0
        result = handler.handle("/clear")
        assert len(handler.messages) == 0
        assert "clear" in result.lower()


class TestHandleModel:
    def test_show_current(self, handler):
        result = handler.handle("/model")
        assert handler.config.model in result

    def test_switch_model(self, handler):
        result = handler.handle("/model claude-opus")
        assert handler.config.model == "claude-opus"
        assert "claude-opus" in result


class TestHandleCost:
    def test_zero_usage(self, handler):
        result = handler.handle("/cost")
        assert "0" in result

    def test_with_usage(self, handler):
        handler.total_input_tokens = 1000
        handler.total_output_tokens = 500
        result = handler.handle("/cost")
        assert "1,000" in result
        assert "500" in result

    def test_with_cache(self, handler):
        handler.total_cache_read = 100
        handler.total_cache_creation = 50
        result = handler.handle("/cost")
        assert "cached" in result


class TestHandleUnknown:
    def test_unknown_command(self, handler):
        result = handler.handle("/foobar")
        assert "unknown" in result.lower()

    def test_not_a_command(self, handler):
        result = handler.handle("hello world")
        assert result is None


# ---------------------------------------------------------------------------
# /init command
# ---------------------------------------------------------------------------
class TestInitProject:
    def test_creates_project_dir(self, tmp_path):
        created = init_project(tmp_path)
        assert (tmp_path / ".langcode").is_dir()
        assert len(created) > 0

    def test_creates_settings_json(self, tmp_path):
        init_project(tmp_path)
        settings = tmp_path / ".langcode" / "settings.json"
        assert settings.exists()
        data = json.loads(settings.read_text())
        assert "model" in data

    def test_creates_gitignore(self, tmp_path):
        init_project(tmp_path)
        gi = tmp_path / ".langcode" / ".gitignore"
        assert gi.exists()
        assert "settings.local.json" in gi.read_text()

    def test_creates_skills_dir(self, tmp_path):
        init_project(tmp_path)
        assert (tmp_path / ".langcode" / "skills").is_dir()

    def test_idempotent(self, tmp_path):
        """Running init twice should not overwrite existing files."""
        init_project(tmp_path)

        settings = tmp_path / ".langcode" / "settings.json"
        settings.write_text(json.dumps({"model": "custom-model"}))

        created = init_project(tmp_path)
        assert created == []  # nothing new created
        assert json.loads(settings.read_text())["model"] == "custom-model"

    def test_returns_created_paths(self, tmp_path):
        created = init_project(tmp_path)
        assert ".langcode/settings.json" in created
        assert ".langcode/.gitignore" in created
        assert ".langcode/skills/" in created
        assert "AGENTS.md" not in created

    def test_slash_init(self, tmp_path):
        config = Config(cwd=tmp_path)
        handler = CommandHandler(config)
        result = handler.handle("/init")
        assert "created" in result.lower()
        assert (tmp_path / ".langcode" / "settings.json").exists()

    def test_slash_init_already_initialized(self, tmp_path):
        config = Config(cwd=tmp_path)
        handler = CommandHandler(config)
        handler.handle("/init")
        result = handler.handle("/init")
        assert "already initialized" in result.lower()


# ---------------------------------------------------------------------------
# Custom commands from commands/*.md
# ---------------------------------------------------------------------------
class TestCustomCommands:
    def _setup_commands(self, tmp_path):
        """Create a project dir with sample custom commands."""
        project_dir = tmp_path / ".langcode"
        cmds_dir = project_dir / "commands"
        cmds_dir.mkdir(parents=True)

        (cmds_dir / "ticket.md").write_text(
            "---\n"
            "description: Work on a JIRA ticket end-to-end\n"
            "---\n"
            "# Ticket Workflow\n\n"
            "Work on ticket: $ARGUMENTS\n"
        )
        (cmds_dir / "pr-review.md").write_text(
            "---\ndescription: Review a pull request\n---\nReview PR $1 on branch $2\n"
        )
        (cmds_dir / "simple.md").write_text("Just do the thing: $ARGUMENTS\n")
        (cmds_dir / "restricted.md").write_text(
            "---\n"
            "description: Security review\n"
            "allowed-tools: Read, Grep\n"
            "model: sonnet\n"
            "---\n"
            "Review security for $ARGUMENTS\n"
        )
        return project_dir

    def test_load_custom_commands(self, tmp_path):
        project_dir = self._setup_commands(tmp_path)
        cmds = load_custom_commands([project_dir])
        assert "/ticket" in cmds
        assert "/pr-review" in cmds
        assert "/simple" in cmds

    def test_load_empty_when_no_dir(self, tmp_path):
        cmds = load_custom_commands([tmp_path / "nonexistent"])
        assert cmds == {}

    def test_expand_arguments(self, tmp_path):
        project_dir = self._setup_commands(tmp_path)
        cmds = load_custom_commands([project_dir])
        result = expand_custom_command(cmds["/ticket"], "PROJ-123")
        assert isinstance(result, CommandResult)
        assert "PROJ-123" in result.prompt
        assert "Ticket Workflow" in result.prompt
        # frontmatter should be stripped
        assert "description:" not in result.prompt

    def test_expand_positional_args(self, tmp_path):
        project_dir = self._setup_commands(tmp_path)
        cmds = load_custom_commands([project_dir])
        result = expand_custom_command(cmds["/pr-review"], "456 feature-branch")
        assert "456" in result.prompt
        assert "feature-branch" in result.prompt

    def test_expand_no_frontmatter(self, tmp_path):
        project_dir = self._setup_commands(tmp_path)
        cmds = load_custom_commands([project_dir])
        result = expand_custom_command(cmds["/simple"], "hello world")
        assert "hello world" in result.prompt

    def test_handler_dispatches_custom_command(self, tmp_path):
        project_dir = self._setup_commands(tmp_path)
        config = Config(cwd=tmp_path, project_dir=project_dir)
        handler = CommandHandler(config)

        result = handler.handle("/ticket PROJ-456")
        assert isinstance(result, CommandResult)
        assert "PROJ-456" in result.prompt

    def test_handler_help_includes_custom_commands(self, tmp_path):
        project_dir = self._setup_commands(tmp_path)
        config = Config(cwd=tmp_path, project_dir=project_dir)
        handler = CommandHandler(config)

        result = handler.handle("/help")
        assert "/ticket" in result
        assert "/pr-review" in result
        assert "JIRA" in result  # description from frontmatter

    def test_builtin_commands_take_priority(self, tmp_path):
        project_dir = tmp_path / ".langcode"
        cmds_dir = project_dir / "commands"
        cmds_dir.mkdir(parents=True)
        (cmds_dir / "help.md").write_text("# Custom help\n")

        config = Config(cwd=tmp_path, project_dir=project_dir)
        handler = CommandHandler(config)
        result = handler.handle("/help")
        assert "/clear" in result

    def test_allowed_tools_parsed(self, tmp_path):
        project_dir = self._setup_commands(tmp_path)
        cmds = load_custom_commands([project_dir])
        result = expand_custom_command(cmds["/restricted"], "auth module")
        assert result.allowed_tools == ["Read", "Grep"]
        assert result.model == "sonnet"

    def test_bang_command_execution(self, tmp_path):
        project_dir = tmp_path / ".langcode"
        cmds_dir = project_dir / "commands"
        cmds_dir.mkdir(parents=True)
        (cmds_dir / "info.md").write_text(
            "---\ndescription: Show info\n---\nCurrent date: !`echo 2025-01-01`\n"
        )
        cmds = load_custom_commands([project_dir])
        result = expand_custom_command(cmds["/info"], "")
        assert "2025-01-01" in result.prompt
        # The !`...` should be replaced with output
        assert "!`" not in result.prompt

    def test_at_file_expansion(self, tmp_path):
        project_dir = tmp_path / ".langcode"
        cmds_dir = project_dir / "commands"
        cmds_dir.mkdir(parents=True)

        # Create a file to reference
        (tmp_path / "README.md").write_text("# Hello World")

        (cmds_dir / "review.md").write_text(
            "---\ndescription: Review\n---\nReview this: @README.md\n"
        )
        cmds = load_custom_commands([project_dir])
        result = expand_custom_command(cmds["/review"], "", cwd=tmp_path)
        assert "Hello World" in result.prompt
