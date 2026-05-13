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

* 🐛 scroll region: scroll up in `vim` corrupts outside scroll region
* 🏃 squeeze another 15% performance out of it
* ✀ fix utf8 and escape code splitting across buffer boundaries
* 🪟 tests run on Windows runner
* 📉 added parser benchmarking and tui graphs
* 🐌 use regex for parsing to speed things up a tad (~2x faster)
* 📚 document half a billion DEC private modes we don't support
* 🔙 DECLM - allow `\n` to act like `\r\n` so we don't have to rely on cooked
  input on the pty when using as a library.
* 🖼️ DEC Special Graphics
* 🐌 Faster colour/style parser
* ⛓️‍💥 Split out from `textual-tty` into separate package

## bugs / todo

- [ ] Implement [grapheme clustering](https://mitchellh.com/writing/grapheme-clusters-in-terminals)
  (thanks Xavier G)
- [ ] `SIGWINCH` handler atomicity + buffer resizes
- [ ] [architecture](architecture) - pretty big
- [ ] gui
  - [ ] make a terminal input class, for standalone input
  - [ ] make `framebuffer.py`
  - [ ] choose a display driver
- [ ] performance improvements
  - [ ] reconsider CSI end char approach
  - [ ] line cache for outputs
  - [.] revisit colours / styles
- [ ] scrollback buffer
  - [ ] implement `logloglog` for scrollback with wrapping
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
- [ ] Document all the escape sequences
  - [ ] collect books for a terminal library
