"""Tests for config: load priority, hooks, env overrides, multi-dir support."""

import json
import os
from unittest.mock import patch

from langcode.core.config import Config, _apply_settings, load_config
from langcode.hooks import HooksConfig


class TestConfigDefaults:
    def test_default_model(self):
        c = Config()
        assert "claude" in c.model

    def test_default_max_tokens(self):
        c = Config()
        assert c.max_tokens == 16384

    def test_default_hooks_empty(self):
        c = Config()
        assert isinstance(c.hooks, HooksConfig)
        assert c.hooks.is_empty()


class TestLoadConfig:
    def test_global_settings(self, tmp_path):
        global_dir = tmp_path / ".langcode"
        global_dir.mkdir()
        (global_dir / "settings.json").write_text(json.dumps({"model": "test-model"}))
        Config(global_dir=global_dir)
        data = json.loads((global_dir / "settings.json").read_text())
        assert data["model"] == "test-model"

    def test_project_settings_override_global(self, tmp_path):
        global_dir = tmp_path / "global"
        global_dir.mkdir()
        (global_dir / "settings.json").write_text(json.dumps({"model": "global-model"}))

        project_dir = tmp_path / "project"
        project_dir.mkdir()
        (project_dir / "settings.json").write_text(json.dumps({"model": "project-model"}))

        config = Config(global_dir=global_dir, project_dir=project_dir)
        _apply_settings(config, global_dir / "settings.json")
        _apply_settings(config, project_dir / "settings.json")
        assert config.model == "project-model"

    def test_local_settings_highest_file_priority(self, tmp_path):
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        (project_dir / "settings.json").write_text(json.dumps({"model": "project-model"}))
        (project_dir / "settings.local.json").write_text(json.dumps({"model": "local-model"}))

        config = Config(project_dir=project_dir)
        _apply_settings(config, project_dir / "settings.json")
        _apply_settings(config, project_dir / "settings.local.json")
        assert config.model == "local-model"

    def test_hooks_merge_across_levels_legacy(self, tmp_path):
        """Legacy hooks format merges across config levels."""
        global_dir = tmp_path / "global"
        global_dir.mkdir()
        (global_dir / "settings.json").write_text(json.dumps({"hooks": {"pre:Write": "confirm"}}))

        project_dir = tmp_path / "project"
        project_dir.mkdir()
        (project_dir / "settings.json").write_text(
            json.dumps({"hooks": {"post:Write": "prettier $FILE"}})
        )

        config = Config(global_dir=global_dir, project_dir=project_dir)
        _apply_settings(config, global_dir / "settings.json")
        _apply_settings(config, project_dir / "settings.json")

        assert len(config.hooks.PreToolUse) == 1
        assert len(config.hooks.PostToolUse) == 1

    def test_hooks_claude_code_format(self, tmp_path):
        """Claude Code top-level hooks format is parsed correctly."""
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        (project_dir / "settings.json").write_text(
            json.dumps(
                {
                    "PreToolUse": [
                        {
                            "matcher": "Write|Edit",
                            "hooks": [{"type": "command", "command": "echo check"}],
                        }
                    ],
                    "Stop": [
                        {
                            "matcher": "*",
                            "hooks": [{"type": "prompt", "prompt": "Verify completion"}],
                        }
                    ],
                }
            )
        )

        config = Config(project_dir=project_dir)
        _apply_settings(config, project_dir / "settings.json")

        assert len(config.hooks.PreToolUse) == 1
        assert len(config.hooks.Stop) == 1
        assert config.hooks.PreToolUse[0].matcher == "Write|Edit"

    def test_hooks_wrapped_new_format(self, tmp_path):
        """Wrapped new-style format: {'hooks': {'PreToolUse': [...]}}."""
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        (project_dir / "settings.json").write_text(
            json.dumps(
                {
                    "hooks": {
                        "PreToolUse": [
                            {"matcher": "*", "hooks": [{"type": "prompt", "prompt": "test"}]}
                        ]
                    }
                }
            )
        )

        config = Config(project_dir=project_dir)
        _apply_settings(config, project_dir / "settings.json")
        assert len(config.hooks.PreToolUse) == 1

    def test_env_override(self):
        with patch.dict(os.environ, {"LANGCODE_MODEL": "env-model"}, clear=False):
            config = load_config()
            assert config.model == "env-model"

    def test_cli_override_beats_env(self):
        with patch.dict(os.environ, {"LANGCODE_MODEL": "env-model"}, clear=False):
            config = load_config(model="cli-model")
            assert config.model == "cli-model"


class TestProjectDirs:
    """Test multi-dir detection: both .langcode/ and .claude/ are loaded."""

    def test_finds_langcode_only(self, tmp_path):
        (tmp_path / ".langcode").mkdir()
        c = Config(cwd=tmp_path)
        assert len(c.project_dirs) == 1
        assert c.project_dirs[0].name == ".langcode"

    def test_finds_claude_only(self, tmp_path):
        (tmp_path / ".claude").mkdir()
        c = Config(cwd=tmp_path)
        assert len(c.project_dirs) == 1
        assert c.project_dirs[0].name == ".claude"

    def test_finds_both(self, tmp_path):
        (tmp_path / ".langcode").mkdir()
        (tmp_path / ".claude").mkdir()
        c = Config(cwd=tmp_path)
        assert len(c.project_dirs) == 2
        names = {d.name for d in c.project_dirs}
        assert names == {".langcode", ".claude"}

    def test_empty_when_neither(self, tmp_path):
        c = Config(cwd=tmp_path)
        assert c.project_dirs == []

    def test_explicit_project_dir_overrides(self, tmp_path):
        """When project_dir is explicitly set, project_dirs returns only that."""
        (tmp_path / ".langcode").mkdir()
        (tmp_path / ".claude").mkdir()
        explicit = tmp_path / ".claude"
        c = Config(cwd=tmp_path, project_dir=explicit)
        assert c.project_dirs == [explicit]

    def test_primary_project_dir_prefers_langcode(self, tmp_path):
        (tmp_path / ".langcode").mkdir()
        (tmp_path / ".claude").mkdir()
        c = Config(cwd=tmp_path)
        assert c.primary_project_dir.name == ".langcode"

    def test_primary_project_dir_fallback_claude(self, tmp_path):
        (tmp_path / ".claude").mkdir()
        c = Config(cwd=tmp_path)
        assert c.primary_project_dir.name == ".claude"

    def test_primary_project_dir_default(self, tmp_path):
        c = Config(cwd=tmp_path)
        assert c.primary_project_dir.name == ".langcode"

    def test_settings_loaded_from_both_dirs(self, tmp_path):
        """load_config should merge settings from .langcode + .claude."""
        lc = tmp_path / ".langcode"
        lc.mkdir()
        (lc / "settings.json").write_text(json.dumps({"hooks": {"pre:Bash": "confirm"}}))

        cl = tmp_path / ".claude"
        cl.mkdir()
        (cl / "settings.json").write_text(json.dumps({"hooks": {"post:Write": "prettier $FILE"}}))

        config = Config(cwd=tmp_path)
        assert len(config.project_dirs) == 2
        for pdir in config.project_dirs:
            _apply_settings(config, pdir / "settings.json")
        assert len(config.hooks.PreToolUse) == 1  # pre:Bash -> PreToolUse
        assert len(config.hooks.PostToolUse) == 1  # post:Write -> PostToolUse

    def test_claude_settings_loaded(self, tmp_path):
        """Config from .claude/settings.json should be loaded even without .langcode."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        (claude_dir / "settings.json").write_text(json.dumps({"model": "claude-from-dotclaude"}))

        config = Config(cwd=tmp_path)
        for pdir in config.project_dirs:
            _apply_settings(config, pdir / "settings.json")
        assert config.model == "claude-from-dotclaude"
