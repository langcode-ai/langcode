"""Integration tests: hooks config loading + execution end-to-end."""

import json
from unittest.mock import MagicMock

from langcode.core.config import Config, _apply_settings
from langcode.hooks import HookDef, HookRule, HooksConfig, execute_hooks
from langcode.hooks.middleware import HooksMiddleware


class TestClaudeCodeConfigEndToEnd:
    """Load Claude Code-style settings.json and execute hooks."""

    def test_pretooluse_from_settings(self, tmp_path):
        """Full pipeline: write settings.json -> load config -> execute PreToolUse."""
        project_dir = tmp_path / ".langcode"
        project_dir.mkdir()

        marker = tmp_path / "ran.txt"
        (project_dir / "settings.json").write_text(
            json.dumps(
                {
                    "PreToolUse": [
                        {
                            "matcher": "Write|Edit",
                            "hooks": [{"type": "command", "command": f"echo checked > {marker}"}],
                        }
                    ]
                }
            )
        )

        config = Config(cwd=tmp_path)
        for pdir in config.project_dirs:
            _apply_settings(config, pdir / "settings.json")

        # Execute hook
        execute_hooks(config.hooks, "PreToolUse", match_value="Write")
        assert marker.exists()
        assert "checked" in marker.read_text()

    def test_stop_from_settings(self, tmp_path):
        """Stop hook from Claude Code settings blocks agent."""
        project_dir = tmp_path / ".langcode"
        project_dir.mkdir()

        script = tmp_path / "check.sh"
        script.write_text('#!/bin/bash\necho \'{"decision": "block", "reason": "tests failing"}\'')
        script.chmod(0o755)

        (project_dir / "settings.json").write_text(
            json.dumps(
                {
                    "Stop": [
                        {
                            "matcher": "*",
                            "hooks": [{"type": "command", "command": f"bash {script}"}],
                        }
                    ]
                }
            )
        )

        config = Config(cwd=tmp_path)
        for pdir in config.project_dirs:
            _apply_settings(config, pdir / "settings.json")

        result = execute_hooks(config.hooks, "Stop", match_value="*")
        assert result.decision == "block"
        assert result.reason == "tests failing"

    def test_legacy_and_new_format_merge(self, tmp_path):
        """Legacy hooks from .langcode + Claude Code format from .claude both work."""
        lc = tmp_path / ".langcode"
        lc.mkdir()
        (lc / "settings.json").write_text(json.dumps({"hooks": {"pre:Bash": "confirm"}}))

        cl = tmp_path / ".claude"
        cl.mkdir()
        (cl / "settings.json").write_text(
            json.dumps(
                {
                    "PostToolUse": [
                        {
                            "matcher": "Write",
                            "hooks": [
                                {"type": "prompt", "prompt": "File written, check formatting"}
                            ],
                        }
                    ]
                }
            )
        )

        config = Config(cwd=tmp_path)
        for pdir in config.project_dirs:
            _apply_settings(config, pdir / "settings.json")

        # Legacy format -> PreToolUse with confirm
        assert len(config.hooks.PreToolUse) == 1
        assert config.hooks.PreToolUse[0].hooks[0].command == "__confirm__"

        # Claude Code format -> PostToolUse with prompt
        assert len(config.hooks.PostToolUse) == 1
        assert config.hooks.PostToolUse[0].hooks[0].prompt == "File written, check formatting"

    def test_session_hooks_from_settings(self, tmp_path):
        """SessionStart/SessionEnd from settings.json."""
        project_dir = tmp_path / ".langcode"
        project_dir.mkdir()

        start_marker = tmp_path / "start.txt"
        end_marker = tmp_path / "end.txt"

        (project_dir / "settings.json").write_text(
            json.dumps(
                {
                    "SessionStart": [
                        {
                            "matcher": "*",
                            "hooks": [
                                {"type": "command", "command": f"echo started > {start_marker}"}
                            ],
                        }
                    ],
                    "SessionEnd": [
                        {
                            "matcher": "*",
                            "hooks": [{"type": "command", "command": f"echo ended > {end_marker}"}],
                        }
                    ],
                }
            )
        )

        config = Config(cwd=tmp_path)
        for pdir in config.project_dirs:
            _apply_settings(config, pdir / "settings.json")

        execute_hooks(config.hooks, "SessionStart", match_value="*")
        assert start_marker.exists()

        execute_hooks(config.hooks, "SessionEnd", match_value="*")
        assert end_marker.exists()


class TestMiddlewareWithNewHooks:
    """Test HooksMiddleware with Claude Code-style hook configs."""

    def test_regex_matcher_via_middleware(self):
        """Write|Edit matcher fires for both Write and Edit via middleware."""
        config = Config()
        config.hooks = HooksConfig(
            PreToolUse=[
                HookRule(
                    matcher="Write|Edit",
                    hooks=[HookDef(type="prompt", prompt="Be careful with file changes")],
                )
            ]
        )
        mw = HooksMiddleware(config)

        for tool in ("Write", "Edit"):
            request = MagicMock()
            request.tool_call = {"name": tool, "id": "1", "args": {}}
            handler = MagicMock(return_value=MagicMock())
            mw.wrap_tool_call(request, handler)
            handler.assert_called_once()

    def test_regex_matcher_does_not_match_others(self):
        config = Config()
        config.hooks = HooksConfig(
            PreToolUse=[
                HookRule(
                    matcher="Write|Edit", hooks=[HookDef(type="command", command="__confirm__")]
                )
            ]
        )
        mw = HooksMiddleware(config)

        # Read should NOT trigger the confirm
        request = MagicMock()
        request.tool_call = {"name": "Read", "id": "1", "args": {}}
        handler = MagicMock(return_value=MagicMock())
        mw.wrap_tool_call(request, handler)
        handler.assert_called_once()  # not blocked

    def test_updated_input_applied(self, tmp_path):
        """PreToolUse hook can modify tool input via updatedInput."""
        script = tmp_path / "modify.sh"
        script.write_text(
            "#!/bin/bash\n"
            'echo \'{"hookSpecificOutput": {"permissionDecision": "allow", '
            '"updatedInput": {"file_path": "/safe/path.txt"}}}\''
        )
        script.chmod(0o755)

        config = Config()
        config.hooks = HooksConfig(
            PreToolUse=[
                HookRule(matcher="Write", hooks=[HookDef(type="command", command=f"bash {script}")])
            ]
        )
        mw = HooksMiddleware(config)

        request = MagicMock()
        request.tool_call = {
            "name": "Write",
            "id": "1",
            "args": {"file_path": "/original/path.txt"},
        }
        handler = MagicMock(return_value=MagicMock())

        mw.wrap_tool_call(request, handler)
        # The args should have been updated
        assert request.tool_call["args"]["file_path"] == "/safe/path.txt"

    def test_multiple_pre_hooks_all_fire(self, tmp_path):
        """Multiple PreToolUse rules that match should all execute."""
        m1 = tmp_path / "h1.txt"
        m2 = tmp_path / "h2.txt"
        config = Config()
        config.hooks = HooksConfig(
            PreToolUse=[
                HookRule(matcher="Write", hooks=[HookDef(type="command", command=f"touch {m1}")]),
                HookRule(matcher=".*", hooks=[HookDef(type="command", command=f"touch {m2}")]),
            ]
        )
        mw = HooksMiddleware(config)

        request = MagicMock()
        request.tool_call = {"name": "Write", "id": "1", "args": {}}
        handler = MagicMock(return_value=MagicMock())
        mw.wrap_tool_call(request, handler)

        assert m1.exists()
        assert m2.exists()

    def test_hook_timeout_does_not_crash(self):
        """Command hook with very short timeout should not crash middleware."""
        config = Config()
        config.hooks = HooksConfig(
            PostToolUse=[
                HookRule(
                    matcher="*", hooks=[HookDef(type="command", command="sleep 60", timeout=1)]
                )
            ]
        )
        mw = HooksMiddleware(config)

        request = MagicMock()
        request.tool_call = {"name": "Write", "id": "1", "args": {}}
        expected = MagicMock()
        handler = MagicMock(return_value=expected)

        result = mw.wrap_tool_call(request, handler)
        assert result == expected  # tool result still returned despite timeout
