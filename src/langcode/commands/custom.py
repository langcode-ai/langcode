"""Custom command loading and expansion from commands/*.md files."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class CommandResult:
    """Structured result from expanding a custom command."""

    prompt: str
    allowed_tools: list[str] = field(default_factory=list)
    model: str = ""


def load_custom_commands(
    project_dirs: list[Path],
    plugins: list | None = None,
) -> dict[str, Path]:
    """Scan commands/ in all project dirs + plugin dirs for .md files."""
    result: dict[str, Path] = {}

    for project_dir in project_dirs:
        commands_dir = project_dir / "commands"
        if not commands_dir.is_dir():
            continue
        for f in sorted(commands_dir.iterdir()):
            if f.suffix == ".md":
                name = f"/{f.stem}"
                if name not in result:
                    result[name] = f

    for plugin in plugins or []:
        prefix = plugin.name
        for cmd_source in plugin.components.command_dirs:
            if cmd_source.is_file() and cmd_source.suffix == ".md":
                name = f"/{prefix}:{cmd_source.stem}"
                if name not in result:
                    result[name] = cmd_source
            elif cmd_source.is_dir():
                for f in sorted(cmd_source.iterdir()):
                    if f.suffix == ".md":
                        name = f"/{prefix}:{f.stem}"
                        if name not in result:
                            result[name] = f

    return result


def _parse_command_frontmatter(path: Path) -> tuple[dict, str]:
    content = path.read_text(encoding="utf-8", errors="replace")
    meta: dict = {}
    body = content
    if content.startswith("---"):
        end = content.find("---", 3)
        if end != -1:
            raw_fm = content[3:end].strip()
            body = content[end + 3 :].lstrip("\n")
            for line in raw_fm.split("\n"):
                line = line.strip()
                if ":" in line:
                    key, val = line.split(":", 1)
                    meta[key.strip()] = val.strip()
    return meta, body


_BANG_CMD_RE = re.compile(r"!`([^`]+)`")


def _expand_bang_commands(text: str) -> str:
    def _replace(m: re.Match) -> str:
        try:
            result = subprocess.run(
                m.group(1), shell=True, capture_output=True, text=True, timeout=30
            )
            return result.stdout.strip()
        except Exception:
            return f"(error running: {m.group(1)})"

    return _BANG_CMD_RE.sub(_replace, text)


def expand_custom_command(path: Path, arguments: str, cwd: Path | None = None) -> CommandResult:
    """Read a command .md file and expand it into a CommandResult."""
    meta, body = _parse_command_frontmatter(path)

    has_arg_placeholder = "$ARGUMENTS" in body or any(f"${i}" in body for i in range(1, 10))
    body = body.replace("$ARGUMENTS", arguments)
    for i, part in enumerate(arguments.split() if arguments else [], 1):
        body = body.replace(f"${i}", part)

    if not has_arg_placeholder and arguments:
        body = f"{body.rstrip()}\n\nUser request: {arguments}"

    body = _expand_bang_commands(body)

    if cwd:
        from langcode.tui.references import expand_at_references

        body = expand_at_references(body, cwd)

    allowed_tools: list[str] = []
    if at := meta.get("allowed-tools"):
        allowed_tools = [t.strip() for t in at.split(",") if t.strip()]

    return CommandResult(prompt=body, allowed_tools=allowed_tools, model=meta.get("model", ""))


def read_command_description(path: Path) -> str:
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""
    if not content.startswith("---"):
        return path.stem
    end = content.find("---", 3)
    if end == -1:
        return path.stem
    for line in content[3:end].split("\n"):
        line = line.strip()
        if line.startswith("description:"):
            return line.split(":", 1)[1].strip()
    return path.stem
