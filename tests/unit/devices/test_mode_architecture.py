import pytest

from bittty import Board, MemoryConnection
from bittty import mode_profiles as mp
from bittty.connections import PrinterStatus
from bittty.devices.modes import (
    MODE_BY_CAPABILITY,
    MODE_SPECS,
    ModeSpec,
    MouseEncoding,
    MouseProtocol,
    resolve_mode_specs,
)
from bittty.model import BITTTY, GNOME, KITTY, LINUX, SCREEN, TMUX, URXVT, VT100, VT220, VT510, XTERM, Model
from bittty.options import DEC_PRINTER_PORT
from bittty.parser import Parser
from bittty.present import MouseCaptureChanged


class Recorder:
    def __init__(self):
        self.events = []

    def present(self, event):
        self.events.append(event)


def _board(model=None):
    board = Board(model=model)
    transport = MemoryConnection()
    board.host.attach(transport)
    return board, Parser(board), transport


def test_hardware_profiles_expose_only_documented_implemented_modes():
    vt100 = Board(model=VT100)
    vt220 = Board(model=VT220)

    expected_vt100 = {
        (False, 4),
        (False, 20),
        (True, 1),
        (True, 3),
        (True, 5),
        (True, 6),
        (True, 7),
    }
    assert set(vt100.modes._modes) == expected_vt100
    assert set(vt220.modes._modes) == expected_vt100 | {
        (False, 2),
        (False, 12),
        (True, 18),
        (True, 19),
        (True, 25),
        (True, 42),
    }


@pytest.mark.parametrize("model", [BITTTY, XTERM, VT100, VT220, LINUX, SCREEN, TMUX, URXVT, GNOME, KITTY])
def test_every_builtin_model_resolves_its_declared_positive_profile(model):
    """What a board resolves is the model's own repertoire plus its installed options."""
    board = Board(model=model)
    expected = {MODE_BY_CAPABILITY[capability].key for capability in model.capabilities}
    expected.difference_update(model.unsupported_modes)

    assert set(board.modes._modes) == expected


def test_custom_positive_profile_and_legacy_subtractive_override():
    minimal = Model(
        name="minimal",
        da1_response="\x1b[?1c",
        mode_capabilities=frozenset({mp.DEC_AUTOWRAP}),
    )
    board = Board(model=minimal)
    assert board.modes.recognizes(True, 7)
    assert not board.modes.recognizes(True, 1)

    legacy = Model(
        name="legacy-custom",
        da1_response="\x1b[?1c",
        unsupported_modes=frozenset({(True, 7)}),
    )
    assert not Board(model=legacy).modes.recognizes(True, 7)


def test_profile_resolution_rejects_unknown_capabilities_and_number_collisions():
    with pytest.raises(ValueError, match="unknown mode capabilities"):
        Board(model=Model(name="bad", da1_response="", mode_capabilities=frozenset({"missing"})))

    conflicting = (
        ModeSpec("family-a.mode-47", 47, True),
        ModeSpec("family-b.mode-47", 47, True),
    )
    with pytest.raises(ValueError, match="claimed by both"):
        resolve_mode_specs(frozenset({"family-a.mode-47", "family-b.mode-47"}), specs=conflicting)


def test_registry_and_profile_catalogue_remain_in_lockstep():
    assert {spec.capability for spec in MODE_SPECS} == mp.ALL_MODE_CAPABILITIES


def test_native_extensions_are_not_misattributed_to_xterm():
    assert mp.XTERM_SYNC_OUTPUT not in XTERM.mode_capabilities
    assert mp.UNICODE_GRAPHEME_CLUSTERING not in XTERM.mode_capabilities
    assert mp.UNICODE_AMBIGUOUS_WIDTH not in XTERM.mode_capabilities

    assert {
        mp.XTERM_SYNC_OUTPUT,
        mp.UNICODE_GRAPHEME_CLUSTERING,
        mp.UNICODE_AMBIGUOUS_WIDTH,
    } <= BITTTY.mode_capabilities


@pytest.mark.parametrize(
    ("model", "present", "absent"),
    [
        (LINUX, {9, 1000}, {12, 47, 66, 1004, 1049, 2004}),
        (SCREEN, {9, 47, 1000, 1006, 1048, 2004}, {12, 40, 1004, 2026}),
        (TMUX, {12, 47, 1004, 1005, 1006, 1049, 2004, 2026}, {5, 9, 40, 1048}),
        (URXVT, {9, 12, 40, 66, 67, 1005, 1015, 1048, 2004}, {69, 1007, 2026}),
        (GNOME, {9, 40, 66, 69, 1004, 1006, 1007, 1036, 1048, 2004}, {12, 42, 1005, 1015, 2026}),
        (KITTY, {12, 1004, 1005, 1006, 1015, 1048, 2004, 2026}, {9, 40, 66, 69, 1007}),
        (VT510, {66, 67, 69, 95, 100, 102, 108, 109, 110}, {9, 1000, 1004, 2026}),
        (BITTTY, {100, 102, 108, 109, 110, 2026, 2027, 8840}, {4, 38, 103, 104}),
    ],
)
def test_emulator_profiles_match_their_audited_private_mode_repertoires(model, present, absent):
    board = Board(model=model)

    assert all(board.modes.recognizes(True, mode) for mode in present)
    assert all(not board.modes.recognizes(True, mode) for mode in absent)


def test_deccolm_semantics_are_selected_by_model():
    dec, dec_parser, _ = _board(VT100)
    dec.blitter.write_text("DEC")
    dec.cursor.set_position(4, 2)
    dec_parser.feed("\x1b[?3h")
    assert dec.width == 132
    assert (dec.cursor.x, dec.cursor.y) == (0, 0)

    xterm, xterm_parser, _ = _board(XTERM)
    xterm_parser.feed("\x1b[?3h")
    assert xterm.width == 80
    xterm_parser.feed("\x1b[?40h\x1b[?3h")
    assert xterm.width == 132

    tmux, tmux_parser, _ = _board(TMUX)
    tmux.blitter.write_text("tmux")
    tmux.cursor.set_position(4, 2)
    tmux_parser.feed("\x1b[?3h")
    assert tmux.width == 80
    assert (tmux.cursor.x, tmux.cursor.y) == (0, 0)
    assert tmux.blitter.current_page.get_cell(0, 0)[1] == " "
    assert tmux.modes.get_private_mode_status(3) == 4

    kitty, kitty_parser, _ = _board(KITTY)
    kitty.blitter.write_text("kitty")
    kitty.cursor.set_position(4, 2)
    kitty_parser.feed("\x1b[?3h")
    assert kitty.width == 80
    assert (kitty.cursor.x, kitty.cursor.y) == (0, 0)
    assert kitty.modes.get_private_mode_status(3) == 1
    kitty.blitter.write_text("kept")
    kitty.cursor.set_position(3, 1)
    kitty_parser.feed("\x1b[?3l")
    assert (kitty.cursor.x, kitty.cursor.y) == (3, 1)
    assert kitty.blitter.current_page.get_cell(0, 0)[1] == "k"
    assert kitty.modes.get_private_mode_status(3) == 2


def test_tracking_modes_are_mutually_exclusive_and_query_the_selector():
    board, parser, transport = _board()

    parser.feed("\x1b[?1000h\x1b[?1002h")
    assert board.modes.mouse_protocol is MouseProtocol.BUTTON
    assert board.modes.get_private_mode_status(1000) == 2
    assert board.modes.get_private_mode_status(1002) == 1

    # Resetting an inactive member is a no-op; resetting the selected one turns tracking off.
    parser.feed("\x1b[?1000l\x1b[?1000$p\x1b[?1002$p")
    assert board.modes.mouse_protocol is MouseProtocol.BUTTON
    assert transport.data[-2:] == ["\x1b[?1000;2$y", "\x1b[?1002;1$y"]

    parser.feed("\x1b[?1002l")
    assert board.modes.mouse_protocol is MouseProtocol.OFF


def test_mouse_encodings_are_mutually_exclusive_and_reset_to_legacy():
    board, parser, _ = _board()

    parser.feed("\x1b[?1005h\x1b[?1015h")
    assert board.modes.mouse_encoding is MouseEncoding.URXVT
    assert board.modes.get_private_mode_status(1005) == 2
    assert board.modes.get_private_mode_status(1015) == 1

    parser.feed("\x1b[?1005l")
    assert board.modes.mouse_encoding is MouseEncoding.URXVT

    parser.feed("\x1b[?1015l")
    assert board.modes.mouse_encoding is MouseEncoding.LEGACY
    assert board.modes.get_private_mode_status(1015) == 2


def test_x10_reports_presses_only_and_ignores_modifiers():
    board, parser, transport = _board()
    parser.feed("\x1b[?9h")

    board.input_mouse(10, 5, 0, "press", {"shift", "ctrl"})
    board.input_mouse(10, 5, 0, "release", {"shift", "ctrl"})
    board.input_mouse(11, 5, 0, "move", {"shift", "ctrl"})

    # X10 reports are bytes: a real connection takes them through write_bytes.
    assert transport.data == [b"\x1b[M" + bytes((32, 42, 37))]


def test_locator_and_xterm_tracking_replace_each_other_and_drive_capture():
    board, parser, _ = _board()
    recorder = Recorder()
    board.display.attach(recorder)

    parser.feed("\x1b[1'z")
    assert board.modes.mouse_protocol is MouseProtocol.LOCATOR
    assert recorder.events[-1] == MouseCaptureChanged("any")

    parser.feed("\x1b[?1000h")
    assert board.modes.mouse_protocol is MouseProtocol.NORMAL
    assert board.mouse.locator_enabled == 0
    assert recorder.events[-1] == MouseCaptureChanged("basic")

    parser.feed("\x1b[1'z")
    assert board.modes.get_private_mode_status(1000) == 2
    assert recorder.events[-1] == MouseCaptureChanged("any")


def test_mode_lists_emit_only_the_final_capture_requirement():
    board, parser, _ = _board()
    recorder = Recorder()
    board.display.attach(recorder)

    parser.feed("\x1b[?1000;1002;1003h")

    assert recorder.events == [MouseCaptureChanged("any")]


def test_declared_defaults_restore_on_hard_reset():
    board, parser, _ = _board()
    parser.feed("\x1b[?7l\x1b[?1035l\x1b[?1046l\x1b[?1003h\x1b[?1006h")

    board.reset(hard=True)

    assert board.modes.auto_wrap is True
    assert board.modes.special_modifiers is True
    assert board.modes.allow_alt_screen is True
    assert board.modes.mouse_protocol is MouseProtocol.OFF
    assert board.modes.mouse_encoding is MouseEncoding.LEGACY


def test_private_mode_save_restore_is_independent_and_ignores_unsaved_modes():
    board, parser, _ = _board()
    parser.feed("\x1b[?5h\x1b[?25l\x1b[?5s")
    parser.feed("\x1b[?5l\x1b[?25h\x1b[?25s")
    parser.feed("\x1b[?5l\x1b[?25l\x1b[?2004h")

    parser.feed("\x1b[?5;25;2004r")

    assert board.modes.reverse_screen is True
    assert board.modes.cursor_visible is True
    assert board.modes.bracketed_paste is True


def test_private_mode_restore_reconstructs_exclusive_mouse_groups():
    board, parser, _ = _board()
    parser.feed("\x1b[?1000;1006h")
    parser.feed("\x1b[?1000;1002;1003;1005;1006;1015s")
    parser.feed("\x1b[?1003h\x1b[?1006l")

    parser.feed("\x1b[?1000;1002;1003;1005;1006;1015r")

    assert board.modes.mouse_protocol is MouseProtocol.NORMAL
    assert board.modes.mouse_encoding is MouseEncoding.SGR


def test_private_mode_restore_batches_frontend_reconciliation():
    board, parser, _ = _board()
    recorder = Recorder()
    board.display.attach(recorder)
    parser.feed("\x1b[?1000h\x1b[?1000;1002;1003s\x1b[?1003h")
    recorder.events.clear()

    parser.feed("\x1b[?1000;1002;1003r")

    assert recorder.events == [MouseCaptureChanged("basic")]


def test_private_mode_1048_save_restore_uses_the_cursor_cache():
    board, parser, _ = _board()
    board.cursor.set_position(3, 2)

    parser.feed("\x1b[?1048s")
    board.cursor.set_position(9, 4)
    parser.feed("\x1b[?1048r")

    assert (board.cursor.x, board.cursor.y) == (3, 2)


def test_ris_clears_private_mode_cache_but_soft_reset_preserves_it():
    board, parser, _ = _board()
    parser.feed("\x1b[?5h\x1b[?5s\x1b[!p\x1b[?5l\x1b[?5r")
    assert board.modes.reverse_screen is True

    parser.feed("\x1bc\x1b[?5l\x1b[?5r")
    assert board.modes.reverse_screen is False


# --- installed options (tier 1: what the terminal *is*) --- #


def test_an_option_contributes_modes_the_model_does_not_declare():
    """Fitting a printer port to a VT100 makes it recognise the print modes.

    Tier 1 of the peripheral model: an option changes the mode repertoire. The
    same modes are unrecognised on the bare model.
    """
    bare = Board(model=VT100)
    assert bare.modes.get_private_mode_status(18) == 0  # DECPFF: not recognised
    assert bare.modes.get_private_mode_status(19) == 0  # DECPEX

    fitted = Model(
        name="vt100+printer",
        da1_response=VT100.da1_response,
        mode_capabilities=VT100.mode_capabilities,
        keymap=VT100.keymap,
        options=frozenset({DEC_PRINTER_PORT}),
    )
    board = Board(model=fitted)
    assert board.modes.get_private_mode_status(18) == 2  # recognised, reset
    assert board.modes.get_private_mode_status(19) == 2


def test_the_printer_repertoire_comes_from_the_installed_port():
    """One mechanism, not two: the port carries both the modes and the protocol level."""
    assert VT100.printer_capabilities.media_copy is False

    assert VT220.printer_capabilities.media_copy is True
    assert VT220.printer_capabilities.configuration is False  # DEC media copy only
    assert VT510.printer_capabilities.configuration is True  # VT510 adds DECSPRTT & co
    assert XTERM.printer_capabilities.disconnected_status is PrinterStatus.NOT_READY


def test_a_fitted_port_with_nothing_plugged_in_still_recognises_its_modes():
    """Tier 1 enables modes; tier 3 only changes the status report.

    A VT220 honours DECPFF with an empty cable — the port is what the terminal
    has. Only DSR changes when nothing is attached.
    """
    board = Board(model=VT220)

    assert board.modes.get_private_mode_status(18) == 2  # known, despite no printer
    assert board.printer.port.connected is False
    assert board.printer.status is PrinterStatus.OFFLINE


def test_capabilities_is_the_model_repertoire_unioned_with_its_options():
    assert mp.DEC_PRINT_FORM_FEED not in VT220.mode_capabilities  # not the model's own
    assert mp.DEC_PRINT_FORM_FEED in VT220.capabilities  # contributed by the port
    assert VT100.capabilities == VT100.mode_capabilities  # no options, no difference
