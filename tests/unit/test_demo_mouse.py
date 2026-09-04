"""The stdio terminal's input demux: SGR mouse interception vs. raw forwarding."""

from bittty import MemoryConnection
from bittty.terminals.stdio import StdioTerminal


def test_demo_forwards_sgr_mouse_press():
    frontend = StdioTerminal()
    connection = MemoryConnection()
    frontend.board.host.attach(connection)
    frontend.board.parser.feed("\033[?1000h\033[?1006h")

    for char in "\033[<20;15;8M":
        frontend.handle_input(char)

    assert "".join(connection.data) == "\033[<20;15;8M"


def test_demo_forwards_non_mouse_escape_input():
    frontend = StdioTerminal()
    connection = MemoryConnection()
    frontend.board.host.attach(connection)

    for char in "\033[A":
        frontend.handle_input(char)

    assert "".join(connection.data) == "\033[A"
