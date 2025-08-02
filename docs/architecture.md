# BitTTY Architecture: A Hardware-Inspired Terminal Emulator

## Overview

BitTTY is designed as a "metal box" - a central hub that mirrors the architecture of hardware terminals from the telegraph era to modern video terminals. Components are attached to provide specific functionality, just like adding cards or peripherals to physical terminal hardware.

## Core Concepts

### The Metal Box (BitTTY)

The BitTTY class is the chassis that:
- Parses incoming byte streams into control codes and text
- Maintains a dispatch table for routing control codes to components
- Manages component registration and capability queries
- Handles the basic command routing between components

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

### Components (Devices)

Components are pluggable modules that handle specific terminal functionality:

#### Printer Component
- Handles line-oriented output (like a teletype printer)
- Implements line printing modes (LNM, etc.)
- Can be used for logging or actual printing
- Registers for: CR, LF, FF, VT, and print-related control codes
- State: page position, margins, tab stops

#### Monitor Component
- Handles screen-oriented output (like a CRT display)
- Manages screen buffers, cursor position, and visual attributes
- Implements scroll regions, screen clearing, and cursor movement
- Registers for: CSI sequences for cursor control, ED, EL, scroll commands, SGR
- State: screen buffers, cursor position, colors, scroll regions

#### Input Component
- Handles keyboard, mouse, and other input devices
- Manages input modes (application keypad, mouse tracking, etc.)
- Translates hardware events into terminal input sequences
- Platform-specific implementations (TextualInput, QtInput, WebInput, etc.)
- State: keyboard modes, mouse tracking state, key mappings

#### PTY Component
- Manages the connection to the actual process
- Handles process spawning and I/O
- Platform-specific (UnixPTY, WindowsPTY, StdioPTY)
- State: process handle, file descriptors

#### Bell Component
- Handles BEL character
- Can produce audio, visual flash, or system notification
- Registers for: BEL (0x07)

## Component Interface

```python
class Component:
    """Base class for all terminal components."""

    def attach(self, terminal: BitTTY) -> None:
        """Called when component is attached to terminal."""
        self.terminal = terminal

    def detach(self) -> None:
        """Called when component is removed from terminal."""
        self.terminal = None

    def get_capabilities(self) -> Dict[str, Any]:
        """Return device capabilities for terminfo/termcap queries."""
        return {}

    def register_commands(self) -> Dict[str, Callable]:
        """Return mapping of control codes to handler methods."""
        return {}

    def receive_command(self, command: Command) -> None:
        """Handle an incoming command (for inter-component communication)."""
        pass
```

## Control Code Registration

Components register which control codes they handle:

```python
class VT100Monitor(Component):
    def register_commands(self):
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

class LinePrinter(Component):
    def register_commands(self):
        return {
            'C0_CR': self.carriage_return,
            'C0_LF': self.line_feed,
            'C0_FF': self.form_feed,
            'C0_VT': self.vertical_tab,
            'TEXT': self.print_text,
        }
```

## Dispatch Flow

1. BitTTY receives bytes from PTY component
2. Parser identifies control code or text and creates Command
3. Dispatcher looks up handler in registration table
4. If found, calls component's handler with command
5. If not found, logs unsupported sequence

```python
class BitTTY:
    def __init__(self):
        self.components = []
        self.dispatch_table = {}

    def add(self, component: Component) -> None:
        """Add a component to the terminal."""
        self.components.append(component)
        component.attach(self)

        # Update dispatch table with component's handlers
        handlers = component.register_commands()
        for code, handler in handlers.items():
            if code not in self.dispatch_table:
                self.dispatch_table[code] = []
            self.dispatch_table[code].append(handler)

    def dispatch(self, command: Command) -> None:
        """Route command to appropriate component handlers."""
        handlers = self.dispatch_table.get(command.name, [])
        if handlers:
            for handler in handlers:
                handler(command)
        else:
            logger.debug(f"Unsupported sequence: {command}")
```

## Inter-Component Communication

Components can communicate through the terminal's command bus:

```python
class TextualInput(Component):
    def enable_mouse_tracking(self):
        # Tell monitor we need mouse events
        self.terminal.send_command(
            Command('ENABLE_MOUSE', 'INTERNAL', ('SGR',), None),
            target='monitor'
        )

class TextualMonitor(Component):
    def receive_command(self, command: Command):
        if command.name == 'ENABLE_MOUSE':
            self.mouse_tracking_mode = command.args[0]
```

## Example Configurations

### Classic VT100 Terminal
```python
tty = BitTTY()
tty.add(UnixPTY("/bin/bash"))
tty.add(VT100Monitor())
tty.add(PS2Keyboard())
tty.add(AudioBell())
```

### 1960s Teletype (ASR-33)
```python
tty = BitTTY()
tty.add(SerialPort("/dev/ttyS0", baud=110))
tty.add(LinePrinter(width=72, uppercase_only=True))
tty.add(TeletypeKeyboard(uppercase_only=True))
tty.add(MechanicalBell())
```

### Modern GUI Terminal
```python
tty = BitTTY()
tty.add(UnixPTY("/bin/zsh"))
tty.add(XTermMonitor())         # Supports 24-bit color, Unicode
tty.add(TextualInput())         # Full keyboard + mouse
tty.add(VisualBell())          # Flash instead of beep
tty.add(ClipboardManager())     # OSC 52 clipboard support
```

### Telegraph Terminal (1910s)
```python
tty = BitTTY()
tty.add(TelegraphLine())
tty.add(TelegraphPrinter())     # Prints on paper tape
tty.add(TelegraphKey())         # Morse code input
```

### Debug Configuration
```python
tty = BitTTY()
tty.add(UnixPTY("/bin/bash"))
tty.add(VT100Monitor())
tty.add(PS2Keyboard())
tty.add(CommandLogger("debug.log"))  # Logs all commands
tty.add(SequenceRecorder())         # Records for playback
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
