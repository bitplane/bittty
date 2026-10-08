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
 │          │  screen read across    │ scrollback             │
 └────┬─────┘                        │ cursor rendition       │
      │                              └────────────────────────┘
   devices + registers + Video (pages)
```

## The Board (`bittty.Board`)

The whole emulator: devices, registers, the child process and its PTY. It routes parser
operations to device handlers through a flat `registry` dict and runs headless — a board
with nothing plugged into its display port behaves identically.

Devices are single-responsibility cards: charset, comm, console, control, cursor, keyboard,
macros, modes, mouse, palette, printer, query, style, title, and the **Blitter** — the device that writes video
memory. It blits; it does not render.

A device is part of the terminal. What plugs *into* it lives in `bittty.peripherals` and is
never imported by core — see [peripherals.md](peripherals.md).

Registers on the board hold physical facts reported by the chrome (focus, caps). The
**console** device keeps the box's own registers: window state (XTWINOPS), the bells, the
answerback, the linux setterm registers (bell pitch, blank timeout) and the OSC desktop
settings (clipboard, working directory, pointer shape, font).

Host-output chunks (`feed_host_data` and `board.parser.feed`) and board resize calls
share a reentrant lock. Both pages, cursor/margins, PTY sizing and frontend resize
reports finish before another thread's output is processed. This does not order
bytes already buffered by the child against its resize signal. Other device access
and rendering still belong on the owning event loop; the board is not generally
thread-safe. Receive callbacks run synchronously under this lock and must not wait
for another thread to feed or resize the board.

## Video (`bittty.Video`)

Video memory: a 2D cell grid, each cell a (Style, char) pair, in two pages (primary and
alternate). A width-2 character has an empty continuation cell. The board writes it through
the blitter; terminals read it on their own cadence (pull) through the display port's
`page`, or the board's `capture_pane()`/`capture_text()`.

Models with page memory (the VT510: 3 pages of 24 lines, 2 of 25 or 36, else one) keep the
primary screen as one of several pages. NP/PP/PPA/PPR/PPB move the cursor between them, and
DECPCCM decides whether the display follows: while it is reset, `blitter.main_page` stays on
the displayed page and `blitter.cursor_on_display` is false, so the chrome hides the cursor.
DECCRA and DECRQCRA name pages; DECCIR and DECRQDE report them.

Models with a DEC status line (VT510, bittty) add a one-row status page. DECSSDT picks its
type (the chrome hears `on_status_line`), and DECSASD sends writes there as to a one-row
display, where only column positions apply and nothing scrolls. The blitter writes on a
*surface* (a page, its rows and its margins) and DECSASD swaps the main surface for the
status line's whole, so `blitter.rows` is 1 there while `board.height` stays the page's.
`blitter.main_page` stays on the main display for the chrome, and `capture_status_line()`
reads the status line.

On a width change, a terminal that reflows (gnome and kitty always; bittty under mode 2028,
on by default) re-wraps page memory's soft-wrapped lines to the new width, never splitting a
wide character, and the cursor keeps its place in its line. Rows that no longer fit go from
below the cursor if blank, then from the top. The alternate screen is cut, as every page is
on terminals that do not reflow.

The terminal frontend reports its measured ambiguous-character width through `TerminalCaps`;
mode 8840 may override that baseline for future writes.

## Terminals (`bittty.terminals`)

The chrome. A concrete terminal composes a Board (never subclasses it) — one it is given,
or one it builds — plugs into its display port, and is named by venue: `StdioTerminal`
renders into the tty this process runs in; future siblings render into a Textual widget, a
browser, a video file. Apart from the board's power switch (`start_process`/`stop_process`)
it touches the board only through the port, `terminal.port`.

The rule for the seam is: **push what would otherwise be lost, pull what is still there.**

- *Pulled:* the screen. The port is a `connections.Screen` — `page` (the displayed video),
  `cursor` (where to draw it, or None), `width`, `height` — read on the terminal's own
  frame clock. `Terminal.damaged_rows()` says which rows changed since the last paint (all
  of them after a page flip). The port also answers what the terminal needs to decode its
  venue's input: `kitty_flags`, `keyboard_selected`, `escape_is_key`.
- *Pushed:* everything else, as typed `on_*` hooks. `ScreenChanged` (once per chunk of host
  output, per local echo and per resize) says the screen is worth a look; the terminal marks
  itself dirty and paints on its tick. `RowsScrolledOff` carries rows leaving the top of the
  primary screen — full-width scrolls of a region at the top, and rows a reflow cuts — as
  detached `Line`s, sent only to a terminal with `keeps_scrollback` set, since copying them
  costs every line feed. `ScrollbackCleared` is ED 3; `ChildExited` is the host side ending
  (its return code, or None for a dropped line). Bell, title, mode changes and the rest are
  side-effects that were never in video memory.

Scrollback is the terminal's, not the board's: a real terminal has none (xterm's saveLines
is the window's), and a board that kept history would stop being small and deterministic.

A terminal given a store (`Terminal(board, scrollback)`) keeps scrollback: the base turns
each row it is sent into a `ScrollbackLine` (text, a style per cell, a shape only when
a cell holds other than one code point, and the line's DECDWL/DECDHL size) and appends it,
saying whether the line goes on. The store (`terminals/scrollback.py`) holds logical lines
numbered for life and lays them out at any width, a line to ceil(width / columns) rows
(its width is its cells, twice that on a double-size line), so history re-wraps on resize
and a line number is a stable reference for whatever indexes a store grows later. The
`Scrollback` protocol is the least a store does; `MemoryScrollback` forgets its oldest
lines past a budget of cells (each line one more, so empty ones count). The view is
the terminal's too: `view_top` anchors it as (line, row within it), so it holds still
while output arrives, and `view_rows()` is history above the screen.
Physical facts flow the other way: the
venue's resize, focus, input, and capabilities go down to the board through the port.
Frontend resizes use a distinct display-port path, so host-requested XTWINOPS/DECSLPP
resizes cannot generate false in-band resize notifications.

## Ports and Connections (`bittty.connections`)

Ports are full-duplex jacks on the board; connections are the cables that plug in. The
package has a module per port (`host`, `display`, `printer`), the in-memory and stream
cables (`cables`), and the settings a port offers its cable (`serial_line`,
`printer_config`). Each port's protocol (`Connection`, `PrinterConnection`) is the whole
interface: a cable implements every method, so ports call them without probing.

- **HostPort** carries bytes both ways (a serial line). A `Connection` — PTY, pipe,
  socket — plugs in (`Board.start_process` plugs in a PTY with a child; `Board.connect`
  any cable); the port's receive pump feeds the child's output into the parser, and
  resizes reach whatever cable is plugged in. A `LineTap` clipped onto the port (`tap`)
  sees every byte both ways and each resize, whatever the cable. `recording` holds a tap
  that writes the line as asciicast v2 (`CastRecorder`; keys sent only on request, as they
  include passwords) and a cable that plays a recording back (`CastReplay`, with speed and
  an idle limit; resizes arrive as XTWINOPS 8). A recording is what crossed the line,
  which is lossless; sampling the screen into frames (quantising) is lossy, and belongs to
  a terminal pulling the screen on its own clock.
- **PrinterPort** carries raw bytes both ways to whatever is on the auxiliary cable: a
  virtual printer, a binary stream, a serial adapter, a bridge to real hardware. Controller
  mode is routed before text decoding, and a capable adapter is offered immutable
  `PrinterConfiguration` snapshots. What is on the far end is a *peripheral*, not part of
  the board — see [peripherals.md](peripherals.md).
- **DisplayPort** carries typed events both ways — present events down to the chrome,
  input/focus/caps up from it — and is the `Screen` the chrome reads. Serialize its event
  streams and a snapshot of the screen, and the chrome can live in another process or
  another machine; the board never notices. The name is the
  video-connector pun, kept on purpose.

## The Model (`bittty.Model`)

The model number: the emulation profile as data (XTERM, VT100, VT102, VT220, VT320, VT420, VT510, LINUX...). DA
responses, keymaps, mode and printer repertoires, charsets. A board is constructed with a
model the way a VT220 ships with its ROMs.

The default BITTTY model is the native superset; named compatibility models expose only their audited repertoires.

## Vocabulary discipline

- "board" never means the chrome; "terminal" never means the emulator core.
- "model" only ever means the model number, never MVC.
- "renderer" only ever means chrome-side output production; nothing board-side renders.
- "display" survives only in `DisplayPort`.
