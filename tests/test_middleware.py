"""Tests for middleware: HooksMiddleware with new hooks engine."""

from unittest.mock import MagicMock, patch

from langcode.core.config import Config
from langcode.hooks import HookDef, HookRule, HooksConfig, convert_legacy_hooks
from langcode.hooks.middleware import HooksMiddleware


def _make_config(**legacy_hooks) -> Config:
    """Create a Config with legacy-style hooks auto-converted."""
    config = Config()
    if legacy_hooks:
        config.hooks = convert_legacy_hooks(legacy_hooks)
    return config


def _make_config_new(**kwargs) -> Config:
    """Create a Config with a HooksConfig directly."""
    config = Config()
    config.hooks = HooksConfig(**kwargs)
    return config


# ---------------------------------------------------------------------------
# Unit tests (mocked subprocess)
# ---------------------------------------------------------------------------
class TestHooksMiddleware:
    def test_no_hooks_passes_through(self):
        config = Config()
        mw = HooksMiddleware(config)

        request = MagicMock()
        request.tool_call = {"name": "Read", "id": "123", "args": {}}
        expected = MagicMock()
        handler = MagicMock(return_value=expected)

        result = mw.wrap_tool_call(request, handler)
        handler.assert_called_once_with(request)
        assert result == expected

    def test_pre_hook_shell_command(self, tmp_path):
        marker = tmp_path / "pre.txt"
        config = _make_config_new(
            PreToolUse=[
                HookRule(
                    matcher="Write", hooks=[HookDef(type="command", command=f"touch {marker}")]
                )
            ]
        )
        mw = HooksMiddleware(config)

        request = MagicMock()
        request.tool_call = {"name": "Write", "id": "123", "args": {}}
        handler = MagicMock(return_value=MagicMock())

        mw.wrap_tool_call(request, handler)
        assert marker.exists()

    def test_post_hook_with_file_substitution(self, tmp_path):
        log = tmp_path / "hook.log"
        config = _make_config_new(
            PostToolUse=[
                HookRule(
                    matcher="Write", hooks=[HookDef(type="command", command=f"echo $FILE > {log}")]
                )
            ]
        )
        mw = HooksMiddleware(config)

        request = MagicMock()
        request.tool_call = {
            "name": "Write",
            "id": "123",
            "args": {"file_path": "src/main.py"},
        }
        handler = MagicMock(return_value=MagicMock())

        mw.wrap_tool_call(request, handler)
        assert "src/main.py" in log.read_text()

    def test_confirm_hook_denied(self):
        config = _make_config(**{"pre:Bash": "confirm"})
        mw = HooksMiddleware(config)

        request = MagicMock()
        request.tool_call = {"name": "Bash", "id": "456", "args": {"command": "rm -rf /"}}
        handler = MagicMock()

        with patch("langcode.hooks.middleware.pt_prompt", return_value="n"):
            result = mw.wrap_tool_call(request, handler)
            handler.assert_not_called()
            assert "denied" in result.content.lower()

    def test_confirm_hook_approved(self):
        config = _make_config(**{"pre:Bash": "confirm"})
        mw = HooksMiddleware(config)

        request = MagicMock()
        request.tool_call = {"name": "Bash", "id": "456", "args": {"command": "echo hi"}}
        expected = MagicMock()
        handler = MagicMock(return_value=expected)

        with patch("langcode.hooks.middleware.pt_prompt", return_value="y"):
            result = mw.wrap_tool_call(request, handler)
            handler.assert_called_once_with(request)
            assert result == expected

    def test_regex_matcher(self):
        """Regex matcher 'Write|Edit' should match both tools."""
        config = _make_config_new(
            PreToolUse=[
                HookRule(matcher="Write|Edit", hooks=[HookDef(type="prompt", prompt="Be careful")])
            ]
        )
        mw = HooksMiddleware(config)

        for tool_name in ("Write", "Edit"):
            request = MagicMock()
            request.tool_call = {"name": tool_name, "id": "1", "args": {}}
            handler = MagicMock(return_value=MagicMock())
            mw.wrap_tool_call(request, handler)
            handler.assert_called_once()

    def test_deny_permission_blocks_tool(self, tmp_path):
        """Hook returning deny JSON blocks the tool."""
        script = tmp_path / "deny.sh"
        script.write_text(
            '#!/bin/bash\necho \'{"hookSpecificOutput": {"permissionDecision": "deny"}}\''
        )
        script.chmod(0o755)

        config = _make_config_new(
            PreToolUse=[
                HookRule(matcher="Write", hooks=[HookDef(type="command", command=f"bash {script}")])
            ]
        )
        mw = HooksMiddleware(config)

        request = MagicMock()
        request.tool_call = {"name": "Write", "id": "d1", "args": {}}
        handler = MagicMock()

        result = mw.wrap_tool_call(request, handler)
        handler.assert_not_called()
        assert "denied" in result.content.lower()


# ---------------------------------------------------------------------------
# Real execution tests — hooks actually run shell commands
# ---------------------------------------------------------------------------
class TestHooksRealExecution:
    """Hooks run real shell commands (no mocking)."""

    def test_pre_hook_actually_runs(self, tmp_path):
        marker = tmp_path / "pre_ran.txt"
        config = _make_config(**{"pre:Write": f"echo ok > {marker}"})
        mw = HooksMiddleware(config)

        request = MagicMock()
        request.tool_call = {"name": "Write", "id": "1", "args": {}}
        handler = MagicMock(return_value=MagicMock())

        mw.wrap_tool_call(request, handler)
        assert marker.exists()
        handler.assert_called_once()

    def test_post_hook_actually_runs(self, tmp_path):
        marker = tmp_path / "post_ran.txt"
        config = _make_config(**{"post:Edit": f"echo done > {marker}"})
        mw = HooksMiddleware(config)

        request = MagicMock()
        request.tool_call = {"name": "Edit", "id": "2", "args": {}}
        handler = MagicMock(return_value=MagicMock())

        mw.wrap_tool_call(request, handler)
        assert marker.exists()

    def test_post_hook_file_substitution_real(self, tmp_path):
        log = tmp_path / "hook.log"
        target = tmp_path / "code.py"
        target.write_text("print('hello')")

        config = _make_config(**{"post:Write": f"echo $FILE > {log}"})
        mw = HooksMiddleware(config)

        request = MagicMock()
        request.tool_call = {
            "name": "Write",
            "id": "3",
            "args": {"file_path": str(target)},
        }
        handler = MagicMock(return_value=MagicMock())

        mw.wrap_tool_call(request, handler)
        assert log.exists()
        assert str(target) in log.read_text()

    def test_pre_hook_runs_before_handler(self, tmp_path):
        pre_marker = tmp_path / "order.log"
        config = _make_config(**{"pre:Write": f"echo pre >> {pre_marker}"})
        mw = HooksMiddleware(config)

        def fake_handler(req):
            with open(pre_marker, "a") as f:
                f.write("handler\n")
            return MagicMock()

        request = MagicMock()
        request.tool_call = {"name": "Write", "id": "4", "args": {}}

        mw.wrap_tool_call(request, fake_handler)
        lines = pre_marker.read_text().strip().splitlines()
        assert lines[0] == "pre"
        assert lines[1] == "handler"

    def test_post_hook_runs_after_handler(self, tmp_path):
        log = tmp_path / "order.log"
        config = _make_config(**{"post:Write": f"echo post >> {log}"})
        mw = HooksMiddleware(config)

        def fake_handler(req):
            with open(log, "a") as f:
                f.write("handler\n")
            return MagicMock()

        request = MagicMock()
        request.tool_call = {"name": "Write", "id": "5", "args": {}}

        mw.wrap_tool_call(request, fake_handler)
        lines = log.read_text().strip().splitlines()
        assert lines[0] == "handler"
        assert lines[1] == "post"

    def test_pre_and_post_hooks_both_run(self, tmp_path):
        log = tmp_path / "both.log"
        config = Config()
        config.hooks = convert_legacy_hooks(
            {
                "pre:Write": f"echo pre >> {log}",
                "post:Write": f"echo post >> {log}",
            }
        )
        mw = HooksMiddleware(config)

        def fake_handler(req):
            with open(log, "a") as f:
                f.write("handler\n")
            return MagicMock()

        request = MagicMock()
        request.tool_call = {"name": "Write", "id": "6", "args": {}}

        mw.wrap_tool_call(request, fake_handler)
        lines = log.read_text().strip().splitlines()
        assert lines == ["pre", "handler", "post"]

    def test_hook_only_fires_for_matching_tool(self, tmp_path):
        marker = tmp_path / "should_not_exist.txt"
        config = _make_config(**{"pre:Write": f"echo bad > {marker}"})
        mw = HooksMiddleware(config)

        request = MagicMock()
        request.tool_call = {"name": "Read", "id": "7", "args": {}}
        handler = MagicMock(return_value=MagicMock())

        mw.wrap_tool_call(request, handler)
        assert not marker.exists()

    def test_post_hook_formatter_style(self, tmp_path):
        target = tmp_path / "messy.py"
        target.write_text("x=1\ny =  2\n")

        config = _make_config(**{"post:Write": "sed -i 's/ *= */=/g' $FILE"})
        mw = HooksMiddleware(config)

        request = MagicMock()
        request.tool_call = {
            "name": "Write",
            "id": "8",
            "args": {"file_path": str(target)},
        }
        handler = MagicMock(return_value=MagicMock())

        mw.wrap_tool_call(request, handler)
        content = target.read_text()
        assert "x=1" in content
        assert "y=2" in content

    def test_multiple_tools_different_hooks(self, tmp_path):
        write_log = tmp_path / "write.log"
        edit_log = tmp_path / "edit.log"
        config = Config()
        config.hooks = convert_legacy_hooks(
            {
                "post:Write": f"echo write_hook > {write_log}",
                "post:Edit": f"echo edit_hook > {edit_log}",
            }
        )
        mw = HooksMiddleware(config)

        req_write = MagicMock()
        req_write.tool_call = {"name": "Write", "id": "w1", "args": {}}
        mw.wrap_tool_call(req_write, MagicMock(return_value=MagicMock()))

        req_edit = MagicMock()
        req_edit.tool_call = {"name": "Edit", "id": "e1", "args": {}}
        mw.wrap_tool_call(req_edit, MagicMock(return_value=MagicMock()))

        assert write_log.read_text().strip() == "write_hook"
        assert edit_log.read_text().strip() == "edit_hook"

    def test_confirm_denied_blocks_tool_real(self):
        config = _make_config(**{"pre:Bash": "confirm"})
        mw = HooksMiddleware(config)

        request = MagicMock()
        request.tool_call = {"name": "Bash", "id": "c1", "args": {"command": "rm -rf /"}}
        handler = MagicMock()

        with patch("langcode.hooks.middleware.pt_prompt", return_value="no"):
            result = mw.wrap_tool_call(request, handler)

        handler.assert_not_called()
        assert "denied" in result.content.lower()
        assert result.tool_call_id == "c1"

    def test_confirm_approved_allows_tool_real(self):
        config = _make_config(**{"pre:Bash": "confirm"})
        mw = HooksMiddleware(config)

        expected = MagicMock()
        request = MagicMock()
        request.tool_call = {"name": "Bash", "id": "c2", "args": {"command": "echo safe"}}
        handler = MagicMock(return_value=expected)

        with patch("langcode.hooks.middleware.pt_prompt", return_value="yes"):
            result = mw.wrap_tool_call(request, handler)

        handler.assert_called_once()
        assert result == expected
