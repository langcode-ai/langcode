"""Tests for langcode.tui.repl._run_repl_loop command dispatch logic."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from langcode.commands import CommandResult
from langcode.tui.repl import _run_repl_loop


def _make_fns(thread_ids=None):
    """Return the injectable callables _run_repl_loop expects."""
    _ids = list(thread_ids or ["tid-001"])
    generate_thread_id = MagicMock(side_effect=_ids + ["tid-extra"] * 10)
    save_session = MagicMock()
    list_sessions = MagicMock(return_value=[])
    create_plan_agent = MagicMock(return_value=MagicMock())
    create_command_agent = MagicMock(return_value=MagicMock())
    return dict(
        generate_thread_id=generate_thread_id,
        save_session=save_session,
        list_sessions=list_sessions,
        create_plan_agent=create_plan_agent,
        create_command_agent=create_command_agent,
    )


def _make_config():
    config = MagicMock()
    config.hooks = MagicMock()
    config.cwd = MagicMock()
    config.verbose = False
    return config


def _make_cmd_handler(is_command=False, handle_result=None):
    h = MagicMock()
    h.is_command = MagicMock(return_value=is_command)
    h.handle = MagicMock(return_value=handle_result)
    h.total_input_tokens = 0
    h.total_output_tokens = 0
    h.total_cache_read = 0
    h.total_cache_creation = 0
    return h


def _loop(inputs, fns=None, cmd_handler=None, mode_state=None, agent=None):
    """Drive _run_repl_loop with a scripted list of session.prompt() return values.

    The last value should raise EOFError to end the loop naturally.
    """
    session = MagicMock()
    # Build side_effect: strings return normally, EOFError ends the loop
    effects = []
    for inp in inputs:
        if inp is EOFError:
            effects.append(EOFError())
        else:
            effects.append(inp)
    session.prompt = MagicMock(side_effect=effects)

    config = _make_config()
    fns = fns or _make_fns()
    cmd_handler = cmd_handler or _make_cmd_handler()
    mode_state = mode_state or {"mode": "act"}
    agent = agent or MagicMock()

    with (
        patch("langcode.tui.repl.expand_at_references", side_effect=lambda t, _: t),
        patch("langcode.tui.repl.execute_hooks", return_value=MagicMock(messages=[])),
        patch(
            "langcode.tui.repl.stream_agent_response",
            return_value={
                "input_tokens": 10,
                "output_tokens": 5,
                "cache_read": 0,
                "cache_creation": 0,
            },
        ),
        patch("langcode.tui.repl.build_context", return_value=""),
        patch("langcode.tui.repl.pick_session_tui", return_value=None),
    ):
        with patch("langcode.tui.repl.console"):
            _run_repl_loop(
                config,
                agent,
                cmd_handler,
                session,
                None,
                mode_state,
                None,
                **fns,
            )

    return session, fns, cmd_handler, mode_state


class TestReplLoopBasic:
    def test_eof_exits_loop(self):
        session, fns, *_ = _loop([EOFError])
        fns["generate_thread_id"].assert_called_once()

    def test_empty_input_skipped(self):
        session, fns, cmd_handler, _ = _loop(["", "  ", EOFError])
        # stream_agent_response should NOT be called for empty inputs
        with patch("langcode.tui.repl.stream_agent_response") as mock_stream:
            _loop(["", EOFError])
            mock_stream.assert_not_called()

    def test_normal_message_calls_stream(self):
        with patch("langcode.tui.repl.stream_agent_response") as mock_stream:
            mock_stream.return_value = {
                "input_tokens": 0,
                "output_tokens": 0,
                "cache_read": 0,
                "cache_creation": 0,
            }
            with (
                patch("langcode.tui.repl.expand_at_references", side_effect=lambda t, _: t),
                patch("langcode.tui.repl.execute_hooks", return_value=MagicMock(messages=[])),
                patch("langcode.tui.repl.build_context", return_value=""),
                patch("langcode.tui.repl.pick_session_tui", return_value=None),
                patch("langcode.tui.repl.console"),
            ):
                config = _make_config()
                fns = _make_fns()
                cmd_handler = _make_cmd_handler(is_command=False)
                session = MagicMock()
                session.prompt = MagicMock(side_effect=["hello world", EOFError()])
                mode_state = {"mode": "act"}

                _run_repl_loop(
                    config, MagicMock(), cmd_handler, session, None, mode_state, None, **fns
                )

            mock_stream.assert_called_once()
            args = mock_stream.call_args
            assert args[0][1] == "hello world"

    def test_token_counts_accumulated(self):
        session, fns, cmd_handler, _ = _loop(["tell me something", EOFError])
        assert cmd_handler.total_input_tokens == 10
        assert cmd_handler.total_output_tokens == 5


class TestReplLoopSlashCommands:
    def test_new_resets_thread_id(self):
        fns = _make_fns(["tid-001", "tid-002"])
        cmd_handler = _make_cmd_handler(is_command=True, handle_result=None)
        cmd_handler.is_command = MagicMock(return_value=True)

        _loop(["/new", EOFError], fns=fns, cmd_handler=cmd_handler)

        # generate_thread_id called twice: once for init, once for /new
        assert fns["generate_thread_id"].call_count == 2

    def test_clear_resets_thread_id(self):
        fns = _make_fns(["tid-001", "tid-002"])
        cmd_handler = _make_cmd_handler(is_command=True)
        _loop(["/clear", EOFError], fns=fns, cmd_handler=cmd_handler)
        assert fns["generate_thread_id"].call_count == 2

    def test_plan_switches_mode(self):
        fns = _make_fns()
        cmd_handler = _make_cmd_handler(is_command=True)
        mode_state = {"mode": "act"}
        _loop(["/plan", EOFError], fns=fns, cmd_handler=cmd_handler, mode_state=mode_state)
        assert mode_state["mode"] == "plan"

    def test_act_switches_mode(self):
        fns = _make_fns()
        cmd_handler = _make_cmd_handler(is_command=True)
        mode_state = {"mode": "plan"}
        _loop(["/act", EOFError], fns=fns, cmd_handler=cmd_handler, mode_state=mode_state)
        assert mode_state["mode"] == "act"

    def test_quit_exits_loop(self):
        cmd_handler = _make_cmd_handler(is_command=True, handle_result="quit")
        session, fns, *_ = _loop(["/quit", EOFError], cmd_handler=cmd_handler)
        # If quit handled early, prompt is only called once (for /quit)
        assert session.prompt.call_count == 1

    def test_string_result_printed_not_streamed(self):
        cmd_handler = _make_cmd_handler(is_command=True, handle_result="some output text")
        with patch("langcode.tui.repl.stream_agent_response") as mock_stream:
            mock_stream.return_value = {}
            _loop(["/somecommand", EOFError], cmd_handler=cmd_handler)
            mock_stream.assert_not_called()

    def test_command_result_uses_restricted_agent(self):
        cmd_result = MagicMock(spec=CommandResult)
        cmd_result.prompt = "do something"
        cmd_result.allowed_tools = ["Read"]
        cmd_result.model = None
        cmd_handler = _make_cmd_handler(is_command=True, handle_result=cmd_result)
        fns = _make_fns()

        with patch("langcode.tui.repl.stream_agent_response") as mock_stream:
            mock_stream.return_value = {
                "input_tokens": 0,
                "output_tokens": 0,
                "cache_read": 0,
                "cache_creation": 0,
            }
            with (
                patch("langcode.tui.repl.expand_at_references", side_effect=lambda t, _: t),
                patch("langcode.tui.repl.execute_hooks", return_value=MagicMock(messages=[])),
                patch("langcode.tui.repl.build_context", return_value=""),
                patch("langcode.tui.repl.pick_session_tui", return_value=None),
                patch("langcode.tui.repl.console"),
            ):
                config = _make_config()
                session = MagicMock()
                session.prompt = MagicMock(side_effect=["/mycmd", EOFError()])
                _run_repl_loop(
                    config, MagicMock(), cmd_handler, session, None, {"mode": "act"}, None, **fns
                )

        fns["create_command_agent"].assert_called_once()


class TestReplLoopPlanMode:
    def test_plan_mode_uses_plan_agent(self):
        fns = _make_fns()
        plan_agent = MagicMock()
        fns["create_plan_agent"].return_value = plan_agent

        with patch("langcode.tui.repl.stream_agent_response") as mock_stream:
            mock_stream.return_value = {
                "input_tokens": 0,
                "output_tokens": 0,
                "cache_read": 0,
                "cache_creation": 0,
            }
            with (
                patch("langcode.tui.repl.expand_at_references", side_effect=lambda t, _: t),
                patch("langcode.tui.repl.execute_hooks", return_value=MagicMock(messages=[])),
                patch("langcode.tui.repl.build_context", return_value=""),
                patch("langcode.tui.repl.pick_session_tui", return_value=None),
                patch("langcode.tui.repl.console"),
            ):
                config = _make_config()
                session = MagicMock()
                session.prompt = MagicMock(side_effect=["what should I do?", EOFError()])
                _run_repl_loop(
                    config,
                    MagicMock(),
                    _make_cmd_handler(),
                    session,
                    None,
                    {"mode": "plan"},
                    None,
                    **fns,
                )

        fns["create_plan_agent"].assert_called_once()
        # stream_agent_response should be called with the plan agent
        assert mock_stream.call_args[0][0] is plan_agent


class TestReplLoopResume:
    def test_resume_picks_session(self):
        fns = _make_fns()
        cmd_handler = _make_cmd_handler(is_command=True)

        with patch("langcode.tui.repl.pick_session_tui", return_value="tid-picked") as mock_pick:
            with patch("langcode.tui.repl.console"):
                config = _make_config()
                session = MagicMock()
                agent = MagicMock()
                agent.get_state = MagicMock(side_effect=Exception("no state"))
                session.prompt = MagicMock(side_effect=["/resume", EOFError()])
                _run_repl_loop(
                    config, agent, cmd_handler, session, None, {"mode": "act"}, None, **fns
                )

        mock_pick.assert_called_once()

    def test_resume_same_session_prints_message(self):
        fns = _make_fns(["current-tid"])
        cmd_handler = _make_cmd_handler(is_command=True)

        # pick_session_tui returns the same thread_id
        with patch("langcode.tui.repl.pick_session_tui", return_value="current-tid"):
            with patch("langcode.tui.repl.console") as mock_console:
                config = _make_config()
                session = MagicMock()
                session.prompt = MagicMock(side_effect=["/resume", EOFError()])
                _run_repl_loop(
                    config, MagicMock(), cmd_handler, session, None, {"mode": "act"}, None, **fns
                )

            printed = " ".join(str(c) for c in mock_console.print.call_args_list)
            assert "already on this session" in printed


class TestReplLoopKeyboardInterrupt:
    def test_single_interrupt_continues(self):
        """First Ctrl-C should show message and continue, not exit."""
        session = MagicMock()
        session.prompt = MagicMock(side_effect=[KeyboardInterrupt(), EOFError()])
        fns = _make_fns()

        with patch("langcode.tui.repl.console") as mock_console:
            config = _make_config()
            _run_repl_loop(
                config,
                MagicMock(),
                _make_cmd_handler(),
                session,
                None,
                {"mode": "act"},
                None,
                **fns,
            )

        printed = " ".join(str(c) for c in mock_console.print.call_args_list)
        assert "Ctrl-C again" in printed

    def test_double_interrupt_exits(self):
        """Two rapid Ctrl-C presses should exit."""
        session = MagicMock()
        session.prompt = MagicMock(side_effect=[KeyboardInterrupt(), KeyboardInterrupt()])

        fns = _make_fns()
        with patch("langcode.tui.repl.console"):
            with patch("langcode.tui.repl.time") as mock_time:
                # First interrupt: now=1.0, last_interrupt=0 → 1.0 >= 1.0 → show message, set last=1.0
                # Second interrupt: now=1.9, last_interrupt=1.0 → 0.9 < 1.0 → exit
                mock_time.time = MagicMock(side_effect=[1.0, 1.9])
                config = _make_config()
                _run_repl_loop(
                    config,
                    MagicMock(),
                    _make_cmd_handler(),
                    session,
                    None,
                    {"mode": "act"},
                    None,
                    **fns,
                )

        assert session.prompt.call_count == 2
