# Unit Test Structure

This tree now mirrors the architecture split:

- `parser/`: parser/tokenizer unit tests. These should assert emitted `Operation` values or parser state-machine behavior, not terminal screen side effects.
- `devices/`: board and direct device tests. These should exercise board routing plus cursor, screen, charset, style, modes, title, keyboard, mouse, control, and query devices through operations or device APIs (reached via `terminal.<device>` or `terminal.board.<device>`).
- `e2e/`: parser-to-terminal integration tests. These keep confidence that real escape sequences still produce the expected terminal behavior.
- `pty/`: platform PTY unit tests.
- root `test_*.py`: lower-level non-device modules such as buffer, transports, style diffing, terminfo capabilities, demo adapters, and platform environment helpers.

Current review notes:

- `parser/test_operations.py` is the preferred parser test style and should be the model for future parser coverage.
- Most former `parser/test_*.py` files asserted terminal side effects, so they have moved to `e2e/`.
- `devices/` now has first-pass coverage for every current device.
- The `Terminal` behavioural facade has been removed; `Terminal` is now a thin lifecycle shell (PTY/process, `resize`, `capture_pane`, `input*`) that exposes the board via `terminal.board` and read-only device handles (`terminal.cursor`, `terminal.screen`, ...). The former `terminal/` facade tests have moved into `devices/` and now drive the devices directly; some still overlap the dedicated `*_device.py` tests and can be consolidated in a future pass.
