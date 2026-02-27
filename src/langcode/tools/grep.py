"""grep - Search file contents with regex."""

from __future__ import annotations

import fnmatch
import os
import re
from pathlib import Path
from typing import Literal

from langchain.tools import tool

from ..core.utils import resolve_path, truncate

MAX_MATCHES = 500


@tool("Grep")
def grep(
    pattern: str,
    path: str = ".",
    glob: str = "",
    output_mode: Literal["content", "files_with_matches", "count"] = "files_with_matches",
    n: bool = True,
    i: bool = False,
    A: int = 0,
    B: int = 0,
    C: int = 0,
    context: int = 0,
    type: str = "",
    head_limit: int = 0,
    offset: int = 0,
    multiline: bool = False,
) -> str:
    """A powerful search tool built on Python regex.

    Usage:
    - ALWAYS use Grep for search tasks. NEVER invoke grep or rg as a Bash command.
    - Supports full regex syntax (e.g., "log.*Error", "function\\s+\\w+")
    - Filter files with glob parameter (e.g., "*.js", "**/*.tsx") or type parameter (e.g., "js", "py", "rust")
    - Output modes: "content" shows matching lines (supports -A/-B/-C context, -n line numbers, head_limit), "files_with_matches" shows file paths (supports head_limit), "count" shows match counts (supports head_limit). Defaults to "files_with_matches".
    - Use Task tool for open-ended searches requiring multiple rounds

    Args:
        pattern: The regular expression pattern to search for in file contents.
        path: File or directory to search in. Defaults to current working directory.
        glob: Glob pattern to filter files (e.g. "*.js", "*.{ts,tsx}").
        output_mode: Output mode: "content" shows matching lines, "files_with_matches" shows file paths only, "count" shows match counts. Defaults to "files_with_matches".
        n: Show line numbers in output. Requires output_mode "content", ignored otherwise. Defaults to true.
        i: Case insensitive search.
        A: Number of lines to show after each match. Requires output_mode "content", ignored otherwise.
        B: Number of lines to show before each match. Requires output_mode "content", ignored otherwise.
        C: Alias for context — lines to show before and after each match.
        context: Number of lines to show before and after each match. Requires output_mode "content", ignored otherwise.
        type: File type to search. Common types: js, py, rust, go, java, ts, css, html, json, md. More efficient than glob for standard file types.
        head_limit: Limit output to first N lines/entries, equivalent to "| head -N". Works across all output modes. Defaults to 0 (unlimited).
        offset: Skip first N lines/entries before applying head_limit. Defaults to 0.
        multiline: Enable multiline mode where . matches newlines and patterns can span lines. Default: false."""

    # Type → glob mapping for common file types
    TYPE_GLOBS: dict[str, str] = {
        "py": "*.py",
        "python": "*.py",
        "js": "*.js",
        "javascript": "*.js",
        "ts": "*.ts",
        "typescript": "*.ts",
        "tsx": "*.tsx",
        "jsx": "*.jsx",
        "go": "*.go",
        "rs": "*.rs",
        "rust": "*.rs",
        "java": "*.java",
        "c": "*.c",
        "cpp": "*.cpp",
        "cs": "*.cs",
        "rb": "*.rb",
        "ruby": "*.rb",
        "php": "*.php",
        "css": "*.css",
        "html": "*.html",
        "json": "*.json",
        "yaml": "*.yaml",
        "yml": "*.yml",
        "md": "*.md",
        "markdown": "*.md",
        "sh": "*.sh",
        "bash": "*.sh",
        "toml": "*.toml",
        "xml": "*.xml",
        "sql": "*.sql",
    }

    effective_glob = glob
    if type and not effective_glob:
        effective_glob = TYPE_GLOBS.get(type.lower(), f"*.{type}")

    base = resolve_path(path)
    if not base.exists():
        return f"Error: path not found: {path}"

    flags = 0
    if i:
        flags |= re.IGNORECASE
    if multiline:
        flags |= re.MULTILINE | re.DOTALL

    try:
        regex = re.compile(pattern, flags)
    except re.error as e:
        return f"Error: invalid regex: {e}"

    # Resolve context lines
    before = B if B else (C if C else context)
    after = A if A else (C if C else context)

    cwd = Path.cwd()

    def _rel(file_path: Path) -> str:
        try:
            return str(file_path.relative_to(cwd))
        except ValueError:
            return str(file_path)

    def _search_file(file_path: Path) -> list[str]:
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except (PermissionError, OSError):
            return []

        rel = _rel(file_path)

        if output_mode == "files_with_matches":
            return [rel] if regex.search(content) else []

        if output_mode == "count":
            if multiline:
                count = len(regex.findall(content))
            else:
                count = sum(1 for line in content.split("\n") if regex.search(line))
            return [f"{rel}:{count}"] if count else []

        # content mode
        lines = content.split("\n")
        matched_indices: set[int] = set()
        for idx, line in enumerate(lines):
            if regex.search(line):
                matched_indices.add(idx)

        if not matched_indices:
            return []

        shown: set[int] = set()
        results: list[str] = []
        for idx in sorted(matched_indices):
            start = max(0, idx - before)
            end = min(len(lines) - 1, idx + after)
            for j in range(start, end + 1):
                if j not in shown:
                    shown.add(j)
                    prefix = f"{rel}:{j + 1}:" if n else f"{rel}:"
                    results.append(f"{prefix}{lines[j].rstrip()}")
        return results

    def _matches_glob(filename: str) -> bool:
        if not effective_glob:
            return True
        patterns = [
            p.strip()
            for p in effective_glob.replace("{", "").replace("}", "").split(",")
            if p.strip()
        ]
        return any(fnmatch.fnmatch(filename, p) for p in patterns)

    all_results: list[str] = []

    if base.is_file():
        all_results = _search_file(base)
    else:
        for root, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for f in sorted(files):
                if f.startswith("."):
                    continue
                if not _matches_glob(f):
                    continue
                all_results.extend(_search_file(Path(root) / f))
                if len(all_results) >= MAX_MATCHES * 2:
                    break

    if not all_results:
        return f"No matches for '{pattern}' in {path}"

    # Apply offset then head_limit
    if offset > 0:
        all_results = all_results[offset:]
    if head_limit > 0:
        all_results = all_results[:head_limit]
    elif len(all_results) > MAX_MATCHES:
        all_results = all_results[:MAX_MATCHES]
        all_results.append(f"\n... (capped at {MAX_MATCHES} matches)")

    return truncate("\n".join(all_results))
