"""The display seam: DisplayPort forwarding, the Terminal ABC, caps push."""

from bittty import Board, TerminalCaps
from bittty.terminals import Terminal
from bittty.present import Bell, MouseModeChanged, Notification, TitleChanged
from bittty.connections import DisplayPort, HostPort


class RecordingTerminal(Terminal):
    """A Terminal that records the hooks it chose to override."""

    def __init__(self, board):
        super().__init__(board)
        self.events = []

    def on_bell(self):
        self.events.append(("bell",))

    def on_title(self, title, icon_title):
        self.events.append(("title", title, icon_title))

    def on_mouse_mode(self, mode, sgr):
        self.events.append(("mouse", mode, sgr))

    # on_notify deliberately NOT overridden -> should be a safe no-op


def _term():
    return Board(width=20, height=3)


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
    board = _term()
    display = RecordingTerminal(board)
    display.attach()
    board.present(TitleChanged("hi", "hi"))
    board.present(Bell())
    assert display.events == [("title", "hi", "hi"), ("bell",)]


def test_unoverridden_hook_is_a_safe_noop():
    board = _term()
    display = RecordingTerminal(board)
    display.attach()
    board.present(Notification("hello"))  # on_notify defaults to no-op
    assert display.events == []


def test_detach_stops_delivery():
    board = _term()
    display = RecordingTerminal(board)
    display.attach()
    display.detach()
    board.present(Bell())
    assert display.events == []


def test_present_with_no_frontend_is_noop():
    board = _term()  # nothing attached
    board.present(Bell())  # must not raise
    assert board.display.connected is False


def test_caps_default_and_push():
    board = _term()
    assert board.caps == TerminalCaps.unknown()
    display = RecordingTerminal(board)
    caps = TerminalCaps(color_depth="256", cell_px=(8, 16))
    display.set_caps(caps)
    assert board.caps is caps


def test_mouse_mode_event_dispatch():
    board = _term()
    display = RecordingTerminal(board)
    display.attach()
    board.present(MouseModeChanged("any", True))
    assert display.events == [("mouse", "any", True)]


class QueueConnection:
    """A real duplex Connection: canned chunks on the read side, writes recorded."""

    def __init__(self, chunks=()):
        self.chunks = list(chunks)
        self.data = []
        self.closed = False

    def write(self, data):
        self.data.append(data)

    async def read_async(self, size):
        return self.chunks.pop(0) if self.chunks else ""


async def test_host_port_receive_side_pumps_into_the_sink():
    port = HostPort()
    seen = []
    port.connect(QueueConnection(["ab", "cd"]), seen.append, on_idle=lambda: True)
    await port._reader_task
    assert seen == ["ab", "cd"]


async def test_host_port_pumps_child_output_through_the_parser_into_video():
    board = Board(width=20, height=3)
    board.host.connect(QueueConnection(["hello"]), board._dispatch_pty_data, on_idle=lambda: True)
    await board.host._reader_task
    assert "hello" in board.capture_pane()


def test_display_port_receive_side_reaches_the_devices():
    """The upward pins: input, mouse, and focus flow from the chrome to the board."""
    board = Board(width=20, height=3)
    connection = QueueConnection()
    board.host.attach(connection)

    board.parser.feed("\x1b[?1000h\x1b[?1006h")  # child asks for SGR mouse reports
    board.display.input_mouse(3, 4, 0, "press", set())
    assert connection.data[-1] == "\x1b[<0;3;4M"

    board.display.input("x")
    assert connection.data[-1] == "x"

    board.display.focus_out()
    assert board.focused is False
    board.display.focus_in()
    assert board.focused is True
