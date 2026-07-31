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
- The whole emulator: hosts the devices and registers (focus, window state, console
  registers), owns the child process and its PTY, and routes parser operations to device
  handlers through a flat `registry` dict
- No UI dependencies; runs headless. The public emulator API (`input_*`, `resize`,
  `capture_pane`, `start_process`) lives here

**Devices** (`src/bittty/devices/`)
- Single-responsibility cards plugged into the board: charset, control, cursor, keyboard,
  modes, mouse, palette, printer, query, style, title — and the **Blitter**
  (`devices/blitter.py`), the device that writes video memory

**Video** (`src/bittty/video.py`)
- Video memory: a 2D cell grid, each cell a (Style, char) pair. The board writes it through
  the blitter; terminals read it (pull) via `capture_pane()`/`get_line()`. Two pages:
  primary and alternate

**Parser** (`src/bittty/parser/core.py`)
- State machine for processing ANSI escape sequences (C0, CSI, OSC, DCS, DEC private modes)
- One-pass ground scanner with bound fast paths: `print_text` for printable runs and
  memoized registry-direct CSI dispatch — keep these hot paths intact

**Terminal** (`src/bittty/terminals/base.py`)
- The chrome ABC. Composes a Board (never subclasses it), plugs into its display port,
  receives present events through typed `on_*` hooks, and pushes physical facts up
  (caps, focus, resize, input)
- **StdioTerminal** (`terminals/stdio.py`): the reference terminal, whose venue is this
  process's stdio/tty

**Ports** (`src/bittty/connections.py`)
- Full-duplex jacks on the board. **HostPort** carries bytes both ways to the child: a
  `Connection` (PTY, pipe, socket) plugs in and the port pumps its receive side into the
  parser. **DisplayPort** carries typed events both ways to the chrome: present events
  down, input/focus/caps up. Its name is the video-connector pun, kept on purpose

**Peripherals** (`src/bittty/peripherals/`)
- Simulations of hardware on the far end of a cable: `peripherals/printer` is a virtual
  printer (DEC PPL / IBM PPDS, page store). A device is part of the terminal; a peripheral
  is what you plug into it. Core imports nothing from here — `tests/unit/test_peripheral_boundary.py`
  enforces it. See `docs/peripherals.md` for the option/configuration/connection tiers

**Model** (`src/bittty/model.py`)
- The model number: the emulation profile as data (XTERM, VT220, LINUX, ...) — DA
  responses, keymaps, mode repertoire, charsets

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

* When there's a bug, write a test case for the component.
* Failing tests are good tests.
* The only functionality that is required, is functionality that is covered by a test. The only
  exception to this is where it has a comment that explains what it supposed to do, why it is
  important enough to exist yet simultaneously not important enough to be covered by a test.
* Do not use mocks in tests. They make a mockery of our codebase.
* The project will degrade into verbose, brittle spaghetti if left unchecked. Periodically propose
  simplifications.
* Branches are a source of shame and disgust. They should be used sparingly.
* Defensive programming is for the weak.
* Do not guess, read the docs. All the files are in source control or in the `.venv` dir at the
  project root.

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
