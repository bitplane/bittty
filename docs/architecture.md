# BitTTY Architecture: A Hardware-Inspired Terminal Emulator

## Overview

BitTTY is designed as a "metal box" - a central hub that mirrors the architecture of hardware terminals from the telegraph era to modern video terminals. Components are attached to provide specific functionality, just like adding cards or peripherals to physical terminal hardware.

## Core Concepts

### The Metal Box (BiTTY)

The BiTTY class is the main board (chassis) that:
- Parses incoming byte streams into control codes and text
- Contains the root Board for command routing
- Manages device registration and capability queries
- Coordinates the overall terminal system

### Commands

Commands are lightweight messages that represent terminal control sequences:

```python
from collections import namedtuple

Command = namedtuple('Command', ['name', 'type', 'args', 'terminator'])

# Examples:
Command('CURSOR_POSITION', 'CSI', ('10', '20'), 'H')      # ESC[10;20H
Command('SET_GRAPHICS', 'CSI', ('1', '31'), 'm')          # ESC[1;31m - bold red
Command('CARRIAGE_RETURN', 'C0', (), None)                # \r
Command('LINE_FEED', 'C0', (), None)                      # \n
Command('PRINT_TEXT', 'TEXT', ('Hello World',), None)     # Regular text
Command('SET_TITLE', 'OSC', ('0', 'My Title'), '\x07')    # OSC 0;My Title BEL
```

Commands can be converted back to escape sequences for recording/debugging:
```python
def command_to_escape(command):
    if command.type == 'C0':
        return C0_CODES[command.name]
    elif command.type == 'CSI':
        params = ';'.join(command.args)
        return f'\x1b[{params}{command.terminator}'
    elif command.type == 'OSC':
        return f'\x1b]{";".join(command.args)}{command.terminator}'
    elif command.type == 'TEXT':
        return command.args[0]
```

### Devices and Boards

The system uses two main abstractions:

#### Device
A Device handles specific terminal functionality and plugs into a Board:

**Printer Devices**
- Handle line-oriented output (like a teletype printer)
- Implement line printing modes (LNM, etc.)
- Can be used for logging or actual printing
- Handle: CR, LF, FF, VT, and print-related control codes
- State: page position, margins, tab stops

**Monitor Devices**
- Handle screen-oriented output (like a CRT display)
- Manage screen buffers, cursor position, and visual attributes
- Implement scroll regions, screen clearing, and cursor movement
- Handle: CSI sequences for cursor control, ED, EL, scroll commands, SGR
- State: screen buffers, cursor position, colors, scroll regions

**Input Devices**
- Handle keyboard, mouse, and other input devices
- Manage input modes (application keypad, mouse tracking, etc.)
- Translate hardware events into terminal input sequences
- Platform-specific implementations (TextualInput, QtInput, WebInput, etc.)
- State: keyboard modes, mouse tracking state, key mappings

**Connection Devices**
- Manage the connection to the actual process
- Handle process spawning and I/O
- Platform-specific (UnixPTY, WindowsPTY, StdioPTY, SerialPort, etc.)
- State: process handle, file descriptors

**Bell Devices**
- Handle BEL character
- Can produce audio, visual flash, or system notification
- Handle: BEL (0x07)

#### Board
A Board routes commands between devices plugged into it. Boards can plug into other boards (like expansion slots), creating a hierarchy for complex terminal configurations.

## Device and Board Interfaces

```python
class Device:
    """A terminal device - handles specific functionality."""

    def __init__(self, board: 'Board | None' = None):
        self.board = board
        if board:
            board.plug_in(self)

    def query(self, feature_name: str) -> Any:
        """Query device capabilities (terminfo-style)."""
        return None

    def handle_command(self, cmd: Command) -> Command | None:
        """Handle a command. Return None if consumed."""
        return None

    def get_command_handlers(self) -> dict[str, Callable]:
        """What commands this device wants to handle."""
        return {}

class Board:
    """A board that devices plug into - handles command routing."""

    def __init__(self, parent_board: 'Board | None' = None):
        self.devices: list[Device] = []
        self.dispatch_table: dict[str, list[Callable]] = {}
        self.parent = parent_board

        if parent_board:
            parent_board.plug_in_board(self)

    def plug_in(self, device: Device):
        """Plug a device into this board."""
        self.devices.append(device)
        handlers = device.get_command_handlers()
        for cmd_name, handler in handlers.items():
            if cmd_name not in self.dispatch_table:
                self.dispatch_table[cmd_name] = []
            self.dispatch_table[cmd_name].append(handler)

    def plug_in_board(self, board: 'Board'):
        """Plug another board into this one (expansion slot)."""
        self.plug_in(BoardDevice(board))

    def dispatch(self, command: Command) -> Command | None:
        """Route command to devices."""
        handlers = self.dispatch_table.get(command.name, [])
        for handler in handlers:
            result = handler(command)
            if result is None:  # Command consumed
                return None
        return command  # No one handled it

class BoardDevice(Device):
    """Wrapper to make a Board look like a Device for nesting."""

    def __init__(self, board: Board):
        self.wrapped_board = board
        super().__init__(None)  # Don't auto-register

    def handle_command(self, cmd: Command) -> Command | None:
        return self.wrapped_board.dispatch(cmd)
```

## Device Registration

Devices register which commands they handle:

```python
class VT100Monitor(Device):
    def get_command_handlers(self):
        return {
            # C0 controls
            'C0_BS': self.backspace,
            'C0_HT': self.horizontal_tab,

            # CSI sequences - cursor movement
            'CSI_CUU': self.cursor_up,        # ESC[A
            'CSI_CUD': self.cursor_down,      # ESC[B
            'CSI_CUF': self.cursor_forward,   # ESC[C
            'CSI_CUB': self.cursor_back,      # ESC[D
            'CSI_CUP': self.cursor_position,  # ESC[H

            # CSI sequences - screen control
            'CSI_ED': self.erase_display,     # ESC[J
            'CSI_EL': self.erase_line,        # ESC[K
            'CSI_DECSTBM': self.set_scroll_region,  # ESC[r

            # CSI sequences - character attributes
            'CSI_SGR': self.set_graphics_rendition,  # ESC[m
        }

class LinePrinter(Device):
    def get_command_handlers(self):
        return {
            'C0_CR': self.carriage_return,
            'C0_LF': self.line_feed,
            'C0_FF': self.form_feed,
            'C0_VT': self.vertical_tab,
            'TEXT': self.print_text,
        }
```

## Dispatch Flow

1. BiTTY receives bytes from connection device
2. Parser identifies control code or text and creates Command
3. Main board dispatches command to plugged-in devices
4. If device consumes command (returns None), dispatch stops
5. If no device handles it, command is logged as unsupported

```python
class BiTTY:
    def __init__(self):
        self.main_board = Board()
        self.parser = Parser(self)

    def plug_in(self, device: Device) -> None:
        """Plug a device into the main board."""
        self.main_board.plug_in(device)

    def plug_in_board(self, board: Board) -> None:
        """Plug an expansion board into the main board."""
        self.main_board.plug_in_board(board)

    def dispatch(self, command: Command) -> None:
        """Route command through the board hierarchy."""
        result = self.main_board.dispatch(command)
        if result is not None:
            logger.debug(f"Unsupported sequence: {command}")
```

## Inter-Device Communication

Devices can communicate by dispatching commands through their board:

```python
class TextualInput(Device):
    def enable_mouse_tracking(self):
        # Send command to other devices on the board
        mouse_cmd = Command('ENABLE_MOUSE', 'INTERNAL', ('SGR',), None)
        self.board.dispatch(mouse_cmd)

class TextualMonitor(Device):
    def get_command_handlers(self):
        return {
            'ENABLE_MOUSE': self.handle_mouse_enable,
            # ... other handlers
        }

    def handle_mouse_enable(self, command: Command):
        self.mouse_tracking_mode = command.args[0]
        return None  # Command consumed
```

## Example Configurations

### Classic VT100 Terminal
```python
tty = BiTTY()
tty.plug_in(UnixPTY("/bin/bash"))
tty.plug_in(VT100Monitor())
tty.plug_in(PS2Keyboard())
tty.plug_in(AudioBell())
```

### Modern GUI Terminal with Expansion Boards
```python
tty = BiTTY()

# Main terminal connection
tty.plug_in(UnixPTY("/bin/zsh"))

# Input expansion board
input_board = Board(tty.main_board)
TextualKeyboard(input_board)    # Full keyboard support
TextualMouse(input_board)       # Mouse tracking

# Output expansion board
output_board = Board(tty.main_board)
XTermMonitor(output_board)      # 24-bit color, Unicode support
VisualBell(output_board)        # Flash instead of beep
ClipboardManager(output_board)  # OSC 52 clipboard support

# Debug expansion board
debug_board = Board(tty.main_board)
CommandLogger("debug.log", debug_board)    # Logs all commands
SequenceRecorder(debug_board)              # Records for playback
```

### 1960s Teletype (ASR-33)
```python
tty = BiTTY()
tty.plug_in(SerialPort("/dev/ttyS0", baud=110))
tty.plug_in(LinePrinter(width=72, uppercase_only=True))
tty.plug_in(TeletypeKeyboard(uppercase_only=True))
tty.plug_in(MechanicalBell())
```

### Telegraph Terminal (1910s)
```python
tty = BiTTY()
tty.plug_in(TelegraphLine())
tty.plug_in(TelegraphPrinter())     # Prints on paper tape
tty.plug_in(TelegraphKey())         # Morse code input
```

### Complex Multi-Board Configuration
```python
tty = BiTTY()

# Connection
tty.plug_in(UnixPTY("/bin/bash"))

# Video card with multiple displays
video_board = Board(tty.main_board)
primary_monitor = VT100Monitor(video_board)
status_display = StatusLineDisplay(video_board)  # Shows title/status

# Sound card
audio_board = Board(video_board)  # Plugged into video board
AudioBell(audio_board)
SpeechSynthesizer(audio_board)

# Input card with multiple devices
input_board = Board(tty.main_board)
PS2Keyboard(input_board)
PS2Mouse(input_board)
GamepadInput(input_board)  # For terminal games
```

## Historical Accuracy

The architecture supports terminals throughout history:

- **1910s Telegraph**: TelegraphPrinter + TelegraphKey + TelegraphLine
- **1930s Teletype**: LinePrinter + TeletypeKeyboard + CurrentLoop
- **1970s Glass TTY**: CharacterDisplay + ASCIIKeyboard + RS232
- **1978 VT100**: RasterMonitor + VT100Keyboard + RS232
- **1980s PC Terminal**: CGAMonitor + XTKeyboard + SerialPort
- **1990s xterm**: XTermMonitor + X11Input + PTY
- **Modern Terminal**: GPUMonitor + USBInput + PTY

## Benefits

1. **Modularity**: Easy to add new terminal types or features
2. **Educational**: Clear mapping to hardware terminal concepts
3. **Testability**: Components can be tested in isolation
4. **Flexibility**: Mix and match components for different use cases
5. **Historical**: Can accurately emulate terminals from any era
6. **Performance**: Lightweight commands, O(1) dispatch, minimal allocation

## Future Considerations

1. **Component Discovery**: Plugin system for loading components
2. **Command Recording**: Record/replay terminal sessions as command streams
3. **Network Terminals**: Components for SSH, Telnet, serial-over-IP
4. **Graphics**: Sixel, ReGIS, Tektronix graphics as components
5. **Accessibility**: Screen reader component that interprets commands