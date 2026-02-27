"""Task management tools: TaskCreate, TaskUpdate, TaskList, TaskGet."""

from __future__ import annotations

import json
from typing import Annotated, Any

from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command


def _get_tasks(state: dict) -> list[dict]:
    return state.get("tasks", [])


def _next_id(tasks: list[dict]) -> str:
    if not tasks:
        return "1"
    max_id = max((int(t.get("id", 0)) for t in tasks if str(t.get("id", "")).isdigit()), default=0)
    return str(max_id + 1)


@tool("TaskCreate")
def task_create(
    subject: str,
    description: str,
    activeForm: str = "",
    metadata: dict[str, Any] | None = None,
    state: Annotated[dict | None, InjectedState] = None,
) -> Command:
    """Create a structured task to track progress on complex multi-step work.

    Use this tool proactively for:
    - Complex multi-step tasks (3+ distinct steps)
    - When user provides multiple tasks at once
    - Non-trivial tasks requiring planning

    Skip for single straightforward tasks completable in 1-2 steps.

    Args:
        subject: Brief, actionable title in imperative form (e.g. "Fix authentication bug in login flow").
        description: Detailed description of what needs to be done, including context and acceptance criteria.
        activeForm: Present continuous form shown while in_progress (e.g. "Fixing authentication bug"). Always provide this.
        metadata: Arbitrary metadata to attach to the task."""
    tasks = list(_get_tasks(state or {}))
    new_task: dict[str, Any] = {
        "id": _next_id(tasks),
        "subject": subject,
        "description": description,
        "activeForm": activeForm,
        "status": "pending",
        "blockedBy": [],
        "blocks": [],
    }
    if metadata:
        new_task["metadata"] = metadata
    tasks.append(new_task)
    return Command(update={"tasks": tasks})  # type: ignore[return-value]


@tool("TaskUpdate")
def task_update(
    taskId: str,
    status: str = "",
    subject: str = "",
    description: str = "",
    activeForm: str = "",
    addBlockedBy: list[str] | None = None,
    addBlocks: list[str] | None = None,
    owner: str = "",
    metadata: dict[str, Any] | None = None,
    state: Annotated[dict | None, InjectedState] = None,
) -> Command:
    """Update a task's status or details.

    Status workflow: pending → in_progress → completed. Use "deleted" to remove a task.

    ONLY mark completed when FULLY accomplished — not if tests are failing, implementation is partial, or errors are unresolved.

    Args:
        taskId: The ID of the task to update.
        status: New status: pending, in_progress, completed, or deleted.
        subject: New subject (imperative form, e.g. "Run tests").
        description: New description for the task.
        activeForm: Present continuous form shown while in_progress (e.g. "Running tests").
        addBlockedBy: Task IDs that must complete before this one can start.
        addBlocks: Task IDs that cannot start until this one completes.
        owner: New owner for the task (agent name).
        metadata: Metadata keys to merge into the task. Set a key to null to delete it."""
    tasks = list(_get_tasks(state or {}))
    new_tasks = []
    for t in tasks:
        if t.get("id") == taskId:
            if status == "deleted":
                continue
            t = dict(t)
            if status:
                t["status"] = status
            if subject:
                t["subject"] = subject
            if description:
                t["description"] = description
            if activeForm:
                t["activeForm"] = activeForm
            if owner:
                t["owner"] = owner
            if addBlockedBy:
                existing = t.get("blockedBy", [])
                t["blockedBy"] = list(set(existing) | set(addBlockedBy))
            if addBlocks:
                existing = t.get("blocks", [])
                t["blocks"] = list(set(existing) | set(addBlocks))
            if metadata:
                existing_meta = dict(t.get("metadata", {}))
                for k, v in metadata.items():
                    if v is None:
                        existing_meta.pop(k, None)
                    else:
                        existing_meta[k] = v
                t["metadata"] = existing_meta
        new_tasks.append(t)
    return Command(update={"tasks": new_tasks})  # type: ignore[return-value]


@tool("TaskList")
def task_list(
    state: Annotated[dict | None, InjectedState] = None,
) -> str:
    """List all tasks in the current session.

    Use this to:
    - See available tasks (status: pending, no owner, not blocked)
    - Check overall progress
    - Find blocked tasks
    - After completing a task, find newly unblocked work

    Prefer working on tasks in ID order (lowest first)."""
    tasks = _get_tasks(state or {})
    if not tasks:
        return "No tasks."
    lines = []
    for t in tasks:
        blocked_by = t.get("blockedBy", [])
        blocked_str = f" [blocked by: {', '.join(blocked_by)}]" if blocked_by else ""
        owner_str = f" [owner: {t['owner']}]" if t.get("owner") else ""
        lines.append(f"[{t['id']}] {t['status'].upper()} — {t['subject']}{blocked_str}{owner_str}")
    return "\n".join(lines)


@tool("TaskGet")
def task_get(
    taskId: str,
    state: Annotated[dict | None, InjectedState] = None,
) -> str:
    """Get full details of a task by ID, including description, status, and dependencies.

    Use this when you need the full description and context before starting work on a task. After fetching, verify its blockedBy list is empty before beginning work.

    Args:
        taskId: The ID of the task to retrieve."""
    tasks = _get_tasks(state or {})
    for t in tasks:
        if t.get("id") == taskId:
            return json.dumps(t, ensure_ascii=False, indent=2)
    return f"Task '{taskId}' not found."
