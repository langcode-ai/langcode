"""build_context: assembles agent memory + agent defs + skills into a single string."""

from __future__ import annotations

from typing import TYPE_CHECKING

from langcode.core.utils import parse_frontmatter_and_body
from langcode.skills.loader import scan_skills

if TYPE_CHECKING:
    from langcode.core.config import Config


def build_context(config: Config, plugins: list | None = None) -> str:
    """Assemble project context for injection into the system prompt.

    Combines:
      - AGENTS.md memory (project-level instructions)
      - User-defined agent definitions (agents/*.md)
      - Plugin agent definitions
      - SKILL.md metadata (progressive disclosure)
      - Plugin skill metadata
    """

    from .memory import load_memory
    from .subagent import load_agents

    parts: list[str] = []

    # ── Project memory (AGENTS.md) ────────────────────────────────────
    parts.extend(load_memory(config))

    # ── User-defined agent defs (agents/*.md) ─────────────────────────
    for name, agent_def in load_agents(config).items():
        tools_info = f"Tools: {', '.join(agent_def.tools)}\n" if agent_def.tools else ""
        model_info = (
            f"Model: {agent_def.model}\n"
            if agent_def.model and agent_def.model != "inherit"
            else ""
        )
        parts.append(
            f"### Agent: {name}\n"
            f"{agent_def.description}\n"
            f"{tools_info}{model_info}"
            f'(Use `Task` with agent_name="{name}" to delegate to this agent)'
        )

    # ── Plugin agent defs ─────────────────────────────────────────────
    for plugin in plugins or []:
        prefix = plugin.name
        for agent_source in plugin.components.agent_dirs:
            if agent_source.is_file() and agent_source.suffix == ".md":
                _append_agent_entry(agent_source, prefix, parts, parse_frontmatter_and_body)
            elif agent_source.is_dir():
                for af in sorted(agent_source.iterdir()):
                    if af.suffix == ".md":
                        _append_agent_entry(af, prefix, parts, parse_frontmatter_and_body)

    # ── Skills ────────────────────────────────────────────────────────
    parts.extend(scan_skills(config, plugins))

    return "\n\n".join(parts)


def _append_agent_entry(path, prefix, parts, parse_fn):
    meta, _ = parse_fn(path)
    name = (meta or {}).get("name", path.stem)
    full_name = f"{prefix}:{name}" if prefix else name
    desc = (meta or {}).get("description", "")
    tools_val = (meta or {}).get("tools", [])
    if isinstance(tools_val, str):
        tools_val = [t.strip() for t in tools_val.split(",") if t.strip()]
    tools_info = f"Tools: {', '.join(tools_val)}\n" if tools_val else ""
    model = (meta or {}).get("model", "inherit")
    model_info = f"Model: {model}\n" if model and model != "inherit" else ""
    parts.append(
        f"### Agent: {full_name}\n"
        f"{desc}\n"
        f"{tools_info}{model_info}"
        f'(Use `Task` with subagent_type="{full_name}" to delegate to this agent)'
    )
