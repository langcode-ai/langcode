"""LangcodeState: extended agent state with task tracking and mode."""

from typing import Any

from langchain.agents import AgentState


class LangcodeState(AgentState):
    """Extended agent state with task tracking and mode."""

    tasks: list[dict[str, Any]]
    mode: str
