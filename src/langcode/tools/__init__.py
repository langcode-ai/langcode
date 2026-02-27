"""Tool registry: get_tools() / get_readonly_tools() / get_tools_by_names()."""

from __future__ import annotations

from langchain.tools import BaseTool

from .ask import ask
from .bash import bash
from .edit import edit
from .glob import glob_tool as glob
from .grep import grep
from .plan_mode import enter_plan_mode, exit_plan_mode
from .read import read
from .task import create_task_tool as create_task_tool
from .todo import task_create, task_get, task_list, task_update
from .web_fetch import web_fetch
from .web_search import web_search
from .write import write

# Name → tool mapping for dynamic lookup.
TOOL_MAP: dict[str, BaseTool] = {
    "Read": read,
    "Write": write,
    "Edit": edit,
    "Glob": glob,
    "Grep": grep,
    "Bash": bash,
    "AskUserQuestion": ask,
    "WebFetch": web_fetch,
    "WebSearch": web_search,
    "TaskCreate": task_create,
    "TaskUpdate": task_update,
    "TaskList": task_list,
    "TaskGet": task_get,
    "EnterPlanMode": enter_plan_mode,
    "ExitPlanMode": exit_plan_mode,
}

# Default sub-agent tools when no explicit tools list is given.
DEFAULT_SUB_TOOLS = ["Read", "Write", "Edit", "Glob", "Grep"]


def get_tools() -> list[BaseTool]:
    """All tools for the main agent."""
    return [
        read,
        write,
        edit,
        glob,
        grep,
        bash,
        ask,
        web_fetch,
        web_search,
        task_create,
        task_update,
        task_list,
        task_get,
        enter_plan_mode,
        exit_plan_mode,
    ]


def get_readonly_tools() -> list[BaseTool]:
    """Read-only tools for sub-agents (plan mode)."""
    return [read, glob, grep]


def get_tools_by_names(names: list[str]) -> list[BaseTool]:
    """Return tools matching the given name list. Unknown names are skipped."""
    return [TOOL_MAP[n] for n in names if n in TOOL_MAP]
