# BitTTY Architecture: A Hardware-Inspired Terminal Emulator

## Note

This is the future plan, not the current state of the project.

## Overview

BitTTY is a modular terminal emulator designed around the hardware metaphor of physical terminals. Components are separated into clear responsibilities that mirror how real terminal hardware was organized.

## Core Philosophy

Instead of abstract "services" and "controllers", BitTTY uses concrete components you can point to:
- **Parser**: decodes terminal protocol
- **Codec**: handles character encoding
- **Screen**: manages display buffers and cursor
- **Connection**: talks to the child process
- **Input**: processes keystrokes
- **Monitor**: shows stuff on screen
- **Keyboard**: gets keypresses

## Architecture


### Component Separation

**Current Issue**: MonitorDevice does too much - it handles display rendering, buffer storage, cursor tracking, character sets, and screen modes all in one class.

**Better Separation**:
```
├── Parser
│   └── just parses bytes → yields Commands (no dispatch)
│
├── Codec
│   ├── input_encoding / output_encoding
│   └── shared by Connection, Screen, Printer
│
├── Memory Components
│   ├── Buffer (2D character grid)
│   ├── Scrollback (line history)
│   └── CharacterMemory (current line + encoding)
│
├── Screen
│   ├── primary_buffer: Buffer
│   ├── alt_buffer: Buffer
│   ├── cursor position (x, y)
│   ├── current_buffer pointer
│   └── screen modes (alt screen, scroll regions)
│
├── Connection (Multi-layer network stack)
│   ├── Application Layer: read_text() / write_text()
│   ├── Session Layer: set_echo() / set_canonical() / terminal modes
│   ├── Transport Layer: encoding / flow_control
│   └── Physical Layer: baud_rate / parity / DTR / modem control
│
├── Input
│   ├── key event processing
│   ├── modifier handling
│   └── input source abstraction
│
└── Devices (hardware interfaces only)
    ├── Monitor - renders Screen.current_buffer
    ├── TTYMonitor - ANSI output to sys.stdout
    ├── Keyboard - sends to Input
    ├── TTYKeyboard - reads from stdin
    ├── Bell - audio/visual notifications
    └── Printer - hard copy output
```

### Key Insights Discovered

1. **Parser vs Dispatcher**: Parser should just parse and yield Commands. Something else should dispatch them.

2. **Input Flow Complexity**: Different input sources (TTY, GUI, WebSocket) need different handling:
   - TTY: raw byte stream, no key up/down events
   - GUI: discrete key events with repeat and modifiers
   - Web: serialized keyboard events

3. **Connection Abstraction**: SSH, telnet, serial ports all have different terminal mode control mechanisms:
   - Direct PTY: uses termios() system calls
   - SSH: uses SSH channel request messages
   - WebSocket: needs custom protocol for mode changes
   - Serial: hardware flow control, baud rates, parity

4. **OSI Model Relevance**: Connection naturally maps to network layers:
   - Physical: baud rates, serial settings, TCP socket options
   - Transport: character encoding, flow control
   - Session: terminal modes (echo, canonical, etc.)
   - Application: read_text()/write_text() interface

5. **Device Abstraction**: Should remain for all components that:
   - Handle Commands and can be queried for capabilities
   - Can be attached/detached from BitTTY
   - Represent hardware-like interfaces

## Commands

Commands are lightweight messages representing terminal operations:

```python
from collections import namedtuple

Command = namedtuple('Command', ['name', 'type', 'args', 'terminator'])

# Examples:
Command('CSI_CUP', 'CSI', ('10', '20'), 'H')      # ESC[10;20H
Command('SGR', 'CSI', ('1', '31'), 'm')           # ESC[1;31m - bold red
Command('C0_CR', 'C0', (), None)                  # \r
Command('TEXT', 'TEXT', ('Hello',), None)         # Regular text
```

## Device Interface

```python
class Device:
    """A terminal device - handles specific functionality."""

    def get_command_handlers(self) -> dict[str, Callable]:
        """What commands this device wants to handle."""
        return {}

    def query(self, feature_name: str) -> Any:
        """Query device capabilities."""
        return None

class Board:
    """A board that devices attach to."""

    def attach(self, component: Device | Board) -> None:
        """Attach a device or board."""

    def dispatch(self, command: Command) -> Command | None:
        """Route command to devices."""
```

## Data Flow

### Terminal Output (Child Process → Display)
```
Child Process → PTY → ConnectionDevice → Parser → Commands →
Screen/Monitor → Host Terminal Display
```

### User Input (Keyboard → Child Process)
```
Host Keyboard → InputDevice → Input → Connection → PTY → Child Process
```

## Cross-Platform Considerations

### Terminal Mode Control
- **Unix**: termios() system calls
- **Windows**: Console API (SetConsoleMode, GetConsoleMode)
- **SSH**: SSH channel request messages
- **WebSocket**: Custom JSON protocol

### Character Encoding
- Input and output encodings may differ
- Codec component handles conversion
- Shared across Connection, Screen, Printer

### Input Models
- **TTY**: Character stream, OS handles repeat
- **GUI**: Key events with up/down/repeat
- **Web**: Serialized keyboard events

## Current Status

The architecture is in active development. We have a working BitTTY implementation with the Command system and Device abstraction, but are refining the component separation to better match the underlying terminal mechanisms.

The goal is to create clean abstractions that:
1. Map clearly to real terminal hardware concepts
2. Handle cross-platform differences gracefully
3. Support different connection types (PTY, SSH, serial, WebSocket)
4. Remain simple and testable

## Open Questions

1. **Input Architecture**: How should different input sources (TTY, Textual, WebSocket) integrate with the Input component?

2. **Connection Layers**: Should the OSI-style layers be separate classes or methods on Connection?

3. **Device Granularity**: What's the right level of Device separation?

4. **Parser Integration**: How should Parser and Command dispatch coordinate?

These questions are being explored through implementation and will be resolved as the architecture stabilizes.
