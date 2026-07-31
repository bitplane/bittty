import asyncio
from dataclasses import replace

import pytest

from bittty import (
    Board,
    PrintDirection,
    PrinterConfiguration,
    PrinterLanguage,
    PrinterType,
    VirtualPrinter,
    VirtualPrinterState,
)


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
        printer.write_bytes(b"\x1b[?27;29;40;41h" + reset)
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


def test_dec_modes_survive_protocol_switching_and_ibm_ignores_dec_mode_commands():
    printer = VirtualPrinter(PrinterType.DEC_AND_IBM)
    printer.write_bytes(b"\x1b[?27;29;40h\x1b%=")
    printer.write_bytes(b"\x1b[?27;29;40l")
    assert printer.state == VirtualPrinterState(
        PrinterLanguage.IBM_PROPRINTER,
        PrintDirection.BIDIRECTIONAL,
        proportional_spacing=True,
        pitch_from_font=True,
        carriage_return_new_line=True,
    )

    printer.write_bytes(b"\x1b%@")
    assert printer.state == VirtualPrinterState(
        PrinterLanguage.DEC_PPL,
        PrintDirection.BIDIRECTIONAL,
        proportional_spacing=True,
        pitch_from_font=True,
        carriage_return_new_line=True,
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
