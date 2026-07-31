# bittty Peripherals: Options, Configuration, and Connections

The board is the machine and a terminal is the chrome. This document covers the third
category: **the hardware you plug into the machine**, and how it decides what the machine
can do.

The north star is a research-grade emulator of every terminal that existed. Most of what a
real terminal could do depended on what was installed in it or hanging off it, so the
capability model is not a detail — it is the mechanism by which the rest of the history
gets implemented.

## The rule

> `devices/` is the terminal. `peripherals/` is what you plug into it.

A **device** is a card in the machine: the cursor, the blitter, the keyboard encoder, the
printer *port*. It is part of the terminal and ships with the board.

A **peripheral** is a simulation of something on the far end of a cable: a virtual LA50, a
VSXXX-AA mouse. It is not part of the terminal, and the board runs identically with nothing
plugged in.

This is enforced, not merely intended: `bittty` core imports nothing from
`bittty.peripherals`, and a test asserts that `import bittty` leaves the peripheral packages
out of `sys.modules`.

## Three tiers, not one

"Plug in hardware and it enables modes" is half right, and the wrong half would make bittty
less faithful. The distinction real hardware draws is:

| Tier | What it is | When | Affects |
| :--- | :--- | :--- | :--- |
| **1. Installed option** | what the terminal *is* — AVO, graphics board, printer port, locator port, keyboard type | power-on, static | **mode repertoire**, DA responses |
| **2. Configuration** | what the terminal *believes* is attached — printer type, baud, parity | Set-Up or host sequences | protocol variant |
| **3. Connection** | what is *actually* on the cable | runtime | **status reports only** |

The printer proves the distinction. A VT220 honours DECPFF and DECPEX, and answers
DECSPRTT, with **nothing plugged into the port**: the modes exist because the terminal has a
printer port, not because a printer is on the end of it. `CSI ? 15 n` reports 13 (no
printer) and that is the only thing the empty cable changes.

**Tier 3 must never gate the mode repertoire.** A terminal does not forget how to parse
DECPFF because you unplugged the printer.

## Tier 1: installed options

Capabilities are already semantic identifiers (`mode_profiles.py`) that models select by
repertoire, and models already compose by set union (`VT220 = VT100 | {...}`). Options
extend that composition to hardware:

```
active capabilities = model.mode_capabilities | ⋃(option.mode_capabilities)
```

An option carries what it contributes to the mode repertoire, what it adds to the DA
response, and which other options it depends on. The dependency edge is not speculative: the
VT340 graphics-print modes (43 DECGEPM, 44 DECGPCM, 45 DECGPCS, 46 DECGPBM, 47 DECGRPM)
require **both** a graphics option and a printer port.

The archetype is the VT100 Advanced Video Option — a board that gave a VT100 132 columns and
simultaneous attributes, and changed its DA response from `?1;0c` to `?1;2c`. bittty
currently expresses this as a hardcoded DA string with a comment; it is an option.

This tier also subsumes `PrinterCapabilities`, which is a second, printer-shaped capability
mechanism sitting beside the general one. `media_copy` and `configuration` are capability
identifiers; `disconnected_status` is tier 3 and belongs on the port.

## Tier 2: configuration

What the terminal has been *told* is attached, independent of what is really there. For the
printer this is `PrinterConfiguration` — type, code page, baud, parity, stop bits, flow
control — set through DECSPRTT, DECSDPT, DECSPPCS, DECSCP, DECSCS, DECSFC and DECSPP, and
reported back through DECRQSS.

Configuration lives board-side, in core, because the terminal holds it whether or not a
peripheral exists to receive it. It is offered to a connected adapter through the port, and
a peripheral that understands it may act on it.

## Tier 3: connections

Ports are the jacks; connections are the cables (see `connections.py`). A connection changes
status reports and whether bytes go anywhere. It never changes what the terminal knows how
to parse.

`MemoryPrinter` and `StreamPrinter` are cables, not printers — an in-memory duplex byte sink
and a `BinaryIO` adapter. They live with the other connections. The thing that *simulates a
printer* is `bittty.peripherals.printer.VirtualPrinter`.

## What is still missing, by cluster

The unsupported column of `DEC_private.md` is largely an inventory of unmodelled hardware.
Grouping it that way turns a long list of orphan modes into a roadmap:

| Cluster | Modes | Count |
| :--- | :--- | ---: |
| Keyboard (LK201/401/450, national variants) | 12, 16, 23, 35, 49, 57, 68, 81, 104, 108, 109, 110 | 12 |
| CRT / display hardware | 4, 9, 51, 55, 97, 106, 114–117 | 10 |
| Comms / transport | 11, 14, 53, 73, 99, 103 | 6 |
| Graphics option | 38, 80, 1070, 8452 | 4 |
| Graphics × printer (needs both) | 43, 44, 45, 46, 47 | 5 |
| Hardcopy / plotter | 20, 24, 70 | 3 |
| ROM options | 21, 22 | 2 |

The **locator** does not appear there because it is CSI sequences rather than private modes:
DECELR, DECSLE, DECRQLP, DECLRP, DECLBD, and locator DSR. DEC shipped two locator devices on
one port — the VSXXX-AA mouse and the VSXXX-AB graphics tablet — which is the same
"one port, several device types" shape the printer port already has. `MouseProtocol.LOCATOR`
and the existing locator tests are the start of peripheral #2.

Mode 103 DECHDPXM is already annotated in `DEC_private.md` as requiring a transport-level
half-duplex interface. That annotation is this document in miniature.

## Printers, for the record

The axes that have architectural consequences:

- **Language** — DEC PPL and IBM PPDS are implemented, one decoder module each under
  `peripherals/printer/languages/`. A `PrinterMechanism` holds the physical state every
  language shares — rendition, direction, autowrap, pitch, character sets — plus the print
  head; each parser owns only its own state and drives the mechanism. Adding Epson ESC/P,
  HP PCL or PostScript means a new parser module implementing `LanguageControl`'s
  counterpart contract, not another branch in a shared feed loop.

  The mechanism is what makes the language switch honest: DECIPEM (mode 58) snapshots it,
  hands the stream to the PPDS decoder, and restores it on the way back, because those
  settings belong to the machine rather than to whichever language is currently driving it.
- **Connection** — serial EIA (RS232/RS423, 300/1200/2400/9600 baud on the VT aux port) or
  Centronics parallel. Modelled by `PrinterPortSelection`.
- **Graphics** — the LA50 prints dot graphics at 72 dpi vertical, 144 or 180 horizontal; the
  LN03 has graphics. Not yet modelled, and the gate for VT340 graphics printing.
- **Some printers are terminals.** The LA36 and LA120 DECwriter are hardcopy *terminals*: a
  machine whose video memory is paper. That makes the page store the video of a hardcopy
  terminal, and a future `HardcopyTerminal` chrome the symmetric sibling of `StdioTerminal`.

Terminal side: effectively every real DEC terminal had a printer port (VT100 with the EIA
auxiliary port, VT102 onward as standard, through the VT510). No software emulator has one
except xterm's print-to-pipe fiction, which is why `xterm` carries media copy without
configuration and linux/screen/tmux/urxvt/gnome/kitty carry no printer at all.

## Unverified

Recorded so nobody mistakes inference for research:

- **DEC PPL levels.** `GENERIC_DEC_PPL2_PRINTER` asserts level 2. The level semantics have
  not been checked against the LA50/LA75/LN03 programmer reference manuals.
- **Locator absence reporting.** The exact DECRQLP report when no locator is connected is
  unconfirmed; needed before locator work starts.

## References

- [Terminals & Printers Handbook, ch. 7](https://vt100.net/docs/tp83/chapter7.html) — VT aux port
- [ch. 12](https://vt100.net/docs/tp83/chapter12.html) — LA50
- [ch. 14](https://vt100.net/docs/tp83/chapter14.html) — LA120 DECwriter III
- [VT330/VT340 Programmer Reference, ch. 15](https://vt100.net/docs/vt3xx-gp/chapter15.html) — locator devices
- [DEC private control sequences](https://vt100.net/emu/ctrlseq_dec.html)
