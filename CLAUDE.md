# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Build and Development
```bash
# Install dependencies and prepare for development
make dev

# Run all tests
make test

# Run tests with verbose output
pytest -vv --asyncio-mode=auto .

# Run a specific test file
pytest -vv --asyncio-mode=auto tests/unit/parser/test_csi_sequences.py

# Run a specific test
pytest -vv --asyncio-mode=auto tests/unit/parser/test_csi_sequences.py::test_cursor_up

# Build coverage report
make

# Run pre-commit hooks (formats with ruff)
pre-commit run --all-files
```

### Demo Applications

Do not run the app as it'll mess with Claude Code's terminal and leak through to the user's terminal.
Instead ask gaz to run it and he'll tell you which tmux pane to peep.

## Architecture Overview

### Core Components

**Terminal** (`src/bittty/terminal.py`)
- Main terminal emulator class that manages state and coordinates other components
- Handles process management via platform-specific PTY implementations
- Maintains terminal modes, cursor position, and screen buffers (primary/alternate)
- No UI dependencies - designed to be subclassed by UI frameworks

**Parser** (`src/bittty/parser.py`)
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

1. **State Machine Pattern**: Parser uses explicit states (GROUND, ESCAPE, CSI_ENTRY, etc.) for sequence parsing
2. **Platform Abstraction**: PTY implementations hide platform differences behind common interface
3. **Separation of Concerns**: Terminal logic separate from UI, making it framework-agnostic
4. **Style Objects**: Immutable style representation allows efficient diffing and caching

### Terminal Modes and Features

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
- **Performance tests**: Benchmarking parser performance

### Known Issues

From README.md
- Scroll region bugs (vim scrolling corrupts outside region)
- Stream corruption during parsing
- Textual-in-textual not working properly yet (cascading update loop = slow)

### Development Notes

- Line length: 120 characters (configured in pyproject.toml)
- Python 3.10+ required, so use appropriate type hints (e.g. `list[str | None]`)
- Uses ruff for linting and formatting
- Pre-commit hooks configured for code quality
- All imports should be at module level (not in functions)
- Use pytest functional style for tests
