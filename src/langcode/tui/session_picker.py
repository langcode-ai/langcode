"""Interactive TUI session picker for /resume command."""

from __future__ import annotations

from pathlib import Path

from prompt_toolkit import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout
from prompt_toolkit.layout.containers import HSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl

from .renderer import console


def pick_session_tui(sessions: list[dict], current_thread_id: str) -> str | None:
    """Show an interactive TUI to pick a session. Returns thread_id or None."""
    if not sessions:
        console.print("no saved sessions", style="dim")
        return None

    selected = [0]
    result: list[str | None] = [None]

    def _get_text():
        lines = []
        for i, s in enumerate(sessions):
            tid = s["thread_id"]
            query = s["last_query"][:80] or "(empty)"
            updated = s["updated_at"] or ""
            cwd = s["cwd"]
            try:
                rel = str(Path(cwd).relative_to(Path.home()))
                cwd_short = f"~/{rel}" if rel != "." else "~"
            except (ValueError, TypeError):
                cwd_short = cwd or ""

            marker = ">" if i == selected[0] else " "
            current = " *" if tid == current_thread_id else ""
            sel = i == selected[0]

            lines.append(("bold" if sel else "", f" {marker} {query}{current}\n"))
            lines.append(("dim", f"   {updated}  {cwd_short}\n"))
        lines.append(("dim", "\n ↑/↓ navigate  enter select  esc cancel"))
        return lines

    kb = KeyBindings()

    @kb.add("up")
    @kb.add("k")
    def _up(event):
        selected[0] = max(0, selected[0] - 1)

    @kb.add("down")
    @kb.add("j")
    def _down(event):
        selected[0] = min(len(sessions) - 1, selected[0] + 1)

    @kb.add("enter")
    def _select(event):
        result[0] = sessions[selected[0]]["thread_id"]
        event.app.exit()

    @kb.add("escape")
    @kb.add("q")
    @kb.add("c-c")
    def _cancel(event):
        event.app.exit()

    layout = Layout(HSplit([Window(FormattedTextControl(_get_text))]))
    app: Application = Application(layout=layout, key_bindings=kb, full_screen=False)
    app.run()
    return result[0]
