"""The child's environment: the caller's, less whatever says which terminal the caller runs in."""

import io

from bittty import VT220, XTERM, Board, TerminalCaps
from bittty.pty import StdioPTY


def _pty():
    return StdioPTY(io.BytesIO(), io.BytesIO(), 24, 80)


def test_the_child_is_not_told_it_runs_in_the_callers_terminal(monkeypatch):
    for name, value in {
        "TMUX": "/tmp/tmux-1000/default,1,0",
        "TMUX_PANE": "%1",
        "TERM_PROGRAM": "tmux",
        "VTE_VERSION": "8400",
        "KITTY_WINDOW_ID": "1",
        "WEZTERM_PANE": "0",
    }.items():
        monkeypatch.setenv(name, value)
    env = _pty().environment(XTERM.environment)
    assert not {"TMUX", "TMUX_PANE", "TERM_PROGRAM", "VTE_VERSION", "KITTY_WINDOW_ID", "WEZTERM_PANE"} & env.keys()


def test_the_child_keeps_the_rest_of_the_callers_environment(monkeypatch):
    monkeypatch.setenv("BITTTY_TEST_VARIABLE", "kept")
    env = _pty().environment(XTERM.environment)
    assert env["BITTTY_TEST_VARIABLE"] == "kept"
    assert env["PATH"]


def test_the_model_says_what_the_child_runs_on(monkeypatch):
    monkeypatch.setenv("COLORTERM", "truecolor")
    assert XTERM.environment == {"TERM": "xterm-256color", "COLORTERM": "truecolor"}
    env = _pty().environment(VT220.environment)
    assert env["TERM"] == "vt220"
    assert "COLORTERM" not in env


def test_the_child_is_told_truecolor_only_when_the_chrome_can_show_it():
    board = Board(model=XTERM)
    assert board.child_environment["COLORTERM"] == "truecolor"  # nothing known: the model's word
    board.set_caps(TerminalCaps(color_depth="256"))
    assert "COLORTERM" not in board.child_environment
    board.set_caps(TerminalCaps(color_depth="truecolor"))
    assert board.child_environment == {"TERM": "xterm-256color", "COLORTERM": "truecolor"}


def test_a_chrome_able_to_show_truecolor_adds_nothing_the_model_lacks():
    board = Board(model=VT220)
    board.set_caps(TerminalCaps(color_depth="truecolor"))
    assert board.child_environment == {"TERM": "vt220"}
