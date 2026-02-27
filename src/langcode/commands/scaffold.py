"""Project scaffolding: /init command and INIT_PROMPT."""

from __future__ import annotations

import json
from pathlib import Path

COMMANDS = {
    "/init": "Initialize .langcode/ project config in current directory",
    "/mcp": "Show MCP server status",
    "/plugin": "Manage plugins (interactive UI)",
    "/new": "Start a new session",
    "/resume": "Resume a previous session",
    "/clear": "Alias for /new",
    "/model": "Switch model (e.g. /model claude-sonnet-4-20250514)",
    "/cost": "Show token usage and estimated cost",
    "/plan": "Switch to plan mode (read-only, no file changes)",
    "/act": "Switch to act mode (full tool access)",
    "/help": "Show available commands",
    "/quit": "Exit LangCode",
}

_DEFAULT_SETTINGS: dict = {
    "model": "anthropic:claude-sonnet-4-5-20250929",
}

_GITIGNORE = """\
settings.local.json
"""

INIT_PROMPT = """\
Analyze this project and generate an AGENTS.md file at the project root.

## Instructions

1. **Explore the project structure** using tools (list files, read key config files like \
package.json, pyproject.toml, Cargo.toml, go.mod, Makefile, etc.)
2. **Identify**:
   - Programming language(s) and framework(s)
   - Project structure and key directories
   - Build/test/lint commands
   - Code conventions and patterns
   - Important configuration
3. **Write AGENTS.md** at the project root with the analysis results.

## AGENTS.md Format

```markdown
# Project

## Overview
{1-2 sentences: what this project is and its core tech stack}

## Structure
{Key directories and their purposes — only non-obvious ones}

## Commands
{Dev, test, build, lint commands — the ones that actually exist}

## Code Style
{Actual conventions found in the codebase, not generic advice}

## Important Notes
{Gotchas, anti-patterns, or anything an AI assistant should know}
```

## Rules
- Keep it concise: 50-150 lines max
- Only include project-specific information, not generic advice
- If AGENTS.md already exists, read it first and update/improve it
- Use the project's actual commands and conventions, don't guess
"""


def init_project(cwd: Path | None = None) -> list[str]:
    """Scaffold .langcode/ directory. Returns list of created paths."""
    cwd = cwd or Path.cwd()
    project_dir = cwd / ".langcode"
    created: list[str] = []

    project_dir.mkdir(parents=True, exist_ok=True)

    settings_path = project_dir / "settings.json"
    if not settings_path.exists():
        settings_path.write_text(json.dumps(_DEFAULT_SETTINGS, indent=2) + "\n")
        created.append(str(settings_path.relative_to(cwd)))

    gi_path = project_dir / ".gitignore"
    if not gi_path.exists():
        gi_path.write_text(_GITIGNORE)
        created.append(str(gi_path.relative_to(cwd)))

    skills_dir = project_dir / "skills"
    if not skills_dir.exists():
        skills_dir.mkdir()
        created.append(str(skills_dir.relative_to(cwd)) + "/")

    return created
