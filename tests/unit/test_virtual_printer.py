import asyncio
from dataclasses import replace

import pytest

from bittty import (
    Board,
    PrintDirection,
    PrinterCharacterSet,
    PrinterCharacterState,
    PrinterColor,
    PrinterConfiguration,
    PrinterDensity,
    PrinterLanguage,
    PrinterRendition,
    PrinterScript,
    PrinterStatus,
    PrinterType,
    PrinterUnderline,
    PrinterUnsolicitedReports,
    VirtualPrinter,
    VirtualPrinterProfile,
    VirtualPrinterState,
)


async def _read_printer_chunks(printer, count):
    return b"".join([await printer.read_bytes_async(1024) for _ in range(count)])


def test_physical_type_selects_fixed_initial_language():
    cases = (
        (PrinterType.DEC_ANSI, PrinterLanguage.DEC_PPL),
        (PrinterType.PROPRINTER, PrinterLanguage.IBM_PROPRINTER),
        (PrinterType.DEC_AND_IBM, PrinterLanguage.DEC_PPL),
    )
    for device_type, language in cases:
        printer = VirtualPrinter(device_type)
        assert printer.device_type is device_type
        assert printer.state == VirtualPrinterState(language, PrintDirection.BIDIRECTIONAL)
        with pytest.raises(AttributeError):
            printer.device_type = PrinterType.PROPRINTER


def test_virtual_printer_keeps_an_exact_raw_trace_and_memory_duplex():
    printer = VirtualPrinter()
    payload = b"text\x00\xff\x1b[?41h"
    assert printer.write_bytes(payload) == len(payload)
    assert bytes(printer.data) == payload

    printer.send_bytes(b"reply")
    assert asyncio.run(printer.read_bytes_async(3)) == b"rep"
    assert asyncio.run(printer.read_bytes_async(8)) == b"ly"

    printer.close()
    with pytest.raises(ValueError, match="closed"):
        printer.write_bytes(b"x")


def test_profile_selects_physical_defaults_and_is_immutable():
    profile = VirtualPrinterProfile(
        "test-ppl3",
        device_type=PrinterType.DEC_AND_IBM,
        primary_device_attributes=[73, 23],
        secondary_device_attributes=[99, 10],
        supports_cursor_position_report=True,
    )
    printer = VirtualPrinter(profile=profile)

    assert printer.profile is profile
    assert printer.device_type is PrinterType.DEC_AND_IBM
    assert profile.primary_device_attributes == (73, 23)
    with pytest.raises(AttributeError):
        profile.name = "changed"
    with pytest.raises(ValueError, match="must match"):
        VirtualPrinter(PrinterType.PROPRINTER, profile=profile)


@pytest.mark.parametrize("introducer", (b"\x1b[", b"\x9b"))
def test_dec_device_attribute_reports_use_profile_identity(introducer):
    profile = VirtualPrinterProfile(
        "reporting-test",
        primary_device_attributes=(73, 23),
        secondary_device_attributes=(53, 10, 0, 0, 0, 0, 0),
    )
    printer = VirtualPrinter(profile=profile)
    printer.write_bytes(b"before" + introducer + b"c" + introducer + b">0c")

    assert asyncio.run(_read_printer_chunks(printer, 2)) == (b"\x1b[?73;23c\x1b[>53;10;0;0;0;0;0c")
    assert printer.current_page.items[0].data == b"before"
    assert bytes(printer.data) == b"before" + introducer + b"c" + introducer + b">0c"


def test_unimplemented_and_malformed_device_attribute_requests_are_silent():
    printer = VirtualPrinter()
    printer.write_bytes(b"\x1b[>c\x1b[1c\x1b[0;0c\x1b[>1c")
    printer.send_bytes(b"sentinel")
    assert asyncio.run(printer.read_bytes_async(1024)) == b"sentinel"


@pytest.mark.parametrize(
    "status,brief,parameters",
    (
        (PrinterStatus.READY, b"\x1b[0n", b"\x1b[?20n"),
        (PrinterStatus.ASSIGNED, b"\x1b[0n", b"\x1b[?20n"),
        (PrinterStatus.OFFLINE, b"\x1b[3n", b"\x1b[?24n"),
        (PrinterStatus.NOT_READY, b"\x1b[3n", b"\x1b[?59n"),
        (PrinterStatus.BUSY, b"\x1b[3n", b"\x1b[?59n"),
    ),
)
def test_dsr_returns_profile_driven_brief_and_extended_status(status, brief, parameters):
    printer = VirtualPrinter(status=status)
    printer.write_bytes(b"\x1b[5n")
    assert asyncio.run(_read_printer_chunks(printer, 2)) == brief + parameters


def test_dsr_unsolicited_modes_follow_status_changes_and_reset():
    printer = VirtualPrinter()
    printer.write_bytes(b"\x1b[?2n")
    assert printer.unsolicited_reports is PrinterUnsolicitedReports.BRIEF
    assert asyncio.run(_read_printer_chunks(printer, 2)) == b"\x1b[0n\x1b[?20n"

    printer.status = PrinterStatus.OFFLINE
    assert asyncio.run(printer.read_bytes_async(1024)) == b"\x1b[3n"
    printer.status = PrinterStatus.OFFLINE

    printer.write_bytes(b"\x1b[?3n")
    assert printer.unsolicited_reports is PrinterUnsolicitedReports.EXTENDED
    assert asyncio.run(_read_printer_chunks(printer, 2)) == b"\x1b[3n\x1b[?24n"
    printer.status = PrinterStatus.READY
    assert asyncio.run(_read_printer_chunks(printer, 2)) == b"\x1b[0n\x1b[?20n"

    printer.reset()
    assert printer.unsolicited_reports is PrinterUnsolicitedReports.DISABLED


def test_private_dsr_one_disables_unsolicited_reports_without_reply():
    printer = VirtualPrinter()
    printer.write_bytes(b"\x1b[?2n")
    assert asyncio.run(_read_printer_chunks(printer, 2)) == b"\x1b[0n\x1b[?20n"
    printer.write_bytes(b"\x1b[?1n")
    printer.status = PrinterStatus.OFFLINE
    printer.send_bytes(b"sentinel")
    assert printer.unsolicited_reports is PrinterUnsolicitedReports.DISABLED
    assert asyncio.run(printer.read_bytes_async(1024)) == b"sentinel"


def test_cursor_position_report_is_profile_gated_and_uses_current_pitch_grid():
    unsupported = VirtualPrinter()
    unsupported.write_bytes(b"AB\x1b[6n")
    unsupported.send_bytes(b"sentinel")
    assert asyncio.run(unsupported.read_bytes_async(1024)) == b"sentinel"

    profile = VirtualPrinterProfile("ppl3-test", supports_cursor_position_report=True)
    printer = VirtualPrinter(profile=profile)
    printer.write_bytes(b"AB\nC\x1b[6n")
    assert asyncio.run(printer.read_bytes_async(1024)) == b"\x1b[2;4R"


def test_report_sequences_remain_fragment_safe_and_ibm_language_ignores_them():
    printer = VirtualPrinter()
    for byte in b"\x1b[0c":
        printer.write_bytes(bytes((byte,)))
    assert asyncio.run(printer.read_bytes_async(1024)) == b"\x1b[?72c"

    ibm = VirtualPrinter(PrinterType.PROPRINTER)
    ibm.write_bytes(b"\x1b[c\x1b[5n")
    ibm.send_bytes(b"sentinel")
    assert asyncio.run(ibm.read_bytes_async(1024)) == b"sentinel"


@pytest.mark.parametrize("introducer", (b"\x1b[", b"\x9b"))
def test_decupm_accepts_7_bit_and_c1_csi(introducer):
    printer = VirtualPrinter()
    printer.write_bytes(introducer + b"?41h")
    assert printer.state.direction is PrintDirection.UNIDIRECTIONAL
    printer.write_bytes(introducer + b"?41l")
    assert printer.state.direction is PrintDirection.BIDIRECTIONAL


@pytest.mark.parametrize(
    "mode, attribute",
    (
        (27, "proportional_spacing"),
        (29, "pitch_from_font"),
        (40, "carriage_return_new_line"),
    ),
)
@pytest.mark.parametrize("introducer", (b"\x1b[", b"\x9b"))
def test_low_cost_dec_ppl_modes_accept_7_bit_and_c1_csi(mode, attribute, introducer):
    printer = VirtualPrinter()
    assert getattr(printer.state, attribute) is False

    printer.write_bytes(introducer + f"?{mode}h".encode())
    assert getattr(printer.state, attribute) is True

    printer.write_bytes(introducer + f"?{mode}l".encode())
    assert getattr(printer.state, attribute) is False


def test_low_cost_dec_ppl_modes_support_ordered_parameter_lists():
    printer = VirtualPrinter()
    printer.write_bytes(b"\x1b[?27;999;29;40h")
    assert printer.state.proportional_spacing is True
    assert printer.state.pitch_from_font is True
    assert printer.state.carriage_return_new_line is True

    printer.write_bytes(b"\x1b[?29l")
    assert printer.state.proportional_spacing is True
    assert printer.state.pitch_from_font is False
    assert printer.state.carriage_return_new_line is True


@pytest.mark.parametrize("introducer", (b"\x1b[", b"\x9b"))
def test_printer_autowrap_accepts_7_bit_and_c1_csi(introducer):
    printer = VirtualPrinter()
    assert printer.state.autowrap is True

    printer.write_bytes(introducer + b"?7l")
    assert printer.state.autowrap is False
    printer.write_bytes(introducer + b"?7h")
    assert printer.state.autowrap is True


@pytest.mark.parametrize(
    "mode, attribute",
    (
        (3, "control_representation"),
        (20, "line_feed_new_line"),
    ),
)
@pytest.mark.parametrize("introducer", (b"\x1b[", b"\x9b"))
def test_standard_printer_modes_accept_7_bit_and_c1_csi(mode, attribute, introducer):
    printer = VirtualPrinter()
    assert getattr(printer.state, attribute) is False

    printer.write_bytes(introducer + f"{mode}h".encode())
    assert getattr(printer.state, attribute) is True

    printer.write_bytes(introducer + f"{mode}l".encode())
    assert getattr(printer.state, attribute) is False


def test_printer_character_and_rendition_defaults_are_explicit_and_immutable():
    printer = VirtualPrinter()

    assert printer.state.rendition == PrinterRendition()
    assert printer.state.characters == PrinterCharacterState()
    assert printer.state.characters.g_sets == (
        PrinterCharacterSet(94, "B"),
        PrinterCharacterSet(94, "B"),
        PrinterCharacterSet(94, "<"),
        PrinterCharacterSet(94, "<"),
    )
    assert printer.state.characters.user_preference == PrinterCharacterSet(94, "%5")
    with pytest.raises(ValueError):
        PrinterCharacterSet(95, "B")
    with pytest.raises(ValueError):
        PrinterCharacterSet(94, "")


def test_sgr_retains_standard_attributes_colour_and_typestyle():
    printer = VirtualPrinter()
    printer.write_bytes(b"\x1b[1;3;4;9;12;31;53m")

    assert printer.state.rendition == PrinterRendition(
        typestyle=12,
        bold=True,
        slanted=True,
        underline=PrinterUnderline.SINGLE,
        strikethrough=True,
        overline=True,
        color=PrinterColor.RED,
    )

    printer.write_bytes(b"\x1b[21;22;23;29;39;55m")
    assert printer.state.rendition == PrinterRendition(
        typestyle=12,
        underline=PrinterUnderline.DOUBLE,
    )

    printer.write_bytes(b"\x1b[m")
    assert printer.state.rendition == PrinterRendition(typestyle=12)


def test_private_sgr_retains_script_and_deprecated_overline_attributes():
    printer = VirtualPrinter()
    printer.write_bytes(b"\x1b[?4;6m")
    assert printer.state.rendition.script is PrinterScript.SUPERSCRIPT
    assert printer.state.rendition.overline is True

    printer.write_bytes(b"\x1b[?5m")
    assert printer.state.rendition.script is PrinterScript.SUBSCRIPT
    printer.write_bytes(b"\x1b[?24;26m")
    assert printer.state.rendition.script is PrinterScript.NORMAL
    assert printer.state.rendition.overline is False


@pytest.mark.parametrize(
    "parameter, density",
    (
        (0, PrinterDensity.DRAFT),
        (1, PrinterDensity.DRAFT),
        (2, PrinterDensity.LETTER_QUALITY),
        (3, PrinterDensity.MEMO),
        (4, PrinterDensity.NEAR_LETTER_QUALITY),
    ),
)
def test_decden_selects_font_density_and_sgr_reset_preserves_it(parameter, density):
    printer = VirtualPrinter()
    printer.write_bytes(f'\x1b[{parameter}"z'.encode())
    assert printer.state.rendition.density is density

    printer.write_bytes(b"\x1b[1;0m")
    assert printer.state.rendition == PrinterRendition(density=density)


def test_sgr_changes_split_page_runs_and_capture_their_rendition():
    printer = VirtualPrinter()
    printer.write_bytes(b"A\x1b[1;34mB\x1b[22;39mC")

    first, second, third = printer.current_page.items
    assert first.state.rendition == PrinterRendition()
    assert second.state.rendition == PrinterRendition(bold=True, color=PrinterColor.BLUE)
    assert third.state.rendition == PrinterRendition()


def test_scs_designates_94_and_96_character_sets_in_all_four_g_sets():
    printer = VirtualPrinter()
    printer.write_bytes(b"\x1b(0\x1b)A\x1b*%5\x1b-A")

    assert printer.state.characters.g_sets == (
        PrinterCharacterSet(94, "0"),
        PrinterCharacterSet(96, "A"),
        PrinterCharacterSet(94, "%5"),
        PrinterCharacterSet(94, "<"),
    )


def test_locking_shifts_invoke_g_sets_into_gl_and_gr():
    printer = VirtualPrinter()

    for sequence, gl, gr in (
        (b"\x0e", 1, 2),
        (b"\x0f", 0, 2),
        (b"\x1bn", 2, 2),
        (b"\x1bo", 3, 2),
        (b"\x1b~", 3, 1),
        (b"\x1b}", 3, 2),
        (b"\x1b|", 3, 3),
    ):
        printer.write_bytes(sequence)
        assert (printer.state.characters.gl, printer.state.characters.gr) == (gl, gr)


@pytest.mark.parametrize("shift", (b"\x1bN", b"\x8e"))
def test_single_shift_is_captured_by_one_print_run_then_cleared(shift):
    printer = VirtualPrinter()
    printer.write_bytes(b"\x1b*0" + shift + b"qA")

    shifted, normal = printer.current_page.items
    assert shifted.data == b"q"
    assert shifted.state.characters.single_shift == 2
    assert normal.data == b"A"
    assert normal.state.characters.single_shift is None
    assert printer.state.characters.single_shift is None


def test_single_shift_survives_controls_and_sequences_until_printable_data():
    printer = VirtualPrinter()
    printer.write_bytes(b"\x1b*0\x1bN\n\x1b[1mq")

    run = printer.current_page.items[0]
    assert run.bounds.top == 3600
    assert run.state.characters.single_shift == 2
    assert run.state.rendition.bold is True
    assert printer.state.characters.single_shift is None


def test_single_shift_skips_space_for_a_94_character_set():
    printer = VirtualPrinter()
    printer.write_bytes(b"\x1b*0\x1bN qA")

    space, shifted, normal = printer.current_page.items
    assert space.data == b" "
    assert space.state.characters.single_shift is None
    assert shifted.data == b"q"
    assert shifted.state.characters.single_shift == 2
    assert normal.state.characters.single_shift is None


def test_single_shift_consumes_space_for_a_96_character_set():
    printer = VirtualPrinter()
    printer.write_bytes(b"\x1b.A\x1bN A")

    shifted, normal = printer.current_page.items
    assert shifted.data == b" "
    assert shifted.state.characters.single_shift == 2
    assert normal.data == b"A"
    assert normal.state.characters.single_shift is None


@pytest.mark.parametrize("level", (b"L", b"M"))
def test_ascef_levels_one_and_two_select_ascii_and_iso_latin_1(level):
    printer = VirtualPrinter()
    printer.write_bytes(b"\x1b " + level)

    assert printer.state.characters.g_sets[:2] == (
        PrinterCharacterSet(94, "B"),
        PrinterCharacterSet(96, "A"),
    )
    assert (printer.state.characters.gl, printer.state.characters.gr) == (0, 1)


@pytest.mark.parametrize(
    "sequence, expected",
    (
        (b"\x1bP0!u>\x1b\\", PrinterCharacterSet(94, ">")),
        (b"\x901!uA\x9c", PrinterCharacterSet(96, "A")),
    ),
)
def test_decaupss_assigns_the_user_preference_character_set(sequence, expected):
    printer = VirtualPrinter()
    printer.write_bytes(sequence)

    assert printer.state.characters.user_preference == expected


def test_character_and_rendition_commands_survive_every_stream_boundary():
    payload = b"\x1b(0\x1b*%5\x1bn\x1bN\x1b[1;4;13;35mA\x1bP1!uA\x1b\\"
    whole = VirtualPrinter()
    whole.write_bytes(payload)

    for boundary in range(len(payload) + 1):
        streamed = VirtualPrinter()
        streamed.write_bytes(payload[:boundary])
        streamed.write_bytes(payload[boundary:])
        assert streamed.current_page == whole.current_page
        assert streamed.state == whole.state


@pytest.mark.parametrize("reset", (b"\x1b[3l", b"\x9b3l"))
def test_crm_shields_other_commands_until_its_own_reset(reset):
    printer = VirtualPrinter(PrinterType.DEC_AND_IBM)
    printer.write_bytes(b"\x1b[?7l\x1b[3h")
    printer.write_bytes(b"\x1b[?7h\x1b[20h\x1b[?58h\x1b[!p\x1bc")
    assert printer.state == VirtualPrinterState(
        PrinterLanguage.DEC_PPL,
        PrintDirection.BIDIRECTIONAL,
        autowrap=False,
        control_representation=True,
    )

    printer.write_bytes(reset)
    printer.write_bytes(b"\x1b[?7h\x1b[20h")
    assert printer.state.autowrap is True
    assert printer.state.control_representation is False
    assert printer.state.line_feed_new_line is True


@pytest.mark.parametrize("reset", (b"\x1b[3l", b"\x9b3l"))
def test_crm_reset_survives_every_stream_boundary(reset):
    for boundary in range(len(reset) + 1):
        printer = VirtualPrinter()
        printer.write_bytes(b"\x1b[3h")
        printer.write_bytes(reset[:boundary])
        printer.write_bytes(reset[boundary:])
        assert printer.state.control_representation is False


def test_crm_reset_near_misses_are_inert_and_parser_resynchronises():
    printer = VirtualPrinter()
    printer.write_bytes(b"\x1b[3h")
    printer.write_bytes(b"\x1b[3m\x1b[33l\x9b3m")
    assert printer.state.control_representation is True

    printer.write_bytes(b"\x1b[3l")
    assert printer.state.control_representation is False


def test_dec_private_parameters_are_applied_in_stream_order():
    printer = VirtualPrinter(PrinterType.DEC_AND_IBM)
    printer.write_bytes(b"\x1b[?999;41h")
    assert printer.state.direction is PrintDirection.UNIDIRECTIONAL

    printer.write_bytes(b"\x1b[?41l\x1b[?41;58;41h")
    assert printer.state == VirtualPrinterState(
        PrinterLanguage.IBM_PROPRINTER,
        PrintDirection.UNIDIRECTIONAL,
    )


@pytest.mark.parametrize("sequence", (b"\x1b[?58h", b"\x1b%="))
def test_dual_printer_can_enter_ibm_and_exact_7_bit_commands_return_to_dec(sequence):
    for exit_sequence in (b"\x1b[?58l", b"\x1b%@"):
        printer = VirtualPrinter(PrinterType.DEC_AND_IBM)
        printer.write_bytes(b"\x1b[?41h" + sequence)
        printer.write_bytes(exit_sequence)
        assert printer.state == VirtualPrinterState(
            PrinterLanguage.DEC_PPL,
            PrintDirection.UNIDIRECTIONAL,
        )


def test_single_language_devices_ignore_language_switching_commands():
    dec = VirtualPrinter(PrinterType.DEC_ANSI)
    dec.write_bytes(b"\x1b[?58h\x1b%=")
    assert dec.state.language is PrinterLanguage.DEC_PPL

    ibm = VirtualPrinter(PrinterType.PROPRINTER)
    ibm.write_bytes(b"\x1b%@\x1b[?58l\x1b[!p\x1bc")
    assert ibm.state.language is PrinterLanguage.IBM_PROPRINTER


def test_ibm_recognises_only_exact_7_bit_exit_sequences():
    printer = VirtualPrinter(PrinterType.DEC_AND_IBM)
    printer.write_bytes(b"\x1b[?41h\x1b%=")
    printer.write_bytes(b"\x9b?58l\x1b[?58m\x1b[%@\x1b[?41l")
    assert printer.state == VirtualPrinterState(
        PrinterLanguage.IBM_PROPRINTER,
        PrintDirection.UNIDIRECTIONAL,
    )

    # DECSTR is recognised in alternate mode, but does not leave it.
    printer.write_bytes(b"\x1b[!p")
    assert printer.state.language is PrinterLanguage.IBM_PROPRINTER


def test_decstr_ris_and_public_reset_have_distinct_reset_scopes():
    printer = VirtualPrinter(PrinterType.DEC_AND_IBM)
    for reset in (b"\x1b[!p", b"\x1bc"):
        printer.write_bytes(b"\x1b[?7l\x1b[20h\x1b[?27;29;40;41h\x1b[1;14;31m\x1b(0" + reset)
        assert printer.state == VirtualPrinterState(
            PrinterLanguage.DEC_PPL,
            PrintDirection.BIDIRECTIONAL,
        )

    printer.write_bytes(b"\x1b[?58h")
    assert printer.state.language is PrinterLanguage.IBM_PROPRINTER
    printer.reset()
    assert printer.state == VirtualPrinterState(
        PrinterLanguage.DEC_PPL,
        PrintDirection.BIDIRECTIONAL,
    )

    native_ibm = VirtualPrinter(PrinterType.PROPRINTER)
    native_ibm.reset()
    assert native_ibm.state.language is PrinterLanguage.IBM_PROPRINTER

    printer.write_bytes(b"\x1b[3h")
    printer.reset()
    assert printer.state.control_representation is False
    assert printer.state.rendition == PrinterRendition()
    assert printer.state.characters == PrinterCharacterState()


def test_dec_modes_survive_protocol_switching_and_ibm_ignores_dec_mode_commands():
    printer = VirtualPrinter(PrinterType.DEC_AND_IBM)
    printer.write_bytes(b"\x1b[?7l\x1b[20h\x1b[?27;29;40h\x1b%=")
    printer.write_bytes(b"\x1b[20l\x1b[?7;27;29;40l")
    assert printer.state == VirtualPrinterState(
        PrinterLanguage.IBM_PROPRINTER,
        PrintDirection.BIDIRECTIONAL,
        proportional_spacing=True,
        pitch_from_font=True,
        carriage_return_new_line=True,
        autowrap=False,
        line_feed_new_line=True,
    )

    printer.write_bytes(b"\x1b%@")
    assert printer.state == VirtualPrinterState(
        PrinterLanguage.DEC_PPL,
        PrintDirection.BIDIRECTIONAL,
        proportional_spacing=True,
        pitch_from_font=True,
        carriage_return_new_line=True,
        autowrap=False,
        line_feed_new_line=True,
    )


@pytest.mark.parametrize(
    "shielded",
    (
        b"\x1bPpayload\x1b[?41h\x1b\\",
        b"\x1b]title\x1b[?41h\x9c",
        b"\x1b]title\x1b[?41h\x07",
        b"\x90payload\x1b[?41h\x9c",
        b"\x9dpayload\x1b[?41h\x18",
    ),
)
def test_control_strings_shield_printer_commands(shielded):
    printer = VirtualPrinter()
    for byte in shielded:
        printer.write_bytes(bytes((byte,)))
    assert printer.state.direction is PrintDirection.BIDIRECTIONAL


@pytest.mark.parametrize("terminator", (b"\x07", b"\x1b\x07", b"\x9c", b"\x1b\x9c", b"\x1b\\"))
def test_osc_termination_resumes_command_parsing(terminator):
    printer = VirtualPrinter()
    printer.write_bytes(b"\x1b]title" + terminator + b"\x1b[?41h")
    assert printer.state.direction is PrintDirection.UNIDIRECTIONAL


@pytest.mark.parametrize(
    "sequence, expected",
    (
        (b"\x1b[?41h", VirtualPrinterState(PrinterLanguage.DEC_PPL, PrintDirection.UNIDIRECTIONAL)),
        (b"\x9b?41h", VirtualPrinterState(PrinterLanguage.DEC_PPL, PrintDirection.UNIDIRECTIONAL)),
        (b"\x1b%=", VirtualPrinterState(PrinterLanguage.IBM_PROPRINTER, PrintDirection.BIDIRECTIONAL)),
    ),
)
def test_commands_survive_every_stream_boundary(sequence, expected):
    for boundary in range(len(sequence) + 1):
        printer = VirtualPrinter(PrinterType.DEC_AND_IBM)
        printer.write_bytes(sequence[:boundary])
        printer.write_bytes(sequence[boundary:])
        assert printer.state == expected


@pytest.mark.parametrize(
    "mode, attribute",
    (
        (27, "proportional_spacing"),
        (29, "pitch_from_font"),
        (40, "carriage_return_new_line"),
    ),
)
def test_low_cost_dec_ppl_modes_survive_every_stream_boundary(mode, attribute):
    sequence = f"\x1b[?{mode}h".encode()
    for boundary in range(len(sequence) + 1):
        printer = VirtualPrinter()
        printer.write_bytes(sequence[:boundary])
        printer.write_bytes(sequence[boundary:])
        assert getattr(printer.state, attribute) is True


def test_ibm_exit_survives_every_stream_boundary():
    sequence = b"\x1b[?58l"
    for boundary in range(len(sequence) + 1):
        printer = VirtualPrinter(PrinterType.DEC_AND_IBM)
        printer.write_bytes(b"\x1b%=")
        printer.write_bytes(sequence[:boundary])
        printer.write_bytes(sequence[boundary:])
        assert printer.state.language is PrinterLanguage.DEC_PPL


def test_malformed_csi_is_bounded_and_parser_resynchronises():
    printer = VirtualPrinter()
    printer.write_bytes(b"\x1b[?" + b"1" * 256)
    printer.write_bytes(b"\x1b[?41h")
    assert printer.state.direction is PrintDirection.UNIDIRECTIONAL


def test_configuration_snapshots_do_not_change_physical_identity():
    printer = VirtualPrinter(PrinterType.DEC_AND_IBM)
    configuration = replace(
        PrinterConfiguration(),
        printer_type=PrinterType.PROPRINTER,
    )
    printer.configure(configuration)

    assert printer.device_type is PrinterType.DEC_AND_IBM
    assert printer.state.language is PrinterLanguage.DEC_PPL
    assert printer.configuration_history == [configuration]


def test_board_routes_raw_controller_data_to_the_virtual_printer_engine():
    board = Board()
    printer = VirtualPrinter(PrinterType.DEC_AND_IBM)
    board.printer.attach(printer)

    board.feed_host_data(b"\x1b[5i\x1b[?41h\x1b[?58h\x1b[4i")

    assert bytes(printer.data) == b"\x1b[?41h\x1b[?58h"
    assert printer.state == VirtualPrinterState(
        PrinterLanguage.IBM_PROPRINTER,
        PrintDirection.UNIDIRECTIONAL,
    )


def test_large_ordinary_write_takes_the_raw_fast_path():
    printer = VirtualPrinter()
    payload = b"ordinary printer text " * 50_000
    printer.write_bytes(payload)
    assert bytes(printer.data) == payload
    assert printer.state == VirtualPrinterState(
        PrinterLanguage.DEC_PPL,
        PrintDirection.BIDIRECTIONAL,
    )
