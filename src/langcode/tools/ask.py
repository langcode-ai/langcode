"""ask - AskUserQuestion tool."""

from __future__ import annotations

from typing import Any

from langchain.tools import tool
from prompt_toolkit import prompt as pt_prompt
from prompt_toolkit.formatted_text import HTML
from rich.console import Console

console = Console()


@tool("AskUserQuestion")
def ask(
    questions: list[dict[str, Any]],
    answers: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> str:
    """Use this tool when you need to ask the user questions during execution. This allows you to:
    1. Gather user preferences or requirements
    2. Clarify ambiguous instructions
    3. Get decisions on implementation choices as you work
    4. Offer choices to the user about what direction to take.

    Usage notes:
    - Users will always be able to select "Other" to provide custom text input
    - Use multiSelect: true to allow multiple answers to be selected for a question
    - If you recommend a specific option, make that the first option in the list and add "(Recommended)" at the end of the label

    Plan mode note: In plan mode, use this tool to clarify requirements or choose between approaches BEFORE finalizing your plan. Do NOT use this tool to ask "Is my plan ready?" or "Should I proceed?" - use ExitPlanMode for plan approval.

    Args:
        questions: Questions to ask the user (1-4 questions). Each question has:
            - question: The complete question text, ending with a question mark.
            - header: Very short label displayed as a chip/tag (max 12 chars). E.g. "Auth method", "Library".
            - options: 2-4 choices, each with a "label" (1-5 words) and "description" (explains trade-offs).
            - multiSelect: Set to true to allow multiple selections.
        answers: User answers collected by the permission component (optional, injected by UI).
        metadata: Optional metadata for tracking and analytics (not displayed to user)."""
    results = []

    for q in questions:
        question_text = q.get("question", "")
        header = q.get("header", "")
        options = q.get("options", [])
        multi = q.get("multiSelect", False)

        console.print(
            f"\n[bold yellow]{header + ': ' if header else ''}[/bold yellow]{question_text}"
        )

        if options:
            for i, opt in enumerate(options, 1):
                label = opt.get("label", str(opt)) if isinstance(opt, dict) else str(opt)
                desc = opt.get("description", "") if isinstance(opt, dict) else ""
                if desc:
                    console.print(f"  [cyan]{i}.[/cyan] {label}  [dim]{desc}[/dim]")
                else:
                    console.print(f"  [cyan]{i}.[/cyan] {label}")
            console.print()

            if multi:
                raw = pt_prompt(HTML("<b>Your answer (comma-separated numbers or text): </b>"))
                selected = []
                for part in raw.split(","):
                    part = part.strip()
                    try:
                        idx = int(part) - 1
                        if 0 <= idx < len(options):
                            opt = options[idx]
                            selected.append(
                                opt.get("label", str(opt)) if isinstance(opt, dict) else str(opt)
                            )
                        else:
                            selected.append(part)
                    except ValueError:
                        if part:
                            selected.append(part)
                results.append(f"{question_text}: {', '.join(selected)}")
            else:
                raw = pt_prompt(HTML("<b>Your answer: </b>"))
                try:
                    idx = int(raw.strip()) - 1
                    if 0 <= idx < len(options):
                        opt = options[idx]
                        answer = opt.get("label", str(opt)) if isinstance(opt, dict) else str(opt)
                    else:
                        answer = raw.strip()
                except ValueError:
                    answer = raw.strip()
                results.append(f"{question_text}: {answer}")
        else:
            raw = pt_prompt(HTML("<b>Your answer: </b>"))
            results.append(f"{question_text}: {raw.strip()}")

    return "\n".join(results)
