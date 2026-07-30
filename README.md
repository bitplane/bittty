# bittty

A pure Python terminal emulator. `Board` is an embeddable, headless emulator core;
the demo and `textual-tty` provide terminal frontends.

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
* [🚦 terminal mode support](docs/DEC_private.md)
* [🐍 pypi](https://pypi.org/project/bittty)
* [🐱 github](https://github.com/bitplane/bittty)

## License

WTFPL with one additional clause

1. Don't blame me

Do wtf you want, but don't blame me when it rips a hole in your trousers.

## Known limitations

- Resizing is not atomic with concurrent PTY output.
- There is no scrollback buffer or reflow on resize.
