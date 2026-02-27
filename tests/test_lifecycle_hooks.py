"""Tests for lifecycle hooks: SessionStart, SessionEnd, UserPromptSubmit, PreCompact, Notification."""

from langcode.core.config import Config
from langcode.hooks import HookDef, HookRule, HooksConfig, execute_hooks


class TestSessionStartHook:
    def test_fires_on_session_start(self, tmp_path):
        marker = tmp_path / "started.txt"
        config = Config()
        config.hooks = HooksConfig(
            SessionStart=[
                HookRule(
                    matcher="*", hooks=[HookDef(type="command", command=f"echo started > {marker}")]
                )
            ]
        )
        execute_hooks(config.hooks, "SessionStart", match_value="*")
        assert marker.exists()
        assert "started" in marker.read_text()

    def test_multiple_hooks_fire(self, tmp_path):
        m1 = tmp_path / "h1.txt"
        m2 = tmp_path / "h2.txt"
        config = Config()
        config.hooks = HooksConfig(
            SessionStart=[
                HookRule(matcher="*", hooks=[HookDef(type="command", command=f"touch {m1}")]),
                HookRule(matcher="*", hooks=[HookDef(type="command", command=f"touch {m2}")]),
            ]
        )
        execute_hooks(config.hooks, "SessionStart", match_value="*")
        assert m1.exists()
        assert m2.exists()

    def test_prompt_hook_returns_message(self):
        config = Config()
        config.hooks = HooksConfig(
            SessionStart=[
                HookRule(
                    matcher="*", hooks=[HookDef(type="prompt", prompt="Welcome to the session")]
                )
            ]
        )
        result = execute_hooks(config.hooks, "SessionStart", match_value="*")
        assert "Welcome to the session" in result.messages


class TestSessionEndHook:
    def test_fires_on_session_end(self, tmp_path):
        marker = tmp_path / "ended.txt"
        config = Config()
        config.hooks = HooksConfig(
            SessionEnd=[
                HookRule(
                    matcher="*", hooks=[HookDef(type="command", command=f"echo bye > {marker}")]
                )
            ]
        )
        execute_hooks(config.hooks, "SessionEnd", match_value="*")
        assert marker.exists()
        assert "bye" in marker.read_text()


class TestUserPromptSubmitHook:
    def test_fires_on_submit(self, tmp_path):
        marker = tmp_path / "submitted.txt"
        config = Config()
        config.hooks = HooksConfig(
            UserPromptSubmit=[
                HookRule(
                    matcher="*",
                    hooks=[HookDef(type="command", command=f"echo submitted > {marker}")],
                )
            ]
        )
        execute_hooks(config.hooks, "UserPromptSubmit", match_value="*")
        assert marker.exists()

    def test_prompt_hook_returns_guidance(self):
        config = Config()
        config.hooks = HooksConfig(
            UserPromptSubmit=[
                HookRule(
                    matcher="*",
                    hooks=[HookDef(type="prompt", prompt="Check security implications")],
                )
            ]
        )
        result = execute_hooks(config.hooks, "UserPromptSubmit", match_value="*")
        assert "Check security implications" in result.messages


class TestPreCompactHook:
    def test_fires_on_precompact(self, tmp_path):
        marker = tmp_path / "compact.txt"
        config = Config()
        config.hooks = HooksConfig(
            PreCompact=[
                HookRule(
                    matcher="*",
                    hooks=[HookDef(type="command", command=f"echo compacting > {marker}")],
                )
            ]
        )
        execute_hooks(config.hooks, "PreCompact", match_value="*")
        assert marker.exists()


class TestNotificationHook:
    def test_fires_on_notification(self, tmp_path):
        marker = tmp_path / "notif.txt"
        config = Config()
        config.hooks = HooksConfig(
            Notification=[
                HookRule(
                    matcher="*", hooks=[HookDef(type="command", command=f"echo notify > {marker}")]
                )
            ]
        )
        execute_hooks(config.hooks, "Notification", match_value="*")
        assert marker.exists()


class TestHookIsolation:
    """Events should not leak across different hook types."""

    def test_session_start_does_not_fire_session_end(self, tmp_path):
        marker = tmp_path / "leak.txt"
        config = Config()
        config.hooks = HooksConfig(
            SessionEnd=[
                HookRule(matcher="*", hooks=[HookDef(type="command", command=f"touch {marker}")])
            ]
        )
        execute_hooks(config.hooks, "SessionStart", match_value="*")
        assert not marker.exists()

    def test_user_prompt_does_not_fire_pre_tool(self, tmp_path):
        marker = tmp_path / "leak.txt"
        config = Config()
        config.hooks = HooksConfig(
            PreToolUse=[
                HookRule(matcher="*", hooks=[HookDef(type="command", command=f"touch {marker}")])
            ]
        )
        execute_hooks(config.hooks, "UserPromptSubmit", match_value="*")
        assert not marker.exists()

    def test_stop_does_not_fire_subagent_stop(self, tmp_path):
        marker = tmp_path / "leak.txt"
        config = Config()
        config.hooks = HooksConfig(
            SubagentStop=[
                HookRule(matcher="*", hooks=[HookDef(type="command", command=f"touch {marker}")])
            ]
        )
        execute_hooks(config.hooks, "Stop", match_value="*")
        assert not marker.exists()
