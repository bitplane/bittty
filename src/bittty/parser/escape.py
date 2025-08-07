"""Simple escape sequence handlers.

Handles simple escape sequences that start with ESC followed by a single character
(not CSI, OSC, or other multi-character sequences). These include cursor operations,
character set designations, and terminal mode changes.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Dict, Callable

if TYPE_CHECKING:
    from ..terminal import Terminal

from .. import constants

logger = logging.getLogger(__name__)


def handle_ris(terminal: Terminal, data: str) -> None:
    """RIS - Reset to Initial State (ESC c)."""
    reset_terminal(terminal)


def handle_ind(terminal: Terminal, data: str) -> None:
    """IND - Index (ESC D) - Line feed."""
    terminal.line_feed()


def handle_ri(terminal: Terminal, data: str) -> None:
    """RI - Reverse Index (ESC M) - Reverse line feed."""
    if terminal.cursor_y <= terminal.scroll_top:
        terminal.scroll(-1)
    else:
        terminal.cursor_y -= 1


def handle_decsc(terminal: Terminal, data: str) -> None:
    """DECSC - Save Cursor (ESC 7)."""
    terminal.save_cursor()


def handle_decrc(terminal: Terminal, data: str) -> None:
    """DECRC - Restore Cursor (ESC 8)."""
    terminal.restore_cursor()


def handle_deckpam(terminal: Terminal, data: str) -> None:
    """DECKPAM - Application Keypad Mode (ESC =)."""
    terminal.set_mode(constants.DECKPAM_APPLICATION_KEYPAD, True)
    terminal.numeric_keypad = False
    # Note: Parser will need to call update_tokenizer() after this


def handle_deckpnm(terminal: Terminal, data: str) -> None:
    """DECKPNM - Numeric Keypad Mode (ESC >)."""
    terminal.set_mode(constants.DECKPAM_APPLICATION_KEYPAD, False)
    terminal.numeric_keypad = True
    # Note: Parser will need to call update_tokenizer() after this


def handle_st(terminal: Terminal, data: str) -> None:
    """ST - String Terminator (ESC \\) - Already handled by sequence patterns."""
    pass


def handle_ss2(terminal: Terminal, data: str) -> None:
    """SS2 - Single Shift 2 (ESC N)."""
    terminal.single_shift_2()


def handle_ss3(terminal: Terminal, data: str) -> None:
    """SS3 - Single Shift 3 (ESC O)."""
    terminal.single_shift_3()


def handle_nel(terminal: Terminal, data: str) -> None:
    """NEL - Next Line (ESC E)."""
    terminal.cursor_x = 0
    terminal.line_feed()


def handle_hts(terminal: Terminal, data: str) -> None:
    """HTS - Horizontal Tab Set (ESC H)."""
    terminal.set_tab_stop(terminal.cursor_x)


def handle_ri_alt(terminal: Terminal, data: str) -> None:
    """Alternative RI implementation if needed."""
    handle_ri(terminal, data)


# Simple escape dispatch table - maps single characters to handler functions
ESCAPE_DISPATCH_TABLE: Dict[str, Callable[[Terminal, str], None]] = {
    "c": handle_ris,  # Reset to Initial State
    "D": handle_ind,  # Index
    "M": handle_ri,  # Reverse Index
    "7": handle_decsc,  # Save Cursor
    "8": handle_decrc,  # Restore Cursor
    "=": handle_deckpam,  # Application Keypad Mode
    ">": handle_deckpnm,  # Numeric Keypad Mode
    "\\": handle_st,  # String Terminator
    "N": handle_ss2,  # Single Shift 2
    "O": handle_ss3,  # Single Shift 3
    "E": handle_nel,  # Next Line
    "H": handle_hts,  # Horizontal Tab Set
}


def dispatch_escape(terminal: Terminal, data: str) -> bool:
    """Main escape sequence dispatcher using O(1) lookup table.

    Returns True if sequence was handled, False if it should be handled elsewhere
    (like charset designation sequences).
    """
    if len(data) < 2:
        return False

    seq_char = data[1]  # Character after ESC

    # Use dispatch table for O(1) lookup
    handler = ESCAPE_DISPATCH_TABLE.get(seq_char)
    if handler:
        handler(terminal, data)
        return True

    return False  # Not handled, might be charset or other sequence


def handle_charset_escape(terminal: Terminal, data: str) -> bool:
    """Handle charset designation escape sequences like ESC(B.

    Returns True if sequence was handled, False otherwise.
    """
    if len(data) < 3:
        return False

    designator = data[1]  # (, ), *, or +
    charset = data[2]  # A, B, 0, etc.

    if designator == "(":
        terminal.set_g0_charset(charset)
        return True
    elif designator == ")":
        terminal.set_g1_charset(charset)
        return True
    elif designator == "*":
        terminal.set_g2_charset(charset)
        return True
    elif designator == "+":
        terminal.set_g3_charset(charset)
        return True

    return False


def reset_terminal(terminal: Terminal) -> None:
    """Reset terminal to initial state."""
    terminal.clear_screen(constants.ERASE_ALL)
    terminal.set_cursor(0, 0)
    terminal.current_ansi_code = ""

    # Reset character sets to defaults
    terminal.g0_charset = "B"  # US ASCII
    terminal.g1_charset = "B"
    terminal.g2_charset = "B"
    terminal.g3_charset = "B"
    terminal.current_charset = 0  # G0
    terminal.single_shift = None
