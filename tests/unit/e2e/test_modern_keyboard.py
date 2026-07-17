"""Modern keyboard negotiation: xterm modifyOtherKeys and the Kitty protocol."""

from bittty import constants
from bittty.parser import Parser
from bittty import Board


class RecordingTransport:
    def __init__(self):
        self.data = []

    def write(self, data):
        self.data.append(data)

    def flush(self):
        pass


def _term():
    terminal = Board(width=20, height=3)
    transport = RecordingTransport()
    terminal.board.host.attach(transport)
    return terminal, Parser(terminal.board), transport


def _sent(transport):
    return "".join(transport.data)


def test_modify_other_keys_encodes_ctrl_letter():
    terminal, parser, transport = _term()
    parser.feed("\x1b[>4;2m")  # modifyOtherKeys level 2
    assert terminal.board.keyboard.modify_other_keys == 2
    terminal.input_key("a", constants.KEY_MOD_CTRL)
    assert _sent(transport) == "\x1b[27;5;97~"  # CSI 27 ; mod ; code ~


def test_modify_other_keys_reset_restores_legacy_control_code():
    terminal, parser, transport = _term()
    parser.feed("\x1b[>4;2m")
    parser.feed("\x1b[>4m")  # Pv omitted -> level 0 (off)
    assert terminal.board.keyboard.modify_other_keys == 0
    terminal.input_key("a", constants.KEY_MOD_CTRL)
    assert _sent(transport) == "\x01"  # legacy Ctrl-A


def test_kitty_push_sets_flags_and_encodes_csi_u():
    terminal, parser, transport = _term()
    parser.feed("\x1b[>1u")  # push flags = 1 (disambiguate)
    assert terminal.board.keyboard.kitty_flags == 1
    terminal.input_key("a", constants.KEY_MOD_CTRL)
    assert _sent(transport) == "\x1b[97;5u"  # CSI code ; mod u


def test_kitty_query_reports_current_flags():
    terminal, parser, transport = _term()
    parser.feed("\x1b[>5u")  # flags = 5
    parser.feed("\x1b[?u")  # query
    assert _sent(transport) == "\x1b[?5u"


def test_kitty_set_modes_add_and_remove_bits():
    terminal, parser, _ = _term()
    kb = terminal.board.keyboard
    parser.feed("\x1b[=1;1u")  # set flags = 1
    assert kb.kitty_flags == 1
    parser.feed("\x1b[=4;2u")  # add bit 4
    assert kb.kitty_flags == 5
    parser.feed("\x1b[=1;3u")  # remove bit 1
    assert kb.kitty_flags == 4


def test_kitty_push_and_pop_restore_flags():
    terminal, parser, _ = _term()
    kb = terminal.board.keyboard
    parser.feed("\x1b[>1u")  # flags 1
    parser.feed("\x1b[>8u")  # push again -> flags 8
    assert kb.kitty_flags == 8
    parser.feed("\x1b[<1u")  # pop one -> back to 1
    assert kb.kitty_flags == 1


def test_plain_csi_u_still_restores_the_cursor():
    terminal, parser, _ = _term()
    terminal.board.cursor.set_position(4, 2)
    parser.feed("\x1b[s")  # save cursor
    terminal.board.cursor.set_position(0, 0)
    parser.feed("\x1b[u")  # restore cursor (SCORC), not a Kitty sequence
    assert (terminal.board.cursor.x, terminal.board.cursor.y) == (4, 2)


def test_ris_clears_modern_keyboard_state():
    terminal, parser, _ = _term()
    parser.feed("\x1b[>4;2m")
    parser.feed("\x1b[>1u")
    parser.feed("\x1bc")  # RIS
    kb = terminal.board.keyboard
    assert kb.modify_other_keys == 0
    assert kb.kitty_flags == 0
    assert kb.kitty_stack == []
