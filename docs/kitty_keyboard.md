# Kitty keyboard protocol

bittty implements the [kitty keyboard protocol](https://sw.kovidgoyal.net/kitty/keyboard-protocol/)
negotiation (`CSI > u` push, `CSI < u` pop, `CSI = u` set, `CSI ? u` query) and the
progressive enhancements the input API can express. The rule throughout is honesty: the
spec's detection scheme is "set flags, query, trust the answer", so bittty never
advertises a flag the encoder ignores.

## What is implemented

| flag | enhancement | status |
| ---: | :--- | :--- |
| 1 | disambiguate escape codes | ✅ |
| 2 | report event types | ❌ ignored on set, absent from query |
| 4 | report alternate keys | ❌ ignored on set, absent from query |
| 8 | report all keys as escape codes | ✅ |
| 16 | report associated text | ✅ (meaningful only with 8, per the spec) |

Unsupported bits are dropped at negotiation time, so an application that requests
`CSI > 31 u` and queries gets `CSI ? 25 u` back and can feature-detect correctly.

Flags 2 and 4 are not implementable today: the input API is `input_key(char, modifier)` —
there is no press/repeat/release event and no physical-key or layout identity in bittty's
vocabulary. They wait on a key-event input layer, the same prerequisite as the DEC
national-keyboard modes.

Only models that really speak the protocol answer the negotiation: `KITTY` and `BITTTY`
carry it in `Model.control_capabilities`. A VT220 or xterm board does not recognise the
sequences at all — real xterm never replies to `CSI ? u`.

## Spec fidelity notes

- **Bounded stack.** The push/pop stack holds 8 entries; a full stack evicts its oldest
  ("Terminals should limit the size of the stack as appropriate, to prevent
  Denial-of-Service attacks").
- **Per-screen state.** Main and alternate screens keep independent flags and stacks, as
  the spec requires. RIS clears both.
- **Unshifted key codes.** ctrl+shift+a is `CSI 97;6u`, never 65. For non-letter shifted
  characters (`!`) the unshifted key needs layout knowledge bittty does not have, so the
  character encodes as given — layout fidelity is flag-4 territory.
- **Legacy escape hatch.** Under flag 1 alone, unmodified Enter, Tab and Backspace keep
  their legacy bytes so `reset` stays typeable after a crashed program leaves the mode on;
  modified they become CSI u (telling ctrl+i from Tab is a stated goal of the protocol).
- **Legacy encodings are suppressed while active**: no alt/meta ESC prefixing (alt lives
  in the modifier field), no DECCKM SS3 cursor forms, no raw DEL for the Delete key under
  mode 1037.
- **Associated text is authoritative.** A chrome that pre-applies shift and sends
  `("A", KEY_MOD_NONE)` yields `CSI 97;;65u` under flags 8|16: the text field carries the
  truth; the shift bit is unknowable from a char+modifier API.

## What reaches the encoder

The protocol applies to the typed input API (`Board.input_key`, `input_fkey`,
`input_numpad_key`) — what embedder chromes and tests use. `StdioTerminal` forwards raw
stdin bytes verbatim (`Board.input`), and translating that legacy byte stream into kitty
events (is `\x01` ctrl+a?, is a batched read a paste?) is its own design problem,
deliberately not attempted here. Raw arrows and nav keys pass through in forms that are
already kitty-correct; the one raw-path behaviour the protocol changes is that DECCKM
rewriting to SS3 is suspended while flags are active, which is what the spec's legacy
tables imply.
