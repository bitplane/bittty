# bittty

A pure Python terminal emulator.

Almost usable; some scroll region problems, doesn't like textual in textual yet.

## Demo

Run the standalone demo:

```bash
python ./demo/terminal.py
```

Or use the textual demo to see it in a TUI:

```bash
uvx textual-tty
```

## Links

* [🏠 home](https://bitplane.net/dev/python/bittty)
* [📖 pydoc](https://bitplane.net/dev/python/bittty/pydoc)
* [🐍 pypi](https://pypi.org/project/bittty)
* [🐱 github](https://github.com/bitplane/bittty)

## License

WTFPL with one additional clause

1. Don't blame me

Do wtf you want, but don't blame me when it rips a hole in your trousers.

## Recent changes

* 🔙 DECLM - allow `\n` to act like `\r\n` so we don't have to rely on cooked
  input on the pty when using as a library.
* 🖼️ DEC Special Graphics
* 🐌 Faster colour/style parser
* ⛓️‍💥 Split out from `textual-tty` into separate package

## bugs / todo

- [ ] [architecture](architecture)
- [ ] gui
  - [ ] make a terminal input class, for standalone input
  - [ ] make `framebuffer.py`
  - [ ] choose a display driver
- [ ] performance improvements
  - [ ] parse with regex over large buffer sizes
  - [ ] line cache for outputs
- [ ] scrollback buffer
  - [ ] implement `logloglog` for scrollback with wrapping
- [ ] bugs
  - [ ] corruption in stream - debug it
  - [ ] scroll region: scroll up in `vim` corrupts outside scroll region
- [ ] add terminal overlay visuals
  - [ ] bell flash effect
  - [ ] make cursor an overlay
  - [ ] make mouse an overlay
  - [ ] debug overlay for scroll regions
- [ ] Support themes
- [ ] bittty-specific escape sequences
  - [ ] visible mouse on / off
  - [ ] debugging info
  - [ ] record
  - [ ] list sequences + values

## Unhandled modes

*   **`DECRLM` (Right-to-Left-Language Mode):** Enables right-to-left language support.
