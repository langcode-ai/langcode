"""edit - Replace exact string in a file."""

from __future__ import annotations

from langchain.tools import tool

from ..core.utils import resolve_path


@tool("Edit")
def edit(file_path: str, old_string: str, new_string: str, replace_all: bool = False) -> str:
    """Performs exact string replacements in files.

    Usage:
    - You must use the Read tool at least once before editing. This tool will error if you attempt an edit without reading the file.
    - When editing text from Read tool output, ensure you preserve the exact indentation (tabs/spaces) as it appears AFTER the line number prefix. Never include any part of the line number prefix in the old_string or new_string.
    - ALWAYS prefer editing existing files. NEVER write new files unless explicitly required.
    - The edit will FAIL if old_string is not unique in the file. Either provide a larger string with more surrounding context to make it unique, or use replace_all to change every instance.
    - Use replace_all for replacing and renaming strings across the file (e.g. renaming a variable).
    - ALWAYS prefer Edit over Write for modifying existing files.

    Args:
        file_path: The absolute path to the file to modify.
        old_string: The text to replace. Must match the file content exactly, including indentation.
        new_string: The text to replace it with (must be different from old_string).
        replace_all: Replace all occurrences of old_string (default false)."""
    path = resolve_path(file_path)
    if not path.exists():
        return f"Error: file not found: {file_path}"

    content = path.read_text(encoding="utf-8", errors="replace")
    count = content.count(old_string)

    if count == 0:
        return f"Error: old_string not found in {file_path}"
    if count > 1 and not replace_all:
        return (
            f"Error: old_string found {count} times. Use replace_all=True or provide more context."
        )

    if replace_all:
        new_content = content.replace(old_string, new_string)
    else:
        new_content = content.replace(old_string, new_string, 1)

    path.write_text(new_content, encoding="utf-8")
    replaced = count if replace_all else 1
    return f"Replaced {replaced} occurrence(s) in {file_path}"
