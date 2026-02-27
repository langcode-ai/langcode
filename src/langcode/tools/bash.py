"""bash - Run a bash command."""

from __future__ import annotations

import subprocess
import threading
import uuid

from langchain.tools import tool

from ..core.utils import truncate

# background task registry: task_id -> (thread, output_list, done_event)
_bg_tasks: dict[str, tuple[threading.Thread, list[str], threading.Event]] = {}


@tool("Bash")
def bash(
    command: str,
    description: str = "",
    timeout: int | None = None,
    run_in_background: bool = False,
    dangerously_disable_sandbox: bool = False,
) -> str:
    """Executes a given bash command and returns its output.

    IMPORTANT: Avoid using this tool to run find, grep, cat, head, tail, sed, awk, or echo commands, unless explicitly instructed. Instead, use the appropriate dedicated tool as this will provide a much better experience:
    - File search: Use Glob (NOT find or ls)
    - Content search: Use Grep (NOT grep or rg)
    - Read files: Use Read (NOT cat/head/tail)
    - Edit files: Use Edit (NOT sed/awk)
    - Write files: Use Write (NOT echo/heredoc)

    # Instructions
    - Always quote file paths that contain spaces with double quotes.
    - Try to maintain your current working directory throughout the session by using absolute paths.
    - Write a clear, concise description of what your command does in the description parameter.

    # Committing changes with git
    Only create commits when requested by the user. When creating git commits:
    - NEVER update the git config
    - NEVER run destructive git commands (push --force, reset --hard) unless explicitly requested
    - NEVER skip hooks (--no-verify) unless explicitly requested
    - Always create NEW commits rather than amending, unless the user explicitly requests a git amend
    - When staging files, prefer adding specific files by name rather than git add -A
    - NEVER commit changes unless the user explicitly asks

    # Creating pull requests
    Use the gh command for ALL GitHub-related tasks including PRs, issues, checks, and releases.

    Args:
        command: The command to execute.
        description: Clear, concise description of what this command does in active voice. For simple commands keep it brief (5-10 words). For complex commands add enough context to clarify what it does.
        timeout: Optional timeout in milliseconds (max 600000). If not specified, defaults to 120000ms.
        run_in_background: Set to true to run this command in the background. Returns a task_id — use TaskOutput to read the output later.
        dangerously_disable_sandbox: Set to true to dangerously override sandbox mode and run without sandboxing."""
    timeout_s = (timeout / 1000) if timeout is not None else 120

    if run_in_background:
        task_id = uuid.uuid4().hex[:8]
        output: list[str] = []
        done = threading.Event()

        def _run():
            try:
                result = subprocess.run(
                    ["bash", "-c", command],
                    capture_output=True,
                    text=True,
                    timeout=timeout_s,
                    cwd=None,
                )
                if result.stdout:
                    output.append(result.stdout)
                if result.stderr:
                    output.append(f"[stderr]\n{result.stderr}")
                output.append(f"[exit code: {result.returncode}]")
            except subprocess.TimeoutExpired:
                output.append(f"Error: command timed out after {timeout_s}s")
            except Exception as e:
                output.append(f"Error: {e}")
            finally:
                done.set()

        t = threading.Thread(target=_run, daemon=True)
        _bg_tasks[task_id] = (t, output, done)
        t.start()
        return f"Background task started. task_id: {task_id}"

    try:
        result = subprocess.run(
            ["bash", "-c", command],
            capture_output=True,
            text=True,
            timeout=timeout_s,
            cwd=None,
        )
        parts = []
        if result.stdout:
            parts.append(result.stdout)
        if result.stderr:
            parts.append(f"[stderr]\n{result.stderr}")
        parts.append(f"[exit code: {result.returncode}]")
        return truncate("\n".join(parts))
    except subprocess.TimeoutExpired:
        return f"Error: command timed out after {timeout_s}s"
    except Exception as e:
        return f"Error: {e}"
