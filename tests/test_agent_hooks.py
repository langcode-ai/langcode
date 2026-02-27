"""Tests for agent-level hooks: run_stop_hooks, run_subagent_stop_hooks."""

from langcode.agents import run_stop_hooks, run_subagent_stop_hooks
from langcode.core.config import Config
from langcode.hooks import HookDef, HookRule, HooksConfig


class TestRunStopHooks:
    def test_no_hooks_returns_true(self):
        config = Config()
        assert run_stop_hooks(config) is True

    def test_approve_returns_true(self, tmp_path):
        script = tmp_path / "approve.sh"
        script.write_text('#!/bin/bash\necho \'{"decision": "approve"}\'')
        script.chmod(0o755)

        config = Config()
        config.hooks = HooksConfig(
            Stop=[HookRule(matcher="*", hooks=[HookDef(type="command", command=f"bash {script}")])]
        )
        assert run_stop_hooks(config) is True

    def test_block_returns_false(self, tmp_path):
        script = tmp_path / "block.sh"
        script.write_text('#!/bin/bash\necho \'{"decision": "block", "reason": "tests not run"}\'')
        script.chmod(0o755)

        config = Config()
        config.hooks = HooksConfig(
            Stop=[HookRule(matcher="*", hooks=[HookDef(type="command", command=f"bash {script}")])]
        )
        assert run_stop_hooks(config) is False

    def test_prompt_hook_does_not_block(self):
        config = Config()
        config.hooks = HooksConfig(
            Stop=[HookRule(matcher="*", hooks=[HookDef(type="prompt", prompt="Verify completion")])]
        )
        assert run_stop_hooks(config) is True


class TestRunSubagentStopHooks:
    def test_no_hooks_returns_true(self):
        config = Config()
        assert run_subagent_stop_hooks(config) is True

    def test_approve_returns_true(self, tmp_path):
        script = tmp_path / "ok.sh"
        script.write_text('#!/bin/bash\necho \'{"decision": "approve"}\'')
        script.chmod(0o755)

        config = Config()
        config.hooks = HooksConfig(
            SubagentStop=[
                HookRule(matcher="*", hooks=[HookDef(type="command", command=f"bash {script}")])
            ]
        )
        assert run_subagent_stop_hooks(config) is True

    def test_block_returns_false(self, tmp_path):
        script = tmp_path / "nope.sh"
        script.write_text('#!/bin/bash\necho \'{"decision": "block", "reason": "incomplete"}\'')
        script.chmod(0o755)

        config = Config()
        config.hooks = HooksConfig(
            SubagentStop=[
                HookRule(matcher="*", hooks=[HookDef(type="command", command=f"bash {script}")])
            ]
        )
        assert run_subagent_stop_hooks(config) is False

    def test_stop_hooks_do_not_affect_subagent(self, tmp_path):
        """Stop hooks should not fire for SubagentStop check."""
        script = tmp_path / "blocker.sh"
        script.write_text('#!/bin/bash\necho \'{"decision": "block"}\'')
        script.chmod(0o755)

        config = Config()
        config.hooks = HooksConfig(
            Stop=[HookRule(matcher="*", hooks=[HookDef(type="command", command=f"bash {script}")])]
        )
        # SubagentStop has no rules, so it should return True even though Stop would block
        assert run_subagent_stop_hooks(config) is True
