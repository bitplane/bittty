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

## Links

* [🏠 home](https://bitplane.net/dev/python/bittty)
* [📖 pydoc](https://bitplane.net/dev/python/bittty/pydoc)
* [🐍 pypi](https://pypi.org/project/bittty)
* [🐱 github](https://github.com/bitplane/bittty)

## License

WTFPL with one additional clause

1. Don't blame me

Do wtf you want, but don't blame me when it rips a hole in your trousers.

## bugs / todo

- [x] split pty out into a cross platform package
- [ ] gui
  - [ ] make a terminal input class, for standalone input
  - [ ] make `framebuffer.py`
  - [ ] choose a backend
- [ ] performance improvements
  - [ ] parse with regex over large buffer sizes
  - [x] lru_cache style handling
  - [ ] line cache for outputs
- [ ] scrollback buffer
  - [ ] implement `logloglog` for scrollback with wrapping
- [ ] bugs
  - [x] blank background to end of line
  - [ ] corruption in stream - debug it
  - [ ] scroll region: scroll up in `vim` corrupts outside scroll region
  - [ ] DEC Special Graphics not working
- [ ] add terminal visuals
  - [ ] bell flash effect
- [ ] Support themes
