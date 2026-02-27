"""glob - Find files matching a pattern."""

from __future__ import annotations

from pathlib import Path

from langchain.tools import tool

from ..core.utils import resolve_path, truncate


@tool("Glob")
def glob_tool(pattern: str, path: str = ".") -> str:
    """Fast file pattern matching tool that works with any codebase size. Returns matching file paths sorted by modification time.

    Args:
        pattern: The glob pattern to match files against (e.g. '**/*.py', 'src/**/*.ts', '*.json').
        path: The directory to search in. If not specified, the current working directory will be used.
              IMPORTANT: Omit this field to use the default directory. DO NOT enter "undefined" or "null" — simply omit it for the default behavior.

    Usage:
    - Use this tool when you need to find files by name patterns.
    - Results are capped at 500 matches, sorted by modification time (newest first).
    - You can call multiple Glob tools in parallel to speculatively search multiple patterns at once.
    - For open-ended searches requiring multiple rounds, consider using the Task tool instead."""
    base = resolve_path(path)
    if not base.exists():
        return f"Error: path not found: {path}"

    matches = list(base.glob(pattern))
    # sort by mtime descending (newest first)
    matches.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    if not matches:
        return f"No files matching '{pattern}' in {path}"

    cwd = Path.cwd()
    lines = []
    for m in matches[:500]:  # cap at 500
        try:
            rel = m.relative_to(cwd)
        except ValueError:
            rel = m
        lines.append(str(rel))

    result = "\n".join(lines)
    if len(matches) > 500:
        result += f"\n\n... and {len(matches) - 500} more files"
    return truncate(result)
