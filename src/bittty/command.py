"""Command system for terminal operations.

Commands are lightweight messages that represent terminal control sequences.
They allow devices to communicate and handle terminal operations in a modular way.
"""

from __future__ import annotations

from collections import namedtuple
from typing import Any

Command = namedtuple("Command", ["name", "type", "args", "terminator"])

# C0 control codes mapping
C0_CODES = {
    "C0_NUL": "\x00",
    "C0_SOH": "\x01",
    "C0_STX": "\x02",
    "C0_ETX": "\x03",
    "C0_EOT": "\x04",
    "C0_ENQ": "\x05",
    "C0_ACK": "\x06",
    "C0_BEL": "\x07",
    "C0_BS": "\x08",
    "C0_HT": "\x09",
    "C0_LF": "\x0a",
    "C0_VT": "\x0b",
    "C0_FF": "\x0c",
    "C0_CR": "\x0d",
    "C0_SO": "\x0e",
    "C0_SI": "\x0f",
    "C0_DLE": "\x10",
    "C0_DC1": "\x11",
    "C0_DC2": "\x12",
    "C0_DC3": "\x13",
    "C0_DC4": "\x14",
    "C0_NAK": "\x15",
    "C0_SYN": "\x16",
    "C0_ETB": "\x17",
    "C0_CAN": "\x18",
    "C0_EM": "\x19",
    "C0_SUB": "\x1a",
    "C0_ESC": "\x1b",
    "C0_FS": "\x1c",
    "C0_GS": "\x1d",
    "C0_RS": "\x1e",
    "C0_US": "\x1f",
    "C0_DEL": "\x7f",
}


def command_to_escape(command: Command) -> str:
    """Convert a Command back to its escape sequence representation.

    This is useful for debugging, logging, and recording terminal sessions.

    Args:
        command: The Command to convert

    Returns:
        The escape sequence string that would generate this command

    Examples:
        >>> cmd = Command("CURSOR_POSITION", "CSI", ("10", "20"), "H")
        >>> command_to_escape(cmd)
        '\\x1b[10;20H'

        >>> cmd = Command("SET_GRAPHICS", "CSI", ("1", "31"), "m")
        >>> command_to_escape(cmd)
        '\\x1b[1;31m'

        >>> cmd = Command("CARRIAGE_RETURN", "C0", (), None)
        >>> command_to_escape(cmd)
        '\\r'
    """
    if command.type == "C0":
        return C0_CODES.get(command.name, "")
    elif command.type == "CSI":
        params = ";".join(str(arg) for arg in command.args) if command.args else ""
        return f'\x1b[{params}{command.terminator or ""}'
    elif command.type == "OSC":
        params = ";".join(str(arg) for arg in command.args) if command.args else ""
        return f'\x1b]{params}{command.terminator or ""}'
    elif command.type == "ESC":
        intermediate = "".join(str(arg) for arg in command.args) if command.args else ""
        return f'\x1b{intermediate}{command.terminator or ""}'
    elif command.type == "DCS":
        params = ";".join(str(arg) for arg in command.args) if command.args else ""
        return f'\x1bP{params}{command.terminator or ""}'
    elif command.type == "TEXT":
        return command.args[0] if command.args else ""
    elif command.type == "INTERNAL":
        # Internal commands don't have escape sequence representations
        return f"<INTERNAL:{command.name}>"
    else:
        return f"<UNKNOWN:{command}>"


def create_c0_command(name: str) -> Command:
    """Create a C0 control command.

    Args:
        name: The C0 control name (e.g., 'C0_CR', 'C0_LF')

    Returns:
        A Command representing the C0 control
    """
    return Command(name, "C0", (), None)


def create_csi_command(name: str, args: tuple[Any, ...], terminator: str) -> Command:
    """Create a CSI (Control Sequence Introducer) command.

    Args:
        name: The command name (e.g., 'CSI_CUP', 'CSI_SGR')
        args: The parameters for the command
        terminator: The final character of the CSI sequence

    Returns:
        A Command representing the CSI sequence
    """
    return Command(name, "CSI", args, terminator)


def create_osc_command(name: str, args: tuple[Any, ...], terminator: str) -> Command:
    """Create an OSC (Operating System Command) command.

    Args:
        name: The command name (e.g., 'OSC_SET_TITLE')
        args: The parameters for the command
        terminator: The terminator (usually BEL or ST)

    Returns:
        A Command representing the OSC sequence
    """
    return Command(name, "OSC", args, terminator)


def create_text_command(text: str) -> Command:
    """Create a command for printable text.

    Args:
        text: The text to print

    Returns:
        A Command representing printable text
    """
    return Command("TEXT", "TEXT", (text,), None)


def create_internal_command(name: str, *args: Any) -> Command:
    """Create an internal command for device communication.

    Args:
        name: The internal command name
        args: Arguments for the command

    Returns:
        A Command for internal device communication
    """
    return Command(name, "INTERNAL", args, None)
