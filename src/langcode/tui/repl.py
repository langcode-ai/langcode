"""Interactive REPL loop built on prompt_toolkit."""

from __future__ import annotations

import time
from collections.abc import Callable

from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import merge_completers
from prompt_toolkit.history import FileHistory

from ..agents.context import build_context
from ..commands import CommandHandler, CommandResult
from ..hooks import execute_hooks
from .completers import _FileCompleter, _SlashCompleter
from .prompt_builders import _build_prompt, _build_toolbar, _create_keybindings
from .references import expand_at_references
from .renderer import console, stream_agent_response
from .session_picker import pick_session_tui


def _inject_mode_change(agent, thread_id: str, new_mode: str) -> None:
    """Inject EnterPlanMode/ExitPlanMode tool call into conversation history."""
    import uuid

    from langchain_core.messages import AIMessage, ToolMessage

    tool_name = "EnterPlanMode" if new_mode == "plan" else "ExitPlanMode"
    call_id = uuid.uuid4().hex[:8]
    agent.update_state(
        {"configurable": {"thread_id": thread_id}},
        {
            "mode": new_mode,
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[
                        {"name": tool_name, "args": {}, "id": call_id, "type": "tool_call"}
                    ],
                ),
                ToolMessage(
                    content=f"Mode switched to {new_mode}.",
                    tool_call_id=call_id,
                ),
            ],
        },
    )


def run_repl(
    config,
    agent,
    cmd_handler: CommandHandler,
    mcp_mgr=None,
    checkpointer=None,
    *,
    print_banner: Callable,
    generate_thread_id: Callable,
    save_session: Callable,
    list_sessions: Callable,
    create_command_agent: Callable,
):
    history_path = config.global_dir / "history"
    config.global_dir.mkdir(parents=True, exist_ok=True)

    mode_state = {"mode": "act"}
    thread_id_ref = {"value": None}

    def _on_mode_toggle(new_mode: str) -> None:
        tid = thread_id_ref["value"]
        if tid:
            try:
                _inject_mode_change(agent, tid, new_mode)
            except Exception:
                pass

    session: PromptSession = PromptSession(
        history=FileHistory(str(history_path)),
        key_bindings=_create_keybindings(mode_state, on_mode_toggle=_on_mode_toggle),
        multiline=False,
        completer=merge_completers([_SlashCompleter(cmd_handler), _FileCompleter(config.cwd)]),
        auto_suggest=AutoSuggestFromHistory(),
        bottom_toolbar=_build_toolbar(config, cmd_handler, mode_state),
    )

    print_banner(config)

    # ── SessionStart hook ───────────────────────────────────────────
    execute_hooks(config.hooks, "SessionStart", match_value="*")

    try:
        _run_repl_loop(
            config,
            agent,
            cmd_handler,
            session,
            mcp_mgr,
            mode_state,
            checkpointer,
            thread_id_ref=thread_id_ref,
            generate_thread_id=generate_thread_id,
            save_session=save_session,
            list_sessions=list_sessions,
            create_command_agent=create_command_agent,
        )
    finally:
        # ── SessionEnd hook ────────────────────────────────────────────
        execute_hooks(config.hooks, "SessionEnd", match_value="*")


def _run_repl_loop(
    config,
    agent,
    cmd_handler,
    session,
    mcp_mgr,
    mode_state,
    checkpointer=None,
    *,
    thread_id_ref: dict,
    generate_thread_id: Callable,
    save_session: Callable,
    list_sessions: Callable,
    create_command_agent: Callable,
):
    from ..agents import create_main_agent, run_stop_hooks

    thread_id = generate_thread_id()
    thread_id_ref["value"] = thread_id
    save_session(config, thread_id)
    last_interrupt: float = 0
    _mcp_tools_loaded = False

    while True:
        # Hot-reload MCP tools once background loading finishes
        if mcp_mgr and not _mcp_tools_loaded and not mcp_mgr.is_loading:
            mcp_tools = mcp_mgr.get_tools()
            if mcp_tools:
                agent = create_main_agent(
                    config, build_context(config), mcp_tools, checkpointer=checkpointer
                )
            _mcp_tools_loaded = True

        try:
            user_input = session.prompt(_build_prompt(mode_state["mode"])).strip()
            last_interrupt = 0
        except KeyboardInterrupt:
            now = time.time()
            if now - last_interrupt < 1.0:
                console.print("\nbye", style="dim")
                break
            last_interrupt = now
            console.print("\npress Ctrl-C again to exit", style="dim")
            continue
        except EOFError:
            console.print()
            break

        if not user_input:
            continue

        # slash commands
        cmd_result = None
        if cmd_handler.is_command(user_input):
            lower = user_input.strip().lower()

            # Handle /new and /clear → start a fresh session
            if lower in ("/new", "/clear"):
                thread_id = generate_thread_id()
                thread_id_ref["value"] = thread_id
                save_session(config, thread_id)
                console.print("new session", style="dim")
                continue

            # Handle /resume → TUI session picker
            if lower == "/resume":
                picked = pick_session_tui(list_sessions(config), thread_id)
                if picked and picked != thread_id:
                    thread_id = picked
                    thread_id_ref["value"] = thread_id
                    # Restore mode from checkpoint state
                    try:
                        snap = agent.get_state({"configurable": {"thread_id": thread_id}})
                        restored = snap.values.get("mode") if snap else None
                        if restored in ("plan", "act"):
                            mode_state["mode"] = restored
                    except Exception:
                        pass
                    console.print(f"resumed session ({mode_state['mode']} mode)", style="dim")
                elif picked == thread_id:
                    console.print("already on this session", style="dim")
                continue

            # Handle /plan and /act → toggle mode
            if lower == "/plan":
                mode_state["mode"] = "plan"
                try:
                    _inject_mode_change(agent, thread_id, "plan")
                except Exception:
                    pass
                console.print("switched to [bold]plan[/bold] mode (read-only)", style="dim")
                continue
            if lower == "/act":
                mode_state["mode"] = "act"
                try:
                    _inject_mode_change(agent, thread_id, "act")
                except Exception:
                    pass
                console.print("switched to [bold]act[/bold] mode", style="dim")
                continue

            result = cmd_handler.handle(user_input)
            if result == "quit":
                break
            elif isinstance(result, CommandResult):
                # Custom command with structured result
                cmd_result = result
                user_input = result.prompt
            elif isinstance(result, str) and result:
                console.print(result)
                continue
            else:
                continue

        # normal message → agent (expand @file references)
        expanded = expand_at_references(user_input, config.cwd)

        # Always update session with latest user query
        save_session(config, thread_id, query=user_input[:200].replace("\n", " "))

        # ── UserPromptSubmit hook ───────────────────────────────────
        submit_result = execute_hooks(config.hooks, "UserPromptSubmit", match_value="*")
        for msg in submit_result.messages:
            if msg:
                console.print(f"  [dim]{msg}[/dim]")

        t0 = time.time()

        # Use restricted agent if custom command specifies allowed-tools/model
        active_agent = agent
        if cmd_result and (cmd_result.allowed_tools or cmd_result.model):
            active_agent = create_command_agent(
                config, cmd_result, mcp_mgr, checkpointer=checkpointer
            )

        try:
            result = stream_agent_response(active_agent, expanded, thread_id, config)
            cmd_handler.total_input_tokens += result.get("input_tokens", 0)
            cmd_handler.total_output_tokens += result.get("output_tokens", 0)
            cmd_handler.total_cache_read += result.get("cache_read", 0)
            cmd_handler.total_cache_creation += result.get("cache_creation", 0)

            # ── Sync mode from agent state ────────────────────────────
            try:
                snap = active_agent.get_state({"configurable": {"thread_id": thread_id}})
                new_mode = snap.values.get("mode") if snap else None
                if new_mode and new_mode != mode_state["mode"]:
                    mode_state["mode"] = new_mode
                    label = "plan (read-only)" if new_mode == "plan" else "act"
                    console.print(f"switched to [bold]{label}[/bold] mode", style="dim")
            except Exception:
                pass

            # ── Stop hook ───────────────────────────────────────────
            run_stop_hooks(config)
        except KeyboardInterrupt:
            console.print("\ninterrupted", style="dim")
        except Exception as e:
            console.print(f"\nerror: {e}", style="bold")
            if config.verbose:
                console.print_exception()
        elapsed = time.time() - t0
        console.print(f"{elapsed:.1f}s", style="dim")
        console.print()
