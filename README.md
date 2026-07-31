# bittty

A pure Python terminal emulator library. `Board` is an embeddable, headless
emulator core; the demo and `textual-tty` provide terminal frontends.

It was written as an alternative to `pyte`, and currently does not have a
graphical front-end.

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
  * [🚦 terminal mode support](https://bitplane.net/dev/python/bittty/DEC_private.html)
* [🐍 pypi](https://pypi.org/project/bittty)
* [🐱 github](https://github.com/bitplane/bittty)

## License

WTFPL with one additional clause

1. Don't blame me

Do wtf you want, but don't blame me when it rips a hole in your trousers.

## Known limitations

- Resizing is not atomic with concurrent PTY output.
- There is no scrollback buffer or reflow on resize.
- Printer pages cover DEC PPL text, layout, rendition, model-driven duplex reports, and status; graphics, font-file metrics, SSU-selected units, and mechanical timing remain unsupported.
