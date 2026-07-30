import pytest

from bittty import Board
from bittty import mode_profiles as mp
from bittty.devices.modes import (
    MODE_BY_CAPABILITY,
    MODE_SPECS,
    ModeSpec,
    MouseEncoding,
    MouseProtocol,
    resolve_mode_specs,
)
from bittty.model import GNOME, KITTY, LINUX, SCREEN, TMUX, URXVT, XTERM, Model, VT100, VT220
from bittty.parser import Parser
from bittty.present import MouseCaptureChanged


class RecordingTransport:
    def __init__(self):
        self.data = []

    def write(self, data):
        self.data.append(data)

    def flush(self):
        pass


class Recorder:
    def __init__(self):
        self.events = []

    def present(self, event):
        self.events.append(event)


def _board(model=None):
    board = Board(model=model)
    transport = RecordingTransport()
    board.host.attach(transport)
    return board, Parser(board), transport


def test_positive_profiles_preserve_the_current_dec_repertoires():
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
        (True, 18),
        (True, 19),
        (True, 25),
        (True, 66),
        (True, 67),
    }
    assert set(vt100.modes._modes) == expected_vt100
    assert set(vt220.modes._modes) == expected_vt100 | {(True, 42)}


@pytest.mark.parametrize("model", [XTERM, VT100, VT220, LINUX, SCREEN, TMUX, URXVT, GNOME, KITTY])
def test_every_builtin_model_resolves_its_declared_positive_profile(model):
    board = Board(model=model)
    expected = {MODE_BY_CAPABILITY[capability].key for capability in model.mode_capabilities}
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

    assert transport.data == ["\x1b[M" + chr(32) + chr(42) + chr(37)]


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
