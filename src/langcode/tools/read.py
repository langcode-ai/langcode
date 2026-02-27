"""read - Read file content with line numbers."""

from __future__ import annotations

from langchain.tools import tool

from ..core.utils import format_lines, resolve_path, truncate


@tool("Read")
def read(file_path: str, offset: int = 0, limit: int = 0, pages: str = "") -> str:
    """Read file content from the local filesystem. Returns lines with line numbers (e.g. '  1|content').

    Args:
        file_path: The absolute path to the file to read. Must be an absolute path, not a relative path.
        offset: The line number to start reading from. Only provide if the file is too large to read at once.
        limit: The number of lines to read. Only provide if the file is too large to read at once.
        pages: Page range for PDF files (e.g., "1-5", "3", "10-20"). Only applicable to PDF files. Maximum 20 pages per request.

    Usage:
    - You MUST read a file before editing it to understand its current content.
    - Use offset and limit for large files to read specific sections.
    - Lines in output are numbered for easy reference when using Edit.
    - You can call multiple Read tools in parallel to read multiple files at once."""
    path = resolve_path(file_path)
    if not path.exists():
        return f"Error: file not found: {file_path}"
    if not path.is_file():
        return f"Error: not a file: {file_path}"

    content = path.read_text(encoding="utf-8", errors="replace")
    lines = content.split("\n")

    if offset > 0:
        lines = lines[offset:]
    if limit > 0:
        lines = lines[:limit]

    result = format_lines("\n".join(lines), offset=offset)
    return truncate(result)
