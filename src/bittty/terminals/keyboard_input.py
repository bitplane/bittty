"""Bounded input framing and Kitty decoding for a terminal-hosted frontend."""

import codecs
import re

from ..keyboard_protocol import FUNCTIONAL, UNICODE_KEYS
from ..keys import KeyEvent, KeyModifiers

_CSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_ESCAPE = re.compile(r"\x1b[ -/]*[0-~]")
_KEY = re.compile(r"\x1b\[([0-9:]*)(?:;([0-9:]*))?(?:;([0-9:]*))?([u~ABCDEFHPQS])\Z")
_REVERSE = {value: key for key, value in FUNCTIONAL.items()}
_REVERSE.update({(code, "u"): key for key, code in UNICODE_KEYS.items()})
_REVERSE.update(
    {(7, "~"): "home", (8, "~"): "end", (11, "~"): "f1", (12, "~"): "f2", (14, "~"): "f4", (57427, "~"): "kp_begin"}
)
_PASTE_END = "\x1b[201~"
_REPLY = re.compile(
    r"\x1b(?:\[\?[0-9;]*c|\[[0-9]+;[0-9]+R|\[\?2027;[0-4]\$y|\[(?:4|6);[0-9]+;[0-9]+t|\]11;.*)", re.DOTALL
)
_TEXT_RUN = re.compile(r"[^\x00-\x1f\x7f-\x9f]+|[\x00-\x1f\x7f-\x9f]+")
_KEYBOARD_REPLY = re.compile(r"\x1b\[\?([0-9]{1,10})u")
_SS3_KEYS = dict(zip("ABCDHFPQRS", ("up", "down", "right", "left", "home", "end", "f1", "f2", "f3", "f4")))
_SS3_KEYS["["] = "escape"
MAX_SEQUENCE = 4096


def decode_key(raw: str) -> KeyEvent | str | None:
    """Decode a complete explicit key report; str means committed text."""
    if raw.startswith("\x1bO") and len(raw) == 3 and raw[-1] in _SS3_KEYS:
        return KeyEvent(_SS3_KEYS[raw[-1]])
    match = _KEY.fullmatch(raw)
    if match is None:
        return None
    key_field, mod_field, text_field, final = match.groups()
    try:
        codes = (key_field or "1").split(":")
        mods = (mod_field or "1").split(":")
        if len(codes) > 3 or len(mods) > 2:
            return None
        code = int(codes[0])
        modifier = int(mods[0] or "1") - 1
        kind = int(mods[1] or "1") if len(mods) == 2 else 1
        if kind not in (1, 2, 3):
            return None
        text = "".join(chr(int(c)) for c in text_field.split(":")) if text_field else None
        key = _REVERSE.get((code, final))
        if key is None:
            if final != "u":
                return None
            if code == 0 and text is not None:
                # Validation is the same as associated key text.
                KeyEvent("text", text=text)
                return text if kind != 3 else ""
            key = chr(code)
        shifted = chr(int(codes[1])) if len(codes) > 1 and codes[1] else None
        base = chr(int(codes[2])) if len(codes) > 2 and codes[2] else None
        return KeyEvent(key, KeyModifiers(modifier), ("press", "repeat", "release")[kind - 1], text, shifted, base)
    except (ValueError, OverflowError):
        return None


class KeyboardInput:
    """Frame input without buffering text runs or whole pastes.

    Unknown sequences pass through intact up to MAX_SEQUENCE. Oversized control
    strings are discarded through their terminator. Paste retains only a possible
    end-marker prefix. Idle flushing resolves short legacy Escape/Alt prefixes;
    it must not break a fragmented explicit keyboard or mouse report.
    """

    def __init__(self, terminal):
        self.terminal = terminal
        self.pending = ""
        self.utf8 = codecs.getincrementaldecoder("utf-8")("replace")
        self.pasting = False
        self.discard = None

    def feed(self, data: str | bytes):
        if isinstance(data, bytes):
            data = self.utf8.decode(data)
        # Bound work buffers even for embedders supplying a very large chunk.
        for offset in range(0, len(data), MAX_SEQUENCE):
            self._feed(data[offset : offset + MAX_SEQUENCE])

    def _feed(self, data):
        data = self.pending + data
        self.pending = ""
        while data:
            if self.pasting:
                end = data.find(_PASTE_END)
                if end >= 0:
                    self.terminal.board.display.input_paste(data[:end], phase="end")
                    self.pasting = False
                    data = data[end + len(_PASTE_END) :]
                    continue
                keep = next((n for n in range(min(5, len(data)), 0, -1) if data.endswith(_PASTE_END[:n])), 0)
                chunk = data[:-keep] if keep else data
                if chunk:
                    self.terminal.board.display.input_paste(chunk, phase="chunk")
                self.pending = data[-keep:] if keep else ""
                return
            if self.discard:
                terminator = re.search(r"[\x07\x9c]|\x1b\\" if self.discard == "string" else r"[@-~]", data)
                if terminator is None:
                    self.pending = "\x1b" if data.endswith("\x1b") else ""
                    return
                data = data[terminator.end() :]
                self.discard = None
                continue
            if not data.startswith("\x1b"):
                end = data.find("\x1b")
                if end < 0:
                    end = len(data)
                self._text(data[:end])
                data = data[end:]
                continue
            if data.startswith("\x1b["):
                match = _CSI.match(data)
                end = match.end() if match else 0
                kind = "csi"
            elif len(data) > 1 and data[1] in "]P_^X":
                match = re.search(r"[\x07\x9c]|\x1b\\", data[2:])
                end = match.end() + 2 if match else 0
                kind = "string"
            elif data.startswith("\x1bO"):
                end = 3 if len(data) >= 3 else 0
                kind = "csi"
            else:
                match = _ESCAPE.match(data)
                end = match.end() if match else 0
                kind = "csi"
            if not end:
                # An embedded control aborts a partial CSI/ESC sequence. Keep
                # unknown input intact, then resume framing at the new control.
                interrupted = re.search(r"[\x00-\x1f]", data[1:]) if kind != "string" else None
                if interrupted is not None:
                    end = interrupted.start() + 1
                    self.terminal.board.display.input(data[:end])
                    data = data[end:]
                    continue
                if len(data) > MAX_SEQUENCE:
                    self.discard = kind
                else:
                    self.pending = data
                return
            raw, data = data[:end], data[end:]
            if len(raw) <= MAX_SEQUENCE:
                self._sequence(raw)

    def _sequence(self, raw):
        terminal = self.terminal
        keyboard_reply = _KEYBOARD_REPLY.fullmatch(raw) if raw.startswith("\x1b[?") else None
        if keyboard_reply is not None:
            if terminal.host_keyboard_pushed:
                terminal.host_keyboard_flags = int(keyboard_reply.group(1)) & 31
        elif (raw[-1] in "Rcty" or raw.startswith("\x1b]")) and _REPLY.fullmatch(raw):
            return
        elif raw == "\x1b[200~":
            self.pasting = True
            terminal.board.display.input_paste("", phase="start")
        elif raw.startswith("\x1b[<") and terminal.handle_sgr_mouse_sequence(raw):
            return
        elif raw in ("\x1b[I", "\x1b[O"):
            terminal.handle_focus(raw == "\x1b[I")
        elif raw == "\x1bO[":
            terminal.board.display.input_key_event(KeyEvent("escape"))
        elif terminal.host_keyboard_flags is not None or terminal.board.keyboard.kitty_flags:
            event = decode_key(raw)
            if isinstance(event, KeyEvent):
                terminal.board.display.input_key_event(event)
            elif isinstance(event, str):
                terminal.board.display.input_text(event)
            else:
                terminal.board.display.input(raw)
        else:
            terminal.board.display.input(raw)

    def _text(self, text):
        board = self.terminal.board
        if not board.keyboard.kitty_flags & 8:
            board.display.input(text)
            return
        # Plain text gives no physical-key identity, even if the outer terminal
        # supports Kitty: an IME or a legacy intermediary may have supplied it.
        for match in _TEXT_RUN.finditer(text):
            chunk = match.group()
            if ord(chunk[0]) >= 32 and not 127 <= ord(chunk[0]) <= 159:
                board.display.input_text(chunk)
            else:
                board.display.input(chunk)

    def flush_trailing(self):
        disambiguated = bool((self.terminal.host_keyboard_flags or 0) & 9)
        if (
            self.pending.startswith("\x1b")
            and len(self.pending) <= 2
            and not self.pasting
            and not self.discard
            and not disambiguated
        ):
            pending = self.pending
            self.pending = ""
            board = self.terminal.board
            if pending == "\x1b" and (board.modes.application_escape or board.modes.escape_sends_fs):
                board.display.input_key_event(KeyEvent("escape"))
            else:
                board.display.input(pending)

    def finish(self):
        self.feed(self.utf8.decode(b"", final=True))
        if self.pasting:
            self.terminal.board.display.input_paste(self.pending, phase="end")
            self.pasting = False
        elif self.pending and not self.discard:
            self.terminal.board.display.input(self.pending)
        self.pending = ""
