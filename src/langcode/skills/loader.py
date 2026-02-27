"""scan_skills: scan SKILL.md files and return skill context strings."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from langcode.core.utils import parse_frontmatter_and_body

if TYPE_CHECKING:
    from langcode.core.config import Config


def scan_skills(config: Config, plugins: list | None = None) -> list[str]:
    """Scan all skill directories and return list of skill context strings."""
    parts: list[str] = []
    seen: set[str] = set()

    skill_dirs = [config.global_dir / "skills"]
    for pdir in config.project_dirs:
        skill_dirs.append(pdir / "skills")

    for skill_dir in skill_dirs:
        _scan_dir(skill_dir, "", seen, parts)

    for plugin in plugins or []:
        for skill_source in plugin.components.skill_dirs:
            if skill_source.is_dir():
                _scan_dir(skill_source, plugin.name, seen, parts)

    return parts


def _scan_dir(skill_dir: Path, prefix: str, seen: set[str], parts: list[str]) -> None:
    if not skill_dir.is_dir():
        return
    for skill_path in sorted(skill_dir.iterdir()):
        if not skill_path.is_dir():
            continue
        skill_file = skill_path / "SKILL.md"
        if not skill_file.exists():
            continue
        meta, _ = parse_frontmatter_and_body(skill_file)
        if not meta:
            continue
        raw_name = meta.get("name", skill_path.name)
        full_name = f"{prefix}:{raw_name}" if prefix else raw_name
        if full_name in seen:
            continue
        seen.add(full_name)

        description = meta.get("description", "")
        entry = (
            f"### Skill: {full_name}\n"
            f"{description}\n"
            f"(Use `Read` on {skill_file} for full instructions)"
        )

        refs_dir = skill_path / "references"
        if refs_dir.is_dir():
            ref_files = sorted(f for f in refs_dir.iterdir() if f.is_file() and f.suffix == ".md")
            if ref_files:
                ref_lines = ", ".join(f"`{f.name}`" for f in ref_files)
                entry += f"\nReferences: {ref_lines} (in {refs_dir})"

        parts.append(entry)
