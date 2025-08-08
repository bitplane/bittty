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

### Core Components

**Terminal** (`src/bittty/terminal.py`)
- Main terminal emulator class that manages state and coordinates other components
- Handles process management via platform-specific PTY implementations
- Maintains terminal modes, cursor position, and screen buffers (primary/alternate)
- No UI dependencies - designed to be subclassed by UI frameworks

**Parser** (`src/bittty/parser/core.py`)
- State machine for processing ANSI escape sequences
- Handles C0 controls, CSI sequences, OSC sequences, and DEC private modes
- Maintains parsing state and buffers for sequence data
- Delegates actions to Terminal methods

**Buffer** (`src/bittty/buffer.py`)
- 2D grid storage for terminal content
- Each cell stores a Style object and character
- Handles scrolling, clearing, and content manipulation
- Supports both primary and alternate screen buffers

**Style** (`src/bittty/style.py`)
- Represents text styling (colors, bold, italic, underline, etc.)
- Parses SGR (Select Graphic Rendition) sequences
- Handles 16-color, 256-color, and RGB color modes
- Provides style diffing for efficient rendering

### PTY Implementations (`src/bittty/pty/`)
- **UnixPTY**: Uses os.openpty() for Unix-like systems
- **WindowsPTY**: Uses Windows ConPTY API
- **StdioPTY**: For testing with stdin/stdout streams
- All implement a common interface for process spawning and I/O

### Key Design Patterns

1. **State Machine Pattern**: Uses regex to parse inputs.
2. **Platform Abstraction**: PTY implementations hide platform differences behind common interface
3. **Separation of Concerns**: Terminal logic separate from UI, making it framework-agnostic
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

- Aim to support all modes in future. Even the really obscure ones. Eventually we will add our own
  private modes.
- DEC private modes (DECARM, DECBKM, DECSCLM, DECNKM, etc.)
- Mouse tracking (basic, button, any, SGR, extended)
- Character sets (ASCII, DEC Special Graphics, UK, etc.)
- Scroll regions and origin mode
- Primary and alternate screen buffers
- Tab stops and margins

### Testing Approach

Tests use pytest with functional style (no unittest classes). Key test categories:
- **Parser tests**: Verify escape sequence parsing and state transitions
- **Terminal tests**: Test terminal operations (cursor, scrolling, clearing, etc.)
- **Integration tests**: End-to-end parsing with real terminal instances
- **Performance tests**: Benchmarking parser performance. More perf tests will be added over time.

### Known Issues

From README.md
- Scroll region bugs (vim scrolling corrupts outside region)

From user
- We need to keep tidying up. The code is too long and looks like a procedural fizzbuzz enterprise
  edition.

### Development Notes

- Line length: 120 characters (configured in pyproject.toml)
- Python 3.10+ required. So type hints rarely need `typing` module.
- Uses ruff for linting and formatting
- Pre-commit hooks configured for code quality
- All imports should be at module level (not in functions)
- Use pytest functional style for tests
