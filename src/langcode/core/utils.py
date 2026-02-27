"""Path helpers, output truncation, line number formatting, frontmatter parsing."""

from __future__ import annotations

import subprocess
from pathlib import Path


def parse_frontmatter(raw: str) -> dict:
    meta: dict = {}
    for line in raw.split("\n"):
        line = line.strip()
        if ":" in line:
            key, val = line.split(":", 1)
            key = key.strip()
            val = val.strip()
            if val.startswith("[") or key in ("triggers", "tools"):
                if val.startswith("["):
                    val = val.strip("[]")
                items = [v.strip().strip("'\"") for v in val.split(",") if v.strip()]
                meta[key] = items
            else:
                meta[key] = val
    return meta


def parse_frontmatter_and_body(path: Path) -> tuple[dict | None, str]:
    content = path.read_text(encoding="utf-8", errors="replace")
    if not content.startswith("---"):
        return None, content
    end = content.find("---", 3)
    if end == -1:
        return None, content
    frontmatter = content[3:end].strip()
    body = content[end + 3 :]
    return parse_frontmatter(frontmatter), body


MAX_OUTPUT_BYTES = 100 * 1024  # 100KB


def resolve_path(path: str, cwd: Path | None = None) -> Path:
    """Resolve *path* relative to *cwd* (default: ``Path.cwd()``)."""
    cwd = cwd or Path.cwd()
    return (cwd / path).resolve()


def safe_path(path: str, cwd: Path | None = None) -> Path:
    """Resolve *path* relative to *cwd*, raising ValueError on traversal."""
    base = (cwd or Path.cwd()).resolve()
    resolved = (base / path).resolve()
    if base not in resolved.parents and resolved != base:
        raise ValueError(f"Path traversal detected: {path!r} escapes {base}")
    return resolved


def format_lines(content: str, offset: int = 0) -> str:
    """Add line numbers: '1|content'."""
    lines = content.split("\n")
    start = offset + 1
    width = len(str(start + len(lines) - 1))
    return "\n".join(f"{start + i:>{width}}|{line}" for i, line in enumerate(lines))


def truncate(text: str, max_bytes: int = MAX_OUTPUT_BYTES) -> str:
    """Truncate text to max_bytes."""
    encoded = text.encode("utf-8", errors="replace")
    if len(encoded) <= max_bytes:
        return text
    truncated = encoded[:max_bytes].decode("utf-8", errors="ignore")
    return truncated + f"\n\n... [truncated, {len(encoded)} bytes total]"


def human_size(size: int) -> str:
    """Format bytes to human readable."""
    for unit in ("B", "KB", "MB", "GB"):
        if abs(size) < 1024:
            return f"{size:.1f}{unit}" if unit != "B" else f"{size}{unit}"
        size /= 1024  # type: ignore
    return f"{size:.1f}TB"


def git_branch() -> str | None:
    """Return current git branch name, or None if not in a repo."""
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        return r.stdout.strip() if r.returncode == 0 else None
    except Exception:
        return None


def short_cwd(p: Path) -> str:
    """Return path relative to home directory, using ~ prefix."""
    try:
        rel = p.relative_to(Path.home())
        return f"~/{rel}" if str(rel) != "." else "~"
    except ValueError:
        return str(p)


def model_name(model: str) -> str:
    """Strip provider prefix from model string (e.g. 'anthropic:claude-3' → 'claude-3')."""
    return model.split(":")[-1] if ":" in model else model
