"""Modern keyboard negotiation: xterm modifyOtherKeys and the Kitty protocol."""

from bittty import Board, MemoryConnection, constants
from bittty.model import KITTY, VT220, XTERM
from bittty.parser import Parser


def _term(model=None):
    board = Board(width=20, height=3) if model is None else Board(width=20, height=3, model=model)
    transport = MemoryConnection()
    board.host.attach(transport)
    return board, Parser(board), transport


def _sent(transport):
    return "".join(transport.data)


def test_modify_other_keys_encodes_ctrl_letter():
    board, parser, transport = _term()
    parser.feed("\x1b[>4;2m")  # modifyOtherKeys level 2
    assert board.keyboard.modify_other_keys == 2
    board.input_key("a", constants.KEY_MOD_CTRL)
    assert _sent(transport) == "\x1b[27;5;97~"  # CSI 27 ; mod ; code ~


def test_modify_other_keys_reset_restores_legacy_control_code():
    board, parser, transport = _term()
    parser.feed("\x1b[>4;2m")
    parser.feed("\x1b[>4m")  # Pv omitted -> level 0 (off)
    assert board.keyboard.modify_other_keys == 0
    board.input_key("a", constants.KEY_MOD_CTRL)
    assert _sent(transport) == "\x01"  # legacy Ctrl-A


def test_kitty_push_sets_flags_and_encodes_csi_u():
    board, parser, transport = _term()
    parser.feed("\x1b[>1u")  # push flags = 1 (disambiguate)
    assert board.keyboard.kitty_flags == 1
    board.input_key("a", constants.KEY_MOD_CTRL)
    assert _sent(transport) == "\x1b[97;5u"  # CSI code ; mod u


def test_kitty_query_reports_current_flags():
    _board, parser, transport = _term()
    parser.feed("\x1b[>9u")  # flags = 9 (disambiguate | report-all-keys)
    parser.feed("\x1b[?u")  # query
    assert _sent(transport) == "\x1b[?9u"


def test_kitty_set_modes_add_and_remove_bits():
    board, parser, _ = _term()
    kb = board.keyboard
    parser.feed("\x1b[=1;1u")  # set flags = 1
    assert kb.kitty_flags == 1
    parser.feed("\x1b[=8;2u")  # add bit 8
    assert kb.kitty_flags == 9
    parser.feed("\x1b[=1;3u")  # remove bit 1
    assert kb.kitty_flags == 8


# --- only the implemented enhancements are negotiable --- #


def test_unsupported_flag_bits_are_ignored_not_stored():
    """Flags 2 and 4 need a key-event input layer bittty does not have.

    The spec's detection scheme is "set flags, query, trust the answer", so
    accepting bits the encoder ignores would be a lie. Ignored on push and on
    set, they never show up in the query report.
    """
    _board, parser, transport = _term()
    parser.feed("\x1b[>31u")  # push all five bits
    parser.feed("\x1b[?u")
    assert _sent(transport) == "\x1b[?25u"  # 1 | 8 | 16 survive

    transport.data.clear()
    parser.feed("\x1b[=2;1u")  # set event-types alone
    parser.feed("\x1b[?u")
    assert _sent(transport) == "\x1b[?0u"


def test_kitty_stack_is_bounded_against_push_spam():
    """The spec: bound the stack against DoS; a full stack evicts the oldest."""
    board, parser, _ = _term()
    parser.feed("\x1b[>1u" * 10_000)
    assert len(board.keyboard.kitty_stack) <= 8

    parser.feed("\x1b[<10000u")  # pop everything, and then some
    assert board.keyboard.kitty_flags == 0
    assert board.keyboard.kitty_stack == []


# --- the protocol is a model repertoire, not a universal answer --- #


def test_a_model_without_the_protocol_does_not_answer_negotiation():
    """Real xterm never replies to CSI ? u; neither does a VT220."""
    for model in (VT220, XTERM):
        board, parser, transport = _term(model)
        parser.feed("\x1b[>1u\x1b[?u")
        assert transport.data == []
        assert "KITTY_QUERY" not in board.registry


def test_kitty_models_answer_negotiation():
    for model in (KITTY, None):  # None = the default bittty model
        _board, parser, transport = _term(model)
        parser.feed("\x1b[?u")
        assert _sent(transport) == "\x1b[?0u"


def test_each_screen_keeps_its_own_kitty_state():
    """The spec: separate stacks for the main and alternate screens."""
    _board, parser, transport = _term()
    parser.feed("\x1b[>1u")  # main screen: flags 1
    parser.feed("\x1b[?1049h")  # enter the alternate screen
    parser.feed("\x1b[?u")
    assert _sent(transport) == "\x1b[?0u"  # fresh state there

    parser.feed("\x1b[>8u")  # alt screen: flags 8
    parser.feed("\x1b[?1049l")  # back to the main screen
    transport.data.clear()
    parser.feed("\x1b[?u")
    assert _sent(transport) == "\x1b[?1u"  # main screen kept its own


def test_ris_clears_kitty_state_on_both_screens():
    board, parser, _ = _term()
    parser.feed("\x1b[>1u\x1b[?1049h\x1b[>8u\x1b[?1049l")
    parser.feed("\x1bc")  # RIS, on the main screen
    assert board.keyboard.kitty_flags == 0
    parser.feed("\x1b[?1049h")
    assert board.keyboard.kitty_flags == 0
    assert board.keyboard.kitty_stack == []


# --- flag 1: disambiguate escape codes --- #


def test_flag1_escape_key_becomes_csi_27():
    board, parser, transport = _term()
    parser.feed("\x1b[>1u")
    board.input_key(constants.ESC)
    assert _sent(transport) == "\x1b[27u"
    transport.data.clear()
    board.input_key(constants.ESC, constants.KEY_MOD_ALT)
    assert _sent(transport) == "\x1b[27;3u"


def test_flag1_unmodified_enter_tab_backspace_keep_legacy_bytes():
    """The spec keeps them raw so `reset` stays typeable after a crash."""
    board, parser, transport = _term()
    parser.feed("\x1b[>1u")
    board.input_key("\r")
    board.input_key("\t")
    board.input_key(constants.BS)
    assert transport.data == ["\r", "\t", constants.DEL]  # DECBKM default: BS key sends DEL


def test_flag1_modified_enter_and_ctrl_i_disambiguate():
    """Telling ctrl+i from Tab is a stated goal of the protocol."""
    board, parser, transport = _term()
    parser.feed("\x1b[>1u")
    board.input_key("\r", constants.KEY_MOD_CTRL)
    board.input_key("i", constants.KEY_MOD_CTRL)
    assert transport.data == ["\x1b[13;5u", "\x1b[105;5u"]


def test_flag1_plain_and_shifted_printables_stay_text():
    board, parser, transport = _term()
    parser.feed("\x1b[>1u")
    board.input_key("a")
    board.input_key("A", constants.KEY_MOD_SHIFT)
    assert transport.data == ["a", "A"]


def test_flag1_alt_key_has_no_escape_prefix():
    """Alt lives in the CSI modifier parameter, never an ESC prefix."""
    board, parser, transport = _term()
    parser.feed("\x1b[?1036h")  # legacy altSendsEscape on
    parser.feed("\x1b[>1u")
    board.input_key("x", constants.KEY_MOD_ALT)
    assert transport.data == ["\x1b[120;3u"]

    transport.data.clear()
    board.input_key("up", constants.KEY_MOD_ALT)
    assert transport.data == ["\x1b[1;3A"]  # folded modifier, no ESC prefix


def test_flag1_ctrl_shift_uses_the_unshifted_codepoint():
    board, parser, transport = _term()
    parser.feed("\x1b[>1u")
    board.input_key("A", constants.KEY_MOD_SHIFT_CTRL)
    assert transport.data == ["\x1b[97;6u"]  # 97, never 65


def test_flag1_delete_key_ignores_mode_1037():
    """Raw DEL for Delete recreates the ambiguity the flag removes."""
    board, parser, transport = _term()
    parser.feed("\x1b[?1037h")  # deleteSendsDEL
    parser.feed("\x1b[>1u")
    board.input_key("delete")
    assert transport.data == ["\x1b[3~"]


def test_flag1_arrows_ignore_application_cursor_mode():
    """SS3 forms are legacy encodings; Kitty ignores DECCKM."""
    board, parser, transport = _term()
    parser.feed("\x1b[?1h")  # DECCKM on
    parser.feed("\x1b[>1u")
    board.input_key("up")
    assert transport.data == ["\x1b[A"]  # not ESC O A


# --- flag 8: report all keys as escape codes --- #


def test_flag8_plain_keys_become_escape_codes():
    board, parser, transport = _term()
    parser.feed("\x1b[>8u")
    board.input_key("a")
    board.input_key("\r")
    board.input_key("\t")
    board.input_key(constants.BS)
    assert transport.data == ["\x1b[97u", "\x1b[13u", "\x1b[9u", "\x1b[127u"]


def test_flag8_numpad_keys_get_functional_codes():
    board, parser, transport = _term()
    parser.feed("\x1b[>8u")
    board.input_numpad_key("5")
    board.input_numpad_key("Enter")
    assert transport.data == ["\x1b[57404u", "\x1b[57414u"]


# --- flag 16: report associated text --- #


def test_flag16_appends_the_text_codepoints():
    board, parser, transport = _term()
    parser.feed("\x1b[>25u")  # 1 | 8 | 16
    board.input_key("a")
    board.input_key("A", constants.KEY_MOD_SHIFT)
    assert transport.data == ["\x1b[97;;97u", "\x1b[97;2;65u"]


def test_flag16_without_flag8_behaves_as_zero():
    """The spec calls 16-without-8 undefined; bittty sends plain text."""
    board, parser, transport = _term()
    parser.feed("\x1b[>16u")
    board.input_key("a")
    assert transport.data == ["a"]


def test_kitty_push_and_pop_restore_flags():
    board, parser, _ = _term()
    kb = board.keyboard
    parser.feed("\x1b[>1u")  # flags 1
    parser.feed("\x1b[>8u")  # push again -> flags 8
    assert kb.kitty_flags == 8
    parser.feed("\x1b[<1u")  # pop one -> back to 1
    assert kb.kitty_flags == 1


def test_plain_csi_u_still_restores_the_cursor():
    board, parser, _ = _term()
    board.cursor.set_position(4, 2)
    parser.feed("\x1b[s")  # save cursor
    board.cursor.set_position(0, 0)
    parser.feed("\x1b[u")  # restore cursor (SCORC), not a Kitty sequence
    assert (board.cursor.x, board.cursor.y) == (4, 2)


def test_ris_clears_modern_keyboard_state():
    board, parser, _ = _term()
    parser.feed("\x1b[>4;2m")
    parser.feed("\x1b[>1u")
    parser.feed("\x1bc")  # RIS
    kb = board.keyboard
    assert kb.modify_other_keys == 0
    assert kb.kitty_flags == 0
    assert kb.kitty_stack == []
