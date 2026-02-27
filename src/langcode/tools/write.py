"""write - Create or overwrite a file."""

from __future__ import annotations

from langchain.tools import tool

from ..core.utils import resolve_path


@tool("Write")
def write(file_path: str, content: str) -> str:
    """Create or overwrite a file with the given content. Parent directories are created automatically.

    Args:
        file_path: The absolute path to the file to write (must be absolute, not relative).
        content: The full content to write to the file.

    Usage:
    - This tool will OVERWRITE the existing file if one exists at the path.
    - If this is an existing file, you MUST use the Read tool first to read the file's contents. This tool will fail if you did not read the file first.
    - ALWAYS prefer editing existing files with Edit. NEVER use Write unless creating a new file or doing a full rewrite.
    - NEVER proactively create documentation files (*.md) or README files unless explicitly requested."""
    path = resolve_path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return f"Wrote {len(content)} bytes to {file_path}"
