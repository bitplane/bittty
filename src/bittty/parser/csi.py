"""CSI (Control Sequence Introducer) sequence handlers.

Handles all CSI sequences that start with ESC[. These include cursor movement,
screen clearing, styling, and terminal mode operations.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import TYPE_CHECKING, List, Optional
from ..style import merge_ansi_styles

if TYPE_CHECKING:
    from ..terminal import Terminal


logger = logging.getLogger(__name__)


@lru_cache(maxsize=1000)
def parse_csi_params(data):
    """Parse CSI parameters when actually needed.

    Args:
        data: Complete CSI sequence like '\x1b[1;2H' or '\x1b[?25h'

    Returns:
        tuple: (params_list, intermediate_chars, final_char)
    """
    if len(data) < 3 or not data.startswith("\x1b["):
        return [], [], ""

    content = data[2:]
    if not content:
        return [], [], ""

    final_char = content[-1]
    sequence = content[:-1]

    if not sequence:
        return [], [], final_char

    # Validate no control chars
    for char in sequence:
        if ord(char) < 0x20:
            return [], [], ""

    # Extract private markers (? < = >) at start
    private_markers = []
    param_start = 0
    for i, char in enumerate(sequence):
        if char in "?<=>":
            private_markers.append(char)
            param_start = i + 1
        else:
            break

    # Extract intermediates (0x20-0x2F) at end
    intermediates = []
    param_end = len(sequence)
    for i in range(len(sequence) - 1, -1, -1):
        char = sequence[i]
        if 0x20 <= ord(char) <= 0x2F:
            intermediates.insert(0, char)
            param_end = i
        else:
            break

    # Parse parameters
    params = []
    param_part = sequence[param_start:param_end]
    if param_part:
        for part in param_part.split(";"):
            if not part:
                params.append(None)
            else:
                # Handle sub-parameters: take only main part before ':'
                main_part = part.split(":")[0]
                try:
                    params.append(int(main_part))
                except ValueError:
                    params.append(main_part)

    return params, private_markers + intermediates, final_char


def dispatch_csi(terminal, raw_csi_data):
    """BLAZING FAST CSI dispatcher with selective parsing and inlined handlers! 🚀

    Revolutionary approach:
    1. **No redundant parsing**: SGR sequences pass raw to style system
    2. **Selective parsing**: Only parse parameters when actually needed
    3. **Inlined handlers**: Zero function call overhead
    4. **Fast path detection**: Check final char before any work

    Args:
        terminal: Terminal instance
        raw_csi_data: Raw CSI sequence like '\x1b[31m' or '\x1b[1;2H'
    """
    if len(raw_csi_data) < 3:
        return

    final_char = raw_csi_data[-1]

    # ⚡ SGR FAST PATH: Pass raw to style system (eliminates double parsing!)
    if final_char == "m":  # SGR - Select Graphic Rendition
        # Check for malformed sequences: ESC[>...m
        if ">" in raw_csi_data:
            logger.debug(f"Ignoring malformed device attributes sequence: {raw_csi_data}")
            return
        # Direct to style system - no parsing needed!
        terminal.current_ansi_code = merge_ansi_styles(terminal.current_ansi_code, raw_csi_data)
        return

    # ⚡ SIMPLE SEQUENCE FAST PATHS: No parameter parsing needed
    if final_char == "H" and raw_csi_data == "\x1b[H":  # Cursor home
        terminal.set_cursor(0, 0)
        return
    elif final_char == "A" and raw_csi_data == "\x1b[A":  # Cursor up 1
        terminal.cursor_y = max(0, terminal.cursor_y - 1)
        return
    elif final_char == "B" and raw_csi_data == "\x1b[B":  # Cursor down 1
        terminal.cursor_y = min(terminal.height - 1, terminal.cursor_y + 1)
        return
    elif final_char == "C" and raw_csi_data == "\x1b[C":  # Cursor right 1
        terminal.cursor_x = min(terminal.width - 1, terminal.cursor_x + 1)
        return
    elif final_char == "D" and raw_csi_data == "\x1b[D":  # Cursor left 1
        terminal.cursor_x = max(0, terminal.cursor_x - 1)
        return
    elif final_char == "K" and raw_csi_data == "\x1b[K":  # Clear line from cursor
        terminal.clear_line(0)  # ERASE_FROM_CURSOR_TO_END
        return
    elif final_char == "J" and raw_csi_data == "\x1b[2J":  # Clear screen
        terminal.clear_screen(2)  # ERASE_ALL
        return

    # Complex sequences need parameter parsing
    params, intermediates, final_char = parse_csi_params(raw_csi_data)

    # ⚡ INLINED HANDLERS: Direct execution without function calls
    if final_char in ("H", "f"):  # CUP - Cursor Position
        row = (params[0] if params and params[0] is not None else 1) - 1
        col = (params[1] if len(params) > 1 and params[1] is not None else 1) - 1
        terminal.set_cursor(col, row)

    elif final_char == "A":  # CUU - Cursor Up
        count = params[0] if params and params[0] is not None else 1
        terminal.cursor_y = max(0, terminal.cursor_y - count)

    elif final_char == "B":  # CUD - Cursor Down
        count = params[0] if params and params[0] is not None else 1
        terminal.cursor_y = min(terminal.height - 1, terminal.cursor_y + count)

    elif final_char == "C":  # CUF - Cursor Forward
        count = params[0] if params and params[0] is not None else 1
        terminal.cursor_x = min(terminal.width - 1, terminal.cursor_x + count)

    elif final_char == "D":  # CUB - Cursor Backward
        count = params[0] if params and params[0] is not None else 1
        terminal.cursor_x = max(0, terminal.cursor_x - count)

    elif final_char == "G":  # CHA - Cursor Horizontal Absolute
        col = (params[0] if params and params[0] is not None else 1) - 1
        terminal.set_cursor(col, None)

    elif final_char == "d":  # VPA - Vertical Position Absolute
        row = (params[0] if params and params[0] is not None else 1) - 1
        terminal.set_cursor(None, row)

    elif final_char == "J":  # ED - Erase in Display
        mode = params[0] if params and params[0] is not None else 0
        terminal.clear_screen(mode)

    elif final_char == "K":  # EL - Erase in Line
        mode = params[0] if params and params[0] is not None else 0
        terminal.clear_line(mode)

    elif final_char == "L":  # IL - Insert Lines
        count = params[0] if params and params[0] is not None else 1
        terminal.insert_lines(count)

    elif final_char == "M":  # DL - Delete Lines
        count = params[0] if params and params[0] is not None else 1
        terminal.delete_lines(count)

    elif final_char == "@":  # ICH - Insert Characters
        count = params[0] if params and params[0] is not None else 1
        terminal.insert_characters(count, terminal.current_ansi_code)

    elif final_char == "P":  # DCH - Delete Characters
        count = params[0] if params and params[0] is not None else 1
        terminal.delete_characters(count)

    elif final_char == "X":  # ECH - Erase Character
        count = params[0] if params and params[0] is not None else 1
        for _ in range(count):
            terminal.current_buffer.set(terminal.cursor_x, terminal.cursor_y, " ", terminal.current_ansi_code)
            if terminal.cursor_x < terminal.width - 1:
                terminal.cursor_x += 1

    elif final_char == "S":  # SU - Scroll Up
        count = params[0] if params and params[0] is not None else 1
        terminal.scroll(count)

    elif final_char == "T":  # SD - Scroll Down
        count = params[0] if params and params[0] is not None else 1
        terminal.scroll(-count)

    elif final_char == "r":  # DECSTBM - Set Scroll Region
        top = (params[0] if params and params[0] is not None else 1) - 1
        bottom = (params[1] if len(params) > 1 and params[1] is not None else terminal.height) - 1
        terminal.set_scroll_region(top, bottom)

    elif final_char == "s":  # DECSC - Save Cursor (alternative)
        terminal.save_cursor()

    elif final_char == "u":  # DECRC - Restore Cursor (alternative)
        terminal.restore_cursor()

    elif final_char == "b":  # REP - Repeat
        count = params[0] if params and params[0] is not None else 1
        terminal.repeat_last_character(count)

    elif final_char == "n":  # DSR/CPR - Device Status Report / Cursor Position Report
        param = params[0] if params and params[0] is not None else 0
        if param == 6:  # CPR - Cursor Position Report
            row = terminal.cursor_y + 1  # Convert to 1-based
            col = terminal.cursor_x + 1  # Convert to 1-based
            terminal.respond(f"\033[{row};{col}R")
        elif param == 5:  # DSR - Device Status Report
            terminal.respond("\033[0n")

    elif final_char == "c":  # DA - Device Attributes
        param = params[0] if params and params[0] is not None else 0
        if not intermediates:  # Primary DA
            if param == 0:
                terminal.respond("\033[?62;1;6;8;9;15;18;21;22;23c")
        elif ">" in intermediates:  # Secondary DA
            terminal.respond("\033[>1;10;0c")

    elif final_char == "p" and "$" in intermediates:  # DECRQM - Request Mode Status
        mode = params[0] if params and params[0] is not None else 0
        private = "?" in intermediates
        if private:
            status = get_private_mode_status(terminal, mode)
        else:
            status = get_ansi_mode_status(terminal, mode)
        prefix = "?" if private else ""
        terminal.respond(f"\033[{prefix}{mode};{status}$y")

    elif final_char == "h":  # SM - Set Mode
        if "?" in intermediates:
            dispatch_sm_rm_private(terminal, params, True)
        else:
            dispatch_sm_rm(terminal, params, True)

    elif final_char == "l":  # RM - Reset Mode
        if "?" in intermediates:
            dispatch_sm_rm_private(terminal, params, False)
        else:
            dispatch_sm_rm(terminal, params, False)

    elif final_char == "t":  # Window operations - consume but don't implement
        pass

    else:
        # Unknown CSI sequence
        params_str = ";".join(str(p) for p in params if p is not None) if params else "<no params>"
        intermediates_str = "".join(intermediates)
        logger.debug(f"Unknown CSI sequence: ESC[{intermediates_str}{params_str}{final_char}")


# Utility functions used by the main dispatcher


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
