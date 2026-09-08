# Keyboard input

`Board.input_key_event(KeyEvent(...))` and `DisplayPort.input_key_event(...)`
accept an unshifted character or named key, modifiers, press/repeat/release,
produced text, and optional shifted/base-layout keys. Unknown text and alternate
identities stay `None`; the board does not infer a keyboard layout.

```python
from bittty import Board, KeyEvent, KeyModifiers

board = Board()
board.input_key_event(KeyEvent("a", KeyModifiers.SHIFT, text="A", shifted_key="A"))
board.input_key_event(KeyEvent("a", event_type="release"))
board.input_text("é")       # committed text, no physical key
board.input_paste("hello")  # paste, independent of keyboard encoding
```

Key names include `up`, `f1`–`f35`, `kp_0`, `kp_enter`, and `left_shift`.
`KeyModifiers` includes Shift, Alt, Ctrl, Super, Hyper, Meta and lock-state bits.
It describes state after the event. Existing `input_key`, `input_fkey`, and
`input_numpad_key` calls remain available; their one-plus-mask modifier argument
retains its original meaning (in particular, bit 8 means Meta, not Super).
Hardware/layout adapters can map their identities into events without adding
platform-specific codes to the board. Historical keyboard layouts remain unimplemented.

DECARM (mode 8, bittty and DEC hardware profiles) filters explicit repeat events;
legacy bytes cannot distinguish repeats. Repeat timing and historical per-key
exceptions remain frontend/hardware-profile work.

DECUDK on bittty, xterm, VT220 and VT510 defines Shift-F6–F20 byte strings, with
clear/merge, download locking and DSR 25. RIS clears definitions and unlocks;
DECSTR preserves them. `keyboard.set_user_keys_locked(False)` is the operator
Set-Up unlock. Storage is bounded by `Model.udk_capacity` (256 bytes on VT220,
4,096 otherwise; the latter is an implementation budget, not a hardware claim).

The bittty profile supports mintty modes 7727/7728: application Escape (`ESC O [`)
takes precedence over Escape-as-Ctrl-Backslash. Existing modifier policies apply
to normal Escape; application Escape carries no modifiers. Kitty encoding takes
precedence, as does modifyOtherKeys for modified character keys. Raw input and
paste are unchanged. Mode 7727 also maps explicitly identified keypad navigation
keys to application-keypad codes when DECKPAM is active and DECCKM is reset.

## Kitty protocol

The `BITTTY` and `KITTY` models implement all five
[Kitty keyboard enhancements](https://sw.kovidgoyal.net/kitty/keyboard-protocol/):
disambiguation, event types, alternate keys, report-all-keys, and associated text.
Negotiation uses push/pop/set/query; unknown flag bits are ignored. Each screen
has independent flags and an eight-entry stack; RIS clears both.

Alternate identities are emitted only when supplied. Associated text requires
report-all-keys; committed text uses key code zero. Paste bypasses keyboard
encoding. Releases cannot cause local echo or margin bells. Legacy encoding
and model-specific keymaps apply when enhancements are inactive; negotiated
canonical encodings take precedence over legacy function-key strings.

## Stdio frontend

`StdioTerminal` probes the outer terminal, pushes the five requested flags when
supported, queries the accepted flags, and pops its stack entry on exit. This
negotiation is independent of the child's flags and screen changes. Input is
decoded incrementally, including UTF-8, keyboard reports, mouse/focus reports,
and bracketed paste. Startup typing is retained until the child starts.

Legacy terminals and intermediaries cannot supply missing releases or layout
identities. Identifiable keys are translated; plain text remains text (key zero
when associated-text reporting is active), and ambiguous control bytes pass
through. A short legacy Escape/Alt prefix is resolved on an idle tick; disambiguated input
can remain fragmented across ticks.

Input framing retains at most 4,096 characters of a pending sequence; oversized sequences
are discarded. Pastes stream in chunks, retaining at most five characters of a
possible end marker. Embedders can stream a single paste with
`input_paste(text, phase="start" | "chunk" | "end")`; the default is `"complete"`.
