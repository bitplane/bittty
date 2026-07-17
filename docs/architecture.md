# bittty Architecture: A Hardware-Inspired Terminal Emulator

The hardware metaphor is load-bearing. The **board** is the machine; a **terminal** is the
chrome a human looks at; two full-duplex **ports** connect the board to its outside world.

```
 child program                                          human
      │                                                   │
   (PTY / pipe / socket = Connection)                 (venue: tty, widget, browser)
      │                                                   │
 ┌────┴─────┐    bytes both ways     ┌────────────────────┴───┐
 │ HostPort ├────────────────────────┤        Terminal        │
 ├──────────┤                        │        (chrome)        │
 │          │  present events down   ├────────────────────────┤
 │  Board   ├──────DisplayPort───────┤ renders Video, arbitr-  │
 │          │  input/focus/caps up   │ ates hover/click, owns │
 └────┬─────┘                        │ cursor rendition       │
      │                              └────────────────────────┘
   devices + registers + Video (pages)
```

## The Board (`bittty.Board`)

The whole emulator: devices, registers, the child process and its PTY. It routes parser
operations to device handlers through a flat `registry` dict and runs headless — a board
with nothing plugged into its display port behaves identically.

Devices are single-responsibility cards: charset, control, cursor, keyboard, modes, mouse,
palette, printer, query, style, title, and the **Blitter** — the device that writes video
memory. It blits; it does not render.

Registers on the board hold physical facts reported by the chrome (focus, window state,
caps) and hardware state the child can set (bell pitch, blank timeout, console requests).

## Video (`bittty.Video`)

Video memory: a 2D cell grid, each cell a (Style, char) pair, in two pages (primary and
alternate). The board writes it through the blitter; terminals read it on their own cadence
(pull) via `capture_pane()` / `get_line()`.

## Terminals (`bittty.terminals`)

The chrome. A concrete terminal composes a Board (never subclasses it), plugs into its
display port, and is named by venue: `StdioTerminal` renders into the tty this process runs
in; future siblings render into a Textual widget, a browser, a video file.

Present events (bell, title, mouse-mode changes...) arrive as typed `on_*` hooks — discrete
side-effects are pushed; screen content is pulled. Physical facts flow the other way: the
venue's resize, focus, input, and capabilities go down to the board through the port.

## Ports and Connections (`bittty.connections`)

Ports are full-duplex jacks on the board; connections are the cables that plug in.

- **HostPort** carries bytes both ways (a serial line). A `Connection` — PTY, pipe,
  socket — plugs in; the port's receive pump feeds the child's output into the parser.
- **DisplayPort** carries typed events both ways: present events down to the chrome,
  input/focus/caps up from it. Serialize its two event streams and the chrome can live in
  another process or another machine; the board never notices. The name is the
  video-connector pun, kept on purpose.

## The Model (`bittty.Model`)

The model number: the emulation profile as data (XTERM, VT220, LINUX...). DA responses,
keymaps, the mode repertoire, charsets. A board is constructed with a model the way a VT220
ships with its ROMs.

## Vocabulary discipline

- "board" never means the chrome; "terminal" never means the emulator core.
- "model" only ever means the model number, never MVC.
- "renderer" only ever means chrome-side output production; nothing board-side renders.
- "display" survives only in `DisplayPort`.
