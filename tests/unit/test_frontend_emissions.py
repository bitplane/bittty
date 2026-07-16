"""Phase 2: devices emit present events alongside (never instead of) their register writes."""

from bittty import Terminal
from bittty.parser import Parser
from bittty.present import (
    Bell,
    ClipboardChanged,
    ConsoleRequest,
    CursorVisibilityChanged,
    CwdChanged,
    FontChanged,
    MouseModeChanged,
    Notification,
    PointerShapeChanged,
    SyncOutputChanged,
    TitleChanged,
    WindowRequest,
    WindowStateChanged,
)


class Recorder:
    def __init__(self):
        self.events = []

    def present(self, event):
        self.events.append(event)


def _term():
    terminal = Terminal(width=20, height=3)
    rec = Recorder()
    terminal.board.display.attach(rec)
    return terminal, Parser(terminal.board), rec


def test_bell_emits_and_still_hooks():
    terminal, parser, rec = _term()
    parser.feed("\x07")  # C0 BEL
    assert Bell() in rec.events


def test_title_event_and_register():
    terminal, parser, rec = _term()
    parser.feed("\x1b]0;hello\x07")  # OSC 0 sets both window + icon title
    assert terminal.board.title.title == "hello"  # register still set
    assert TitleChanged("hello", "hello") in rec.events


def test_cwd_notify_pointer_font_events_and_registers():
    terminal, parser, rec = _term()
    parser.feed("\x1b]7;file:///tmp\x07")
    parser.feed("\x1b]9;ding\x07")
    parser.feed("\x1b]22;pointer\x07")
    parser.feed("\x1b]50;Fira 12\x07")
    assert terminal.board.cwd == "file:///tmp" and CwdChanged("file:///tmp") in rec.events
    assert "ding" in terminal.board.notifications and Notification("ding") in rec.events
    assert terminal.board.pointer_shape == "pointer" and PointerShapeChanged("pointer") in rec.events
    assert terminal.board.font == "Fira 12" and FontChanged("Fira 12") in rec.events


def test_clipboard_event_and_register():
    terminal, parser, rec = _term()
    parser.feed("\x1b]52;c;aGk=\x07")  # base64 "hi"
    assert terminal.board.clipboard["c"] == "hi"
    assert ClipboardChanged("c", "hi") in rec.events


def test_window_state_and_request_events():
    terminal, parser, rec = _term()
    parser.feed("\x1b[2t")  # iconify
    assert terminal.board.window_iconified is True
    assert any(isinstance(e, WindowStateChanged) and e.iconified for e in rec.events)
    parser.feed("\x1b[5t")  # raise
    assert "raise" in terminal.board.window_requests
    assert WindowRequest("raise") in rec.events


def test_console_switch_event():
    terminal, parser, rec = _term()
    parser.feed("\x1b[12;3]")  # setterm: switch to console 3
    assert ("switch", 3) in terminal.board.console_requests
    assert ConsoleRequest("switch", 3) in rec.events


def test_mouse_mode_is_edge_triggered():
    terminal, parser, rec = _term()
    parser.feed("\x1b[?1000h")  # basic tracking on
    parser.feed("\x1b[?1000h")  # again -> no new event (edge-triggered)
    parser.feed("\x1b[?1006h")  # add SGR encoding
    parser.feed("\x1b[?1000l")  # tracking off
    mouse_events = [e for e in rec.events if isinstance(e, MouseModeChanged)]
    assert mouse_events == [
        MouseModeChanged("basic", False),
        MouseModeChanged("basic", True),
        MouseModeChanged("off", True),
    ]


def test_cursor_and_sync_events():
    terminal, parser, rec = _term()
    parser.feed("\x1b[?25l")  # hide cursor
    assert CursorVisibilityChanged(False) in rec.events
    parser.feed("\x1b[?2026h")  # sync output on
    assert SyncOutputChanged(True) in rec.events


def test_events_are_dropped_with_no_frontend():
    # backward-compat: unattached board mutates registers and never errors
    terminal = Terminal(width=20, height=3)
    parser = Parser(terminal.board)
    parser.feed("\x1b]2;t\x07\x1b[?1000h\x07")
    assert terminal.board.title.title == "t"
    assert terminal.board.modes.mouse_tracking is True
