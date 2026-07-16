from bittty.operations import Operation
from bittty.parser import Parser
from bittty.style import parse_sgr_sequence


class CollectingSink:
    def __init__(self):
        self.operations = []

    def handle_operation(self, operation: Operation) -> None:
        self.operations.append(operation)


def test_parser_emits_batched_print_operation(terminal):
    sink = CollectingSink()
    parser = Parser(sink)

    parser.feed("hello")

    assert sink.operations == [Operation("PRINT", ("hello",), "hello")]
    assert terminal.board.screen.current_buffer.get_line_text(0).strip() == ""


def test_parser_emits_control_operations(terminal):
    sink = CollectingSink()
    parser = Parser(sink)

    parser.feed("\r\n")

    # The CR+LF pair is fused into one token (one pipeline trip per line).
    assert sink.operations == [Operation("C0_CRLF", raw="\r\n")]

    sink.operations.clear()
    parser.feed("\rx\n")  # lone CR and LF still arrive separately

    assert sink.operations == [
        Operation("C0_CR", raw="\r"),
        Operation("PRINT", ("x",), "x"),
        Operation("C0_LF", raw="\n"),
    ]


def test_parser_emits_escape_and_csi_operations(terminal):
    sink = CollectingSink()
    parser = Parser(sink)

    parser.feed("\x1b7\x1b[2t")

    assert sink.operations == [
        Operation("SAVE", raw="\x1b7"),
        Operation("XTWINOPS", ((2,),), raw="\x1b[2t"),
    ]


def test_parser_emits_semantic_cursor_operations(terminal):
    sink = CollectingSink()
    parser = Parser(sink)

    parser.feed("\x1b[2;3H\x1b[4A\x1b[5B\x1b[6C\x1b[7D\x1b[8G\x1b[9d\x1b[10;11f")

    assert sink.operations == [
        Operation("CUP", (2, 1), "\x1b[2;3H"),
        Operation("CUU", (4,), "\x1b[4A"),
        Operation("CUD", (5,), "\x1b[5B"),
        Operation("CUF", (6,), "\x1b[6C"),
        Operation("CUB", (7,), "\x1b[7D"),
        Operation("CHA", (7,), "\x1b[8G"),
        Operation("VPA", (8,), "\x1b[9d"),
        Operation("HVP", (10, 9), "\x1b[10;11f"),
    ]


def test_parser_emits_semantic_edit_operations(terminal):
    sink = CollectingSink()
    parser = Parser(sink)

    parser.feed("\x1b[2J\x1b[3K\x1b[4L\x1b[5M\x1b[6@\x1b[7P\x1b[8X\x1b[9S\x1b[10T")

    assert sink.operations == [
        Operation("ED", (2,), "\x1b[2J"),
        Operation("EL", (3,), "\x1b[3K"),
        Operation("IL", (4,), "\x1b[4L"),
        Operation("DL", (5,), "\x1b[5M"),
        Operation("ICH", (6,), "\x1b[6@"),
        Operation("DCH", (7,), "\x1b[7P"),
        Operation("ECH", (8,), "\x1b[8X"),
        Operation("SU", (9,), "\x1b[9S"),
        Operation("SD", (10,), "\x1b[10T"),
    ]


def test_parser_emits_semantic_cursor_state_and_screen_operations(terminal):
    sink = CollectingSink()
    parser = Parser(sink)

    parser.feed("\x1b[2;9r\x1b[r\x1b[s\x1b[u\x1b[3b")

    assert sink.operations == [
        Operation("DECSTBM", (1, 8), "\x1b[2;9r"),
        Operation("DECSTBM", (0, None), "\x1b[r"),
        Operation("SAVE", raw="\x1b[s"),
        Operation("RESTORE", raw="\x1b[u"),
        Operation("REP", (3,), "\x1b[3b"),
    ]


def test_parser_emits_style_and_query_operations(terminal):
    sink = CollectingSink()
    parser = Parser(sink)

    parser.feed("\x1b[31m\x1b[6n\x1b[5n\x1b[c\x1b[>0c\x1b[?25$p\x1b[4$p")

    assert sink.operations == [
        Operation("SGR", (parse_sgr_sequence("\x1b[31m"), False), "\x1b[31m"),
        Operation("CPR", (6,), "\x1b[6n"),
        Operation("DSR", (5,), "\x1b[5n"),
        Operation("DA1", (0,), "\x1b[c"),
        Operation("DA2", (0,), "\x1b[>0c"),
        Operation("DECRQM", (25, True), "\x1b[?25$p"),
        Operation("DECRQM", (4, False), "\x1b[4$p"),
    ]


def test_parser_emits_reset_sgr_operation(terminal):
    sink = CollectingSink()
    parser = Parser(sink)

    parser.feed("\x1b[m\x1b[0m\x1b[00m")

    # A pure reset carries None (no trailing attributes to merge after the reset).
    assert sink.operations == [
        Operation("SGR", (None, True), "\x1b[m"),
        Operation("SGR", (None, True), "\x1b[0m"),
        Operation("SGR", (None, True), "\x1b[00m"),
    ]


def test_parser_emits_mode_operations(terminal):
    sink = CollectingSink()
    parser = Parser(sink)

    parser.feed("\x1b[4h\x1b[4l\x1b[?25h\x1b[?25l\x1b[?1000;1006h")

    assert sink.operations == [
        Operation("SM", ((4,), True, False), "\x1b[4h"),
        Operation("RM", ((4,), False, False), "\x1b[4l"),
        Operation("DECSET", ((25,), True, True), "\x1b[?25h"),
        Operation("DECRST", ((25,), False, True), "\x1b[?25l"),
        Operation("DECSET", ((1000, 1006), True, True), "\x1b[?1000;1006h"),
    ]


def test_parser_emits_string_sequence_content_and_raw_data(terminal):
    sink = CollectingSink()
    parser = Parser(sink)

    parser.feed("\x1b]2;Title\x07\x1bPpayload\x1b\\")

    assert sink.operations == [
        Operation("SET_WINDOW_TITLE", ("Title",), "\x1b]2;Title\x07"),
        Operation("DCS_UNHANDLED", ("payload",), "\x1bPpayload\x1b\\"),
    ]


def test_default_operation_sink_preserves_terminal_behavior(terminal):
    parser = Parser(terminal.board)

    parser.feed("Hi\tThere\r\nNext")

    assert terminal.board.screen.current_buffer.get_line_text(0).startswith("Hi      There")
    assert terminal.board.screen.current_buffer.get_line_text(1).startswith("Next")
