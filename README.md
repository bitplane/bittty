# bittty

A pure Python terminal emulator.

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

* 🏃 more performance
* 🏗️ rewrite architecture
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

## Known limitations

- Wide characters, combining characters and grapheme clusters are treated as one cell.
- Resizing is not atomic with concurrent PTY output.
- There is no scrollback buffer or reflow on resize.
