# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Build and Development
```bash
# Install dependencies and prepare for development
make dev

# Run all tests
make test

# Run pre-commit hooks
pre-commit run --all-files

# Clean all build artifacts
make clean
```



## Architecture Overview

The hardware metaphor is load-bearing: the **board** is the machine, a **terminal** is the
chrome a human looks at, and two full-duplex ports connect the board to its outside world.

### Core Components

**Board** (`src/bittty/devices/board.py`)
- The whole emulator: hosts the devices and a few registers (focus, conformance level), owns
  the child process and its PTY, and routes parser operations to device handlers through a
  flat `registry` dict built from its `devices`. `width`/`height` are the blitter's page size
- No UI dependencies; runs headless. The public emulator API (`input_*`, `resize`,
  `capture_pane`, `start_process`) lives here

**Devices** (`src/bittty/devices/`)
- Single-responsibility cards plugged into the board: charset, comm, console, control,
  cursor, keyboard, macros, modes, mouse, palette, printer, query, style, title — and the **Blitter**
  (`devices/blitter.py`), the device that writes video memory

**Video** (`src/bittty/video.py`)
- Video memory: a 2D cell grid, each cell a (Style, char) pair. The board writes it through
  the blitter; terminals read it (pull) through the display port's `page`. Pages: page
  memory for the primary screen (several on the VT510), and the alternate screen

**Parser** (`src/bittty/parser/core.py`)
- State machine for processing ANSI escape sequences (C0, CSI, OSC, DCS, DEC private modes)
- One-pass ground scanner with bound fast paths: `print_text` for printable runs and
  memoized registry-direct CSI dispatch — keep these hot paths intact

**Terminal** (`src/bittty/terminals/base.py`)
- The chrome ABC. Composes a Board (never subclasses it; given one or builds one), plugs
  into its display port and talks to the board only through it (`terminal.port`): present
  events arrive at typed `on_*` hooks, physical facts go up (caps, focus, resize, input),
  and the screen is pulled (`port.page`, `port.cursor`, `damaged_rows()`). The rule: push
  what would otherwise be lost (rows scrolling off, the child exiting), pull what is still
  there. Scrollback belongs to the terminal: give it a store (`terminals/scrollback.py`) and
  it keeps the rows sent to it as numbered logical lines, laid out at any width, and can
  show history above the screen (`view_rows()`)
- **StdioTerminal** (`terminals/stdio.py`): the reference terminal, whose venue is this
  process's stdio/tty

**Ports** (`src/bittty/connections/`)
- Full-duplex jacks on the board. **HostPort** carries bytes both ways to the child: a
  `Connection` (PTY, pipe, socket, a replayed recording) plugs in and the port pumps its
  receive side into the parser; a `LineTap` on the port sees everything that crosses it
  (`recording`: asciicast v2 recorder and replay cable). **DisplayPort** carries typed
  events both ways to the chrome — present events down, input/focus/caps up — and is the
  `Screen` the chrome reads. Its name is the video-connector pun, kept on purpose.
  **PrinterPort** carries bytes to the auxiliary cable. The package also holds the
  in-memory/stream cables and the settings a port offers its cable (`serial_line`,
  `printer_config`). A cable implements its whole protocol; ports never probe for methods

**Peripherals** (`src/bittty/peripherals/`)
- Simulations of hardware on the far end of a cable: `peripherals/printer` is a virtual
  printer (DEC PPL / IBM PPDS, page store). A device is part of the terminal; a peripheral
  is what you plug into it. Core imports nothing from here — `tests/unit/test_peripheral_boundary.py`
  enforces it. See `docs/peripherals.md` for the option/configuration/connection tiers

**Options** (`src/bittty/options.py`)
- Hardware fitted at power-on: what the terminal *is*. An `Option` contributes mode
  capabilities (and, for a port, its protocol repertoire), so `Model.capabilities` is the
  model's own set unioned with its options. Fitting a port enables modes; plugging something
  into it only changes status reports. See `docs/peripherals.md`

**Model** (`src/bittty/model.py`)
- The model number: the emulation profile as data (XTERM, VT220, LINUX, ...) — DA
  responses, keymaps, mode repertoire, charsets

**Keyboard** (`src/bittty/keyboard/`)
- Key facts and their encodings, as data: `keys` (KeyEvent, KeyModifiers — what the chrome
  reports), `keymap` (each model's KeyMap), `styles` (xterm's selectable keyboards) and
  `kitty` (the Kitty protocol encoder, `KittyFlags`, `KittyStack`), `xterm` (XTMODKEYS
  resources) and `udk` (DECUDK memory). The keyboard *device* (`devices/keyboard.py`) is
  the card that uses them

**Style** (`src/bittty/style.py`)
- Packed-int text styling (colors, bold, italic, underline, etc.)
- Parses SGR (Select Graphic Rendition) sequences; 16-color, 256-color, and RGB
- Provides style diffing for efficient rendering

### PTY Implementations (`src/bittty/pty/`)
- **UnixPTY**: Uses os.openpty() for Unix-like systems
- **WindowsPTY**: Uses Windows ConPTY API
- **StdioPTY**: For testing with stdin/stdout streams
- All implement the `Connection` interface for process spawning and I/O

### Glossary and vocabulary discipline

| Term | Means | Never means |
|---|---|---|
| board | the emulator machine | the chrome |
| device | a card in the terminal | something you plug in |
| peripheral | a simulation of what's on the far end of a cable | a device |
| terminal | the chrome a human looks at | the emulator core |
| video | the cell-grid memory (pages) | — |
| blitter | the device that writes video | a renderer |
| model | the model number (XTERM, VT220) | MVC-model |
| renderer | chrome-side output production | anything board-side |
| connection | a cable implementation (PTY, pipe, socket) | — |
| port | a full-duplex jack on the board | — |

- "display" survives only in `DisplayPort`, deliberately.
- `bittty.Terminal` is deliberately not exported at top level; import chrome classes from
  `bittty.terminals`.
- There are no compat aliases: the pre-0.1.0 names (`TerminalBoard`, `Buffer`,
  `Personality`, `WritableTransport`, `DisplayCaps`, the old backend `Terminal`) are gone.

### Key Design Patterns

1. **Streaming parser**: Preserves parser state across input chunks and dispatches completed operations.
2. **Platform Abstraction**: PTY implementations hide platform differences behind common interface
3. **Separation of Concerns**: Board logic separate from UI, making it framework-agnostic
4. **Style Objects**: Immutable style representation allows efficient diffing and caching

## CODING STANDARDS

* Observe the Zen of Python.
* When there's a bug, write a failing test case for it.
* Failing tests are good tests - they have earned their keep.
* The only required functionality is functionality covered by tests. The only
  exception to this is when it has a comment explaining what it supposed to do,
  and why it is important enough to exist yet simultaneously not be important
  enough to be covered by a test. Such excuses should be rare.
* Do not invent mocks for tests. They affirm false assumptions and make a mockery
  of the test suite.
* The project will degrade into verbose, brittle spaghetti if left unchecked. This
  applies at the architectural level too. Periodically propose simplifications
  and feature freezes for refactoring.
* Branches are a source of shame and disgust, and so should be used sparingly.
  Branches at boundaries are often unavoidable pities towards an interface, they
  are not our shame.
* Defensive programming is for the weak; guards belong at trust boundaries, not
  defending against our own code. Make our code trustworthy by defending our
  borders.
* Do not guess, read the docs and code. All the files are in source control or
  in the `.venv` dir at the project root.

### Terminal Modes and Features

- `docs/DEC_private.md` is the capability inventory. A mode is supported only when it
  has observable behaviour, not merely a parser entry or stored flag.
- Character sets, scroll regions, origin mode, alternate buffers, tab stops, margins,
  focus reporting, bracketed paste, and basic/button/any SGR mouse reporting are implemented.

### Testing Approach

Tests use pytest with functional style (no unittest classes). Key test categories:
- **Parser tests**: Verify escape sequence parsing and state transitions
- **Terminal tests**: Test terminal operations (cursor, scrolling, clearing, etc.)
- **Integration tests**: End-to-end parsing with real terminal instances
- **Performance tests**: Benchmarking parser performance.

### Development Notes

- Line length: 120 characters (configured in pyproject.toml)
- Python 3.10+ required. So type hints rarely need `typing` module.
- Uses ruff for linting and formatting
- Pre-commit hooks configured for code quality
- All imports should be at module level (not in functions)
- Use pytest functional style for tests
