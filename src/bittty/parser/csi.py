"""CSI (Control Sequence Introducer) sequence handlers.

Handles all CSI sequences that start with ESC[. These include cursor movement,
screen clearing, styling, and terminal mode operations.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, List, Optional, Callable, Dict

if TYPE_CHECKING:
    from ..terminal import Terminal


logger = logging.getLogger(__name__)


def handle_cup(terminal: Terminal, params: List[Optional[int]], intermediates: List[str]) -> None:
    """CUP - Cursor Position (H or f)."""
    row = (params[0] if params and params[0] is not None else 1) - 1  # Convert to 0-based
    col = (params[1] if len(params) > 1 and params[1] is not None else 1) - 1  # Convert to 0-based
    terminal.set_cursor(col, row)


def handle_cuu(terminal: Terminal, params: List[Optional[int]], intermediates: List[str]) -> None:
    """CUU - Cursor Up (A)."""
    count = params[0] if params and params[0] is not None else 1
    terminal.cursor_y = max(0, terminal.cursor_y - count)


def handle_cud(terminal: Terminal, params: List[Optional[int]], intermediates: List[str]) -> None:
    """CUD - Cursor Down (B)."""
    count = params[0] if params and params[0] is not None else 1
    terminal.cursor_y = min(terminal.height - 1, terminal.cursor_y + count)


def handle_cuf(terminal: Terminal, params: List[Optional[int]], intermediates: List[str]) -> None:
    """CUF - Cursor Forward (C)."""
    count = params[0] if params and params[0] is not None else 1
    terminal.cursor_x = min(terminal.width - 1, terminal.cursor_x + count)


def handle_cub(terminal: Terminal, params: List[Optional[int]], intermediates: List[str]) -> None:
    """CUB - Cursor Backward (D)."""
    count = params[0] if params and params[0] is not None else 1
    terminal.cursor_x = max(0, terminal.cursor_x - count)


def handle_cha(terminal: Terminal, params: List[Optional[int]], intermediates: List[str]) -> None:
    """CHA - Cursor Horizontal Absolute (G)."""
    col = (params[0] if params and params[0] is not None else 1) - 1  # Convert to 0-based
    terminal.set_cursor(col, None)


def handle_vpa(terminal: Terminal, params: List[Optional[int]], intermediates: List[str]) -> None:
    """VPA - Vertical Position Absolute (d)."""
    row = (params[0] if params and params[0] is not None else 1) - 1  # Convert to 0-based
    terminal.set_cursor(None, row)


def handle_ed(terminal: Terminal, params: List[Optional[int]], intermediates: List[str]) -> None:
    """ED - Erase in Display (J)."""
    mode = params[0] if params and params[0] is not None else 0
    terminal.clear_screen(mode)


def handle_el(terminal: Terminal, params: List[Optional[int]], intermediates: List[str]) -> None:
    """EL - Erase in Line (K)."""
    mode = params[0] if params and params[0] is not None else 0
    terminal.clear_line(mode)


def handle_il(terminal: Terminal, params: List[Optional[int]], intermediates: List[str]) -> None:
    """IL - Insert Lines (L)."""
    count = params[0] if params and params[0] is not None else 1
    terminal.insert_lines(count)


def handle_dl(terminal: Terminal, params: List[Optional[int]], intermediates: List[str]) -> None:
    """DL - Delete Lines (M)."""
    count = params[0] if params and params[0] is not None else 1
    terminal.delete_lines(count)


def handle_ich(terminal: Terminal, params: List[Optional[int]], intermediates: List[str]) -> None:
    """ICH - Insert Characters (@)."""
    count = params[0] if params and params[0] is not None else 1
    # Use current ANSI sequence for inserted spaces
    terminal.insert_characters(count, terminal.current_ansi_code)


def handle_dch(terminal: Terminal, params: List[Optional[int]], intermediates: List[str]) -> None:
    """DCH - Delete Characters (P)."""
    count = params[0] if params and params[0] is not None else 1
    terminal.delete_characters(count)


def handle_su(terminal: Terminal, params: List[Optional[int]], intermediates: List[str]) -> None:
    """SU - Scroll Up (S)."""
    count = params[0] if params and params[0] is not None else 1
    terminal.scroll(count)


def handle_sd(terminal: Terminal, params: List[Optional[int]], intermediates: List[str]) -> None:
    """SD - Scroll Down (T)."""
    count = params[0] if params and params[0] is not None else 1
    terminal.scroll(-count)


def handle_decstbm(terminal: Terminal, params: List[Optional[int]], intermediates: List[str]) -> None:
    """DECSTBM - Set Scroll Region (r)."""
    top = (params[0] if params and params[0] is not None else 1) - 1  # Convert to 0-based
    bottom = (params[1] if len(params) > 1 and params[1] is not None else terminal.height) - 1  # Convert to 0-based
    terminal.set_scroll_region(top, bottom)


def handle_rep(terminal: Terminal, params: List[Optional[int]], intermediates: List[str]) -> None:
    """REP - Repeat (b)."""
    count = params[0] if params and params[0] is not None else 1
    terminal.repeat_last_character(count)


def handle_sgr(terminal: Terminal, params: List[Optional[int]], intermediates: List[str]) -> None:
    """SGR - Select Graphic Rendition (m)."""
    # Check for malformed sequences: ESC[>...m (device attributes syntax with SGR ending)
    if ">" in intermediates:
        # This is a malformed sequence - device attributes should end with 'c', not 'm'
        # Likely from vim's terminal emulation leaking sequences
        params_str = ";".join(str(p) for p in params if p is not None)
        logger.debug(f"Ignoring malformed device attributes sequence: ESC[{';'.join(intermediates)}{params_str}m")
        return

    dispatch_sgr(terminal, params)


def handle_sm(terminal: Terminal, params: List[Optional[int]], intermediates: List[str]) -> None:
    """SM - Set Mode (h)."""
    if "?" in intermediates:
        dispatch_sm_rm_private(terminal, params, True)
    else:
        dispatch_sm_rm(terminal, params, True)


def handle_rm(terminal: Terminal, params: List[Optional[int]], intermediates: List[str]) -> None:
    """RM - Reset Mode (l)."""
    if "?" in intermediates:
        dispatch_sm_rm_private(terminal, params, False)
    else:
        dispatch_sm_rm(terminal, params, False)


def handle_decrqm(terminal: Terminal, params: List[Optional[int]], intermediates: List[str]) -> None:
    """DECRQM - Request Mode Status (p with $ intermediate)."""
    mode = params[0] if params and params[0] is not None else 0
    private = "?" in intermediates

    if private:
        # Private mode query
        status = get_private_mode_status(terminal, mode)
    else:
        # ANSI mode query
        status = get_ansi_mode_status(terminal, mode)

    # Response format: ESC[?{mode};{status}$y for private modes
    # Response format: ESC[{mode};{status}$y for ANSI modes
    prefix = "?" if private else ""
    terminal.respond(f"\033[{prefix}{mode};{status}$y")


def handle_window_ops(terminal: Terminal, params: List[Optional[int]], intermediates: List[str]) -> None:
    """Window operations (t) - consume but don't implement."""
    pass


def handle_pm(terminal: Terminal, params: List[Optional[int]], intermediates: List[str]) -> None:
    """PM - Privacy Message (^) - consume but don't implement."""
    pass


def handle_decsc_alt(terminal: Terminal, params: List[Optional[int]], intermediates: List[str]) -> None:
    """DECSC - Save Cursor alternative (s)."""
    terminal.save_cursor()


def handle_decrc_alt(terminal: Terminal, params: List[Optional[int]], intermediates: List[str]) -> None:
    """DECRC - Restore Cursor alternative (u)."""
    terminal.restore_cursor()


def handle_ech(terminal: Terminal, params: List[Optional[int]], intermediates: List[str]) -> None:
    """ECH - Erase Character (X)."""
    count = params[0] if params and params[0] is not None else 1
    # Erase n characters at cursor position
    for _ in range(count):
        terminal.current_buffer.set(terminal.cursor_x, terminal.cursor_y, " ", terminal.current_ansi_code)
        if terminal.cursor_x < terminal.width - 1:
            terminal.cursor_x += 1


def handle_dsr_cpr(terminal: Terminal, params: List[Optional[int]], intermediates: List[str]) -> None:
    """DSR/CPR - Device Status Report / Cursor Position Report (n)."""
    param = params[0] if params and params[0] is not None else 0
    if param == 6:  # CPR - Cursor Position Report
        row = terminal.cursor_y + 1  # Convert to 1-based
        col = terminal.cursor_x + 1  # Convert to 1-based
        terminal.respond(f"\033[{row};{col}R")
    elif param == 5:  # DSR - Device Status Report
        # Report OK status
        terminal.respond("\033[0n")


def handle_da(terminal: Terminal, params: List[Optional[int]], intermediates: List[str]) -> None:
    """DA - Device Attributes (c)."""
    handle_device_attributes(terminal, params, intermediates)


# CSI dispatch table - maps final characters to handler functions
CSI_DISPATCH_TABLE: Dict[str, Callable[[Terminal, List[Optional[int]], List[str]], None]] = {
    # Cursor movement
    "H": handle_cup,  # Cursor Position
    "f": handle_cup,  # Cursor Position (alternative)
    "A": handle_cuu,  # Cursor Up
    "B": handle_cud,  # Cursor Down
    "C": handle_cuf,  # Cursor Forward
    "D": handle_cub,  # Cursor Backward
    "G": handle_cha,  # Cursor Horizontal Absolute
    "d": handle_vpa,  # Vertical Position Absolute
    # Screen/line operations
    "J": handle_ed,  # Erase in Display
    "K": handle_el,  # Erase in Line
    "L": handle_il,  # Insert Lines
    "M": handle_dl,  # Delete Lines
    "@": handle_ich,  # Insert Characters
    "P": handle_dch,  # Delete Characters
    "X": handle_ech,  # Erase Character
    # Scrolling
    "S": handle_su,  # Scroll Up
    "T": handle_sd,  # Scroll Down
    "r": handle_decstbm,  # Set Scroll Region
    # Styling and modes
    "m": handle_sgr,  # Select Graphic Rendition
    "h": handle_sm,  # Set Mode
    "l": handle_rm,  # Reset Mode
    # Cursor save/restore
    "s": handle_decsc_alt,  # Save Cursor (alternative)
    "u": handle_decrc_alt,  # Restore Cursor (alternative)
    # Misc
    "b": handle_rep,  # Repeat
    "n": handle_dsr_cpr,  # Device Status Report / Cursor Position Report
    "c": handle_da,  # Device Attributes
    "t": handle_window_ops,  # Window operations
    "^": handle_pm,  # Privacy Message
}


def dispatch_csi(terminal: Terminal, final_char: str, params: List[Optional[int]], intermediates: List[str]) -> None:
    """Main CSI dispatcher using O(1) lookup table."""
    # Handle special cases with intermediates first
    if "$" in intermediates and final_char == "p":
        handle_decrqm(terminal, params, intermediates)
        return

    # Use dispatch table for standard cases
    handler = CSI_DISPATCH_TABLE.get(final_char)
    if handler:
        handler(terminal, params, intermediates)
    else:
        # Unknown CSI sequence, log it
        params_str = ";".join(str(p) for p in params if p is not None) if params else "<no params>"
        intermediates_str = "".join(intermediates)
        logger.debug(f"Unknown CSI sequence: ESC[{intermediates_str}{params_str}{final_char}")


def dispatch_sgr(terminal: Terminal, params: List[Optional[int]]) -> None:
    """Handle SGR (Select Graphic Rendition) sequences."""
    from ..style import merge_ansi_styles

    # Use an empty list if params is None
    if not params:
        params = [0]  # Reset if no parameters

    # Build the ANSI sequence from the parameters (same as original parser)
    params_str = ";".join(str(p) if p is not None else "" for p in params)
    new_ansi_sequence = f"\033[{params_str}m"

    # Merge with existing style
    terminal.current_ansi_code = merge_ansi_styles(terminal.current_ansi_code, new_ansi_sequence)


def dispatch_sm_rm(terminal: Terminal, params: List[Optional[int]], set_mode: bool) -> None:
    """Handle SM/RM (Set/Reset Mode) for standard modes."""
    for param in params:
        if param is None:
            continue

        if param == 4:  # IRM - Insert/Replace Mode
            terminal.insert_mode = set_mode
        elif param == 7:  # AWM - Auto Wrap Mode
            terminal.auto_wrap = set_mode
        elif param == 12:  # SRM - Send/Receive Mode
            # SRM works backwards: SET = disable echo, RESET = enable echo
            terminal.local_echo = not set_mode
        elif param == 20:  # LNM - Line Feed/New Line Mode
            terminal.linefeed_newline_mode = set_mode
        elif param == 25:  # DECTCEM - Text Cursor Enable Mode (standard mode)
            terminal.cursor_visible = set_mode
        # Add more standard modes as needed


def dispatch_sm_rm_private(terminal: Terminal, params: List[Optional[int]], set_mode: bool) -> None:
    """Handle SM/RM (Set/Reset Mode) for private modes (prefixed with ?)."""
    for param in params:
        if param is None:
            continue

        if param == 1:  # DECCKM - Cursor Keys Mode
            terminal.cursor_application_mode = set_mode
        elif param == 2:  # DECANM - ANSI/VT52 Mode
            # Switch between ANSI and VT52 mode
            terminal.ansi_mode = set_mode
        elif param == 3:  # DECCOLM - 132 Column Mode
            # Switch between 80/132 column mode
            if set_mode:
                terminal.resize(132, terminal.height)
            else:
                terminal.resize(80, terminal.height)
        elif param == 4:  # DECSCLM - Scrolling Mode
            terminal.scroll_mode = set_mode
        elif param == 5:  # DECSCNM - Screen Mode
            terminal.reverse_screen = set_mode
        elif param == 6:  # DECOM - Origin Mode
            terminal.origin_mode = set_mode
        elif param == 7:  # DECAWM - Auto Wrap Mode
            terminal.auto_wrap = set_mode
        elif param == 8:  # DECARM - Auto Repeat Mode
            terminal.auto_repeat = set_mode
        elif param == 9:  # X10 Mouse Tracking
            if set_mode:
                terminal.mouse_mode = "x10"
            else:
                terminal.mouse_mode = None
        elif param == 12:  # Cursor Blinking
            terminal.cursor_blinking = set_mode
        elif param == 20:  # DECNLM - Line Feed/New Line Mode
            terminal.linefeed_newline_mode = set_mode
        elif param == 25:  # DECTCEM - Text Cursor Enable Mode
            terminal.cursor_visible = set_mode
        elif param == 47:  # Alternate Screen Buffer
            if set_mode:
                terminal.alternate_screen_on()
            else:
                terminal.alternate_screen_off()
        elif param == 66:  # DECNKM - Numeric Keypad Mode
            # When DECNKM is set (h), keypad is in application mode (numeric_keypad = False)
            # When DECNKM is reset (l), keypad is in numeric mode (numeric_keypad = True)
            terminal.numeric_keypad = not set_mode
        elif param == 67:  # DECBKM - Backarrow Key Mode
            terminal.backarrow_key_sends_bs = set_mode
        elif param == 1000:  # VT200 Mouse Tracking
            if set_mode:
                terminal.mouse_mode = "vt200"
            else:
                terminal.mouse_mode = None
        elif param == 1002:  # Button Event Mouse Tracking
            if set_mode:
                terminal.mouse_mode = "button"
            else:
                terminal.mouse_mode = None
        elif param == 1003:  # Any Event Mouse Tracking
            if set_mode:
                terminal.mouse_mode = "any"
            else:
                terminal.mouse_mode = None
        elif param == 1006:  # SGR Mouse Mode
            terminal.sgr_mouse = set_mode
        elif param == 1015:  # URXVT Mouse Mode
            terminal.urxvt_mouse = set_mode
        elif param == 1047:  # Alternate Screen Buffer (alternative)
            if set_mode:
                terminal.alternate_screen_on()
            else:
                terminal.alternate_screen_off()
        elif param == 1048:  # Save/Restore Cursor
            if set_mode:
                terminal.save_cursor()
            else:
                terminal.restore_cursor()
        elif param == 1049:  # Alternate Screen + Save/Restore Cursor
            if set_mode:
                terminal.save_cursor()
                terminal.alternate_screen_on()
            else:
                terminal.alternate_screen_off()
                terminal.restore_cursor()
        elif param == 2004:  # Bracketed Paste Mode
            terminal.bracketed_paste = set_mode
        elif param == 69:  # DECKBUM - Keyboard Usage Mode
            terminal.keyboard_usage_mode = set_mode
        elif param == 2028:  # DECARSM - Auto Resize Mode
            terminal.auto_resize_mode = set_mode


def get_private_mode_status(terminal: Terminal, mode: int) -> int:
    """Get the status of a private mode for DECRQM response."""
    # Status codes:
    # 0 = not recognized
    # 1 = set
    # 2 = reset
    # 3 = permanently set
    # 4 = permanently reset

    if mode == 1:  # DECCKM
        return 1 if terminal.cursor_application_mode else 2
    elif mode == 2:  # DECANM
        return 1 if terminal.ansi_mode else 2
    elif mode == 3:  # DECCOLM
        return 1 if terminal.width == 132 else 2
    elif mode == 6:  # DECOM
        return 1 if terminal.origin_mode else 2
    elif mode == 7:  # DECAWM
        return 1 if terminal.auto_wrap else 2
    elif mode == 25:  # DECTCEM
        return 1 if terminal.cursor_visible else 2
    elif mode == 47 or mode == 1047:  # Alternate screen
        return 1 if terminal.in_alt_screen else 2
    elif mode == 1049:  # Alternate screen + cursor
        return 1 if terminal.in_alt_screen else 2
    elif mode == 69:  # DECKBUM
        return 1 if terminal.keyboard_usage_mode else 2
    elif mode == 2028:  # DECARSM
        return 1 if terminal.auto_resize_mode else 2
    else:
        return 0  # Not recognized


def get_ansi_mode_status(terminal: Terminal, mode: int) -> int:
    """Get the status of an ANSI mode for DECRQM response."""
    if mode == 4:  # IRM
        return 1 if terminal.insert_mode else 2
    elif mode == 7:  # AWM
        return 1 if terminal.auto_wrap else 2
    elif mode == 12:  # SRM
        # SRM works backwards: mode set = echo disabled
        return 1 if not terminal.local_echo else 2
    elif mode == 20:  # LNM
        return 1 if terminal.linefeed_newline_mode else 2
    elif mode == 25:  # DECTCEM
        return 1 if terminal.cursor_visible else 2
    else:
        return 0  # Not recognized


def handle_device_attributes(terminal: Terminal, params: List[Optional[int]], intermediates: List[str]) -> None:
    """Handle Device Attributes (DA) request."""
    param = params[0] if params and params[0] is not None else 0

    if not intermediates:  # Primary DA
        if param == 0:
            # VT220 identity with extensive capabilities
            # 62 = VT220, 1 = 132-columns, 6 = selective erase, 8 = user defined keys
            # 9 = national replacement character sets, 15 = technical character set
            # 18 = windowing capability, 21 = horizontal scrolling, 22 = color, 23 = Greek
            terminal.respond("\033[?62;1;6;8;9;15;18;21;22;23c")
    elif ">" in intermediates:  # Secondary DA
        # Report as VT220 with version number
        terminal.respond("\033[>1;10;0c")
    elif "=" in intermediates:  # Tertiary DA
        # Not implemented
        pass
