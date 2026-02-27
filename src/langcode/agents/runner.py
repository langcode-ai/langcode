"""Agent factory: create_main_agent, create_sub_agent, checkpointer, stop-hook runners."""

from __future__ import annotations

from typing import TYPE_CHECKING

from langchain.agents import create_agent
from langchain.agents.middleware import (
    ClearToolUsesEdit,
    ContextEditingMiddleware,
    ModelCallLimitMiddleware,
    ModelRetryMiddleware,
    SummarizationMiddleware,
    ToolRetryMiddleware,
)
from langchain_anthropic.middleware import (
    AnthropicPromptCachingMiddleware,
)

from langcode.hooks import execute_hooks
from langcode.hooks.middleware import HooksMiddleware
from langcode.tools import DEFAULT_SUB_TOOLS, get_tools, get_tools_by_names
from langcode.tools.task import create_task_tool

from .patch import PatchToolCallsMiddleware
from .prompt import build_prompt
from .state import LangcodeState

if TYPE_CHECKING:
    from langgraph.checkpoint.base import BaseCheckpointSaver

    from langcode.agents.subagent import AgentDef
    from langcode.core.config import Config


def create_sqlite_checkpointer(config: Config) -> BaseCheckpointSaver:
    """Create a SqliteSaver stored at ~/.langcode/checkpoints.sqlite."""
    import sqlite3

    from langgraph.checkpoint.sqlite import SqliteSaver

    config.global_dir.mkdir(parents=True, exist_ok=True)
    db_path = config.global_dir / "checkpoints.sqlite"
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    return SqliteSaver(conn)


def create_main_agent(
    config: Config,
    skills_content: str = "",
    mcp_tools: list | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
):
    """Create the main coding agent with full tools and middleware."""
    tools = get_tools()
    tools.append(create_task_tool(config))
    if mcp_tools:
        tools.extend(mcp_tools)

    middleware = [
        PatchToolCallsMiddleware(),
        AnthropicPromptCachingMiddleware(ttl="5m"),
        ModelRetryMiddleware(
            max_retries=3, backoff_factor=2.0, initial_delay=1.0, on_failure="continue"
        ),
        ToolRetryMiddleware(max_retries=2, backoff_factor=2.0, initial_delay=0.5),
        ModelCallLimitMiddleware(run_limit=200),
        SummarizationMiddleware(
            model=config.model, trigger=("fraction", 0.85), keep=("fraction", 0.10)
        ),
        ContextEditingMiddleware(edits=[ClearToolUsesEdit(trigger=100000, keep=5)]),
        HooksMiddleware(config),
    ]

    if checkpointer is None:
        checkpointer = create_sqlite_checkpointer(config)

    return create_agent(
        model=config.model,
        tools=tools,
        system_prompt=build_prompt(config, skills_content),
        middleware=middleware,
        state_schema=LangcodeState,
        checkpointer=checkpointer,
    )


def create_sub_agent(
    config: Config,
    agent_def: AgentDef | None = None,
    model_override: str | None = None,
):
    """Create a sub-agent, optionally configured by an AgentDef."""
    _default_prompt = (
        "You are a sub-agent for LangCode. Given the user's message, use the "
        "tools available to complete the task. Do what has been asked; nothing "
        "more, nothing less. When you complete the task, respond with a detailed "
        "writeup.\n\n"
        "Guidelines:\n"
        "- For file searches: use Grep or Glob to search broadly, Read when you "
        "know the specific file path.\n"
        "- Be thorough: check multiple locations, consider different naming "
        "conventions, look for related files.\n"
        "- NEVER create files unless absolutely necessary. Prefer editing existing files.\n"
        "- In your final response, share relevant file names and code snippets. "
        "Use absolute file paths.\n"
        "- Do not use emojis."
    )

    if agent_def is not None:
        tool_names = agent_def.tools if agent_def.tools else list(DEFAULT_SUB_TOOLS)
        tools = get_tools_by_names(tool_names)
        model = model_override or (
            config.model
            if (agent_def.model == "inherit" or not agent_def.model)
            else agent_def.model
        )
        system_prompt = agent_def.prompt or (
            f"You are the '{agent_def.name}' sub-agent. {agent_def.description}\n\n{_default_prompt}"
        )
    else:
        tools = get_tools_by_names(list(DEFAULT_SUB_TOOLS))
        model = model_override or config.model
        system_prompt = _default_prompt

    return create_agent(model=model, tools=tools, system_prompt=system_prompt)


def run_stop_hooks(config: Config) -> bool:
    """Run Stop hooks. Returns True if agent should stop."""
    return execute_hooks(config.hooks, "Stop", match_value="*").decision != "block"


def run_subagent_stop_hooks(config: Config) -> bool:
    """Run SubagentStop hooks. Returns True if subagent should stop."""
    return execute_hooks(config.hooks, "SubagentStop", match_value="*").decision != "block"
