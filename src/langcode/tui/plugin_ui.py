"""Interactive /plugin TUI with tabbed interface.

Full-screen prompt_toolkit Application with keyboard navigation:
  Tab/Shift-Tab  switch tabs
  Up/Down/j/k    navigate items
  Enter          action on selected item
  i              install plugin
  a              add marketplace
  q/Escape       close
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from prompt_toolkit import Application
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import (
    FormattedTextControl,
    HSplit,
    Layout,
    Window,
)
from prompt_toolkit.layout.dimension import Dimension

if TYPE_CHECKING:
    from ..core.config import Config
    from ..plugins import Plugin

TAB_NAMES = ["Discover", "Installed", "Marketplaces", "Errors"]


# ── State ───────────────────────────────────────────────────────────


class _UIState:
    def __init__(self, config: Config, plugins: list[Plugin] | None = None):
        from ..plugins import list_plugins

        self.config = config
        self.current_tab = 0
        self.cursor = 0
        self.installed = list_plugins(config) if plugins is None else list(plugins)
        self.errors = [p for p in self.installed if p.error]
        self.status_msg = ""
        self.input_mode: str = ""  # "", "install", "marketplace", "scope"
        self.input_buffer: str = ""
        self.pending_action: dict = {}
        self._refresh_items()

    def _refresh_items(self) -> None:
        """Rebuild the items list for the current tab."""
        if self.current_tab == 0:
            from ..plugins.marketplace import discover_plugins

            self._discover = discover_plugins(self.config)
            self.item_count = len(self._discover)
        elif self.current_tab == 1:
            self.item_count = len(self.installed)
        elif self.current_tab == 2:
            from ..plugins.marketplace import list_marketplaces

            self._markets = list_marketplaces(self.config)
            self.item_count = len(self._markets)
        elif self.current_tab == 3:
            self.item_count = len(self.errors)
        self.cursor = min(self.cursor, max(0, self.item_count - 1))

    def reload(self) -> None:
        from ..plugins import list_plugins

        self.installed = list_plugins(self.config)
        self.errors = [p for p in self.installed if p.error]
        self._refresh_items()

    def switch_tab(self, delta: int) -> None:
        self.current_tab = (self.current_tab + delta) % len(TAB_NAMES)
        self.cursor = 0
        self._refresh_items()

    def move_cursor(self, delta: int) -> None:
        if self.item_count > 0:
            self.cursor = max(0, min(self.item_count - 1, self.cursor + delta))


# ── Rendering ───────────────────────────────────────────────────────


def _render_tabs(state: _UIState) -> FormattedText:
    parts: list[tuple[str, str]] = [("", "  ")]
    for i, name in enumerate(TAB_NAMES):
        if i == state.current_tab:
            parts.append(("bold reverse", f" {name} "))
        else:
            parts.append(("", f" {name} "))
        parts.append(("", "  "))
    parts.append(("", "\n"))
    return FormattedText(parts)


def _render_content(state: _UIState) -> FormattedText:
    parts: list[tuple[str, str]] = []

    if state.input_mode:
        return _render_input_mode(state)

    if state.current_tab == 0:
        _render_discover(state, parts)
    elif state.current_tab == 1:
        _render_installed(state, parts)
    elif state.current_tab == 2:
        _render_marketplaces_tab(state, parts)
    elif state.current_tab == 3:
        _render_errors(state, parts)

    return FormattedText(parts)


def _render_discover(state: _UIState, parts: list) -> None:
    items = getattr(state, "_discover", [])
    if not items:
        parts.append(("italic", "  no plugins available — press 'a' to add a marketplace\n"))
        return

    parts.append(
        ("bold", "  Plugin                    Version  Marketplace          Description\n")
    )
    parts.append(("", "  " + "─" * 76 + "\n"))
    for i, (market_name, entry) in enumerate(items):
        prefix = " > " if i == state.cursor else "   "
        style = "bold" if i == state.cursor else ""
        name = entry.name[:24].ljust(24)
        ver = (entry.version or "-")[:8].ljust(8)
        mkt = market_name[:18].ljust(18)
        desc = (entry.description or "")[:30]
        parts.append((style, f"  {prefix}{name}  {ver}  {mkt}  {desc}\n"))


def _render_installed(state: _UIState, parts: list) -> None:
    items = state.installed
    if not items:
        parts.append(("italic", "  no plugins installed\n"))
        return

    parts.append(("bold", "  Plugin                    Version  Status     Source\n"))
    parts.append(("", "  " + "─" * 68 + "\n"))
    for i, p in enumerate(items):
        prefix = " > " if i == state.cursor else "   "
        style = "bold" if i == state.cursor else ""
        name = p.name[:24].ljust(24)
        ver = (p.manifest.version or "-")[:8].ljust(8)
        if p.error:
            status = "error"
            st_style = "fg:red"
        elif p.enabled:
            status = "enabled"
            st_style = "fg:green"
        else:
            status = "disabled"
            st_style = "fg:yellow"
        src = (p.marketplace or p.source or "-")[:20]
        parts.append((style, f"  {prefix}{name}  {ver}  "))
        parts.append((st_style, status.ljust(9)))
        parts.append(("", f"  {src}\n"))


def _render_marketplaces_tab(state: _UIState, parts: list) -> None:
    items = getattr(state, "_markets", [])
    if not items:
        parts.append(("italic", "  no marketplaces — press 'a' to add one\n"))
        return

    parts.append(("bold", "  Name                 Source                                Plugins\n"))
    parts.append(("", "  " + "─" * 68 + "\n"))
    for i, m in enumerate(items):
        prefix = " > " if i == state.cursor else "   "
        style = "bold" if i == state.cursor else ""
        name = m.name[:20].ljust(20)
        src_str = f"{m.source_type}: {m.source_ref}" if m.source_ref else "-"
        src_str = src_str[:34].ljust(34)
        parts.append((style, f"  {prefix}{name}  {src_str}  {len(m.plugins)}\n"))


def _render_errors(state: _UIState, parts: list) -> None:
    items = state.errors
    if not items:
        parts.append(("italic", "  no plugin errors\n"))
        return

    for i, p in enumerate(items):
        prefix = " > " if i == state.cursor else "   "
        style = "bold" if i == state.cursor else ""
        parts.append((style, f"  {prefix}{p.name}: "))
        parts.append(("fg:red", f"{p.error}\n"))


def _render_input_mode(state: _UIState) -> FormattedText:
    parts: list[tuple[str, str]] = []
    if state.input_mode == "install":
        parts.append(("bold", "  Install Plugin\n\n"))
        parts.append(("", "  Enter path or name@marketplace:\n"))
        parts.append(("bold", f"  > {state.input_buffer}█\n"))
    elif state.input_mode == "marketplace":
        parts.append(("bold", "  Add Marketplace\n\n"))
        parts.append(("", "  Enter source (path, owner/repo, or git URL):\n"))
        parts.append(("bold", f"  > {state.input_buffer}█\n"))
    elif state.input_mode == "scope":
        parts.append(("bold", "  Choose Scope\n\n"))
        parts.append(("", "  [1] user   [2] project   [3] local\n"))
    elif state.input_mode == "confirm_uninstall":
        idx = state.cursor
        items = state.installed
        if 0 <= idx < len(items):
            parts.append(("bold", f"  Uninstall '{items[idx].name}'?\n\n"))
            parts.append(("", "  [y] yes   [n] no\n"))
    elif state.input_mode == "confirm_toggle":
        idx = state.cursor
        items = state.installed
        if 0 <= idx < len(items):
            p = items[idx]
            action = "Disable" if p.enabled else "Enable"
            parts.append(("bold", f"  {action} '{p.name}'?\n\n"))
            parts.append(("", "  [y] yes   [n] no\n"))
    return FormattedText(parts)


def _render_statusbar(state: _UIState) -> FormattedText:
    parts: list[tuple[str, str]] = []
    if state.status_msg:
        parts.append(("bold", f"  {state.status_msg}\n"))
    if state.input_mode:
        parts.append(("", "  Esc: cancel"))
    else:
        parts.append(("", "  Tab: switch tabs  ↑↓: navigate  Enter: action  "))
        parts.append(("", "i: install  a: add marketplace  q: close"))
    return FormattedText(parts)


# ── Actions ─────────────────────────────────────────────────────────


def _do_install(state: _UIState, source: str, scope: str) -> None:
    from ..plugins import install_plugin_from_path
    from ..plugins.marketplace import install_from_marketplace

    if "@" in source and not Path(source).exists():
        pname, mname = source.split("@", 1)
        p = install_from_marketplace(state.config, pname, mname, scope)
        if p and not p.error:
            state.status_msg = f"Installed {p.name}"
        else:
            state.status_msg = f"Install failed: {p.error if p else 'unknown'}"
    else:
        path = Path(source).resolve()
        if not path.is_dir():
            state.status_msg = f"Not a directory: {source}"
            return
        p = install_plugin_from_path(state.config, path, scope)
        if p and not p.error:
            state.status_msg = f"Installed {p.name}"
        else:
            state.status_msg = f"Install failed: {p.error if p else 'unknown'}"
    state.reload()


def _do_add_marketplace(state: _UIState, source: str) -> None:
    from ..plugins.marketplace import add_marketplace

    m = add_marketplace(state.config, source)
    if m:
        state.status_msg = f"Added marketplace {m.name} ({len(m.plugins)} plugins)"
    else:
        state.status_msg = "Failed to add marketplace"
    state.reload()


def _do_uninstall(state: _UIState, idx: int) -> None:
    from ..plugins import uninstall_plugin

    if 0 <= idx < len(state.installed):
        name = state.installed[idx].name
        uninstall_plugin(state.config, name)
        state.status_msg = f"Uninstalled {name}"
        state.reload()


def _do_toggle(state: _UIState, idx: int) -> None:
    from ..plugins import disable_plugin, enable_plugin

    if 0 <= idx < len(state.installed):
        p = state.installed[idx]
        if p.enabled:
            disable_plugin(state.config, p.name)
            state.status_msg = f"Disabled {p.name}"
        else:
            enable_plugin(state.config, p.name)
            state.status_msg = f"Enabled {p.name}"
        state.reload()


def _do_install_from_discover(state: _UIState, idx: int, scope: str) -> None:
    """Install the selected plugin from the Discover tab."""
    items = getattr(state, "_discover", [])
    if not (0 <= idx < len(items)):
        return
    market_name, entry = items[idx]
    from ..plugins.marketplace import install_from_marketplace

    p = install_from_marketplace(state.config, entry.name, market_name, scope)
    if p and not p.error:
        state.status_msg = f"Installed {p.name}"
    else:
        state.status_msg = f"Install failed: {p.error if p else 'unknown'}"
    state.reload()


# ── Application ─────────────────────────────────────────────────────


def run_plugin_ui(config: Config, plugins: list[Plugin] | None = None) -> str | None:
    """Run the full-screen plugin TUI. Returns None."""
    state = _UIState(config, plugins)

    kb = KeyBindings()

    # ── Tab switching ──
    @kb.add("tab")
    def _tab(event):
        if state.input_mode:
            return
        state.status_msg = ""
        state.switch_tab(1)

    @kb.add("s-tab")
    def _stab(event):
        if state.input_mode:
            return
        state.status_msg = ""
        state.switch_tab(-1)

    # ── Navigation ──
    @kb.add("up")
    def _up(event):
        if state.input_mode:
            return
        state.move_cursor(-1)

    @kb.add("down")
    def _down(event):
        if state.input_mode:
            return
        state.move_cursor(1)

    @kb.add("k")
    def _k_nav(event):
        if state.input_mode:
            state.input_buffer += "k"
        else:
            state.move_cursor(-1)

    @kb.add("j")
    def _j_nav(event):
        if state.input_mode:
            state.input_buffer += "j"
        else:
            state.move_cursor(1)

    # ── Quit ──
    @kb.add("q")
    def _quit(event):
        if state.input_mode:
            # 'q' typed in input buffer
            state.input_buffer += "q"
            return
        event.app.exit()

    @kb.add("escape")
    def _esc(event):
        if state.input_mode:
            state.input_mode = ""
            state.input_buffer = ""
            state.pending_action = {}
            state.status_msg = ""
        else:
            event.app.exit()

    # ── Enter: action on selected item ──
    @kb.add("enter")
    def _enter(event):
        if state.input_mode == "install":
            if state.input_buffer.strip():
                state.pending_action = {"action": "install", "source": state.input_buffer.strip()}
                state.input_mode = "scope"
                state.input_buffer = ""
            return
        elif state.input_mode == "marketplace":
            if state.input_buffer.strip():
                _do_add_marketplace(state, state.input_buffer.strip())
            state.input_mode = ""
            state.input_buffer = ""
            return
        elif state.input_mode == "scope":
            # default user
            _finish_scoped_action(state, "user")
            return
        elif state.input_mode in ("confirm_uninstall", "confirm_toggle"):
            return  # handled by y/n
        elif state.input_mode:
            return

        # Normal mode: Enter on selected item
        if state.current_tab == 0:
            # Discover: install selected plugin
            if state.item_count > 0:
                state.pending_action = {"action": "install_discover", "idx": state.cursor}
                state.input_mode = "scope"
        elif state.current_tab == 1:
            # Installed: toggle enable/disable
            if state.item_count > 0:
                state.input_mode = "confirm_toggle"
        elif state.current_tab == 2:
            pass  # no action on marketplace select

    # ── Scope selection (1/2/3) ──
    @kb.add("1")
    def _one(event):
        if state.input_mode == "scope":
            _finish_scoped_action(state, "user")
        elif state.input_mode:
            state.input_buffer += "1"
        else:
            state.current_tab = 0
            state.cursor = 0
            state._refresh_items()
            state.status_msg = ""

    @kb.add("2")
    def _two(event):
        if state.input_mode == "scope":
            _finish_scoped_action(state, "project")
        elif state.input_mode:
            state.input_buffer += "2"
        else:
            state.current_tab = 1
            state.cursor = 0
            state._refresh_items()
            state.status_msg = ""

    @kb.add("3")
    def _three(event):
        if state.input_mode == "scope":
            _finish_scoped_action(state, "local")
        elif state.input_mode:
            state.input_buffer += "3"
        else:
            state.current_tab = 2
            state.cursor = 0
            state._refresh_items()
            state.status_msg = ""

    @kb.add("4")
    def _four(event):
        if state.input_mode:
            state.input_buffer += "4"
        else:
            state.current_tab = 3
            state.cursor = 0
            state._refresh_items()
            state.status_msg = ""

    # ── Confirm y/n ──
    @kb.add("y")
    def _yes(event):
        if state.input_mode == "confirm_uninstall":
            _do_uninstall(state, state.cursor)
            state.input_mode = ""
        elif state.input_mode == "confirm_toggle":
            _do_toggle(state, state.cursor)
            state.input_mode = ""
        elif state.input_mode:
            state.input_buffer += "y"

    @kb.add("n")
    def _no(event):
        if state.input_mode in ("confirm_uninstall", "confirm_toggle"):
            state.input_mode = ""
            state.status_msg = "Cancelled"
        elif state.input_mode:
            state.input_buffer += "n"

    # ── Shortcuts ──
    @kb.add("i")
    def _install(event):
        if state.input_mode:
            state.input_buffer += "i"
            return
        state.input_mode = "install"
        state.input_buffer = ""
        state.status_msg = ""

    @kb.add("a")
    def _add_market(event):
        if state.input_mode:
            state.input_buffer += "a"
            return
        state.input_mode = "marketplace"
        state.input_buffer = ""
        state.status_msg = ""

    @kb.add("u")
    def _uninstall(event):
        if state.input_mode:
            state.input_buffer += "u"
            return
        if state.current_tab == 1 and state.item_count > 0:
            state.input_mode = "confirm_uninstall"

    @kb.add("e")
    def _enable(event):
        if state.input_mode:
            state.input_buffer += "e"
            return
        # Quick enable on Installed tab
        if state.current_tab == 1 and state.item_count > 0:
            idx = state.cursor
            if 0 <= idx < len(state.installed) and not state.installed[idx].enabled:
                _do_toggle(state, idx)

    @kb.add("d")
    def _disable(event):
        if state.input_mode:
            state.input_buffer += "d"
            return
        if state.current_tab == 1 and state.item_count > 0:
            idx = state.cursor
            if 0 <= idx < len(state.installed) and state.installed[idx].enabled:
                _do_toggle(state, idx)

    # ── Text input for install/marketplace modes ──
    @kb.add("backspace")
    def _backspace(event):
        if state.input_mode in ("install", "marketplace"):
            state.input_buffer = state.input_buffer[:-1]

    @kb.add("space")
    def _space(event):
        if state.input_mode in ("install", "marketplace"):
            state.input_buffer += " "

    # Printable ASCII chars not already bound as standalone shortcuts
    _text_chars = "bcfghlmoprstuvwxz"
    _text_chars += _text_chars.upper()
    # uppercase of letters that have separate shortcut bindings
    _text_chars += "ADEIJKNQY"
    _text_chars += "056789"
    _text_chars += "-_./~:@+="

    for _ch in _text_chars:

        @kb.add(_ch)
        def _char_input(event, ch=_ch):
            if state.input_mode in ("install", "marketplace"):
                state.input_buffer += ch

    # ── Layout ──

    tab_bar = Window(
        content=FormattedTextControl(lambda: _render_tabs(state)),
        height=1,
    )
    separator = Window(height=1, char="─", style="class:separator")
    content_area = Window(
        content=FormattedTextControl(lambda: _render_content(state)),
        height=Dimension(min=5, preferred=20),
    )
    status_bar = Window(
        content=FormattedTextControl(lambda: _render_statusbar(state)),
        height=2,
        style="reverse",
    )

    layout = Layout(
        HSplit(
            [
                tab_bar,
                separator,
                content_area,
                separator,
                status_bar,
            ]
        )
    )

    app: Application = Application(
        layout=layout,
        key_bindings=kb,
        full_screen=True,
        mouse_support=False,
    )

    app.run()
    return None


def _finish_scoped_action(state: _UIState, scope: str) -> None:
    """Execute the pending scoped action (install)."""
    action = state.pending_action.get("action", "")
    if action == "install":
        source = state.pending_action.get("source", "")
        if source:
            _do_install(state, source, scope)
    elif action == "install_discover":
        idx = state.pending_action.get("idx", -1)
        _do_install_from_discover(state, idx, scope)

    state.input_mode = ""
    state.input_buffer = ""
    state.pending_action = {}
