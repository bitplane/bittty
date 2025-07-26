# bittty

A pure Python terminal emulator.

Currently buggy and a bit slow, but it's still somewhat usable.

## Demo

Run the standalone demo:

```bash
python ./demo/terminal.py
```

Or use the textual demo to see it in a TUI:

```bash
uvx textual-tty
```

## Usage

There's 3 main classes:

1. `Terminal`, a standalone terminal that doesn't need Textual.
2. `TextualTerminal`, a tty widget subclass.
3. `TerminalApp`, a terminal emulator in a window.

Read the demo code for more info.

## Links

* [🏠 home](https://bitplane.net/dev/python/bittty)
* [🐍 pypi](https://pypi.org/project/bittty)
* [🐱 github](https://github.com/bitplane/bittty)

## License

WTFPL with one additional clause

1. Don't blame me

Do wtf you want, but don't blame me when it rips a hole in your trousers.

## todo / ideas

- [ ] split pty out into a cross platform package
- [x] break terminal project out from Textual deps
  - [x] write a minimal demo that doesn't need textual
  - [ ] gui
    - [ ] make `framebuffer.py`
    - [ ] choose a backend
- [ ] performance improvements
  - [ ] parse with regex over large buffer sizes
- [ ] scrollback buffer
  - [ ] implement `logloglog` for scrollback with wrapping
- [ ] bugs
  - [ ] blank background to end of line
  - [ ] corruption in stream - debug it
  - [ ] scroll region: scroll up in `vim` corrupts outside scroll region
- [ ] reduce redundancy redundancy of repeated repeated code code
  - [ ] code code of of redundancy redundancy
- [ ] add terminal visuals
  - [ ] bell flash effect
- [ ] Support themes
