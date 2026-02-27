"""Rich-based streaming output renderer for agent responses."""

from __future__ import annotations

from langchain.messages import AIMessageChunk
from rich.console import Console
from rich.status import Status

console = Console()


def _extract_usage(token) -> dict:
    usage = getattr(token, "usage_metadata", None)
    if not usage:
        return {}
    if isinstance(usage, dict):
        details = usage.get("input_token_details", {}) or {}
        return {
            "input_tokens": usage.get("input_tokens", 0) or 0,
            "output_tokens": usage.get("output_tokens", 0) or 0,
            "cache_read": details.get("cache_read", 0) or 0,
            "cache_creation": details.get("cache_creation", 0) or 0,
        }
    details = getattr(usage, "input_token_details", None)
    return {
        "input_tokens": getattr(usage, "input_tokens", 0) or 0,
        "output_tokens": getattr(usage, "output_tokens", 0) or 0,
        "cache_read": getattr(details, "cache_read", 0) or 0 if details else 0,
        "cache_creation": getattr(details, "cache_creation", 0) or 0 if details else 0,
    }


def _format_tool_args(args: dict) -> str:
    """Format tool call args as a compact one-line summary."""
    parts = []
    for k, v in args.items():
        sv = str(v).replace("\n", "\\n")
        if len(sv) > 60:
            sv = sv[:57] + "..."
        parts.append(f"{k}: {sv}")
    return ", ".join(parts)


def stream_agent_response(agent, user_message: str, thread_id: str, config) -> dict:
    """Stream agent response with Rich rendering. Returns token usage stats.

    Uses thread_id + checkpointer for conversation state management.
    Only the new user message is passed; history is managed by the checkpoint.

    Raises KeyboardInterrupt immediately on Ctrl-C for fast interruption.
    """
    import signal

    interrupted = False

    def _on_sigint(signum, frame):
        nonlocal interrupted
        interrupted = True
        raise KeyboardInterrupt

    text_buffer = ""
    current_tool = None
    input_tokens = 0
    output_tokens = 0
    cache_read = 0
    cache_creation = 0
    spinner: Status | None = Status("thinking...", console=console, spinner="dots")
    spinner.start()

    old_handler = signal.getsignal(signal.SIGINT)
    signal.signal(signal.SIGINT, _on_sigint)

    run_config = {"configurable": {"thread_id": thread_id}}

    try:
        for stream_mode, data in agent.stream(
            {"messages": [{"role": "user", "content": user_message}]},
            stream_mode=["messages", "updates"],
            config=run_config,
        ):
            if interrupted:
                break

            if stream_mode == "messages":
                token, metadata = data
                if isinstance(token, AIMessageChunk):
                    if token.text:
                        if spinner:
                            spinner.stop()
                            spinner = None
                        text_buffer += token.text
                        console.print(token.text, end="", markup=False, highlight=False)
                    if token.tool_call_chunks:
                        for tc in token.tool_call_chunks:
                            if tc.get("name"):
                                if spinner:
                                    spinner.stop()
                                    spinner = None
                                current_tool = tc["name"]
                                console.print(f"\n  > {current_tool}", style="dim")

            elif stream_mode == "updates":
                for source, update in data.items():
                    if source == "model":
                        for msg in update.get("messages", []):
                            u = _extract_usage(msg)
                            if u:
                                input_tokens += u["input_tokens"]
                                output_tokens += u["output_tokens"]
                                cache_read += u["cache_read"]
                                cache_creation += u["cache_creation"]
                            tool_calls = getattr(msg, "tool_calls", None) or []
                            for tc in tool_calls:
                                name = tc.get("name") or tc.get("function", {}).get("name")
                                if not name:
                                    continue
                                # Print name if not yet printed from chunks
                                if name != current_tool:
                                    if spinner:
                                        spinner.stop()
                                        spinner = None
                                    console.print(f"\n  > {name}", style="dim")
                                current_tool = name
                                # Print args summary
                                args = tc.get("args", {})
                                if args and isinstance(args, dict):
                                    summary = _format_tool_args(args)
                                    if summary:
                                        console.print(f"    {summary}", style="dim")
                    elif source == "tools":
                        if not spinner:
                            spinner = Status(
                                f"  running {current_tool}...",
                                console=console,
                                spinner="dots",
                            )
                            spinner.start()
                        msgs = update.get("messages", [])
                        for msg in msgs:
                            if hasattr(msg, "content"):
                                if spinner:
                                    spinner.stop()
                                    spinner = None
                                content = (
                                    msg.content
                                    if isinstance(msg.content, str)
                                    else str(msg.content)
                                )
                                preview = content[:200] + "..." if len(content) > 200 else content
                                indented = preview.replace("\n", "\n    ")
                                console.print(f"    {indented}", style="dim")
    finally:
        signal.signal(signal.SIGINT, old_handler)
        if spinner:
            spinner.stop()

    if interrupted:
        raise KeyboardInterrupt

    if text_buffer:
        console.print()

    return {
        "text": text_buffer,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_read": cache_read,
        "cache_creation": cache_creation,
    }
