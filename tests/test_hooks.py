"""Tests for hooks engine: data models, parsing, matching, execution."""

from langcode.hooks import (
    HOOK_EVENTS,
    HookDef,
    HookRule,
    HooksConfig,
    convert_legacy_hooks,
    execute_hooks,
    parse_hook_def,
    parse_hook_rule,
    parse_hooks_config,
    run_command_hook,
)

# ── Data models ─────────────────────────────────────────────────────


class TestHookDef:
    def test_command_type(self):
        h = HookDef(type="command", command="echo hi")
        assert h.type == "command"
        assert h.command == "echo hi"

    def test_prompt_type(self):
        h = HookDef(type="prompt", prompt="Check safety")
        assert h.type == "prompt"
        assert h.prompt == "Check safety"

    def test_default_timeout(self):
        h = HookDef(type="command", command="echo")
        assert h.timeout == 30


class TestHookRule:
    def test_wildcard_matches_anything(self):
        r = HookRule(matcher="*")
        assert r.matches("Write") is True
        assert r.matches("Read") is True
        assert r.matches("") is True

    def test_regex_matcher(self):
        r = HookRule(matcher="Write|Edit")
        assert r.matches("Write") is True
        assert r.matches("Edit") is True
        assert r.matches("Read") is False

    def test_exact_matcher(self):
        r = HookRule(matcher="Bash")
        assert r.matches("Bash") is True
        assert r.matches("Read") is False

    def test_bad_regex_falls_back_to_exact(self):
        r = HookRule(matcher="[invalid")
        assert r.matches("[invalid") is True
        assert r.matches("something") is False


class TestHooksConfig:
    def test_empty_by_default(self):
        cfg = HooksConfig()
        assert cfg.is_empty() is True

    def test_get_rules(self):
        rule = HookRule(matcher="*", hooks=[HookDef(type="prompt", prompt="test")])
        cfg = HooksConfig(PreToolUse=[rule])
        assert cfg.get_rules("PreToolUse") == [rule]
        assert cfg.get_rules("PostToolUse") == []

    def test_merge(self):
        cfg1 = HooksConfig(PreToolUse=[HookRule(matcher="Write")])
        cfg2 = HooksConfig(PreToolUse=[HookRule(matcher="Edit")])
        cfg1.merge(cfg2)
        assert len(cfg1.PreToolUse) == 2

    def test_merge_across_events(self):
        cfg1 = HooksConfig(PreToolUse=[HookRule(matcher="*")])
        cfg2 = HooksConfig(Stop=[HookRule(matcher="*")])
        cfg1.merge(cfg2)
        assert len(cfg1.PreToolUse) == 1
        assert len(cfg1.Stop) == 1

    def test_not_empty_after_add(self):
        cfg = HooksConfig(Stop=[HookRule(matcher="*")])
        assert cfg.is_empty() is False


# ── Parsing ─────────────────────────────────────────────────────────


class TestParseHookDef:
    def test_command_hook(self):
        h = parse_hook_def({"type": "command", "command": "echo ok", "timeout": 10})
        assert h.type == "command"
        assert h.command == "echo ok"
        assert h.timeout == 10

    def test_prompt_hook(self):
        h = parse_hook_def({"type": "prompt", "prompt": "Validate safety"})
        assert h.type == "prompt"
        assert h.prompt == "Validate safety"

    def test_defaults(self):
        h = parse_hook_def({})
        assert h.type == "command"
        assert h.timeout == 30


class TestParseHookRule:
    def test_basic(self):
        r = parse_hook_rule(
            {
                "matcher": "Write|Edit",
                "hooks": [{"type": "command", "command": "echo check"}],
            }
        )
        assert r.matcher == "Write|Edit"
        assert len(r.hooks) == 1
        assert r.hooks[0].command == "echo check"

    def test_multiple_hooks(self):
        r = parse_hook_rule(
            {
                "matcher": "*",
                "hooks": [
                    {"type": "command", "command": "lint"},
                    {"type": "prompt", "prompt": "Check for issues"},
                ],
            }
        )
        assert len(r.hooks) == 2


class TestParseHooksConfig:
    def test_claude_code_format(self):
        cfg = parse_hooks_config(
            {
                "PreToolUse": [
                    {"matcher": "Write|Edit", "hooks": [{"type": "command", "command": "echo pre"}]}
                ],
                "Stop": [{"matcher": "*", "hooks": [{"type": "prompt", "prompt": "Verify"}]}],
            }
        )
        assert len(cfg.PreToolUse) == 1
        assert len(cfg.Stop) == 1
        assert cfg.PreToolUse[0].matcher == "Write|Edit"

    def test_wrapped_format(self):
        cfg = parse_hooks_config(
            {
                "hooks": {
                    "PreToolUse": [
                        {"matcher": "*", "hooks": [{"type": "prompt", "prompt": "test"}]}
                    ]
                }
            }
        )
        assert len(cfg.PreToolUse) == 1

    def test_ignores_unknown_keys(self):
        cfg = parse_hooks_config({"model": "test", "PreToolUse": []})
        assert cfg.is_empty()

    def test_all_nine_events(self):
        data = {event: [{"matcher": "*", "hooks": []}] for event in HOOK_EVENTS}
        cfg = parse_hooks_config(data)
        for event in HOOK_EVENTS:
            assert len(cfg.get_rules(event)) == 1


class TestConvertLegacyHooks:
    def test_pre_confirm(self):
        cfg = convert_legacy_hooks({"pre:Bash": "confirm"})
        assert len(cfg.PreToolUse) == 1
        assert cfg.PreToolUse[0].matches("Bash")
        assert cfg.PreToolUse[0].hooks[0].command == "__confirm__"

    def test_pre_command(self):
        cfg = convert_legacy_hooks({"pre:Write": "echo checking"})
        assert len(cfg.PreToolUse) == 1
        assert cfg.PreToolUse[0].hooks[0].command == "echo checking"

    def test_post_command(self):
        cfg = convert_legacy_hooks({"post:Edit": "ruff format $FILE"})
        assert len(cfg.PostToolUse) == 1
        assert cfg.PostToolUse[0].hooks[0].command == "ruff format $FILE"

    def test_mixed(self):
        cfg = convert_legacy_hooks(
            {
                "pre:Bash": "confirm",
                "post:Write": "prettier $FILE",
            }
        )
        assert len(cfg.PreToolUse) == 1
        assert len(cfg.PostToolUse) == 1

    def test_ignores_invalid_keys(self):
        cfg = convert_legacy_hooks({"invalid": "nope"})
        assert cfg.is_empty()


# ── Execution ───────────────────────────────────────────────────────


class TestRunCommandHook:
    def test_echo(self):
        h = HookDef(type="command", command="echo hello")
        code, stdout, stderr = run_command_hook(h)
        assert code == 0
        assert "hello" in stdout

    def test_variable_substitution(self):
        h = HookDef(type="command", command="echo $FILE")
        code, stdout, _ = run_command_hook(h, variables={"FILE": "test.py"})
        assert code == 0
        assert "test.py" in stdout

    def test_timeout(self):
        h = HookDef(type="command", command="sleep 60", timeout=1)
        code, _, stderr = run_command_hook(h)
        assert code == -1
        assert "timed out" in stderr


class TestExecuteHooks:
    def test_no_matching_rules(self):
        cfg = HooksConfig(
            PreToolUse=[
                HookRule(matcher="Write", hooks=[HookDef(type="command", command="echo x")])
            ]
        )
        result = execute_hooks(cfg, "PreToolUse", match_value="Read")
        assert result.permission == "allow"
        assert result.messages == []

    def test_command_hook_runs(self, tmp_path):
        marker = tmp_path / "ran.txt"
        cfg = HooksConfig(
            PreToolUse=[
                HookRule(
                    matcher="Write", hooks=[HookDef(type="command", command=f"echo ok > {marker}")]
                )
            ]
        )
        execute_hooks(cfg, "PreToolUse", match_value="Write")
        assert marker.exists()

    def test_prompt_hook_adds_message(self):
        cfg = HooksConfig(
            PreToolUse=[
                HookRule(
                    matcher="*", hooks=[HookDef(type="prompt", prompt="Be careful with writes")]
                )
            ]
        )
        result = execute_hooks(cfg, "PreToolUse", match_value="Write")
        assert "Be careful with writes" in result.messages

    def test_confirm_hook_sets_ask(self):
        cfg = HooksConfig(
            PreToolUse=[
                HookRule(matcher="Bash", hooks=[HookDef(type="command", command="__confirm__")])
            ]
        )
        result = execute_hooks(cfg, "PreToolUse", match_value="Bash")
        assert result.permission == "ask"

    def test_json_permission_decision(self, tmp_path):
        script = tmp_path / "hook.sh"
        script.write_text(
            "#!/bin/bash\n"
            'echo \'{"hookSpecificOutput": {"permissionDecision": "deny"}, "systemMessage": "blocked"}\''
        )
        script.chmod(0o755)
        cfg = HooksConfig(
            PreToolUse=[
                HookRule(matcher="Write", hooks=[HookDef(type="command", command=f"bash {script}")])
            ]
        )
        result = execute_hooks(cfg, "PreToolUse", match_value="Write")
        assert result.permission == "deny"
        assert "blocked" in result.messages

    def test_json_stop_decision(self, tmp_path):
        script = tmp_path / "stop.sh"
        script.write_text('#!/bin/bash\necho \'{"decision": "block", "reason": "tests not run"}\'')
        script.chmod(0o755)
        cfg = HooksConfig(
            Stop=[HookRule(matcher="*", hooks=[HookDef(type="command", command=f"bash {script}")])]
        )
        result = execute_hooks(cfg, "Stop", match_value="*")
        assert result.decision == "block"
        assert result.reason == "tests not run"

    def test_multiple_rules_all_fire(self, tmp_path):
        m1 = tmp_path / "m1.txt"
        m2 = tmp_path / "m2.txt"
        cfg = HooksConfig(
            PostToolUse=[
                HookRule(matcher="Write", hooks=[HookDef(type="command", command=f"touch {m1}")]),
                HookRule(matcher="*", hooks=[HookDef(type="command", command=f"touch {m2}")]),
            ]
        )
        execute_hooks(cfg, "PostToolUse", match_value="Write")
        assert m1.exists()
        assert m2.exists()

    def test_variable_substitution(self, tmp_path):
        log = tmp_path / "log.txt"
        cfg = HooksConfig(
            PostToolUse=[
                HookRule(
                    matcher="*", hooks=[HookDef(type="command", command=f"echo $FILE > {log}")]
                )
            ]
        )
        execute_hooks(cfg, "PostToolUse", match_value="Write", variables={"FILE": "main.py"})
        assert "main.py" in log.read_text()

    def test_wrong_event_no_fire(self, tmp_path):
        marker = tmp_path / "no.txt"
        cfg = HooksConfig(
            PreToolUse=[
                HookRule(matcher="*", hooks=[HookDef(type="command", command=f"touch {marker}")])
            ]
        )
        execute_hooks(cfg, "PostToolUse", match_value="Write")
        assert not marker.exists()
