"""Tests for skills: AGENTS.md loading, SKILL.md frontmatter parsing, progressive disclosure, agent defs."""

from langcode.agents.context import build_context as load_skills
from langcode.agents.defs import load_agents
from langcode.core.config import Config
from langcode.skills.frontmatter import parse_frontmatter_and_body as _parse_frontmatter_and_body
from langcode.skills.frontmatter import parse_skill_frontmatter as _parse_skill_frontmatter


class TestParseSkillFrontmatter:
    def test_basic_frontmatter(self, tmp_path):
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text(
            "---\n"
            "name: testing-patterns\n"
            "description: TDD workflow and testing best practices\n"
            "---\n"
            "# Full content here\n"
        )
        meta = _parse_skill_frontmatter(skill_file)
        assert meta is not None
        assert meta["name"] == "testing-patterns"
        assert meta["description"] == "TDD workflow and testing best practices"

    def test_no_frontmatter_returns_none(self, tmp_path):
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text("# Just a regular markdown file\n")
        assert _parse_skill_frontmatter(skill_file) is None

    def test_incomplete_frontmatter_returns_none(self, tmp_path):
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text("---\nname: test\nno closing delimiter\n")
        assert _parse_skill_frontmatter(skill_file) is None

    def test_description_is_trigger(self, tmp_path):
        """Claude Code style: description field serves as trigger info."""
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text(
            "---\n"
            "name: hook-skill\n"
            'description: This skill should be used when the user asks to "create a hook" or "add a PreToolUse hook"\n'
            "---\n"
        )
        meta = _parse_skill_frontmatter(skill_file)
        assert "create a hook" in meta["description"]
        assert "PreToolUse" in meta["description"]

    def test_quoted_triggers_still_work(self, tmp_path):
        """Old-style triggers field is still parsed if present."""
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text(
            "---\n"
            "name: react-ui\n"
            "description: React patterns\n"
            "triggers: ['react', \"component\", ui]\n"
            "---\n"
        )
        meta = _parse_skill_frontmatter(skill_file)
        assert "react" in meta["triggers"]
        assert "component" in meta["triggers"]
        assert "ui" in meta["triggers"]


class TestLoadSkills:
    def test_loads_agents_md_from_cwd(self, tmp_path):
        agents_file = tmp_path / "AGENTS.md"
        agents_file.write_text("# Project Rules\nAlways use TypeScript strict mode.")

        config = Config(
            cwd=tmp_path,
            global_dir=tmp_path / "global",
            project_dir=tmp_path / "project",
        )
        result = load_skills(config)
        assert "Project Rules" in result
        assert "TypeScript strict mode" in result

    def test_loads_agents_md_from_project_dir(self, tmp_path):
        project_dir = tmp_path / ".langcode"
        project_dir.mkdir()
        (project_dir / "AGENTS.md").write_text("Project-level rules")

        config = Config(
            cwd=tmp_path,
            global_dir=tmp_path / "global",
            project_dir=project_dir,
        )
        result = load_skills(config)
        assert "Project-level rules" in result

    def test_loads_agents_md_from_global_dir(self, tmp_path):
        global_dir = tmp_path / ".langcode"
        global_dir.mkdir()
        (global_dir / "AGENTS.md").write_text("Global rules")

        config = Config(
            cwd=tmp_path / "cwd",
            global_dir=global_dir,
            project_dir=tmp_path / "project",
        )
        result = load_skills(config)
        assert "Global rules" in result

    def test_all_levels_combined(self, tmp_path):
        global_dir = tmp_path / "global"
        global_dir.mkdir()
        (global_dir / "AGENTS.md").write_text("Global context")

        project_dir = tmp_path / "project"
        project_dir.mkdir()
        (project_dir / "AGENTS.md").write_text("Project context")

        (tmp_path / "AGENTS.md").write_text("Root context")

        config = Config(cwd=tmp_path, global_dir=global_dir, project_dir=project_dir)
        result = load_skills(config)
        assert "Global context" in result
        assert "Project context" in result
        assert "Root context" in result

    def test_empty_agents_md_skipped(self, tmp_path):
        (tmp_path / "AGENTS.md").write_text("")
        config = Config(
            cwd=tmp_path,
            global_dir=tmp_path / "global",
            project_dir=tmp_path / "project",
        )
        result = load_skills(config)
        assert result == ""

    def test_progressive_disclosure_skills(self, tmp_path):
        """Skills should only show name + description, not full content."""
        global_dir = tmp_path / "global"
        skills_dir = global_dir / "skills" / "testing-patterns"
        skills_dir.mkdir(parents=True)
        (skills_dir / "SKILL.md").write_text(
            "---\n"
            "name: testing-patterns\n"
            "description: TDD workflow\n"
            "---\n"
            "# Full detailed content that should NOT appear\n"
            "This is the full skill body.\n"
        )

        config = Config(
            cwd=tmp_path,
            global_dir=global_dir,
            project_dir=tmp_path / "project",
        )
        result = load_skills(config)
        assert "testing-patterns" in result
        assert "TDD workflow" in result
        # full body should NOT be in the output
        assert "Full detailed content that should NOT appear" not in result
        # should hint to use read tool
        assert "read" in result.lower()

    def test_multiple_skills(self, tmp_path):
        global_dir = tmp_path / "global"
        for name, desc in [("skill-a", "Description A"), ("skill-b", "Description B")]:
            d = global_dir / "skills" / name
            d.mkdir(parents=True)
            (d / "SKILL.md").write_text(f"---\nname: {name}\ndescription: {desc}\n---\n")

        config = Config(
            cwd=tmp_path,
            global_dir=global_dir,
            project_dir=tmp_path / "project",
        )
        result = load_skills(config)
        assert "skill-a" in result
        assert "Description A" in result
        assert "skill-b" in result
        assert "Description B" in result

    # ── project-level skills ─────────────────────────────────────────

    def test_project_level_skills(self, tmp_path):
        project_dir = tmp_path / ".langcode"
        skill_dir = project_dir / "skills" / "my-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: my-skill\ndescription: Project skill\n---\n# Body\n"
        )

        config = Config(
            cwd=tmp_path,
            global_dir=tmp_path / "global",
            project_dir=project_dir,
        )
        result = load_skills(config)
        assert "my-skill" in result
        assert "Project skill" in result
        assert "Body" not in result  # progressive disclosure

    def test_project_skills_and_global_skills_both_loaded(self, tmp_path):
        global_dir = tmp_path / "global"
        gskill = global_dir / "skills" / "global-skill"
        gskill.mkdir(parents=True)
        (gskill / "SKILL.md").write_text("---\nname: global-skill\ndescription: From global\n---\n")

        project_dir = tmp_path / ".langcode"
        pskill = project_dir / "skills" / "project-skill"
        pskill.mkdir(parents=True)
        (pskill / "SKILL.md").write_text(
            "---\nname: project-skill\ndescription: From project\n---\n"
        )

        config = Config(cwd=tmp_path, global_dir=global_dir, project_dir=project_dir)
        result = load_skills(config)
        assert "global-skill" in result
        assert "project-skill" in result

    # ── references/ subdirectory support ─────────────────────────────

    def test_skill_with_references_dir(self, tmp_path):
        """Skills with references/ subdir should list ref files in output."""
        global_dir = tmp_path / "global"
        skill_dir = global_dir / "skills" / "advanced-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: advanced-skill\ndescription: Complex skill\n---\n# Core instructions\n"
        )
        refs = skill_dir / "references"
        refs.mkdir()
        (refs / "patterns.md").write_text("# Patterns\n")
        (refs / "advanced.md").write_text("# Advanced\n")

        config = Config(cwd=tmp_path, global_dir=global_dir, project_dir=tmp_path / "p")
        result = load_skills(config)
        assert "advanced-skill" in result
        assert "patterns.md" in result
        assert "advanced.md" in result
        assert "references" in result.lower()

    def test_skill_without_references_dir(self, tmp_path):
        """Skills without references/ should not mention references."""
        global_dir = tmp_path / "global"
        skill_dir = global_dir / "skills" / "simple-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("---\nname: simple-skill\ndescription: Simple\n---\n")

        config = Config(cwd=tmp_path, global_dir=global_dir, project_dir=tmp_path / "p")
        result = load_skills(config)
        assert "simple-skill" in result
        assert "References:" not in result

    # ── agents/*.md loading ──────────────────────────────────────────

    def test_loads_agents_dir(self, tmp_path):
        project_dir = tmp_path / ".langcode"
        agents_dir = project_dir / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "code-reviewer.md").write_text(
            "---\n"
            "name: code-reviewer\n"
            "description: Reviews code against project standards\n"
            "---\n"
            "# Full review instructions\n"
        )

        config = Config(
            cwd=tmp_path,
            global_dir=tmp_path / "global",
            project_dir=project_dir,
        )
        result = load_skills(config)
        assert "code-reviewer" in result
        assert "Reviews code" in result
        assert "Full review instructions" not in result
        assert "task" in result.lower()

    def test_multiple_agents(self, tmp_path):
        project_dir = tmp_path / ".langcode"
        agents_dir = project_dir / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "reviewer.md").write_text(
            "---\nname: reviewer\ndescription: Code reviewer\n---\n"
        )
        (agents_dir / "workflow.md").write_text(
            "---\nname: workflow\ndescription: Git workflow\n---\n"
        )

        config = Config(cwd=tmp_path, global_dir=tmp_path / "g", project_dir=project_dir)
        result = load_skills(config)
        assert "reviewer" in result
        assert "workflow" in result

    def test_agent_without_frontmatter(self, tmp_path):
        project_dir = tmp_path / ".langcode"
        agents_dir = project_dir / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "helper.md").write_text("# Just some instructions\n")

        config = Config(cwd=tmp_path, global_dir=tmp_path / "g", project_dir=project_dir)
        result = load_skills(config)
        assert "helper" in result

    def test_agents_show_tools_and_model(self, tmp_path):
        project_dir = tmp_path / ".langcode"
        agents_dir = project_dir / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "reviewer.md").write_text(
            "---\n"
            "name: reviewer\n"
            "description: Code review agent\n"
            "tools: [read, grep, glob]\n"
            "model: opus\n"
            "---\n"
            "Review the code.\n"
        )

        config = Config(cwd=tmp_path, global_dir=tmp_path / "g", project_dir=project_dir)
        result = load_skills(config)
        assert "reviewer" in result
        assert "read" in result
        assert "grep" in result
        assert "Model: opus" in result
        assert 'agent_name="reviewer"' in result

    def test_agents_inherit_model_not_shown(self, tmp_path):
        project_dir = tmp_path / ".langcode"
        agents_dir = project_dir / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "helper.md").write_text(
            "---\nname: helper\ndescription: A helper\nmodel: inherit\n---\n"
        )

        config = Config(cwd=tmp_path, global_dir=tmp_path / "g", project_dir=project_dir)
        result = load_skills(config)
        assert "Model:" not in result


class TestParseFrontmatterAndBody:
    def test_with_frontmatter(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_text(
            "---\n"
            "name: test-agent\n"
            "description: A test agent\n"
            "tools: [read, write]\n"
            "model: opus\n"
            "---\n"
            "# Instructions\nDo the thing.\n"
        )
        meta, body = _parse_frontmatter_and_body(f)
        assert meta is not None
        assert meta["name"] == "test-agent"
        assert meta["tools"] == ["read", "write"]
        assert meta["model"] == "opus"
        assert "# Instructions" in body
        assert "Do the thing." in body

    def test_without_frontmatter(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_text("# Just markdown\nNo frontmatter here.\n")
        meta, body = _parse_frontmatter_and_body(f)
        assert meta is None
        assert "Just markdown" in body

    def test_tools_as_comma_string(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_text("---\ntools: read, write, edit\n---\nBody\n")
        meta, body = _parse_frontmatter_and_body(f)
        assert meta["tools"] == ["read", "write", "edit"]


class TestLoadAgents:
    def test_basic_load(self, tmp_path):
        project_dir = tmp_path / ".langcode"
        agents_dir = project_dir / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "code-reviewer.md").write_text(
            "---\n"
            "name: code-reviewer\n"
            "description: Reviews code for quality\n"
            "tools: [read, grep, glob]\n"
            "model: opus\n"
            "---\n"
            "You are a code reviewer.\n"
        )

        config = Config(cwd=tmp_path, global_dir=tmp_path / "g", project_dir=project_dir)
        agents = load_agents(config)
        assert "code-reviewer" in agents
        agent = agents["code-reviewer"]
        assert agent.description == "Reviews code for quality"
        assert agent.tools == ["read", "grep", "glob"]
        assert agent.model == "opus"
        assert "code reviewer" in agent.prompt

    def test_defaults(self, tmp_path):
        project_dir = tmp_path / ".langcode"
        agents_dir = project_dir / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "simple.md").write_text("---\nname: simple\n---\nDo stuff.\n")

        config = Config(cwd=tmp_path, global_dir=tmp_path / "g", project_dir=project_dir)
        agents = load_agents(config)
        agent = agents["simple"]
        assert agent.model == "inherit"
        assert agent.tools == []
        assert agent.description == ""

    def test_no_frontmatter_uses_stem(self, tmp_path):
        project_dir = tmp_path / ".langcode"
        agents_dir = project_dir / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "my-agent.md").write_text("# Just instructions\n")

        config = Config(cwd=tmp_path, global_dir=tmp_path / "g", project_dir=project_dir)
        agents = load_agents(config)
        assert "my-agent" in agents
        assert "Just instructions" in agents["my-agent"].prompt

    def test_project_overrides_global(self, tmp_path):
        global_dir = tmp_path / "global"
        gagents = global_dir / "agents"
        gagents.mkdir(parents=True)
        (gagents / "reviewer.md").write_text(
            "---\nname: reviewer\ndescription: Global reviewer\n---\n"
        )

        project_dir = tmp_path / ".langcode"
        pagents = project_dir / "agents"
        pagents.mkdir(parents=True)
        (pagents / "reviewer.md").write_text(
            "---\nname: reviewer\ndescription: Project reviewer\n---\n"
        )

        config = Config(cwd=tmp_path, global_dir=global_dir, project_dir=project_dir)
        agents = load_agents(config)
        assert agents["reviewer"].description == "Project reviewer"

    def test_multiple_agents(self, tmp_path):
        project_dir = tmp_path / ".langcode"
        agents_dir = project_dir / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "a.md").write_text("---\nname: agent-a\n---\n")
        (agents_dir / "b.md").write_text("---\nname: agent-b\n---\n")
        (agents_dir / "readme.txt").write_text("not an agent")

        config = Config(cwd=tmp_path, global_dir=tmp_path / "g", project_dir=project_dir)
        agents = load_agents(config)
        assert "agent-a" in agents
        assert "agent-b" in agents
        assert len(agents) == 2

    def test_empty_agents_dir(self, tmp_path):
        config = Config(cwd=tmp_path, global_dir=tmp_path / "g", project_dir=tmp_path / "nope")
        agents = load_agents(config)
        assert agents == {}

    def test_path_stored(self, tmp_path):
        project_dir = tmp_path / ".langcode"
        agents_dir = project_dir / "agents"
        agents_dir.mkdir(parents=True)
        agent_file = agents_dir / "test.md"
        agent_file.write_text("---\nname: test\n---\n")

        config = Config(cwd=tmp_path, global_dir=tmp_path / "g", project_dir=project_dir)
        agents = load_agents(config)
        assert agents["test"].path == agent_file
