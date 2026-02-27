"""Project memory: load AGENTS.md files for injection into the agent's context."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langcode.core.config import Config


def load_memory(config: Config) -> list[str]:
    """Load all AGENTS.md files (global → project → cwd).

    Returns a list of non-empty content strings, each prefixed with its path.
    Later files take priority conceptually but all are included.
    """
    candidates = [
        config.global_dir / "AGENTS.md",
        *[pdir / "AGENTS.md" for pdir in config.project_dirs],
        config.cwd / "AGENTS.md",
    ]

    seen: set[Path] = set()
    parts: list[str] = []
    for path in candidates:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if path.exists():
            content = path.read_text(encoding="utf-8", errors="replace").strip()
            if content:
                parts.append(f"### {path}\n{content}")
    return parts
