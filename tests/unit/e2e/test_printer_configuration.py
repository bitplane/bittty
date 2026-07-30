"""Model-gated VT510 printer configuration and adapter snapshots."""

from bittty import (
    Board,
    MemoryPrinter,
    PrintedDataType,
    PrinterConfiguration,
    PrinterFlowControl,
    PrinterParity,
    PrinterPortSelection,
    PrinterStatus,
    PrinterType,
    ProPrinterCodePage,
)
from bittty.model import VT100, VT220, VT510, XTERM
from bittty.parser import Parser


class RecordingHost:
    def __init__(self):
        self.data = []

    def write(self, data):
        self.data.append(data)

    def write_bytes(self, data):
        self.data.append(data)

    def flush(self):
        pass


def test_configuration_defaults_and_full_snapshot_on_attach():
    board = Board(model=VT510)
    printer = MemoryPrinter()

    board.printer.attach(printer)

    assert board.printer.configuration == PrinterConfiguration()
    assert printer.configuration_history == [PrinterConfiguration()]


def test_all_vt510_setters_update_one_typed_snapshot_each():
    board = Board(model=VT510)
    printer = MemoryPrinter()
    board.printer.attach(printer)
    parser = Parser(board)

    sequences = (
        "\x1b[3$s",
        "\x1b[4)p",
        "\x1b[850*p",
        "\x1b[2;1*u",
        "\x1b[3;7*r",
        "\x1b[2;3;4;2*s",
        "\x1b[2;2;6;2+w",
    )
    for sequence in sequences:
        before = len(printer.configuration_history)
        parser.feed(sequence)
        assert len(printer.configuration_history) == before + 1

    assert board.printer.configuration == PrinterConfiguration(
        port=PrinterPortSelection.COMM1,
        printer_type=PrinterType.DEC_AND_IBM,
        printed_data_type=PrintedDataType.ALL,
        code_page=ProPrinterCodePage.MULTILINGUAL,
        baud_rate=19200,
        data_bits=7,
        parity=PrinterParity.MARK,
        stop_bits=2,
        transmit_flow_control=PrinterFlowControl.NONE,
        receive_flow_control=PrinterFlowControl.NONE,
    )


def test_invalid_and_non_printer_selectors_are_ignored():
    board = Board(model=VT510)
    printer = MemoryPrinter()
    board.printer.attach(printer)
    parser = Parser(board)

    parser.feed("\x1b[99$s\x1b[999*p\x1b[2;2*u\x1b[1;6*r\x1b[1;3;4;1*s\x1b[1;2;3;2+w")

    assert board.printer.configuration == PrinterConfiguration()
    assert printer.configuration_history == [PrinterConfiguration()]


def test_default_selectors_and_c1_csi_restore_defaults():
    board = Board(model=VT510)
    parser = Parser(board)
    parser.feed("\x1b[2$s\x1b[3)p\x1b[866*p\x1b[3;6*r\x1b[2;3;4;1*s\x1b[2;2;3;2+w")

    parser.feed("\x1b[$s\x1b[)p\x9b437*p\x1b[3;*r\x1b[2;3;1;*s\x1b[2;;;+w")

    assert board.printer.configuration == PrinterConfiguration()


def test_model_gating_wins_over_an_attached_printer():
    for model in (VT100,):
        board = Board(model=model)
        printer = MemoryPrinter()
        host = RecordingHost()
        board.printer.attach(printer)
        board.host.attach(host)
        Parser(board).feed("\x1b[5iprint\x1b[3$s\x1b[?15n")
        assert bytes(printer.data) == b""
        assert board.capture_text() == "print"
        assert printer.configuration_history == []
        assert host.data == []

    # Basic Media Copy models print but do not expose VT510 configuration.
    for model in (VT220, XTERM):
        board = Board(model=model)
        printer = MemoryPrinter()
        board.printer.attach(printer)
        Parser(board).feed("\x1b[2$s\x1b[5iprint\x1b[4i")
        assert board.printer.configuration == PrinterConfiguration()
        assert printer.configuration_history == []
        assert bytes(printer.data) == b"print"


def test_detached_status_is_model_correct_and_attachment_does_not_change_da1():
    cases = ((VT220, "\x1b[?13n"), (VT510, "\x1b[?13n"), (XTERM, "\x1b[?11n"))
    for model, expected in cases:
        board = Board(model=model)
        host = RecordingHost()
        board.host.attach(host)
        parser = Parser(board)
        parser.feed("\x1b[?15n")
        assert host.data == [expected]
        board.printer.attach(MemoryPrinter())
        parser.feed("\x1b[c")
        assert host.data[-1] == model.da1_response


def test_configuration_failure_marks_not_ready_and_later_success_recovers():
    class FailingPrinter(MemoryPrinter):
        fail = True

        def configure(self, configuration):
            if self.fail:
                raise OSError("no printer")
            super().configure(configuration)

    board = Board(model=VT510)
    printer = FailingPrinter()
    board.printer.attach(printer)
    assert board.printer.status is PrinterStatus.NOT_READY

    printer.fail = False
    Parser(board).feed("\x1b[2$s")
    assert board.printer.status is PrinterStatus.READY
    assert printer.configuration is not None


def test_decnulm_and_flow_control_filter_both_directions_and_reset():
    board = Board(model=VT510)
    printer = MemoryPrinter()
    host = RecordingHost()
    board.printer.attach(printer)
    board.host.attach(host)
    parser = Parser(board)

    parser.feed("\x1b[6i")
    board.printer.receive_bytes(b"A\x00\x11\x13B")
    assert host.data == [b"A\x00B"]

    parser.feed("\x1b[2;3;4;1*s\x1b[?102h")
    board.printer.receive_bytes(b"C\x00\x11\x13D")
    assert host.data[-1] == b"C\x11\x13D"

    board.feed_host_data(b"\x1b[5iE\x00\x11\x13F\x1b[4i")
    assert bytes(printer.data) == b"E\x11\x13F"

    parser.feed("\x1b[?102$p\x1b[!p\x1b[?102$p")
    assert host.data[-2:] == ["\x1b[?102;1$y", "\x1b[?102;2$y"]
    assert board.printer.configuration.ignore_null is False


def test_resets_preserve_physical_configuration_but_clear_decnulm():
    for reset in ("\x1b[!p", "\x1bc"):
        board = Board(model=VT510)
        parser = Parser(board)
        parser.feed("\x1b[3$s\x1b[2;1*u\x1b[3;7*r\x1b[?102h")
        parser.feed(reset)

        assert board.printer.configuration == PrinterConfiguration(
            port=PrinterPortSelection.COMM1,
            printer_type=PrinterType.DEC_AND_IBM,
            baud_rate=19200,
        )


def test_decnulm_is_unrecognised_outside_configurable_models():
    board = Board(model=VT220)
    host = RecordingHost()
    board.host.attach(host)
    Parser(board).feed("\x1b[?102h\x1b[?102$p")
    assert host.data == ["\x1b[?102;0$y"]
