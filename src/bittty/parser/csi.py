"""CSI (Control Sequence Introducer) operation parser."""

from __future__ import annotations

import logging
from functools import lru_cache
from ..operations import Operation
from ..style import parse_sgr_sequence


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


def parse_csi_operation(raw_csi_data: str) -> Operation | None:
    """Return a semantic operation for CSI sequences migrated to the operation layer."""
    if len(raw_csi_data) < 3:
        return None

    params, intermediates, final_char = parse_csi_params(raw_csi_data)

    if final_char == "m" and ">" not in raw_csi_data:  # SGR - Select Graphic Rendition
        reset = raw_csi_data in ("\x1b[m", "\x1b[0m", "\x1b[00m")
        return Operation("SGR", (parse_sgr_sequence(raw_csi_data), reset), raw_csi_data)

    if final_char == "n":  # DSR/CPR - Device Status Report / Cursor Position Report
        param = params[0] if params and params[0] is not None else 0
        if param == 5:
            return Operation("DSR", (param,), raw_csi_data)
        if param == 6:
            return Operation("CPR", (param,), raw_csi_data)

    if final_char == "c":  # DA - Device Attributes
        param = params[0] if params and params[0] is not None else 0
        if ">" in intermediates:
            return Operation("DA2", (param,), raw_csi_data)
        if "=" in intermediates:
            return Operation("DA3", (param,), raw_csi_data)
        if not intermediates and param == 0:
            return Operation("DA1", (param,), raw_csi_data)

    if final_char == "p" and "$" in intermediates:  # DECRQM - Request Mode Status
        mode = params[0] if params and params[0] is not None else 0
        private = "?" in intermediates
        return Operation("DECRQM", (mode, private), raw_csi_data)

    if final_char == "p" and "!" in intermediates:  # DECSTR - Soft Terminal Reset
        return Operation("DECSTR", (), raw_csi_data)

    if final_char == "q" and " " in intermediates:  # DECSCUSR - Set Cursor Style
        style = params[0] if params and params[0] is not None else 0
        return Operation("DECSCUSR", (style,), raw_csi_data)

    if final_char == "p" and '"' in intermediates:  # DECSCL - Set Conformance Level
        return Operation("DECSCL", (tuple(params),), raw_csi_data)

    if final_char == "q" and '"' in intermediates:  # DECSCA - Select Character Protection
        mode = params[0] if params and params[0] is not None else 0
        return Operation("DECSCA", (mode,), raw_csi_data)

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
            ps1 = params[0] if params and params[0] is not None else 0
            ps2 = params[1] if len(params) > 1 and params[1] is not None else 0
            return Operation("DECELR", (ps1, ps2), raw_csi_data)
        if final_char == "{":  # DECSLE - Select Locator Events
            return Operation("DECSLE", (tuple(params),), raw_csi_data)
        if final_char == "|":  # DECRQLP - Request Locator Position
            return Operation("DECRQLP", (params[0] if params and params[0] is not None else 0,), raw_csi_data)
        if final_char == "w":  # DECEFR - Enable Filter Rectangle
            return Operation("DECEFR", (tuple(params),), raw_csi_data)

    if final_char in ("h", "l"):  # SM/RM - Set/Reset Mode
        set_mode = final_char == "h"
        private = "?" in intermediates
        name = ("DECSET" if set_mode else "DECRST") if private else ("SM" if set_mode else "RM")
        return Operation(name, (tuple(params), set_mode, private), raw_csi_data)

    if any(intermediate != "?" for intermediate in intermediates):
        return None

    if final_char in ("H", "f"):  # CUP/HVP - Cursor Position
        row = (params[0] if params and params[0] is not None else 1) - 1
        col = (params[1] if len(params) > 1 and params[1] is not None else 1) - 1
        name = "CUP" if final_char == "H" else "HVP"
        return Operation(name, (col, row), raw_csi_data)

    if final_char == "A":  # CUU - Cursor Up
        count = params[0] if params and params[0] is not None else 1
        return Operation("CUU", (count,), raw_csi_data)

    if final_char == "B":  # CUD - Cursor Down
        count = params[0] if params and params[0] is not None else 1
        return Operation("CUD", (count,), raw_csi_data)

    if final_char == "C":  # CUF - Cursor Forward
        count = params[0] if params and params[0] is not None else 1
        return Operation("CUF", (count,), raw_csi_data)

    if final_char == "D":  # CUB - Cursor Backward
        count = params[0] if params and params[0] is not None else 1
        return Operation("CUB", (count,), raw_csi_data)

    if final_char == "G":  # CHA - Cursor Horizontal Absolute
        col = (params[0] if params and params[0] is not None else 1) - 1
        return Operation("CHA", (col,), raw_csi_data)

    if final_char == "d":  # VPA - Vertical Position Absolute
        row = (params[0] if params and params[0] is not None else 1) - 1
        return Operation("VPA", (row,), raw_csi_data)

    if final_char == "`":  # HPA - Horizontal Position Absolute
        col = (params[0] if params and params[0] is not None else 1) - 1
        return Operation("HPA", (col,), raw_csi_data)

    if final_char == "E":  # CNL - Cursor Next Line
        count = params[0] if params and params[0] is not None else 1
        return Operation("CNL", (count,), raw_csi_data)

    if final_char == "F":  # CPL - Cursor Previous Line
        count = params[0] if params and params[0] is not None else 1
        return Operation("CPL", (count,), raw_csi_data)

    if final_char == "a":  # HPR - Horizontal Position Relative
        count = params[0] if params and params[0] is not None else 1
        return Operation("HPR", (count,), raw_csi_data)

    if final_char == "e":  # VPR - Vertical Position Relative
        count = params[0] if params and params[0] is not None else 1
        return Operation("VPR", (count,), raw_csi_data)

    if final_char == "I":  # CHT - Cursor Horizontal (Forward) Tab
        count = params[0] if params and params[0] is not None else 1
        return Operation("CHT", (count,), raw_csi_data)

    if final_char == "Z":  # CBT - Cursor Backward Tab
        count = params[0] if params and params[0] is not None else 1
        return Operation("CBT", (count,), raw_csi_data)

    if final_char == "g":  # TBC - Tab Clear
        mode = params[0] if params and params[0] is not None else 0
        return Operation("TBC", (mode,), raw_csi_data)

    if final_char == "t":  # XTWINOPS - Window manipulation / reports
        return Operation("XTWINOPS", (tuple(params),), raw_csi_data)

    if final_char == "]":  # linux console setterm hardware directives
        return Operation("LINUX_SETTERM", (tuple(params),), raw_csi_data)

    if final_char == "J":  # ED / DECSED - Erase in Display (selective with ?)
        mode = params[0] if params and params[0] is not None else 0
        return Operation("DECSED" if "?" in intermediates else "ED", (mode,), raw_csi_data)

    if final_char == "K":  # EL / DECSEL - Erase in Line (selective with ?)
        mode = params[0] if params and params[0] is not None else 0
        return Operation("DECSEL" if "?" in intermediates else "EL", (mode,), raw_csi_data)

    if final_char == "L":  # IL - Insert Lines
        count = params[0] if params and params[0] is not None else 1
        return Operation("IL", (count,), raw_csi_data)

    if final_char == "M":  # DL - Delete Lines
        count = params[0] if params and params[0] is not None else 1
        return Operation("DL", (count,), raw_csi_data)

    if final_char == "@":  # ICH - Insert Characters
        count = params[0] if params and params[0] is not None else 1
        return Operation("ICH", (count,), raw_csi_data)

    if final_char == "P":  # DCH - Delete Characters
        count = params[0] if params and params[0] is not None else 1
        return Operation("DCH", (count,), raw_csi_data)

    if final_char == "X":  # ECH - Erase Character
        count = params[0] if params and params[0] is not None else 1
        return Operation("ECH", (count,), raw_csi_data)

    if final_char == "S":  # SU - Scroll Up
        count = params[0] if params and params[0] is not None else 1
        return Operation("SU", (count,), raw_csi_data)

    if final_char == "T":  # SD - Scroll Down
        count = params[0] if params and params[0] is not None else 1
        return Operation("SD", (count,), raw_csi_data)

    if final_char == "r":  # DECSTBM - Set Top and Bottom Margins
        top = (params[0] if params and params[0] is not None else 1) - 1
        bottom = (params[1] - 1) if len(params) > 1 and params[1] is not None else None
        return Operation("DECSTBM", (top, bottom), raw_csi_data)

    if final_char == "s":  # Save Cursor
        return Operation("SAVE", raw=raw_csi_data)

    if final_char == "u":  # Restore Cursor
        return Operation("RESTORE", raw=raw_csi_data)

    if final_char == "b":  # REP - Repeat
        count = params[0] if params and params[0] is not None else 1
        return Operation("REP", (count,), raw_csi_data)

    return None
