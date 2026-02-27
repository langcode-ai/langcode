"""CLI entry point + prompt-toolkit REPL + Rich streaming output."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import click
from rich.console import Console
from rich.text import Text

from .agents import create_main_agent, create_sqlite_checkpointer
from .agents.context import build_context
from .commands import CommandHandler, CommandResult, init_project
from .core.config import load_config
from .core.utils import git_branch as _git_branch
from .core.utils import model_name as _model_name
from .core.utils import short_cwd as _short_cwd
from .mcp import MCPManager
from .tui import run_repl, stream_agent_response

console = Console()

LOGO = (
    "[bold]"
    "  _                 _            \n"
    " | |   __ _  ___ __| | ___  ___ \n"
    " | |__/ _` |/ __/ _` |/ _ \\/ __|\n"
    " |____\\__,_|\\__\\__,_|\\___/\\___|\n"
    "[/bold]"
)


# ── Banner ──────────────────────────────────────────────────────────


def _print_banner(config):
    console.print()
    console.print(LOGO)

    info = Text("  ")
    info.append("v0.1.0", style="dim")
    info.append("  ")
    info.append(_model_name(config.model), style="bold")
    info.append("  ")
    info.append(_short_cwd(config.cwd))
    branch = _git_branch()
    if branch:
        info.append(f" ({branch})")
    console.print(info)
    console.print("  /help | Shift+Tab: plan/act | Ctrl-C to interrupt", style="dim")
    console.print()


# ── Command agent (restricted tools/model from custom commands) ─────


def _create_command_agent(config, cmd_result: CommandResult, mcp_mgr=None, checkpointer=None):
    """Create a temporary agent restricted by a custom command's frontmatter."""
    from .agents.prompt import build_prompt
    from .tools import get_tools, get_tools_by_names

    # Resolve tools
    if cmd_result.allowed_tools:
        tools = get_tools_by_names(cmd_result.allowed_tools)
        # Also include MCP tools matching Bash(pattern) style
        if mcp_mgr and not mcp_mgr.is_loading:
            tools.extend(mcp_mgr.get_tools())
    else:
        tools = get_tools()
        if mcp_mgr and not mcp_mgr.is_loading:
            tools.extend(mcp_mgr.get_tools())

    # Resolve model
    model = cmd_result.model if cmd_result.model else config.model

    if checkpointer is None:
        checkpointer = create_sqlite_checkpointer(config)

    from langchain.agents import create_agent

    return create_agent(
        model=model,
        tools=tools,
        system_prompt=build_prompt(config),
        checkpointer=checkpointer,
    )


def _generate_thread_id() -> str:
    """Generate a new 8-char hex thread ID."""
    import uuid

    return uuid.uuid4().hex[:8]


# ── Session metadata (separate sqlite db) ────────────────────────────


def _get_sessions_conn(config):
    """Open a connection to sessions.sqlite and ensure the table exists."""
    import sqlite3

    config.global_dir.mkdir(parents=True, exist_ok=True)
    db_path = config.global_dir / "sessions.sqlite"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE IF NOT EXISTS sessions ("
        "  thread_id TEXT PRIMARY KEY,"
        "  created_at TEXT NOT NULL,"
        "  updated_at TEXT NOT NULL,"
        "  cwd TEXT NOT NULL DEFAULT '',"
        "  last_query TEXT NOT NULL DEFAULT ''"
        ")"
    )
    conn.commit()
    return conn


def _save_session(config, thread_id: str, query: str = ""):
    """Create a session or update its last_query."""
    conn = _get_sessions_conn(config)
    if query:
        conn.execute(
            "INSERT INTO sessions (thread_id, created_at, updated_at, cwd, last_query) "
            "VALUES (?, datetime('now'), datetime('now'), ?, ?) "
            "ON CONFLICT(thread_id) DO UPDATE SET "
            "updated_at = datetime('now'), last_query = excluded.last_query",
            (thread_id, str(config.cwd), query),
        )
    else:
        conn.execute(
            "INSERT OR IGNORE INTO sessions (thread_id, created_at, updated_at, cwd, last_query) "
            "VALUES (?, datetime('now'), datetime('now'), ?, '')",
            (thread_id, str(config.cwd)),
        )
    conn.commit()
    conn.close()


def _list_sessions(config) -> list[dict]:
    """Return all sessions with a last_query, ordered by most recent first."""
    conn = _get_sessions_conn(config)
    try:
        rows = conn.execute(
            "SELECT thread_id, created_at, updated_at, cwd, last_query "
            "FROM sessions WHERE last_query != '' ORDER BY updated_at DESC"
        ).fetchall()
        return [
            {
                "thread_id": r[0],
                "created_at": r[1],
                "updated_at": r[2],
                "cwd": r[3],
                "last_query": r[4],
            }
            for r in rows
        ]
    except Exception:
        return []
    finally:
        conn.close()


# ── One-shot ────────────────────────────────────────────────────────


def _run_once(config, agent, prompt: str):
    t0 = time.time()
    thread_id = _generate_thread_id()
    try:
        stream_agent_response(agent, prompt, thread_id, config)
    except KeyboardInterrupt:
        console.print("\ninterrupted", style="dim")
    except Exception as e:
        console.print(f"\nerror: {e}", style="bold")
        if config.verbose:
            console.print_exception()
    elapsed = time.time() - t0
    console.print(f"{elapsed:.1f}s", style="dim")


# ── MCP CLI subcommands ─────────────────────────────────────────────


def _handle_mcp_cli() -> None:
    """Handle `langcode mcp add/list/remove/get/add-json`."""
    from .core.config import Config
    from .mcp import (
        mcp_add_server,
        mcp_get_server,
        mcp_list_servers,
        mcp_remove_server,
    )

    args = sys.argv[2:]
    if not args:
        _mcp_usage()
        return

    sub = args[0]
    rest = args[1:]
    config = Config()  # no API key needed for management

    if sub == "list":
        all_servers = mcp_list_servers(config)
        if not all_servers:
            console.print("no MCP servers configured", style="dim")
            return
        for name, cfg in all_servers.items():
            transport = cfg.get("type", "stdio") if "url" in cfg else "stdio"
            if transport in ("streamable-http", "http"):
                transport = "http"
            endpoint = cfg.get("url", "") or cfg.get("command", "")
            if cfg.get("args") and not cfg.get("url"):
                endpoint += " " + " ".join(cfg["args"])
            source = cfg.get("_source", "")
            console.print(
                f"  [bold]{name:<16}[/bold] {transport:<6} {endpoint}  [dim]{source}[/dim]"
            )

    elif sub == "add":
        _mcp_cli_add(config, rest)

    elif sub == "add-json":
        if len(rest) < 2:
            console.print("usage: langcode mcp add-json <name> '<json>'", style="dim")
            return
        name = rest[0]
        try:
            server_config = json.loads(rest[1])
        except json.JSONDecodeError as e:
            console.print(f"invalid JSON: {e}", style="bold")
            return
        scope = "user" if "--scope" in rest and "user" in rest else "project"
        path = mcp_add_server(config, name, server_config, scope)
        console.print(f"added [bold]{name}[/bold] to {path}")

    elif sub == "remove":
        if not rest:
            console.print("usage: langcode mcp remove <name> [--scope user]", style="dim")
            return
        name = rest[0]
        scope = "user" if "--scope" in rest and "user" in rest else "project"
        if mcp_remove_server(config, name, scope):
            console.print(f"removed [bold]{name}[/bold]")
        else:
            console.print(f"server [bold]{name}[/bold] not found", style="dim")

    elif sub == "get":
        if not rest:
            console.print("usage: langcode mcp get <name>", style="dim")
            return
        info = mcp_get_server(config, rest[0])
        if info:
            display = {k: v for k, v in info.items() if not k.startswith("_")}
            console.print(json.dumps(display, indent=2))
            console.print(f"[dim]source: {info.get('_source', '')}[/dim]")
        else:
            console.print(f"server [bold]{rest[0]}[/bold] not found", style="dim")

    else:
        _mcp_usage()


def _mcp_cli_add(config, args: list[str]) -> None:
    """Parse `langcode mcp add [opts] <name> [url | -- command args...]`."""
    from .mcp import mcp_add_server

    transport = "stdio"
    scope = "project"
    env_vars: dict[str, str] = {}
    headers: dict[str, str] = {}

    # Split on '--'
    command_args: list[str] = []
    if "--" in args:
        idx = args.index("--")
        command_args = args[idx + 1 :]
        args = args[:idx]

    # Parse options + positional
    positional: list[str] = []
    i = 0
    while i < len(args):
        if args[i] in ("--transport", "-t") and i + 1 < len(args):
            transport = args[i + 1]
            i += 2
        elif args[i] in ("--scope", "-s") and i + 1 < len(args):
            scope = args[i + 1]
            i += 2
        elif args[i] in ("--env", "-e") and i + 1 < len(args):
            k, _, v = args[i + 1].partition("=")
            env_vars[k] = v
            i += 2
        elif args[i] == "--header" and i + 1 < len(args):
            k, _, v = args[i + 1].partition(":")
            headers[k.strip()] = v.strip()
            i += 2
        else:
            positional.append(args[i])
            i += 1

    if not positional:
        console.print(
            "usage: langcode mcp add [--transport stdio|http|sse] "
            "[--scope project|user] [--env KEY=VAL]... <name> [url | -- cmd args...]",
            style="dim",
        )
        return

    name = positional[0]
    url = positional[1] if len(positional) > 1 else None

    if transport in ("http", "sse") or url:
        if not url:
            console.print("HTTP/SSE transport requires a URL", style="bold")
            return
        server_config: dict = {"type": transport, "url": url}
        if headers:
            server_config["headers"] = headers
    else:
        if not command_args:
            console.print("stdio transport requires a command after '--'", style="bold")
            return
        server_config = {
            "command": command_args[0],
            "args": command_args[1:],
        }
        if env_vars:
            server_config["env"] = env_vars

    path = mcp_add_server(config, name, server_config, scope)
    console.print(f"added [bold]{name}[/bold] to {path}")


def _mcp_usage() -> None:
    console.print("usage: langcode mcp <command>", style="dim")
    console.print()
    console.print("  [bold]add[/bold]       Add an MCP server")
    console.print("  [bold]add-json[/bold]  Add from JSON config")
    console.print("  [bold]list[/bold]      List configured servers")
    console.print("  [bold]get[/bold]       Show server details")
    console.print("  [bold]remove[/bold]    Remove a server")
    console.print()
    console.print("examples:", style="dim")
    console.print(
        "  langcode mcp add --transport http github https://api.github.com/mcp", style="dim"
    )
    console.print("  langcode mcp add myserver -- npx -y @some/package", style="dim")
    console.print(
        '  langcode mcp add-json sentry \'{"type":"http","url":"https://mcp.sentry.dev/mcp"}\'',
        style="dim",
    )


# ── Plugin CLI subcommands ───────────────────────────────────────────


def _handle_plugin_cli() -> None:
    """Handle `langcode plugin install/uninstall/enable/disable/update/list/marketplace/validate`."""
    from .core.config import load_config
    from .plugins import (
        disable_plugin,
        enable_plugin,
        install_plugin_from_path,
        list_plugins,
        uninstall_plugin,
        update_plugin,
        validate_plugin,
    )
    from .plugins.marketplace import (
        install_from_marketplace,
    )

    args = sys.argv[2:]
    if not args:
        _plugin_usage()
        return

    sub = args[0]
    rest = args[1:]
    config = load_config()

    if sub == "list":
        plugins = list_plugins(config)
        if not plugins:
            console.print("no plugins installed", style="dim")
            console.print("use `langcode plugin install` to add one", style="dim")
            return
        for p in plugins:
            status = "[green]on[/green]" if p.enabled else "[dim]off[/dim]"
            ver = f"v{p.manifest.version}" if p.manifest.version else ""
            market = f"@{p.marketplace}" if p.marketplace else ""
            err = f" [red]({p.error})[/red]" if p.error else ""
            console.print(
                f"  [bold]{p.name}{market}[/bold]  {ver}  {status}{err}"
                f"  [dim]{p.manifest.description}[/dim]"
            )

    elif sub == "install":
        if not rest:
            console.print(
                "usage: langcode plugin install <name@marketplace | path> [--scope user|project|local]",
                style="dim",
            )
            return
        scope = _parse_scope(rest)
        target = rest[0]
        if "@" in target and not Path(target).exists():
            # name@marketplace format
            parts = target.split("@", 1)
            pname, mname = parts[0], parts[1]
            p = install_from_marketplace(config, pname, mname, scope)
            if p and not p.error:
                console.print(f"installed [bold]{p.name}[/bold]")
            elif p:
                console.print(f"error: {p.error}", style="bold")
        else:
            # local path
            path = Path(target).resolve()
            if not path.is_dir():
                console.print(f"not a directory: {target}", style="bold")
                return
            p = install_plugin_from_path(config, path, scope)
            if p and not p.error:
                console.print(f"installed [bold]{p.name}[/bold] from {path}")
            elif p:
                console.print(f"error: {p.error}", style="bold")

    elif sub in ("uninstall", "remove", "rm"):
        if not rest:
            console.print(
                "usage: langcode plugin uninstall <name> [--scope user|project|local]", style="dim"
            )
            return
        scope = _parse_scope(rest)
        if uninstall_plugin(config, rest[0], scope):
            console.print(f"uninstalled [bold]{rest[0]}[/bold]")

    elif sub == "enable":
        if not rest:
            console.print(
                "usage: langcode plugin enable <name> [--scope user|project|local]", style="dim"
            )
            return
        scope = _parse_scope(rest)
        enable_plugin(config, rest[0], scope)
        console.print(f"enabled [bold]{rest[0]}[/bold]")

    elif sub == "disable":
        if not rest:
            console.print(
                "usage: langcode plugin disable <name> [--scope user|project|local]", style="dim"
            )
            return
        scope = _parse_scope(rest)
        disable_plugin(config, rest[0], scope)
        console.print(f"disabled [bold]{rest[0]}[/bold]")

    elif sub == "update":
        if not rest:
            console.print("usage: langcode plugin update <name>", style="dim")
            return
        p = update_plugin(config, rest[0])
        if p:
            console.print(f"updated [bold]{rest[0]}[/bold]")
        else:
            console.print(f"could not update [bold]{rest[0]}[/bold] (no source info)", style="dim")

    elif sub == "validate":
        target = rest[0] if rest else "."
        errors = validate_plugin(Path(target).resolve())
        if errors:
            for e in errors:
                console.print(f"  [red]error:[/red] {e}")
        else:
            console.print("[green]plugin is valid[/green]")

    elif sub in ("marketplace", "market"):
        _handle_marketplace_cli(config, rest)

    else:
        _plugin_usage()


def _handle_marketplace_cli(config, args: list[str]) -> None:
    """Handle `langcode plugin marketplace add/remove/update/list`."""
    from .plugins.marketplace import (
        add_marketplace,
        list_marketplaces,
        remove_marketplace,
        update_marketplace,
    )

    if not args:
        _marketplace_usage()
        return

    sub = args[0]
    rest = args[1:]

    if sub == "add":
        if not rest:
            console.print("usage: langcode plugin marketplace add <source>", style="dim")
            return
        m = add_marketplace(config, rest[0])
        if m:
            console.print(f"added marketplace [bold]{m.name}[/bold] ({len(m.plugins)} plugins)")

    elif sub in ("remove", "rm"):
        if not rest:
            console.print("usage: langcode plugin marketplace remove <name>", style="dim")
            return
        if remove_marketplace(config, rest[0]):
            console.print(f"removed marketplace [bold]{rest[0]}[/bold]")
        else:
            console.print(f"marketplace [bold]{rest[0]}[/bold] not found", style="dim")

    elif sub == "update":
        if not rest:
            console.print("usage: langcode plugin marketplace update <name>", style="dim")
            return
        m = update_marketplace(config, rest[0])
        if m:
            console.print(f"updated marketplace [bold]{m.name}[/bold]")
        else:
            console.print(f"could not update [bold]{rest[0]}[/bold]", style="dim")

    elif sub == "list":
        markets = list_marketplaces(config)
        if not markets:
            console.print("no marketplaces configured", style="dim")
            return
        for m in markets:
            n_plugins = len(m.plugins)
            console.print(
                f"  [bold]{m.name}[/bold]  "
                f"{m.source_type}  "
                f"[dim]{m.source_ref}[/dim]  "
                f"{n_plugins} plugin(s)"
            )

    else:
        _marketplace_usage()


def _parse_scope(args: list[str]) -> str:
    """Extract --scope value from args, default 'user'."""
    for i, a in enumerate(args):
        if a in ("--scope", "-s") and i + 1 < len(args):
            return args[i + 1]
    return "user"


def _plugin_usage() -> None:
    console.print("usage: langcode plugin <command>", style="dim")
    console.print()
    console.print("  [bold]list[/bold]          List installed plugins")
    console.print("  [bold]install[/bold]       Install a plugin (path or name@marketplace)")
    console.print("  [bold]uninstall[/bold]     Remove a plugin")
    console.print("  [bold]enable[/bold]        Enable a disabled plugin")
    console.print("  [bold]disable[/bold]       Disable a plugin without removing")
    console.print("  [bold]update[/bold]        Update a plugin from its source")
    console.print("  [bold]validate[/bold]      Validate a plugin directory")
    console.print("  [bold]marketplace[/bold]   Manage marketplaces (add/remove/update/list)")
    console.print()
    console.print("examples:", style="dim")
    console.print("  langcode plugin install ./my-plugin", style="dim")
    console.print("  langcode plugin install code-fmt@acme-tools --scope project", style="dim")
    console.print("  langcode plugin marketplace add anthropics/claude-code", style="dim")


def _marketplace_usage() -> None:
    console.print("usage: langcode plugin marketplace <command>", style="dim")
    console.print()
    console.print("  [bold]add[/bold]      Add a marketplace (path, owner/repo, or git URL)")
    console.print("  [bold]list[/bold]     List configured marketplaces")
    console.print("  [bold]update[/bold]   Refresh a marketplace from its source")
    console.print("  [bold]remove[/bold]   Remove a marketplace")
    console.print()
    console.print("examples:", style="dim")
    console.print("  langcode plugin marketplace add ./my-marketplace", style="dim")
    console.print("  langcode plugin marketplace add anthropics/claude-code", style="dim")


# ── CLI entry point ─────────────────────────────────────────────────


@click.command()
@click.argument("prompt", required=False, default=None)
@click.option("--model", "-m", default=None, help="Model name")
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
@click.option(
    "--plugin-dir",
    multiple=True,
    type=click.Path(exists=True),
    help="Load plugins from directory (repeatable)",
)
def _click_main(prompt: str | None, model: str | None, verbose: bool, plugin_dir: tuple[str, ...]):
    """LangCode — AI coding agent."""
    # `langcode init` — scaffold + AI analysis
    if prompt and prompt.strip().lower() == "init":
        from .commands import INIT_PROMPT

        init_project()
        # continue to run AI analysis below
        prompt = INIT_PROMPT

    config = load_config(model=model, verbose=verbose)

    if not config.api_key:
        console.print("error: ANTHROPIC_API_KEY not set", style="bold")
        console.print("set via environment variable or .env file", style="dim")
        sys.exit(1)

    # ── Load plugins ─────────────────────────────────────────────────
    from .plugins import load_enabled_plugins

    extra_plugin_dirs = [Path(d) for d in plugin_dir] if plugin_dir else []
    loaded_plugins = load_enabled_plugins(config, extra_plugin_dirs)

    # Merge plugin hooks into config
    from .hooks import parse_hooks_config as _parse_hooks

    for p in loaded_plugins:
        if p.components.hooks_config:
            config.hooks.merge(_parse_hooks(p.components.hooks_config))

    skills_content = build_context(config, loaded_plugins)

    mcp_mgr = MCPManager()
    mcp_mgr.load_config(config)

    # Also load plugin MCP servers
    for p in loaded_plugins:
        if p.components.mcp_servers:
            mcp_mgr.add_plugin_servers(p.components.mcp_servers)

    # Start MCP servers in background — don't block the REPL
    mcp_mgr.start_in_background()

    try:
        # Create shared checkpointer — all agents (main, plan, command) use the same one
        checkpointer = create_sqlite_checkpointer(config)

        # Create agent without MCP tools first; they'll be added once ready
        agent = create_main_agent(config, skills_content, mcp_tools=[], checkpointer=checkpointer)
        cmd_handler = CommandHandler(config, mcp_manager=mcp_mgr, plugins=loaded_plugins)

        if prompt:
            # One-shot mode: wait for MCP to finish loading
            if mcp_mgr.server_names:
                mcp_mgr._thread.join() if mcp_mgr._thread else None
                if mcp_mgr.get_tools():
                    agent = create_main_agent(
                        config, skills_content, mcp_mgr.get_tools(), checkpointer=checkpointer
                    )
            _run_once(config, agent, prompt)
        else:
            run_repl(
                config,
                agent,
                cmd_handler,
                mcp_mgr,
                checkpointer=checkpointer,
                print_banner=_print_banner,
                generate_thread_id=_generate_thread_id,
                save_session=_save_session,
                list_sessions=_list_sessions,
                create_command_agent=_create_command_agent,
            )
    finally:
        mcp_mgr.stop_all()


def main():
    """True entry point — intercepts subcommands before click."""
    if len(sys.argv) > 1 and sys.argv[1] == "mcp":
        _handle_mcp_cli()
        return
    if len(sys.argv) > 1 and sys.argv[1] == "plugin":
        _handle_plugin_cli()
        return
    _click_main()


if __name__ == "__main__":
    main()
