from bittty.operations import Operation
from bittty.style import Color, Style, parse_sgr_sequence
from bittty.terminal import Terminal


def test_charset_device_translates_active_and_single_shift_charsets():
    terminal = Terminal(width=10, height=3)
    charset = terminal.charset

    charset.set_g0_charset("0")
    assert charset.translate("q") == "─"

    charset.set_g2_charset("0")
    charset.set_g0_charset("B")
    charset.single_shift_2()
    assert charset.translate("qz") == "─z"
    assert charset.single_shift is None


def test_charset_device_handles_operations_and_reset():
    terminal = Terminal(width=10, height=3)
    charset = terminal.charset

    charset.handle_charset_operation(Operation("charset", "SCS_G1", ("0",), "\x1b)0"))
    charset.handle_escape_operation(Operation("escape", "SS3", raw="\x1bO"))

    assert charset.g1_charset == "0"
    assert charset.single_shift == 3

    charset.reset()
    assert [charset.g0_charset, charset.g1_charset, charset.g2_charset, charset.g3_charset] == ["B", "B", "B", "B"]
    assert charset.current_charset == 0
    assert charset.single_shift is None


def test_style_device_applies_reset_and_merge():
    terminal = Terminal(width=10, height=3)
    style = terminal.style

    style.apply_sgr(Style(bold=True))
    style.apply_sgr(Style(fg=Color("indexed", 1)))

    parsed = parse_sgr_sequence(style.current_ansi_code)
    assert parsed.bold is True
    assert parsed.fg == Color("indexed", 1)

    style.apply_sgr(Style(), reset=True)
    assert style.current_ansi_code == ""


def test_style_device_reports_background_ansi():
    terminal = Terminal(width=10, height=3)

    terminal.style.current_ansi_code = "\x1b[48;5;21m"

    assert terminal.style.background_ansi() == "\x1b[48;5;21m"
