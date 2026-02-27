"""Claude Code-compatible marketplace system.

Handles marketplace.json parsing, marketplace add/remove/update,
and plugin source resolution (local path, GitHub, git URL).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from rich.console import Console

if TYPE_CHECKING:
    from langcode.core.config import Config
    from langcode.plugins.models import Plugin

console = Console()


# ── Data models ─────────────────────────────────────────────────────


@dataclass
class PluginEntry:
    """A plugin listing inside a marketplace.json."""

    name: str
    source: str | dict = ""  # relative path, GitHub spec, or git URL
    description: str = ""
    version: str = ""
    author: dict[str, str] = field(default_factory=dict)
    homepage: str = ""
    keywords: list[str] = field(default_factory=list)
    category: str = ""


@dataclass
class Marketplace:
    """A parsed marketplace.json."""

    name: str
    owner: dict[str, str] = field(default_factory=dict)
    plugins: list[PluginEntry] = field(default_factory=list)
    description: str = ""
    source_type: str = ""  # "local", "github", "git"
    source_ref: str = ""  # original source (path, owner/repo, URL)
    local_path: Path | None = None  # where the marketplace is stored


# ── Marketplace cache ───────────────────────────────────────────────


def _marketplace_cache_dir(config: Config) -> Path:
    return config.global_dir / "marketplaces"


def _marketplace_meta_path(config: Config) -> Path:
    return config.global_dir / "marketplaces" / "_marketplaces.json"


def _load_marketplace_meta(config: Config) -> dict:
    """Load marketplace metadata (sources, names, etc.)."""
    path = _marketplace_meta_path(config)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _save_marketplace_meta(config: Config, meta: dict) -> None:
    path = _marketplace_meta_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(meta, indent=2) + "\n")


# ── Parse marketplace.json ──────────────────────────────────────────


def _parse_marketplace_json(path: Path) -> Marketplace | None:
    """Parse a marketplace.json file."""
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None

    name = data.get("name", "")
    if not name:
        return None

    plugins = []
    for entry in data.get("plugins", []):
        if not isinstance(entry, dict):
            continue
        pname = entry.get("name", "")
        if not pname:
            continue
        plugins.append(
            PluginEntry(
                name=pname,
                source=entry.get("source", ""),
                description=entry.get("description", ""),
                version=entry.get("version", ""),
                author=entry.get("author", {}),
                homepage=entry.get("homepage", ""),
                keywords=entry.get("keywords", []),
                category=entry.get("category", ""),
            )
        )

    desc = ""
    metadata = data.get("metadata", {})
    if isinstance(metadata, dict):
        desc = metadata.get("description", "")

    return Marketplace(
        name=name,
        owner=data.get("owner", {}),
        plugins=plugins,
        description=desc,
    )


def _find_marketplace_json(root: Path) -> Path | None:
    """Find marketplace.json in standard locations."""
    # .claude-plugin/marketplace.json (Claude Code standard)
    p = root / ".claude-plugin" / "marketplace.json"
    if p.exists():
        return p
    # marketplace.json at root
    p = root / "marketplace.json"
    if p.exists():
        return p
    return None


# ── Source resolution ───────────────────────────────────────────────


def _is_github_ref(source: str) -> bool:
    """Check if source looks like owner/repo."""
    parts = source.strip().split("/")
    return (
        len(parts) == 2
        and all(p and not p.startswith("-") for p in parts)
        and not source.startswith(".")
        and not source.startswith("/")
        and ":" not in source
    )


def _is_git_url(source: str) -> bool:
    return source.endswith(".git") or source.startswith("git@")


def _clone_source(source: str, dest: Path) -> bool:
    """Clone a git source (GitHub or URL) to dest. Returns success."""
    if _is_github_ref(source):
        # Split ref if present (owner/repo#ref)
        ref = ""
        if "#" in source:
            source, ref = source.rsplit("#", 1)
        url = f"https://github.com/{source}.git"
        cmd = ["git", "clone", "--depth", "1"]
        if ref:
            cmd.extend(["--branch", ref])
        cmd.extend([url, str(dest)])
    elif _is_git_url(source):
        ref = ""
        if "#" in source:
            source, ref = source.rsplit("#", 1)
        cmd = ["git", "clone", "--depth", "1"]
        if ref:
            cmd.extend(["--branch", ref])
        cmd.extend([source, str(dest)])
    else:
        return False

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


# ── Marketplace management ──────────────────────────────────────────


def add_marketplace(config: Config, source: str) -> Marketplace | None:
    """Add a marketplace from a source (local path, GitHub, git URL).

    Returns the parsed Marketplace on success, None on failure.
    """
    cache_dir = _marketplace_cache_dir(config)
    cache_dir.mkdir(parents=True, exist_ok=True)

    source = source.strip()
    source_path = Path(source).resolve()

    # ── Local path ──
    if source_path.is_dir():
        mj = _find_marketplace_json(source_path)
        if not mj:
            console.print(f"no marketplace.json found in {source_path}", style="bold")
            return None
        marketplace = _parse_marketplace_json(mj)
        if not marketplace:
            console.print("failed to parse marketplace.json", style="bold")
            return None
        # Copy to cache
        dest = cache_dir / marketplace.name
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(source_path, dest, symlinks=True)
        marketplace.source_type = "local"
        marketplace.source_ref = str(source_path)
        marketplace.local_path = dest
        _register_marketplace(config, marketplace)
        return marketplace

    if source_path.is_file() and source_path.name == "marketplace.json":
        marketplace = _parse_marketplace_json(source_path)
        if not marketplace:
            console.print("failed to parse marketplace.json", style="bold")
            return None
        dest = cache_dir / marketplace.name
        dest.mkdir(parents=True, exist_ok=True)
        cp_dir = dest / ".claude-plugin"
        cp_dir.mkdir(exist_ok=True)
        shutil.copy2(source_path, cp_dir / "marketplace.json")
        marketplace.source_type = "local"
        marketplace.source_ref = str(source_path.parent)
        marketplace.local_path = dest
        _register_marketplace(config, marketplace)
        return marketplace

    # ── GitHub or git URL ──
    if _is_github_ref(source) or _is_git_url(source):
        # Clone to temp, then move
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp) / "repo"
            if not _clone_source(source, tmp_path):
                console.print(f"failed to clone {source}", style="bold")
                return None
            mj = _find_marketplace_json(tmp_path)
            if not mj:
                console.print(f"no marketplace.json in {source}", style="bold")
                return None
            marketplace = _parse_marketplace_json(mj)
            if not marketplace:
                console.print("failed to parse marketplace.json", style="bold")
                return None
            dest = cache_dir / marketplace.name
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(tmp_path, dest, symlinks=True)
            marketplace.source_type = "github" if _is_github_ref(source) else "git"
            marketplace.source_ref = source
            marketplace.local_path = dest
            _register_marketplace(config, marketplace)
            return marketplace

    console.print(f"unknown marketplace source: {source}", style="bold")
    return None


def remove_marketplace(config: Config, name: str) -> bool:
    """Remove a marketplace by name. Returns True if found."""
    cache_dir = _marketplace_cache_dir(config)
    dest = cache_dir / name
    if dest.exists():
        shutil.rmtree(dest)

    meta = _load_marketplace_meta(config)
    markets = meta.get("marketplaces", {})
    if name in markets:
        del markets[name]
        meta["marketplaces"] = markets
        _save_marketplace_meta(config, meta)
        return True
    return dest.exists()


def update_marketplace(config: Config, name: str) -> Marketplace | None:
    """Update a marketplace by re-fetching from its original source."""
    meta = _load_marketplace_meta(config)
    markets = meta.get("marketplaces", {})
    info = markets.get(name)
    if not info:
        return None
    source = info.get("source_ref", "")
    if not source:
        return None
    return add_marketplace(config, source)


def list_marketplaces(config: Config) -> list[Marketplace]:
    """List all registered marketplaces."""
    result: list[Marketplace] = []
    cache_dir = _marketplace_cache_dir(config)

    meta = _load_marketplace_meta(config)
    markets = meta.get("marketplaces", {})

    for name, info in markets.items():
        local = cache_dir / name
        mj = _find_marketplace_json(local) if local.is_dir() else None
        marketplace = _parse_marketplace_json(mj) if mj else None
        if marketplace:
            marketplace.source_type = info.get("source_type", "")
            marketplace.source_ref = info.get("source_ref", "")
            marketplace.local_path = local
            result.append(marketplace)
        else:
            # Placeholder for broken/missing marketplace
            result.append(
                Marketplace(
                    name=name,
                    source_type=info.get("source_type", ""),
                    source_ref=info.get("source_ref", ""),
                )
            )

    # Also check extraKnownMarketplaces from config
    for name, info in config.known_marketplaces.items():
        if any(m.name == name for m in result):
            continue
        source_info = info.get("source", info)
        result.append(
            Marketplace(
                name=name,
                source_type=source_info.get("source", ""),
                source_ref=source_info.get("repo", source_info.get("url", "")),
            )
        )

    return result


def discover_plugins(config: Config) -> list[tuple[str, PluginEntry]]:
    """Discover all available plugins from all marketplaces.

    Returns list of (marketplace_name, PluginEntry).
    """
    result: list[tuple[str, PluginEntry]] = []
    for marketplace in list_marketplaces(config):
        for plugin in marketplace.plugins:
            result.append((marketplace.name, plugin))
    return result


# ── Install plugin from marketplace ─────────────────────────────────


def install_from_marketplace(
    config: Config,
    plugin_name: str,
    marketplace_name: str,
    scope: str = "user",
) -> Plugin | None:
    """Install a plugin from a marketplace. Returns Plugin on success."""
    from langcode.plugins import install_plugin_from_path

    cache_dir = _marketplace_cache_dir(config)
    market_dir = cache_dir / marketplace_name

    # Find the marketplace
    mj = _find_marketplace_json(market_dir) if market_dir.is_dir() else None
    marketplace = _parse_marketplace_json(mj) if mj else None
    if not marketplace:
        console.print(f"marketplace '{marketplace_name}' not found", style="bold")
        return None

    # Find the plugin entry
    entry = None
    for p in marketplace.plugins:
        if p.name == plugin_name:
            entry = p
            break
    if not entry:
        console.print(
            f"plugin '{plugin_name}' not found in {marketplace_name}",
            style="bold",
        )
        return None

    # Resolve source
    source = entry.source
    if isinstance(source, str) and source.startswith("./"):
        # Relative path within marketplace
        plugin_dir = market_dir / source.lstrip("./")
        if not plugin_dir.is_dir():
            console.print(f"plugin source not found: {plugin_dir}", style="bold")
            return None
        return install_plugin_from_path(config, plugin_dir, scope, marketplace_name)

    elif isinstance(source, dict):
        src_type = source.get("source", "")
        if src_type == "github":
            repo = source.get("repo", "")
            if not repo:
                console.print("plugin source missing 'repo'", style="bold")
                return None
            ref = source.get("ref", "")
            import tempfile

            with tempfile.TemporaryDirectory() as tmp:
                tmp_path = Path(tmp) / "plugin"
                git_source = f"{repo}#{ref}" if ref else repo
                if not _clone_source(git_source, tmp_path):
                    console.print(f"failed to clone {repo}", style="bold")
                    return None
                return install_plugin_from_path(config, tmp_path, scope, marketplace_name)
        elif src_type in ("url", "git"):
            url = source.get("url", "")
            if not url:
                console.print("plugin source missing 'url'", style="bold")
                return None
            ref = source.get("ref", "")
            import tempfile

            with tempfile.TemporaryDirectory() as tmp:
                tmp_path = Path(tmp) / "plugin"
                git_source = f"{url}#{ref}" if ref else url
                if not _clone_source(git_source, tmp_path):
                    console.print(f"failed to clone {url}", style="bold")
                    return None
                return install_plugin_from_path(config, tmp_path, scope, marketplace_name)

    elif isinstance(source, str) and (_is_github_ref(source) or _is_git_url(source)):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp) / "plugin"
            if not _clone_source(source, tmp_path):
                console.print(f"failed to clone {source}", style="bold")
                return None
            return install_plugin_from_path(config, tmp_path, scope, marketplace_name)

    console.print(f"unsupported plugin source: {source}", style="bold")
    return None


# ── Helpers ─────────────────────────────────────────────────────────


def _register_marketplace(config: Config, marketplace: Marketplace) -> None:
    """Register a marketplace in the metadata file."""
    meta = _load_marketplace_meta(config)
    markets = meta.get("marketplaces", {})
    markets[marketplace.name] = {
        "source_type": marketplace.source_type,
        "source_ref": marketplace.source_ref,
    }
    meta["marketplaces"] = markets
    _save_marketplace_meta(config, meta)
