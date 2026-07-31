"""Simulations of hardware plugged into the board — not part of the terminal.

`devices/` is the terminal; `peripherals/` is what you plug into it. The board
imports nothing from here: it runs identically with every port empty, and a test
asserts that `import bittty` leaves these packages out of `sys.modules`.

See docs/peripherals.md.
"""
