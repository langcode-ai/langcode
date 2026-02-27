"""plan_mode - EnterPlanMode and ExitPlanMode tools for switching between plan/act modes."""

from __future__ import annotations

from typing import Annotated

from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command


@tool("EnterPlanMode")
def enter_plan_mode(
    state: Annotated[dict, InjectedState],
) -> Command:
    """Use this tool proactively when you're about to start a non-trivial implementation task. Getting user sign-off on your approach before writing code prevents wasted effort and ensures alignment. This tool transitions you into plan mode where you can explore the codebase and design an implementation approach for user approval.

    ## When to Use This Tool

    Prefer using EnterPlanMode for implementation tasks unless they're simple. Use it when ANY of these conditions apply:
    - New feature implementation requiring architectural decisions
    - Multiple valid approaches exist for the task
    - Code modifications that affect existing behavior or structure
    - Multi-file changes (more than 2-3 files)
    - Unclear requirements where you need to explore before understanding the full scope
    - If you would use AskUserQuestion to clarify the approach, use EnterPlanMode instead

    ## When NOT to Use This Tool

    Only skip EnterPlanMode for simple tasks:
    - Single-line or few-line fixes (typos, obvious bugs, small tweaks)
    - Tasks where the user has given very specific, detailed instructions
    - Pure research/exploration tasks (use the Task tool with Explore agent instead)

    ## Important Notes

    - In plan mode you can explore the codebase but CANNOT modify files
    - Use ExitPlanMode when you have finished planning and are ready for user approval to implement"""
    return Command(update={"mode": "plan"})  # type: ignore[return-value]


@tool("ExitPlanMode")
def exit_plan_mode(
    allowedPrompts: list[dict[str, str]] | None = None,
    state: Annotated[dict | None, InjectedState] = None,
) -> Command:
    """Use this tool when you are in plan mode and have finished designing your plan and are ready for user approval.

    ## How This Tool Works
    - This tool signals that you're done planning and ready for the user to review and approve
    - After calling this tool, the session switches back to act mode for implementation

    ## When to Use This Tool
    IMPORTANT: Only use this tool when the task requires planning the implementation steps of a task that requires writing code. For research tasks — do NOT use this tool.

    ## Before Using This Tool
    Ensure your plan is complete and unambiguous:
    - If you have unresolved questions, use AskUserQuestion first
    - Once your plan is finalized, use THIS tool to request approval

    Do NOT use AskUserQuestion to ask "Is my plan okay?" — that's exactly what THIS tool does.

    Args:
        allowedPrompts: Prompt-based permissions needed to implement the plan. Each entry has:
            - tool: The tool this prompt applies to (e.g. "Bash")
            - prompt: Semantic description of the action, e.g. "run tests", "install dependencies" """
    return Command(update={"mode": "act"})  # type: ignore[return-value]
