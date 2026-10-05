"""The hardcopy terminal: a keyboard send/receive printer on the host line, the LA120 DECwriter III.

Its video is paper. The host's output prints; the printer's reports answer the host
("ESC [ c or ESC [ 0 c: LA120 transmits ESC [ ? 2 c", Terminals & Printers Handbook ch. 14);
the keyboard transmits to the host.
"""

import asyncio

from bittty import MemoryConnection
from bittty.peripherals.printer import LA120, HardcopyTerminal, PrinterTextRun


def _printed(terminal):
    return [item.text for item in terminal.printer.current_page.items if isinstance(item, PrinterTextRun)]


def test_the_host_prints_on_paper():
    terminal = HardcopyTerminal(MemoryConnection())
    terminal.receive(b"hello\r\nworld")
    assert _printed(terminal) == ["hello", "world"]


def test_it_identifies_itself_as_an_la120():
    wire = MemoryConnection()
    terminal = HardcopyTerminal(wire)
    terminal.receive(b"\x1b[c")
    assert wire.text == "\x1b[?2c"
    assert terminal.printer.profile is LA120


def test_the_la120_takes_fanfold_paper_14_7_8_inches_wide():
    terminal = HardcopyTerminal(MemoryConnection())
    assert terminal.printer.page_geometry.width == 21_600 * 119 // 8


def test_the_keyboard_transmits_to_the_host():
    wire = MemoryConnection()
    terminal = HardcopyTerminal(wire)
    terminal.type("ls\r")
    assert wire.text == "ls\r" and _printed(terminal) == []


def test_local_echo_prints_what_is_typed():
    wire = MemoryConnection()
    terminal = HardcopyTerminal(wire, local_echo=True)
    terminal.type("ls")
    assert wire.text == "ls" and _printed(terminal) == ["ls"]


def test_the_host_line_pumps_onto_paper():
    wire = MemoryConnection(receive=[b"one\r\n", b"two"])
    terminal = HardcopyTerminal(wire)

    async def run():
        terminal.connect()
        await asyncio.sleep(0.05)
        terminal.disconnect()

    asyncio.run(run())
    assert _printed(terminal) == ["one", "two"]
