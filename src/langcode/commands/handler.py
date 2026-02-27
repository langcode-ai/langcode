"""CommandHandler: dispatch slash commands to built-in and custom handlers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.console import Console

from .custom import (
    CommandResult,
    expand_custom_command,
    load_custom_commands,
    read_command_description,
)
from .scaffold import COMMANDS, init_project

if TYPE_CHECKING:
    from langcode.core.config import Config

console = Console()


class CommandHandler:
    """Handle slash commands (built-in + custom from commands/*.md + plugins)."""

    def __init__(self, config: Config, mcp_manager=None, plugins=None):
        self.config = config
        self.mcp_manager = mcp_manager
        self.plugins = plugins or []
        self.messages: list[dict] = []
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_cache_read = 0
        self.total_cache_creation = 0
        self.custom_commands = load_custom_commands(config.project_dirs, self.plugins)

    def is_command(self, text: str) -> bool:
        return text.strip().startswith("/")

    def handle(self, text: str) -> str | CommandResult | None:
        text = text.strip()
        if not text.startswith("/"):
            return None

        parts = text.split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        if cmd == "/help":
            lines = [""]
            for c, desc in COMMANDS.items():
                lines.append(f"  [bold]{c:<12}[/bold] [dim]{desc}[/dim]")
            for c, path in self.custom_commands.items():
                desc = read_command_description(path)
                lines.append(f"  [bold]{c:<12}[/bold] [dim]{desc}[/dim]")
            lines.append("")
            return "\n".join(lines)

        elif cmd == "/quit":
            return "quit"

        elif cmd == "/init":
            created = init_project(self.config.cwd)
            self.custom_commands = load_custom_commands(self.config.project_dirs)
            if not created:
                return "already initialized"
            return "created: " + ", ".join(created)

        elif cmd == "/mcp":
            return self._handle_mcp()

        elif cmd == "/plugin":
            return self._handle_plugin(arg)

        elif cmd == "/clear":
            self.messages.clear()
            return "context cleared"

        elif cmd == "/model":
            if not arg:
                return f"model: [bold]{self.config.model}[/bold]"
            self.config.model = arg
            return f"model set to {arg}"

        elif cmd == "/cost":
            total = self.total_input_tokens + self.total_output_tokens
            lines = [
                f"  in:     {self.total_input_tokens:,}",
                f"  out:    {self.total_output_tokens:,}",
            ]
            if self.total_cache_read or self.total_cache_creation:
                lines.append(
                    f"  cached: {self.total_cache_read:,} read / {self.total_cache_creation:,} write"
                )
            lines.append(f"  total:  {total:,} tokens")
            return "\n".join(lines)

        elif cmd in self.custom_commands:
            return expand_custom_command(self.custom_commands[cmd], arg, cwd=self.config.cwd)

        else:
            return f"unknown command: {cmd}\n[dim]type /help for available commands[/dim]"

    def _handle_plugin(self, arg: str) -> str:
        if not arg:
            from langcode.tui.plugin_ui import run_plugin_ui

            run_plugin_ui(self.config, self.plugins)
            return ""

        parts = arg.split(maxsplit=1)
        sub = parts[0].lower()
        rest = parts[1] if len(parts) > 1 else ""

        from langcode.plugins import (
            disable_plugin,
            enable_plugin,
            install_plugin_from_path,
            list_plugins,
            uninstall_plugin,
        )
        from langcode.plugins.marketplace import (
            add_marketplace,
            install_from_marketplace,
            list_marketplaces,
            remove_marketplace,
        )

        if sub == "install" and rest:
            target = rest.split()[0]
            scope = "user"
            if "--scope" in rest:
                for tok in rest.split():
                    if tok in ("user", "project", "local"):
                        scope = tok
            if "@" in target and not __import__("pathlib").Path(target).exists():
                pname, mname = target.split("@", 1)
                p = install_from_marketplace(self.config, pname, mname, scope)
                return (
                    f"installed [bold]{p.name}[/bold]"
                    if p and not p.error
                    else "[red]install failed[/red]"
                )
            else:
                from pathlib import Path

                p = install_plugin_from_path(self.config, Path(target).resolve(), scope)
                return (
                    f"installed [bold]{p.name}[/bold]"
                    if p and not p.error
                    else f"[red]install failed: {p.error if p else 'unknown'}[/red]"
                )

        elif sub in ("uninstall", "remove") and rest:
            uninstall_plugin(self.config, rest.split()[0])
            return f"uninstalled [bold]{rest.split()[0]}[/bold]"

        elif sub == "enable" and rest:
            enable_plugin(self.config, rest.split()[0])
            return f"enabled [bold]{rest.split()[0]}[/bold]"

        elif sub == "disable" and rest:
            disable_plugin(self.config, rest.split()[0])
            return f"disabled [bold]{rest.split()[0]}[/bold]"

        elif sub == "list":
            plugins = list_plugins(self.config)
            if not plugins:
                return "[dim]no plugins installed[/dim]"
            lines = [""]
            for p in plugins:
                st = "[green]on[/green]" if p.enabled else "[dim]off[/dim]"
                lines.append(f"  [bold]{p.name}[/bold]  {st}  [dim]{p.manifest.description}[/dim]")
            lines.append("")
            return "\n".join(lines)

        elif sub in ("marketplace", "market"):
            mp = rest.split(maxsplit=1)
            msub = mp[0] if mp else ""
            marg = mp[1] if len(mp) > 1 else ""
            if msub == "add" and marg:
                m = add_marketplace(self.config, marg)
                if m:
                    return f"added marketplace [bold]{m.name}[/bold] ({len(m.plugins)} plugins)"
                return "[red]failed to add marketplace[/red]"
            elif msub in ("remove", "rm") and marg:
                remove_marketplace(self.config, marg)
                return f"removed marketplace [bold]{marg}[/bold]"
            elif msub == "list":
                markets = list_marketplaces(self.config)
                if not markets:
                    return "[dim]no marketplaces[/dim]"
                lines = [""]
                for m in markets:
                    lines.append(
                        f"  [bold]{m.name}[/bold]  [dim]{m.source_ref}[/dim]  {len(m.plugins)} plugin(s)"
                    )
                lines.append("")
                return "\n".join(lines)
            return "[dim]usage: /plugin marketplace add|remove|list[/dim]"

        return "[dim]usage: /plugin [install|uninstall|enable|disable|list|marketplace][/dim]"

    def _handle_mcp(self) -> str:
        from langcode.mcp import mcp_list_servers

        all_servers = mcp_list_servers(self.config)
        if not all_servers:
            return (
                "[dim]no MCP servers configured[/dim]\n[dim]use `langcode mcp add` to add one[/dim]"
            )

        status_map: dict[str, str] = {}
        n_tools = 0
        if self.mcp_manager:
            status_map = self.mcp_manager.server_status
            n_tools = len(self.mcp_manager.get_tools())

        lines = ["", "  [bold]MCP Servers[/bold]", ""]
        n_ok = 0
        for name, cfg in all_servers.items():
            transport = cfg.get("type", "stdio") if "url" in cfg else "stdio"
            if transport in ("streamable-http", "http"):
                transport = "http"
            endpoint = cfg.get("url", "") or cfg.get("command", "")
            if cfg.get("args") and not cfg.get("url"):
                endpoint += " " + " ".join(cfg["args"])

            is_loading = self.mcp_manager and self.mcp_manager.is_loading
            st = status_map.get(name, "")
            if st == "ok":
                badge = "[green]ok[/green]"
                n_ok += 1
            elif st == "error":
                badge = "[red]x[/red]"
            elif is_loading:
                badge = "[yellow]...[/yellow]"
            else:
                badge = "[dim]--[/dim]"
            lines.append(f"  {name:<16} {transport:<6} {badge:<4} [dim]{endpoint}[/dim]")

        lines.append("")
        lines.append(f"  [dim]{n_ok}/{len(all_servers)} connected, {n_tools} tool(s)[/dim]")
        lines.append("")
        return "\n".join(lines)
