# Unit Test Structure

This tree now mirrors the architecture split:

- `parser/`: parser/tokenizer unit tests. These should assert emitted `Operation` values or parser state-machine behavior, not terminal screen side effects.
- `devices/`: board and direct device tests. These should exercise board routing plus cursor, screen, charset, style, modes, title, keyboard, mouse, control, and query devices through operations or device APIs.
- `e2e/`: parser-to-terminal integration tests. These keep confidence that real escape sequences still produce the expected terminal behavior.
- `terminal/`: compatibility/facade tests for the legacy `Terminal` public API. These should shrink over time as equivalent direct device coverage grows.
- `pty/`: platform PTY unit tests.
- root `test_*.py`: lower-level non-device modules such as buffer, transports, style diffing, terminfo capabilities, demo adapters, and platform environment helpers.

Current review notes:

- `parser/test_operations.py` is the preferred parser test style and should be the model for future parser coverage.
- Most former `parser/test_*.py` files asserted terminal side effects, so they have moved to `e2e/`.
- `devices/` now has first-pass coverage for every current device.
- `terminal/` still has many behavior tests that duplicate device responsibilities. Keep them while the facade remains public, but future passes should either move assertions into `devices/` or collapse them into fewer compatibility smoke tests.
