"""DEC locator: DECELR / DECSLE / DECRQLP / DECEFR and the DECLRP report."""

from dataclasses import replace

from bittty import Board, MemoryConnection
from bittty.model import LINUX, XTERM
from bittty.options import DEC_LOCATOR, LOCATOR_PORT
from bittty.parser import Parser


def _driver():
    board = Board(width=80, height=24)
    transport = MemoryConnection()
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


# --- the locator port is an installed option (tier 1) --- #


def test_a_terminal_without_a_locator_port_does_not_recognise_the_sequences():
    """No port means the control functions do not exist, so nothing is answered.

    That is a different thing from having a port with nothing on it, which
    answers DECRQLP with "locator unavailable" — see the test below.
    """
    board = Board(model=LINUX)
    transport = MemoryConnection()
    board.host.attach(transport)
    parser = Parser(board)

    parser.feed("\x1b['|")  # DECRQLP
    parser.feed("\x1b[1;2'z")  # DECELR
    parser.feed("\x1b['|")

    assert transport.data == []
    assert "DECRQLP" not in board.registry


def test_a_fitted_port_with_no_device_reports_locator_unavailable():
    """xterm's Pe=0 means unavailable, and carries no further parameters."""
    board = Board(model=XTERM)
    transport = MemoryConnection()
    board.host.attach(transport)

    Parser(board).feed("\x1b['|")

    assert transport.data == ["\x1b[0&w"]
    assert "DECRQLP" in board.registry


def test_the_port_is_what_decides_not_the_model_repertoire():
    assert DEC_LOCATOR in XTERM.provides
    assert DEC_LOCATOR not in LINUX.provides
    assert LOCATOR_PORT in XTERM.options


# --- DECEFR: the filter rectangle --- #


def test_filter_rectangle_reports_leaving_once():
    board, parser, transport = _driver()
    parser.feed("\x1b[1'z")
    board.input_mouse(10, 5, 0, "move", set())
    parser.feed("\x1b[3;8;7;12'w")  # top 3, left 8, bottom 7, right 12
    board.input_mouse(12, 7, 0, "move", set())  # still inside
    board.input_mouse(13, 7, 0, "move", set())  # out
    board.input_mouse(20, 9, 0, "move", set())  # the rectangle is one-shot
    assert transport.data == ["\x1b[10;0;7;13;1&w"]


def test_omitted_filter_edges_default_to_the_locator_position():
    """A host-sent `CSI ;;; ' w` is legal: every edge is the current position."""
    board, parser, transport = _driver()
    parser.feed("\x1b[1'z")
    board.input_mouse(10, 5, 0, "move", set())
    parser.feed("\x1b[;;;'w")
    board.input_mouse(11, 5, 0, "move", set())
    assert transport.data == ["\x1b[10;0;5;11;1&w"]


def test_a_short_filter_defaults_its_missing_edges():
    board, parser, transport = _driver()
    parser.feed("\x1b[1'z")
    board.input_mouse(10, 5, 0, "move", set())
    parser.feed("\x1b[1;1'w")  # bottom and right omitted: the locator's row and column
    board.input_mouse(10, 5, 0, "move", set())  # the corner is inside
    board.input_mouse(10, 6, 0, "move", set())
    assert transport.data == ["\x1b[10;0;6;10;1&w"]


def test_a_filter_set_around_elsewhere_reports_at_once():
    board, parser, transport = _driver()
    parser.feed("\x1b[1'z")
    board.input_mouse(10, 5, 0, "move", set())
    parser.feed("\x1b[1;1;2;2'w")
    assert transport.data == ["\x1b[10;0;5;10;1&w"]


def test_enabling_the_locator_cancels_the_filter():
    board, parser, transport = _driver()
    parser.feed("\x1b[1'z")
    board.input_mouse(10, 5, 0, "move", set())
    parser.feed("\x1b[5;10;5;10'w\x1b[1'z")
    board.input_mouse(11, 5, 0, "move", set())
    assert transport.data == []


# --- DECELR pixel units --- #


def test_pixel_units_report_the_pointer_pixel():
    board, parser, transport = _driver()
    parser.feed("\x1b[1;1'z")  # DECELR: enable, pixel coordinates
    board.input_mouse(10, 5, 0, "move", set(), pixel=(93, 70))
    parser.feed("\x1b['|")
    assert transport.data == ["\x1b[1;0;71;94;1&w"]


def test_pixel_units_fall_back_to_the_cell_corner():
    board, parser, transport = _driver()
    board.set_caps(replace(board.caps, cell_px=(9, 18)))
    parser.feed("\x1b[1;1'z")
    board.input_mouse(10, 5, 0, "move", set())
    parser.feed("\x1b['|")
    assert transport.data == ["\x1b[1;0;73;82;1&w"]


def test_a_pixel_filter_is_in_pixels():
    board, parser, transport = _driver()
    parser.feed("\x1b[1;1'z")
    board.input_mouse(10, 5, 0, "move", set(), pixel=(93, 70))
    parser.feed("\x1b[60;90;80;100'w")
    board.input_mouse(10, 5, 0, "move", set(), pixel=(99, 79))
    board.input_mouse(11, 5, 0, "move", set(), pixel=(100, 79))
    assert transport.data == ["\x1b[10;0;80;101;1&w"]


def test_a_filter_needs_the_locator_enabled():
    board, parser, transport = _driver()
    parser.feed("\x1b[1;1;2;2'w")
    board.input_mouse(10, 5, 0, "move", set())
    parser.feed("\x1b[1'z")
    board.input_mouse(11, 5, 0, "move", set())
    assert transport.data == []


def test_hard_reset_turns_the_locator_off():
    board, parser, transport = _driver()
    parser.feed("\x1b[1'z\x1b[1'{")  # enabled, reporting button-down
    board.reset(hard=True)
    board.input_mouse(3, 4, 0, "press", set())
    parser.feed("\x1b['|")
    assert transport.data == ["\x1b[0&w"]
    assert board.mouse.capture() == "off"


def test_disabling_the_locator_leaves_xterm_tracking_alone():
    board, parser, transport = _driver()
    parser.feed("\x1b[?1000h\x1b[0'z")
    board.input_mouse(3, 4, 0, "press", set())
    assert transport.data == [b"\x1b[M" + bytes((32, 35, 36))]
