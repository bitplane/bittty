"""CSI (Control Sequence Introducer) operation parser."""

from __future__ import annotations

import logging
from functools import lru_cache

from ..operations import Operation
from ..style import parse_sgr_with_reset

logger = logging.getLogger(__name__)


def param(params, index=0, default=None):
    """Return params[index] when present and not None, else default."""
    return params[index] if len(params) > index and params[index] is not None else default


@lru_cache(maxsize=1000)
def parse_csi_params(data):
    """Parse CSI parameters when actually needed.

    Args:
        data: Complete CSI sequence like '\x1b[1;2H' or '\x1b[?25h'

    Returns:
        tuple: (params_list, intermediate_chars, final_char)
    """
    if data.startswith("\x1b["):
        content = data[2:]
    elif data.startswith("\x9b"):
        content = data[1:]
    else:
        return [], [], ""
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


@lru_cache(maxsize=4096)
def parse_csi_operation(raw_csi_data: str) -> Operation | None:
    """Return a semantic operation for CSI sequences migrated to the operation layer.

    Cached: real terminal traffic repeats a small CSI vocabulary (a full-screen
    TUI session uses a few hundred distinct sequences), and Operation is frozen
    with immutable args, so one instance per distinct sequence is safe to share.
    """
    if len(raw_csi_data) < 2:
        return None

    params, intermediates, final_char = parse_csi_params(raw_csi_data)

    if final_char == "m" and ">" not in raw_csi_data:  # SGR - Select Graphic Rendition
        style, reset = parse_sgr_with_reset(raw_csi_data)
        return Operation("SGR", (style, reset), raw_csi_data)

    # Hot path: the common cursor moves are params-only (no intermediates), and dominate
    # real CSI traffic after SGR. Dispatch them here — with inline param extraction —
    # before the pile of rare intermediate-gated branches below. Anything with an
    # intermediate (e.g. SR is `SP A`) skips this and falls through to its handler.
    if not intermediates:
        if final_char == "H" or final_char == "f":  # CUP / HVP
            p = params
            row = (p[0] if p and p[0] is not None else 1) - 1
            col = (p[1] if len(p) > 1 and p[1] is not None else 1) - 1
            return Operation("CUP" if final_char == "H" else "HVP", (col, row), raw_csi_data)
        if final_char == "A":  # CUU
            return Operation("CUU", (params[0] if params and params[0] is not None else 1,), raw_csi_data)
        if final_char == "B":  # CUD
            return Operation("CUD", (params[0] if params and params[0] is not None else 1,), raw_csi_data)
        if final_char == "C":  # CUF
            return Operation("CUF", (params[0] if params and params[0] is not None else 1,), raw_csi_data)
        if final_char == "D":  # CUB
            return Operation("CUB", (params[0] if params and params[0] is not None else 1,), raw_csi_data)

    if final_char == "n":  # DSR/CPR - Device Status Report / Cursor Position Report
        code = param(params, 0, 0)
        if intermediates == ["?"] and code == 15:
            return Operation("DSR_PRINTER", (code,), raw_csi_data)
        if code == 5:
            return Operation("DSR", (code,), raw_csi_data)
        if code == 6:
            return Operation("CPR", (code,), raw_csi_data)

    if final_char == "c":  # DA - Device Attributes
        code = param(params, 0, 0)
        if ">" in intermediates:
            return Operation("DA2", (code,), raw_csi_data)
        if "=" in intermediates:
            return Operation("DA3", (code,), raw_csi_data)
        if not intermediates and code == 0:
            return Operation("DA1", (code,), raw_csi_data)

    if final_char == "p" and "$" in intermediates:  # DECRQM - Request Mode Status
        mode = param(params, 0, 0)
        private = "?" in intermediates
        return Operation("DECRQM", (mode, private), raw_csi_data)

    if final_char == "p" and "!" in intermediates:  # DECSTR - Soft Terminal Reset
        return Operation("DECSTR", (), raw_csi_data)

    if final_char == "q" and " " in intermediates:  # DECSCUSR - Set Cursor Style
        style = param(params, 0, 0)
        return Operation("DECSCUSR", (style,), raw_csi_data)

    if final_char == "q" and ">" in intermediates:  # XTVERSION - report terminal name/version
        return Operation("XTVERSION", (param(params, 0, 0),), raw_csi_data)

    if final_char == "p" and '"' in intermediates:  # DECSCL - Set Conformance Level
        return Operation("DECSCL", (tuple(params),), raw_csi_data)

    # VT510 printer configuration. Keep exact intermediate matching here:
    # several finals also name older cursor, margin, and rectangular functions.
    printer_configuration = {
        ("$", "s"): "DECSPRTT",
        (")", "p"): "DECSDPT",
        ("*", "p"): "DECSPPCS",
        ("*", "u"): "DECSCP",
        ("*", "r"): "DECSCS",
        ("*", "s"): "DECSFC",
        ("+", "w"): "DECSPP",
    }.get(("".join(intermediates), final_char))
    if printer_configuration is not None:
        return Operation(printer_configuration, (tuple(params),), raw_csi_data)

    if final_char == "q" and '"' in intermediates:  # DECSCA - Select Character Protection
        mode = param(params, 0, 0)
        return Operation("DECSCA", (mode,), raw_csi_data)

    if final_char == "y" and "*" in intermediates:  # DECRQCRA - Request Checksum of Rectangular Area
        return Operation("DECRQCRA", (tuple(params),), raw_csi_data)

    if final_char == "x" and "*" in intermediates:  # DECSACE - Select Attribute Change Extent
        return Operation("DECSACE", (param(params, 0, 0),), raw_csi_data)

    if final_char == "|" and "$" in intermediates:  # DECSCPP - Select Columns Per Page
        return Operation("DECSCPP", (param(params, 0, 80),), raw_csi_data)

    if "#" in intermediates:  # xterm SGR / colour attribute stacks
        stack_op = {
            "{": "XTPUSHSGR",  # push SGR attributes
            "}": "XTPOPSGR",  # pop SGR attributes
            "P": "XTPUSHCOLORS",  # push the colour palette
            "Q": "XTPOPCOLORS",  # pop the colour palette
        }.get(final_char)
        if stack_op is not None:
            return Operation(stack_op, (tuple(params),), raw_csi_data)

    if "$" in intermediates:  # DEC rectangular-area functions
        rect = {
            "x": "DECFRA",  # Fill Rectangular Area
            "z": "DECERA",  # Erase Rectangular Area
            "{": "DECSERA",  # Selective Erase Rectangular Area
            "v": "DECCRA",  # Copy Rectangular Area
            "r": "DECCARA",  # Change Attributes in Rectangular Area
            "t": "DECRARA",  # Reverse Attributes in Rectangular Area
        }.get(final_char)
        if rect is not None:
            return Operation(rect, (tuple(params),), raw_csi_data)

    if "'" in intermediates:  # DEC locator (pointing device) family
        if final_char == "z":  # DECELR - Enable Locator Reporting
            ps1 = param(params, 0, 0)
            ps2 = param(params, 1, 0)
            return Operation("DECELR", (ps1, ps2), raw_csi_data)
        if final_char == "{":  # DECSLE - Select Locator Events
            return Operation("DECSLE", (tuple(params),), raw_csi_data)
        if final_char == "|":  # DECRQLP - Request Locator Position
            return Operation("DECRQLP", (param(params, 0, 0),), raw_csi_data)
        if final_char == "w":  # DECEFR - Enable Filter Rectangle
            return Operation("DECEFR", (tuple(params),), raw_csi_data)
        if final_char == "}":  # DECIC - Insert Column(s)
            return Operation("DECIC", (param(params, 0, 1),), raw_csi_data)
        if final_char == "~":  # DECDC - Delete Column(s)
            return Operation("DECDC", (param(params, 0, 1),), raw_csi_data)

    if " " in intermediates:  # SPACE-intermediate functions (DECSCUSR handled above)
        count = param(params, 0, 1)
        volume = param(params, 0, 0)
        if final_char == "@":  # SL - Scroll Left (data pans left, right edge blanks)
            return Operation("SL", (count,), raw_csi_data)
        if final_char == "A":  # SR - Scroll Right
            return Operation("SR", (count,), raw_csi_data)
        if final_char == "t":  # DECSWBV - Set Warning Bell Volume
            return Operation("DECSWBV", (volume,), raw_csi_data)
        if final_char == "u":  # DECSMBV - Set Margin Bell Volume
            return Operation("DECSMBV", (volume,), raw_csi_data)

    if final_char == "m" and ">" in intermediates:  # XTMODKEYS - set key-modifier options
        return Operation("XTMODKEYS", (tuple(params),), raw_csi_data)

    if final_char == "u":  # Kitty keyboard protocol (private markers) or SCORC restore-cursor
        if ">" in intermediates:  # push flags onto the stack
            return Operation("KITTY_PUSH", (param(params, 0, 0),), raw_csi_data)
        if "<" in intermediates:  # pop n entries off the stack
            return Operation("KITTY_POP", (param(params, 0, 1),), raw_csi_data)
        if "=" in intermediates:  # set flags with a mode (1 set / 2 add / 3 remove)
            flags = param(params, 0, 0)
            mode = param(params, 1, 1)
            return Operation("KITTY_SET", (flags, mode), raw_csi_data)
        if "?" in intermediates:  # query current flags
            return Operation("KITTY_QUERY", (), raw_csi_data)
        if not intermediates:
            return Operation("RESTORE", raw=raw_csi_data)

    if final_char in ("h", "l"):  # SM/RM - Set/Reset Mode
        set_mode = final_char == "h"
        private = "?" in intermediates
        name = ("DECSET" if set_mode else "DECRST") if private else ("SM" if set_mode else "RM")
        return Operation(name, (tuple(params), set_mode, private), raw_csi_data)

    if intermediates == ["?"] and final_char in ("s", "r"):
        # XTSAVE / XTRESTORE — save or restore the listed DEC private modes.
        name = "XTSAVE" if final_char == "s" else "XTRESTORE"
        return Operation(name, (tuple(params),), raw_csi_data)

    if any(intermediate != "?" for intermediate in intermediates):
        return None

    # CUP/HVP and CUU/CUD/CUF/CUB (params-only) are handled by the hot path near the top.

    if final_char == "G":  # CHA - Cursor Horizontal Absolute
        col = (param(params, 0, 1)) - 1
        return Operation("CHA", (col,), raw_csi_data)

    if final_char == "d":  # VPA - Vertical Position Absolute
        row = (param(params, 0, 1)) - 1
        return Operation("VPA", (row,), raw_csi_data)

    if final_char == "`":  # HPA - Horizontal Position Absolute
        col = (param(params, 0, 1)) - 1
        return Operation("HPA", (col,), raw_csi_data)

    if final_char == "E":  # CNL - Cursor Next Line
        count = param(params, 0, 1)
        return Operation("CNL", (count,), raw_csi_data)

    if final_char == "F":  # CPL - Cursor Previous Line
        count = param(params, 0, 1)
        return Operation("CPL", (count,), raw_csi_data)

    if final_char == "a":  # HPR - Horizontal Position Relative
        count = param(params, 0, 1)
        return Operation("HPR", (count,), raw_csi_data)

    if final_char == "e":  # VPR - Vertical Position Relative
        count = param(params, 0, 1)
        return Operation("VPR", (count,), raw_csi_data)

    if final_char == "I":  # CHT - Cursor Horizontal (Forward) Tab
        count = param(params, 0, 1)
        return Operation("CHT", (count,), raw_csi_data)

    if final_char == "Z":  # CBT - Cursor Backward Tab
        count = param(params, 0, 1)
        return Operation("CBT", (count,), raw_csi_data)

    if final_char == "g":  # TBC - Tab Clear
        mode = param(params, 0, 0)
        return Operation("TBC", (mode,), raw_csi_data)

    if final_char == "t":  # XTWINOPS - Window manipulation / reports
        return Operation("XTWINOPS", (tuple(params),), raw_csi_data)

    if final_char == "]":  # linux console setterm hardware directives
        return Operation("LINUX_SETTERM", (tuple(params),), raw_csi_data)

    if final_char == "J":  # ED / DECSED - Erase in Display (selective with ?)
        mode = param(params, 0, 0)
        return Operation("DECSED" if "?" in intermediates else "ED", (mode,), raw_csi_data)

    if final_char == "K":  # EL / DECSEL - Erase in Line (selective with ?)
        mode = param(params, 0, 0)
        return Operation("DECSEL" if "?" in intermediates else "EL", (mode,), raw_csi_data)

    if final_char == "L":  # IL - Insert Lines
        count = param(params, 0, 1)
        return Operation("IL", (count,), raw_csi_data)

    if final_char == "M":  # DL - Delete Lines
        count = param(params, 0, 1)
        return Operation("DL", (count,), raw_csi_data)

    if final_char == "@":  # ICH - Insert Characters
        count = param(params, 0, 1)
        return Operation("ICH", (count,), raw_csi_data)

    if final_char == "P":  # DCH - Delete Characters
        count = param(params, 0, 1)
        return Operation("DCH", (count,), raw_csi_data)

    if final_char == "X":  # ECH - Erase Character
        count = param(params, 0, 1)
        return Operation("ECH", (count,), raw_csi_data)

    if final_char == "S":  # SU - Scroll Up
        count = param(params, 0, 1)
        return Operation("SU", (count,), raw_csi_data)

    if final_char == "T":  # SD - Scroll Down
        count = param(params, 0, 1)
        return Operation("SD", (count,), raw_csi_data)

    if final_char == "r":  # DECSTBM - Set Top and Bottom Margins
        top = (param(params, 0, 1)) - 1
        bottom = (params[1] - 1) if len(params) > 1 and params[1] is not None else None
        return Operation("DECSTBM", (top, bottom), raw_csi_data)

    if final_char == "s":  # DECSLRM (Pl;Pr) when margin mode is on, else Save Cursor (SCOSC)
        if params:
            return Operation("DECSLRM", (tuple(params),), raw_csi_data)
        return Operation("SAVE", raw=raw_csi_data)

    if final_char == "b":  # REP - Repeat
        count = param(params, 0, 1)
        return Operation("REP", (count,), raw_csi_data)

    if final_char == "j":  # HPB - Horizontal Position Backward
        count = param(params, 0, 1)
        return Operation("HPB", (count,), raw_csi_data)

    if final_char == "k":  # VPB - Vertical Position Backward
        count = param(params, 0, 1)
        return Operation("VPB", (count,), raw_csi_data)

    if final_char == "i":  # MC - Media Copy (printer control), DEC private with ?
        ps = param(params, 0, 0)
        return Operation("DECMC" if "?" in intermediates else "MC", (ps,), raw_csi_data)

    if final_char == "W":  # CTC / DECST8C - Cursor Tabulation Control
        if "?" in intermediates:  # DECST8C - reset to a tab stop every 8 columns
            return Operation("DECST8C", (), raw_csi_data)
        mode = param(params, 0, 0)
        return Operation("CTC", (mode,), raw_csi_data)

    return None
