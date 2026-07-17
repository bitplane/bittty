"""DEC locator: DECELR / DECSLE / DECRQLP / DECEFR and the DECLRP report."""

from bittty.parser import Parser
from bittty import Board


class RecordingTransport:
    def __init__(self):
        self.data = []

    def write(self, data):
        self.data.append(data)

    def flush(self):
        pass


def _driver():
    board = Board(width=80, height=24)
    transport = RecordingTransport()
    board.host.attach(transport)
    return board, Parser(board), transport


def test_request_locator_when_disabled_reports_unavailable():
    _, parser, transport = _driver()
    parser.feed("\x1b['|")  # DECRQLP with the locator off
    assert transport.data == ["\x1b[0&w"]


def test_request_locator_reports_position():
    board, parser, transport = _driver()
    parser.feed("\x1b[1;2'z")  # DECELR: enable, cell coordinates
    board.input_mouse(10, 5, 0, "move", set())  # move to col 10, row 5
    parser.feed("\x1b['|")  # DECRQLP
    assert transport.data == ["\x1b[1;0;5;10;1&w"]


def test_button_events_report_when_selected():
    board, parser, transport = _driver()
    parser.feed("\x1b[1'z")  # enable locator
    parser.feed("\x1b[1'{")  # DECSLE: report button-down
    board.input_mouse(3, 4, 0, "press", set())  # left press at col 3, row 4
    # event 2 = left down, button mask 4 (left), row 4, col 3
    assert transport.data == ["\x1b[2;4;4;3;1&w"]


def test_button_up_not_reported_unless_selected():
    board, parser, transport = _driver()
    parser.feed("\x1b[1'z\x1b[1'{")  # enable + report down only
    board.input_mouse(3, 4, 0, "press", set())
    board.input_mouse(3, 4, 0, "release", set())  # release not selected -> silent
    assert transport.data == ["\x1b[2;4;4;3;1&w"]  # only the press


def test_one_shot_disables_after_one_report():
    board, parser, transport = _driver()
    parser.feed("\x1b[2'z")  # DECELR mode 2 = one-shot
    parser.feed("\x1b['|")  # first request reports...
    parser.feed("\x1b['|")  # ...second finds the locator disabled again
    assert transport.data == ["\x1b[1;0;0;0;1&w", "\x1b[0&w"]
