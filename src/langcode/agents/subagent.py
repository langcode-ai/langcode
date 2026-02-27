"""Sub-agent definition dataclass and loader for agents/*.md files."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from langcode.core.utils import parse_frontmatter_and_body

if TYPE_CHECKING:
    from langcode.core.config import Config


@dataclass
class AgentDef:
    """A sub-agent definition loaded from agents/*.md."""

    name: str
    description: str = ""
    model: str = "inherit"
    tools: list[str] = field(default_factory=list)
    prompt: str = ""
    path: Path | None = None


def load_agents(config: Config) -> dict[str, AgentDef]:
    """Load user-defined agent definitions from agents/*.md.

    Search order: global_dir → project_dirs. Later dirs override earlier.
    """
    agents: dict[str, AgentDef] = {}
    for parent in [config.global_dir, *config.project_dirs]:
        agents_dir = parent / "agents"
        if not agents_dir.is_dir():
            continue
        for agent_file in sorted(agents_dir.iterdir()):
            if agent_file.suffix != ".md":
                continue
            meta, body = parse_frontmatter_and_body(agent_file)
            name = (meta or {}).get("name", agent_file.stem)
            tools_val = _normalise_tools((meta or {}).get("tools", []))
            agents[name] = AgentDef(
                name=name,
                description=(meta or {}).get("description", ""),
                model=(meta or {}).get("model", "inherit"),
                tools=tools_val,
                prompt=body.strip(),
                path=agent_file,
            )
    return agents


def load_builtin_agents() -> dict[str, AgentDef]:
    """Load built-in agents from agents/built-in/."""
    agents: dict[str, AgentDef] = {}
    builtin_dir = Path(__file__).parent / "built-in"
    if not builtin_dir.is_dir():
        return agents
    for agent_file in sorted(builtin_dir.iterdir()):
        if agent_file.suffix != ".md":
            continue
        meta, body = parse_frontmatter_and_body(agent_file)
        name = (meta or {}).get("name", agent_file.stem)
        tools_val = _normalise_tools((meta or {}).get("tools", []))
        agents[name] = AgentDef(
            name=name,
            description=(meta or {}).get("description", ""),
            model=(meta or {}).get("model", "inherit"),
            tools=tools_val,
            prompt=body.strip(),
            path=agent_file,
        )
    return agents


def _normalise_tools(val) -> list[str]:
    if isinstance(val, str):
        return [t.strip() for t in val.split(",") if t.strip()]
    return list(val) if val else []
