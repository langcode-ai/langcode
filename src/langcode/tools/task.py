"""task - Delegate a subtask to a sub-agent."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from langchain.tools import tool

if TYPE_CHECKING:
    from ..core.config import Config


# Module-level cache for loaded agent definitions.
_agents_cache: dict | None = None


def _get_agents(config: Config):
    """Load and cache agent definitions."""
    global _agents_cache
    if _agents_cache is None:
        from ..agents.subagent import load_agents

        _agents_cache = load_agents(config)
    return _agents_cache


def create_task_tool(config: Config):
    """Create a task tool bound to a config (needs to create sub-agent)."""
    from ..agents import create_sub_agent, run_subagent_stop_hooks

    @tool("Task")
    def task(
        description: str,
        prompt: str,
        subagent_type: str = "",
        model: str = "",
        resume: str = "",
        run_in_background: bool = False,
        max_turns: int = 0,
    ) -> str:
        """Launch a new agent to handle complex, multi-step tasks autonomously.

        The Task tool launches specialized agents (subprocesses) that autonomously handle complex tasks. Each agent type has specific capabilities and tools available to it.

        Available agent types and the tools they have access to:
        - general-purpose: General-purpose agent for researching complex questions, searching for code, and executing multi-step tasks. When you are searching for a keyword or file and are not confident that you will find the right match in the first few tries use this agent to perform the search for you. (Tools: *)
        - Explore: Fast agent specialized for exploring codebases. Use this when you need to quickly find files by patterns (eg. "src/components/**/*.tsx"), search code for keywords (eg. "API endpoints"), or answer questions about the codebase (eg. "how do API endpoints work?"). When calling this agent, specify the desired thoroughness level: "quick" for basic searches, "medium" for moderate exploration, or "very thorough" for comprehensive analysis across multiple locations and naming conventions. (Tools: All tools except Write, Edit)
        - Plan: Software architect agent for designing implementation plans. Use this when you need to plan the implementation strategy for a task. Returns step-by-step plans, identifies critical files, and considers architectural trade-offs. (Tools: All tools except Write, Edit)

        When using the Task tool, you must specify a subagent_type parameter to select which agent type to use.

        When NOT to use the Task tool:
        - If you want to read a specific file path, use the Read or Glob tool instead of the Task tool, to find the match more quickly
        - If you are searching for a specific class definition like "class Foo", use the Glob tool instead, to find the match more quickly
        - If you are searching for code within a specific file or set of 2-3 files, use the Read tool instead of the Task tool, to find the match more quickly
        - Other tasks that are not related to the agent descriptions above

        Usage notes:
        - Always include a short description (3-5 words) summarizing what the agent will do
        - Launch multiple agents concurrently whenever possible, to maximize performance; to do that, use a single message with multiple tool uses
        - When the agent is done, it will return a single message back to you. The result returned by the agent is not visible to the user. To show the user the result, you should send a text message back to the user with a concise summary of the result.
        - Provide clear, detailed prompts so the agent can work autonomously and return exactly the information you need.
        - Clearly tell the agent whether you expect it to write code or just to do research (search, file reads, web fetches, etc.), since it is not aware of the user's intent
        - If the user specifies that they want you to run agents "in parallel", you MUST send a single message with multiple Task tool use content blocks.

        Args:
            description: A short (3-5 word) description of the task.
            prompt: The task for the agent to perform.
            subagent_type: The type of specialized agent to use for this task.
            model: Optional model to use for this agent. If not specified, inherits from parent. Prefer haiku for quick, straightforward tasks to minimize cost and latency.
            resume: Optional agent ID to resume from. If provided, the agent will continue with its full previous context preserved.
            run_in_background: Set to true to run this agent in the background. Returns immediately with a task_id.
            max_turns: Maximum number of agentic turns (API round-trips) before stopping."""
        agent_def = None
        if subagent_type:
            agents = _get_agents(config)
            agent_def = agents.get(subagent_type)
            if agent_def is None:
                available = ", ".join(agents.keys()) if agents else "(none)"
                return f"Error: agent '{subagent_type}' not found. Available agents: {available}"

        # Override model if specified
        effective_model = model if model else None
        sub_agent = create_sub_agent(config, agent_def=agent_def, model_override=effective_model)

        thread_id = resume if resume else uuid.uuid4().hex[:8]
        result = sub_agent.invoke(
            {"messages": [{"role": "user", "content": f"Task: {description}\n\n{prompt}"}]},
            config={"configurable": {"thread_id": thread_id}},
        )

        # Run SubagentStop hooks
        run_subagent_stop_hooks(config)

        # extract final AI message text
        messages = result.get("messages", [])
        for msg in reversed(messages):
            if hasattr(msg, "content") and isinstance(msg.content, str) and msg.content:
                return msg.content
        return "Sub-agent completed without text response."

    return task
