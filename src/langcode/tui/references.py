"""@ file/directory reference: inline expansion for user messages."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

_MAX_FILE_SIZE = 100_000  # characters


def list_project_files(cwd: Path) -> list[str]:
    """List all project files respecting .gitignore. Tries rg, then git."""
    return _list_rg(cwd) or _list_git(cwd) or []


def _list_rg(cwd: Path) -> list[str] | None:
    try:
        r = subprocess.run(
            ["rg", "--files", "--sort=path", "--no-messages"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=cwd,
        )
        if r.returncode <= 1 and r.stdout.strip():
            return r.stdout.strip().splitlines()
    except FileNotFoundError:
        pass
    except Exception:
        pass
    return None


def _list_git(cwd: Path) -> list[str] | None:
    try:
        r = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=cwd,
        )
        if r.returncode == 0 and r.stdout.strip():
            files = r.stdout.strip().splitlines()
            files.sort()
            return files
    except FileNotFoundError:
        pass
    except Exception:
        pass
    return None


def _list_dir(full: Path, rel_path: str) -> str | None:
    """List file paths in a directory without reading contents."""
    files = list_project_files(full)
    if not files:
        return None
    prefix = rel_path.rstrip("/") + "/"
    listing = "\n".join(prefix + f for f in files if (full / f).is_file())
    return f'<directory path="{rel_path}">\n{listing}\n</directory>' if listing else None


def expand_at_references(text: str, cwd: Path) -> str:
    """Expand @filepath or @dir/ references by inlining file content."""

    def _replace(m: re.Match) -> str:
        rel_path = m.group(1)
        try:
            full = (cwd / rel_path).resolve()
        except Exception:
            return m.group(0)
        # safety: must be within cwd
        cwd_resolved = cwd.resolve()
        if not (full == cwd_resolved or str(full).startswith(str(cwd_resolved) + "/")):
            return m.group(0)

        if full.is_dir():
            return _list_dir(full, rel_path) or m.group(0)

        if full.is_file():
            try:
                content = full.read_text(encoding="utf-8", errors="replace")
            except Exception:
                return f'<file path="{rel_path}" />'
            if len(content) > _MAX_FILE_SIZE:
                content = content[:_MAX_FILE_SIZE] + "\n[truncated]"
            return f'<file path="{rel_path}">\n{content}\n</file>'

        return m.group(0)

    return re.sub(r"(?:^|(?<=\s))@([\w./\-]+)", _replace, text)
