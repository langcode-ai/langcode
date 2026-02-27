"""Integration tests using real data from ref_repo/claude-code-showcase/.claude/.

Tests langcode features against the real showcase configuration:
- Skills: 6 real SKILL.md files with frontmatter parsing + progressive disclosure
- AGENTS.md: Real CLAUDE.md as project context
- Config/Hooks: Real settings.json hooks config
- MCP: Real .mcp.json with 8 servers
- References: @ expansion on real showcase files
- Tools: read/write/edit on real skill files
"""

import json
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

from langcode.agents.context import build_context as load_skills
from langcode.agents.prompt import build_prompt
from langcode.commands import (
    CommandHandler,
    CommandResult,
    expand_custom_command,
    load_custom_commands,
)
from langcode.core.config import Config
from langcode.hooks.middleware import HooksMiddleware
from langcode.mcp import MCPManager
from langcode.skills.frontmatter import parse_skill_frontmatter as _parse_skill_frontmatter
from langcode.tui.references import expand_at_references

SHOWCASE_DIR = Path(__file__).parent.parent / "ref_repo" / "claude-code-showcase"
CLAUDE_DIR = SHOWCASE_DIR / ".claude"


def _has_showcase():
    return CLAUDE_DIR.exists()


skip_no_showcase = pytest.mark.skipif(
    not _has_showcase(), reason="ref_repo/claude-code-showcase not available"
)


# ---------------------------------------------------------------------------
# Real SKILL.md frontmatter parsing
# ---------------------------------------------------------------------------
class TestRealSkillFrontmatter:
    """Parse the 6 real SKILL.md files from the showcase."""

    @skip_no_showcase
    @pytest.mark.parametrize(
        "skill_name,expected_name,expected_keywords",
        [
            ("testing-patterns", "testing-patterns", ["Jest", "TDD"]),
            ("systematic-debugging", "systematic-debugging", ["debugging", "root cause"]),
            ("react-ui-patterns", "react-ui-patterns", ["React", "loading"]),
            ("graphql-schema", "graphql-schema", ["GraphQL", "mutation"]),
            ("core-components", "core-components", ["component", "design"]),
            ("formik-patterns", "formik-patterns", ["Formik", "form"]),
        ],
    )
    def test_parse_real_skill(self, skill_name, expected_name, expected_keywords):
        skill_file = CLAUDE_DIR / "skills" / skill_name / "SKILL.md"
        meta = _parse_skill_frontmatter(skill_file)

        assert meta is not None, f"Failed to parse {skill_name}"
        assert meta["name"] == expected_name
        assert "description" in meta
        assert len(meta["description"]) > 10  # non-trivial description

    @skip_no_showcase
    def test_all_skills_have_description(self):
        skills_dir = CLAUDE_DIR / "skills"
        for skill_dir in skills_dir.iterdir():
            skill_file = skill_dir / "SKILL.md"
            if skill_file.exists():
                meta = _parse_skill_frontmatter(skill_file)
                if meta:
                    assert meta.get("description"), f"{skill_dir.name} missing description"

    @skip_no_showcase
    def test_testing_patterns_has_triggers(self):
        """testing-patterns SKILL.md does NOT have explicit triggers line,
        so triggers should default to empty list."""
        skill_file = CLAUDE_DIR / "skills" / "testing-patterns" / "SKILL.md"
        meta = _parse_skill_frontmatter(skill_file)
        assert meta is not None
        # The real file has no triggers: key in frontmatter
        assert isinstance(meta.get("triggers"), list)


# ---------------------------------------------------------------------------
# Real Skills loading with progressive disclosure
# ---------------------------------------------------------------------------
class TestRealSkillsLoading:
    @skip_no_showcase
    def test_load_skills_with_real_skill_files(self, tmp_path):
        """Copy real skills to global_dir and verify progressive disclosure."""
        global_dir = tmp_path / ".langcode"
        skills_dst = global_dir / "skills"

        # Copy all real skill dirs
        src_skills = CLAUDE_DIR / "skills"
        for skill_dir in src_skills.iterdir():
            if skill_dir.is_dir() and (skill_dir / "SKILL.md").exists():
                dst = skills_dst / skill_dir.name
                dst.mkdir(parents=True)
                shutil.copy2(skill_dir / "SKILL.md", dst / "SKILL.md")

        config = Config(
            cwd=tmp_path,
            global_dir=global_dir,
            project_dir=tmp_path / "project",
        )
        result = load_skills(config)

        # All skill names should appear
        for name in [
            "testing-patterns",
            "systematic-debugging",
            "react-ui-patterns",
            "graphql-schema",
            "core-components",
            "formik-patterns",
        ]:
            assert name in result, f"{name} not found in loaded skills"

        # Full body content should NOT appear (progressive disclosure)
        assert "getMockX" not in result  # from testing-patterns body
        assert "Four-Phase Framework" not in result  # from debugging body
        assert "NEVER inline `gql` literals" not in result  # from graphql body

        # Should hint to use read tool
        assert "read" in result.lower()

    @skip_no_showcase
    def test_load_real_claude_md_as_agents(self, tmp_path):
        """Use the real CLAUDE.md as an AGENTS.md file."""
        claude_md = SHOWCASE_DIR / "CLAUDE.md"
        agents_md = tmp_path / "AGENTS.md"
        shutil.copy2(claude_md, agents_md)

        config = Config(
            cwd=tmp_path,
            global_dir=tmp_path / "global",
            project_dir=tmp_path / "project",
        )
        result = load_skills(config)

        # Real CLAUDE.md content should appear
        assert "TypeScript strict mode" in result
        assert "npm test" in result
        assert "Conventional Commits" in result
        assert "getMockX" in result  # factory pattern mention

    @skip_no_showcase
    def test_combined_agents_and_skills(self, tmp_path):
        """Load both AGENTS.md (CLAUDE.md) and SKILL.md files together."""
        # Copy CLAUDE.md as AGENTS.md
        shutil.copy2(SHOWCASE_DIR / "CLAUDE.md", tmp_path / "AGENTS.md")

        # Copy skills
        global_dir = tmp_path / ".langcode"
        src_skills = CLAUDE_DIR / "skills"
        for skill_dir in src_skills.iterdir():
            if skill_dir.is_dir() and (skill_dir / "SKILL.md").exists():
                dst = global_dir / "skills" / skill_dir.name
                dst.mkdir(parents=True)
                shutil.copy2(skill_dir / "SKILL.md", dst / "SKILL.md")

        config = Config(cwd=tmp_path, global_dir=global_dir, project_dir=tmp_path / "project")
        result = load_skills(config)

        # Both AGENTS.md content and skill metadata should be present
        assert "TypeScript strict mode" in result  # from CLAUDE.md
        assert "testing-patterns" in result  # skill name
        assert "react-ui-patterns" in result  # skill name


# ---------------------------------------------------------------------------
# Real hooks config
# ---------------------------------------------------------------------------
class TestRealHooksConfig:
    @skip_no_showcase
    def test_showcase_settings_readable(self):
        settings = json.loads((CLAUDE_DIR / "settings.json").read_text())
        assert "hooks" in settings
        assert "PreToolUse" in settings["hooks"]
        assert "PostToolUse" in settings["hooks"]

    def test_hooks_middleware_with_showcase_style_hooks(self):
        """Test that our HooksMiddleware supports pre/post hooks like the showcase."""
        config = Config(
            hooks={
                "pre:bash": "confirm",
                "post:write": "npx prettier --write $FILE",
                "post:edit": "npx prettier --write $FILE",
            }
        )
        HooksMiddleware(config)

        # pre:bash → confirm
        assert config.get_hook("pre:bash") == "confirm"
        # post:write → formatter
        assert "prettier" in config.get_hook("post:write")
        # post:edit → formatter
        assert "prettier" in config.get_hook("post:edit")
        # no hook for read
        assert config.get_hook("pre:read") is None


# ---------------------------------------------------------------------------
# Real MCP config
# ---------------------------------------------------------------------------
class TestRealMCPConfig:
    @skip_no_showcase
    def test_load_showcase_mcp_json(self, tmp_path):
        """The showcase uses 'mcpServers' key but our MCPManager expects 'servers'.
        Verify we handle the real structure (or document the difference)."""
        mcp_data = json.loads((SHOWCASE_DIR / ".mcp.json").read_text())

        # Showcase uses "mcpServers" key
        assert "mcpServers" in mcp_data
        servers = mcp_data["mcpServers"]
        assert len(servers) == 8

        # All expected servers present
        expected = ["jira", "github", "linear", "sentry", "postgres", "slack", "notion", "memory"]
        for name in expected:
            assert name in servers, f"Missing server: {name}"

    @skip_no_showcase
    def test_load_adapted_mcp_config(self, tmp_path):
        """Adapt the showcase .mcp.json to our format and load it."""
        mcp_data = json.loads((SHOWCASE_DIR / ".mcp.json").read_text())

        # Convert mcpServers → servers (our format)
        adapted = {"servers": mcp_data["mcpServers"]}
        (tmp_path / ".mcp.json").write_text(json.dumps(adapted))

        config = Config(cwd=tmp_path)
        mgr = MCPManager()
        mgr.load_config(config)

        assert len(mgr._server_configs) == 8
        assert mgr._server_configs["jira"]["command"] == "npx"
        assert mgr._server_configs["memory"]["command"] == "npx"
        assert mgr._server_configs["github"]["transport"] == "stdio"


# ---------------------------------------------------------------------------
# Real @ reference expansion on showcase files
# ---------------------------------------------------------------------------
class TestRealAtReferences:
    @skip_no_showcase
    def test_expand_real_skill_file(self):
        """Expand @.claude/skills/testing-patterns/SKILL.md"""
        result = expand_at_references(
            "read @.claude/skills/testing-patterns/SKILL.md",
            cwd=SHOWCASE_DIR,
        )
        assert "testing-patterns" in result
        assert "TDD" in result
        assert "<file" in result

    @skip_no_showcase
    def test_expand_real_claude_md(self):
        """Expand @CLAUDE.md"""
        result = expand_at_references("check @CLAUDE.md", cwd=SHOWCASE_DIR)
        assert "TypeScript strict mode" in result
        assert "npm test" in result

    @skip_no_showcase
    def test_expand_real_agent_file(self):
        """Expand a real agent definition file."""
        result = expand_at_references(
            "review @.claude/agents/code-reviewer.md",
            cwd=SHOWCASE_DIR,
        )
        assert "code-reviewer" in result

    @skip_no_showcase
    def test_expand_real_command_file(self):
        """Expand a real command file."""
        result = expand_at_references(
            "look at @.claude/commands/ticket.md",
            cwd=SHOWCASE_DIR,
        )
        assert "Ticket Workflow" in result or "JIRA" in result


# ---------------------------------------------------------------------------
# Real tools on showcase files
# ---------------------------------------------------------------------------
class TestRealToolsOnShowcase:
    @skip_no_showcase
    def test_read_real_skill_file(self):
        from langcode.tools.read import read

        with patch("langcode.core.utils.Path.cwd", return_value=SHOWCASE_DIR):
            result = read.invoke({"file_path": ".claude/skills/testing-patterns/SKILL.md"})
        assert "testing-patterns" in result
        assert "TDD" in result
        # should have line numbers
        assert "1|" in result

    @skip_no_showcase
    def test_read_real_settings_json(self):
        from langcode.tools.read import read

        with patch("langcode.core.utils.Path.cwd", return_value=SHOWCASE_DIR):
            result = read.invoke({"file_path": ".claude/settings.json"})
        assert "hooks" in result
        assert "PreToolUse" in result

    @skip_no_showcase
    def test_grep_across_skills(self):
        from langcode.tools.grep import grep

        with patch("langcode.core.utils.Path.cwd", return_value=SHOWCASE_DIR):
            result = grep.invoke(
                {
                    "pattern": "Integration with Other Skills",
                    "path": str(CLAUDE_DIR / "skills"),
                    "output_mode": "content",
                }
            )
        # Multiple skills reference integration
        assert "Integration with Other Skills" in result

    @skip_no_showcase
    def test_glob_skill_files(self):
        from langcode.tools.glob import glob_tool

        with patch("langcode.core.utils.Path.cwd", return_value=SHOWCASE_DIR):
            result = glob_tool.invoke(
                {
                    "pattern": "**/SKILL.md",
                    "path": str(CLAUDE_DIR / "skills"),
                }
            )
        assert "testing-patterns" in result
        assert "react-ui-patterns" in result

    @skip_no_showcase
    def test_ls_skills_directory(self):
        from langcode.tools.glob import glob_tool

        with patch("langcode.core.utils.Path.cwd", return_value=SHOWCASE_DIR):
            result = glob_tool.invoke({"pattern": "*/", "path": str(CLAUDE_DIR / "skills")})
        assert "testing-patterns" in result
        assert "core-components" in result

    @skip_no_showcase
    def test_write_and_edit_round_trip(self, tmp_path):
        """Write a skill file, then edit it — mimics showcase workflow."""
        from langcode.tools.edit import edit
        from langcode.tools.read import read
        from langcode.tools.write import write

        skill_content = (
            "---\n"
            "name: my-custom-skill\n"
            "description: A custom skill for testing\n"
            "triggers: [custom, test]\n"
            "---\n"
            "# My Custom Skill\n"
            "Original content.\n"
        )

        with patch("langcode.core.utils.Path.cwd", return_value=tmp_path):
            # Write
            write.invoke(
                {
                    "file_path": "skills/my-custom-skill/SKILL.md",
                    "content": skill_content,
                }
            )

            # Edit
            edit.invoke(
                {
                    "file_path": "skills/my-custom-skill/SKILL.md",
                    "old_string": "Original content.",
                    "new_string": "Updated content with more detail.",
                }
            )

            # Read back
            result = read.invoke({"file_path": "skills/my-custom-skill/SKILL.md"})

        assert "Updated content with more detail." in result
        assert "my-custom-skill" in result

        # Verify frontmatter still parseable
        meta = _parse_skill_frontmatter(tmp_path / "skills" / "my-custom-skill" / "SKILL.md")
        assert meta["name"] == "my-custom-skill"
        assert "custom" in meta["triggers"]


# ---------------------------------------------------------------------------
# Prompt assembly with real project context
# ---------------------------------------------------------------------------
class TestRealPromptAssembly:
    @skip_no_showcase
    def test_prompt_with_real_skills(self, tmp_path):
        """Build a system prompt using real skill data."""
        # Copy CLAUDE.md as AGENTS.md
        shutil.copy2(SHOWCASE_DIR / "CLAUDE.md", tmp_path / "AGENTS.md")

        # Copy skills
        global_dir = tmp_path / ".langcode"
        src_skills = CLAUDE_DIR / "skills"
        for skill_dir in src_skills.iterdir():
            if skill_dir.is_dir() and (skill_dir / "SKILL.md").exists():
                dst = global_dir / "skills" / skill_dir.name
                dst.mkdir(parents=True)
                shutil.copy2(skill_dir / "SKILL.md", dst / "SKILL.md")

        config = Config(cwd=tmp_path, global_dir=global_dir, project_dir=tmp_path / "project")
        skills_content = load_skills(config)
        prompt = build_prompt(config, skills_content)

        # Prompt should include role
        assert "LangCode" in prompt
        # Should include project context from CLAUDE.md
        assert "Project Context" in prompt
        assert "TypeScript strict mode" in prompt
        # Should include skill names
        assert "testing-patterns" in prompt
        assert "react-ui-patterns" in prompt
        # Should include environment
        assert "Environment" in prompt


# ---------------------------------------------------------------------------
# Commands with showcase-style workflow
# ---------------------------------------------------------------------------
class TestShowcaseWorkflow:
    def test_model_switch_to_opus_like_showcase_agent(self):
        """Showcase code-reviewer agent uses opus model."""
        config = Config()
        handler = CommandHandler(config)

        # Switch model like the showcase agent config
        handler.handle("/model anthropic:claude-opus-4-20250514")
        assert config.model == "anthropic:claude-opus-4-20250514"

    def test_cost_tracking_after_work(self):
        """Simulate a coding session and check cost tracking."""
        config = Config()
        handler = CommandHandler(config)

        # Simulate usage
        handler.total_input_tokens = 50_000
        handler.total_output_tokens = 10_000
        handler.total_cache_read = 40_000
        handler.total_cache_creation = 5_000

        result = handler.handle("/cost")
        assert "50,000" in result
        assert "10,000" in result
        assert "cached" in result

    def test_clear_and_restart(self):
        """Clear context like starting fresh on a new ticket."""
        config = Config()
        handler = CommandHandler(config)
        handler.messages = [
            {"role": "user", "content": "work on PROJ-123"},
            {"role": "assistant", "content": "I'll look at that ticket..."},
        ]

        handler.handle("/clear")
        assert len(handler.messages) == 0


# ---------------------------------------------------------------------------
# .claude/ directory detection
# ---------------------------------------------------------------------------
class TestBothDirsLoaded:
    """When both .langcode/ and .claude/ exist, BOTH are loaded."""

    @skip_no_showcase
    def test_skills_from_both_dirs(self, tmp_path):
        # .langcode/skills with one skill
        lc_dir = tmp_path / ".langcode" / "skills" / "lc-skill"
        lc_dir.mkdir(parents=True)
        (lc_dir / "SKILL.md").write_text(
            "---\nname: lc-skill\ndescription: From .langcode\ntriggers: []\n---\n"
        )
        # .claude/skills with another skill
        cl_dir = tmp_path / ".claude" / "skills" / "cl-skill"
        cl_dir.mkdir(parents=True)
        (cl_dir / "SKILL.md").write_text(
            "---\nname: cl-skill\ndescription: From .claude\ntriggers: []\n---\n"
        )

        config = Config(cwd=tmp_path, global_dir=tmp_path / "g")
        result = load_skills(config)
        assert "lc-skill" in result
        assert "cl-skill" in result

    @skip_no_showcase
    def test_commands_from_both_dirs(self, tmp_path):
        lc_cmds = tmp_path / ".langcode" / "commands"
        lc_cmds.mkdir(parents=True)
        (lc_cmds / "lc-cmd.md").write_text("do LC thing: $ARGUMENTS\n")

        cl_cmds = tmp_path / ".claude" / "commands"
        cl_cmds.mkdir(parents=True)
        (cl_cmds / "cl-cmd.md").write_text("do CL thing: $ARGUMENTS\n")

        config = Config(cwd=tmp_path)
        handler = CommandHandler(config)
        result = handler.handle("/help")
        assert "/lc-cmd" in result
        assert "/cl-cmd" in result

    @skip_no_showcase
    def test_agents_from_both_dirs(self, tmp_path):
        lc_agents = tmp_path / ".langcode" / "agents"
        lc_agents.mkdir(parents=True)
        (lc_agents / "reviewer.md").write_text(
            "---\nname: lc-reviewer\ndescription: LC reviewer\n---\n"
        )

        cl_agents = tmp_path / ".claude" / "agents"
        cl_agents.mkdir(parents=True)
        (cl_agents / "deployer.md").write_text(
            "---\nname: cl-deployer\ndescription: CL deployer\n---\n"
        )

        config = Config(cwd=tmp_path, global_dir=tmp_path / "g")
        result = load_skills(config)
        assert "lc-reviewer" in result
        assert "cl-deployer" in result


class TestClaudeDirCompat:
    @skip_no_showcase
    def test_project_dirs_finds_claude(self):
        """project_dirs should include .claude/ in the showcase repo."""
        config = Config(cwd=SHOWCASE_DIR, global_dir=SHOWCASE_DIR / "nonexistent_global")
        names = {d.name for d in config.project_dirs}
        assert ".claude" in names

    @skip_no_showcase
    def test_load_skills_from_claude_dir(self):
        """Skills from .claude/skills/ should load via auto-detection."""
        config = Config(
            cwd=SHOWCASE_DIR,
            global_dir=SHOWCASE_DIR / "nonexistent_global",
        )
        result = load_skills(config)
        # Skills from .claude/skills/
        assert "testing-patterns" in result
        assert "react-ui-patterns" in result
        assert "graphql-schema" in result

    @skip_no_showcase
    def test_load_agents_from_claude_dir(self):
        """Agents from .claude/agents/ should be loaded via auto-detection."""
        config = Config(
            cwd=SHOWCASE_DIR,
            global_dir=SHOWCASE_DIR / "nonexistent_global",
        )
        result = load_skills(config)
        assert "code-reviewer" in result
        assert "github-workflow" in result

    @skip_no_showcase
    def test_agents_progressive_disclosure(self):
        """Agent .md bodies should NOT appear, only name + description."""
        config = Config(
            cwd=SHOWCASE_DIR,
            global_dir=SHOWCASE_DIR / "nonexistent_global",
        )
        result = load_skills(config)
        # description should appear
        assert "code-reviewer" in result
        # full body should NOT
        assert "## Review Checklist" not in result
        assert "## Core Setup" not in result


# ---------------------------------------------------------------------------
# Real custom commands from .claude/commands/
# ---------------------------------------------------------------------------
class TestRealCustomCommands:
    @skip_no_showcase
    def test_load_showcase_commands(self):
        cmds = load_custom_commands([CLAUDE_DIR])
        assert "/ticket" in cmds
        assert "/pr-review" in cmds
        assert "/pr-summary" in cmds
        assert "/code-quality" in cmds
        assert "/docs-sync" in cmds
        assert "/onboard" in cmds

    @skip_no_showcase
    def test_expand_ticket_command(self):
        cmds = load_custom_commands([CLAUDE_DIR])
        result = expand_custom_command(cmds["/ticket"], "PROJ-123")
        assert "PROJ-123" in result.prompt
        assert "Ticket" in result.prompt or "ticket" in result.prompt
        # frontmatter should be stripped
        assert "allowed-tools" not in result.prompt

    @skip_no_showcase
    def test_expand_pr_review_command(self):
        cmds = load_custom_commands([CLAUDE_DIR])
        result = expand_custom_command(cmds["/pr-review"], "42")
        assert "42" in result.prompt

    @skip_no_showcase
    def test_handler_with_showcase_commands(self):
        """CommandHandler auto-detects .claude/ and loads commands from it."""
        config = Config(cwd=SHOWCASE_DIR)
        handler = CommandHandler(config)

        # /ticket should return a CommandResult with the prompt
        result = handler.handle("/ticket PROJ-789")
        assert isinstance(result, CommandResult)
        assert "PROJ-789" in result.prompt

    @skip_no_showcase
    def test_help_shows_showcase_commands(self):
        config = Config(cwd=SHOWCASE_DIR)
        handler = CommandHandler(config)

        result = handler.handle("/help")
        assert "/ticket" in result
        assert "/pr-review" in result
