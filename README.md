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

## Recent changes

* DEC Special Graphics
* Faster colour/style parser
* Split out from `textual-tty` into separate package

## bugs / todo

- [ ] gui
  - [ ] make a terminal input class, for standalone input
  - [ ] make `framebuffer.py`
  - [ ] choose a backend
- [ ] performance improvements
  - [ ] parse with regex over large buffer sizes
  - [ ] line cache for outputs
- [ ] scrollback buffer
  - [ ] implement `logloglog` for scrollback with wrapping
- [ ] bugs
  - [ ] corruption in stream - debug it
  - [ ] scroll region: scroll up in `vim` corrupts outside scroll region
- [ ] add terminal visuals
  - [ ] bell flash effect
- [ ] Support themes

## Unhandled modes

*   **`KAM` (Keyboard Action Mode):** Determines how the keyboard is locked.
*   **`HEM` (Horizontal Editing Mode):** Manages horizontal editing.
*   **`PUM` (Positioning Unit Mode):** Defines the unit for positioning.
*   **`VEM` (Vertical Editing Mode):** Manages vertical editing.
*   **`GATM` (Guarded Area Transfer Mode):** Controls the transfer of data in guarded areas.
*   **`TAT` (Tabulation at All Positions):** Enables tabulation at any position.
*   **`TSM` (Tabulation Stop Mode):** Manages tabulation stops.
*   **`DFM` (Delete Form Mode):** Controls the form of deletion.
*   **`FEAM` (Format Effector Action Mode):** Determines the action of format effectors.
*   **`FETM` (Format Effector Transfer Mode):** Controls the transfer of format effectors.
*   **`MATM` (Multiple Area Transfer Mode):** Manages the transfer of multiple areas.
*   **`TTM` (Transfer Termination Mode):** Controls the termination of data transfer.
*   **`SATM` (Selected Area Transfer Mode):** Manages the transfer of selected areas.
*   **`TSM` (Tabulation Stop Mode):** Manages tabulation stops.
*   **`EBM` (Editing Boundary Mode):** Controls the boundary for editing.
*   **`DCKM` (Data-Compression Mode):** Manages data compression.
*   **`ZDM` (Zero-Default Mode):** Controls the use of zero as a default value.
*   **`NRM` (Numeric-Representation Mode):** Manages the representation of numeric values.
*   **`GRCM` (Graphic-Rendition-Combination Mode):** Controls the combination of graphic renditions.
*   **`DECCOLM` (Column Mode):** Switches between 80 and 132 columns per line.
*   **`DECSCNM` (Screen Mode):** Switches between normal and reverse screen video.
*   **`DECOM` (Origin Mode):** Sets the origin for cursor positioning.
*   **`DECINLM` (Interlace Mode):** Sets the interlace mode for display.
*   **`DECPFF` (Print-Form-Feed Mode):** Controls the action of the form-feed character.
*   **`DECPEX` (Printer-Extent Mode):** Sets the extent of the printer.
*   **`DECTEK` (Tektronix Mode):** Switches to Tektronix graphics mode.
*   **`DECKBUM` (Keyboard-Usage Mode):** Controls the usage of the keyboard.
*   **`DECNAKB` (Greek-National-Replacement-Keyboard Mode):** Enables the Greek national replacement keyboard.
*   **`DECRLM` (Right-to-Left-Language Mode):** Enables right-to-left language support.
*   **`DECHCCM` (Hebrew-Character-Set-Control Mode):** Controls the Hebrew character set.
*   **`DECVCCM` (VT52-Cursor-Control Mode):** Enables VT52 cursor control.
*   **`DECPCCM` (PC-Crossing-Character-Set Mode):** Enables the PC crossing character set.
*   **`DECNCSM` (National-Character-Set Mode):** Sets the national character set.
*   **`DECRLCM` (Right-to-Left-Copy Mode):** Controls the copy direction for right-to-left languages.
*   **`DECCRTSM` (CRT-Save Mode):** Enables the CRT save mode.
*   **`DECARSM` (Auto-Resize Mode):** Enables auto-resizing of the terminal.
*   **`DECMCM` (Modem-Control Mode):** Controls the modem.
*   **`DECAAM` (Auto-Answerback Mode):** Enables auto-answerback.
*   **`DECCANSM` (Conceal-Answerback-Message Mode):** Conceals the answerback message.
*   **`DECNULM` (Null-Modem Mode):** Enables null-modem support.
*   **`DECHDPXM` (Half-Duplex-Mode):** Enables half-duplex communication.
*   **`DECESKM` (Enable-Secondary-Keyboard-Language-Mode):** Enables a secondary keyboard language.
*   **`DECOSCNM` (Other-Screen-Function-Mode):** Enables other screen functions.
