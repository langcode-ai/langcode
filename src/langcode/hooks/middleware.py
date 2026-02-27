"""HooksMiddleware: runs PreToolUse / PostToolUse hooks around tool calls."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from langchain.agents.middleware import AgentMiddleware
from langchain.messages import ToolMessage
from langchain.tools.tool_node import ToolCallRequest
from langgraph.types import Command
from prompt_toolkit import prompt as pt_prompt
from rich.console import Console

from langcode.hooks import execute_hooks

if TYPE_CHECKING:
    from langcode.core.config import Config

console = Console()


class HooksMiddleware(AgentMiddleware):
    """Run PreToolUse / PostToolUse hooks around tool calls."""

    def __init__(self, config: Config):
        self.config = config

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command],
    ) -> ToolMessage | Command:
        tool_name = request.tool_call["name"]
        args = request.tool_call.get("args", {})

        file_path = args.get("file_path", "") or args.get("path", "")
        variables = {
            "TOOL_NAME": tool_name,
            "FILE": str(file_path),
        }

        pre_result = execute_hooks(
            self.config.hooks,
            "PreToolUse",
            match_value=tool_name,
            variables=variables,
        )

        if pre_result.permission == "deny":
            return ToolMessage(
                content="Tool call denied by hook.",
                tool_call_id=request.tool_call["id"],
            )

        if pre_result.permission == "ask":
            args_preview = str(args)[:200]
            console.print(
                f"\n[bold yellow]Tool:[/bold yellow] {tool_name}\n[dim]{args_preview}[/dim]"
            )
            answer = pt_prompt("Allow? [y/N] ").strip().lower()
            if answer not in ("y", "yes"):
                return ToolMessage(
                    content="Tool call denied by user.",
                    tool_call_id=request.tool_call["id"],
                )

        if pre_result.updated_input:
            merged = {**args, **pre_result.updated_input}
            request.tool_call["args"] = merged

        for msg in pre_result.messages:
            if msg and msg != "__confirm__":
                console.print(f"  [dim]hook: {msg}[/dim]")

        result = handler(request)

        post_result = execute_hooks(
            self.config.hooks,
            "PostToolUse",
            match_value=tool_name,
            variables=variables,
        )
        for msg in post_result.messages:
            if msg:
                console.print(f"  [dim]hook: {msg}[/dim]")

        return result
