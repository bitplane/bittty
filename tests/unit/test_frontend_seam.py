"""Phase 1 of the frontend seam: DisplayPort forwarding, the Display ABC, caps push."""

from bittty import DisplayCaps, Terminal
from bittty.frontends import Display
from bittty.present import Bell, MouseModeChanged, Notification, TitleChanged
from bittty.transports import DisplayPort


class RecordingDisplay(Display):
    """A Display that records the hooks it chose to override."""

    def __init__(self, terminal):
        super().__init__(terminal)
        self.events = []

    def on_bell(self):
        self.events.append(("bell",))

    def on_title(self, title, icon_title):
        self.events.append(("title", title, icon_title))

    def on_mouse_mode(self, mode, sgr):
        self.events.append(("mouse", mode, sgr))

    # on_notify deliberately NOT overridden -> should be a safe no-op


def _term():
    return Terminal(width=20, height=3)


def test_display_port_forwards_and_is_null_safe():
    port = DisplayPort()
    seen = []
    port.present(Bell())  # unattached -> no-op, no error
    assert seen == []

    class Sink:
        def present(self, event):
            seen.append(event)

    port.attach(Sink())
    port.present(Bell())
    assert seen == [Bell()]
    port.detach()
    port.present(Bell())  # detached -> no-op
    assert seen == [Bell()]


def test_board_present_reaches_attached_frontend():
    terminal = _term()
    display = RecordingDisplay(terminal)
    display.attach()
    terminal.board.present(TitleChanged("hi", "hi"))
    terminal.board.present(Bell())
    assert display.events == [("title", "hi", "hi"), ("bell",)]


def test_unoverridden_hook_is_a_safe_noop():
    terminal = _term()
    display = RecordingDisplay(terminal)
    display.attach()
    terminal.board.present(Notification("hello"))  # on_notify defaults to no-op
    assert display.events == []


def test_detach_stops_delivery():
    terminal = _term()
    display = RecordingDisplay(terminal)
    display.attach()
    display.detach()
    terminal.board.present(Bell())
    assert display.events == []


def test_present_with_no_frontend_is_noop():
    terminal = _term()  # nothing attached
    terminal.board.present(Bell())  # must not raise
    assert terminal.board.display.connected is False


def test_display_caps_default_and_push():
    terminal = _term()
    assert terminal.board.display_caps == DisplayCaps.unknown()
    display = RecordingDisplay(terminal)
    caps = DisplayCaps(color_depth="256", cell_px=(8, 16))
    display.set_caps(caps)
    assert terminal.board.display_caps is caps


def test_mouse_mode_event_dispatch():
    terminal = _term()
    display = RecordingDisplay(terminal)
    display.attach()
    terminal.board.present(MouseModeChanged("any", True))
    assert display.events == [("mouse", "any", True)]
