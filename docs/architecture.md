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

A device is part of the terminal. What plugs *into* it lives in `bittty.peripherals` and is
never imported by core — see [peripherals.md](peripherals.md).

Registers on the board hold physical facts reported by the chrome (focus, window state,
caps) and hardware state the child can set (bell pitch, blank timeout, console requests).

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
the blitter; terminals read it on their own cadence (pull) via `capture_pane()`,
`capture_text()`, or `get_line()`.

Models with page memory (the VT510: 3 pages of 24 lines, 2 of 25 or 36, else one) keep the
primary screen as one of several pages. NP/PP/PPA/PPR/PPB move the cursor between them, and
DECPCCM decides whether the display follows: while it is reset, `blitter.main_page` stays on
the displayed page and `blitter.cursor_on_display` is false, so the chrome hides the cursor.
DECCRA and DECRQCRA name pages; DECCIR and DECRQDE report them.

Models with a DEC status line (VT510, bittty) add a one-row status page. DECSSDT picks its
type (the chrome hears `on_status_line`), and DECSASD sends writes there as to a one-row
display, where only column positions apply and nothing scrolls. `blitter.main_page` stays on
the main display for the chrome, and `capture_status_line()` reads the status line.

On a width change, a terminal that reflows (gnome and kitty always; bittty under mode 2028,
on by default) re-wraps page memory's soft-wrapped lines to the new width, never splitting a
wide character, and the cursor keeps its place in its line. Rows that no longer fit go from
below the cursor if blank, then from the top. The alternate screen is cut, as every page is
on terminals that do not reflow.

The terminal frontend reports its measured ambiguous-character width through `TerminalCaps`;
mode 8840 may override that baseline for future writes.

## Terminals (`bittty.terminals`)

The chrome. A concrete terminal composes a Board (never subclasses it), plugs into its
display port, and is named by venue: `StdioTerminal` renders into the tty this process runs
in; future siblings render into a Textual widget, a browser, a video file.

Present events (bell, title, mouse-capture changes...) arrive as typed `on_*` hooks — discrete
side-effects are pushed; screen content is pulled. Physical facts flow the other way: the
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
  socket — plugs in; the port's receive pump feeds the child's output into the parser.
- **PrinterPort** carries raw bytes both ways to whatever is on the auxiliary cable: a
  virtual printer, a binary stream, a serial adapter, a bridge to real hardware. Controller
  mode is routed before text decoding, and a capable adapter is offered immutable
  `PrinterConfiguration` snapshots. What is on the far end is a *peripheral*, not part of
  the board — see [peripherals.md](peripherals.md).
- **DisplayPort** carries typed events both ways: present events down to the chrome,
  input/focus/caps up from it. Serialize its two event streams and the chrome can live in
  another process or another machine; the board never notices. The name is the
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
