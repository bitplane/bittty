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
