"""Prompt-toolkit prompt/toolbar builders and key binding factories."""

from __future__ import annotations

from prompt_toolkit.formatted_text import HTML, FormattedText
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys

from ..core.utils import model_name as _model_name


def _build_prompt(mode: str = "act") -> FormattedText:
    if mode == "plan":
        return FormattedText([("class:prompt.plan", "plan> ")])
    return FormattedText([("class:prompt", "> ")])


def _fmt_tokens(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1000:
        return f"{n / 1000:.1f}K"
    return str(n)


def _build_toolbar(config, cmd_handler, mode_state):
    def _toolbar():
        mode = mode_state["mode"]
        mode_label = f"<b>{mode.upper()}</b>"
        m = _model_name(config.model)
        ctx = cmd_handler.total_input_tokens + cmd_handler.total_output_tokens
        parts = [f" {mode_label} | {m}"]
        if ctx:
            tok = _fmt_tokens(ctx)
            cache_r = cmd_handler.total_cache_read
            if cache_r:
                parts.append(f" | {tok} tokens ({_fmt_tokens(cache_r)} cached)")
            else:
                parts.append(f" | {tok} tokens")
        parts.append(" | shift+tab: toggle mode | /help")
        return HTML("".join(parts))

    return _toolbar


def _create_keybindings(mode_state: dict, on_mode_toggle=None) -> KeyBindings:
    kb = KeyBindings()

    @kb.add(Keys.Enter)
    def _(event):
        event.current_buffer.validate_and_handle()

    @kb.add("escape", "enter")
    def _(event):
        event.current_buffer.insert_text("\n")

    @kb.add("s-tab")
    def _(event):
        old = mode_state["mode"]
        new_mode = "plan" if old == "act" else "act"
        mode_state["mode"] = new_mode
        if on_mode_toggle:
            on_mode_toggle(new_mode)
        if event.app:
            event.app.invalidate()

    return kb
