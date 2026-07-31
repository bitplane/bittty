"""The devices/peripherals boundary, enforced.

`devices/` is the terminal; `peripherals/` is what you plug into it. The board
runs with every port empty, so core must never import a peripheral. See
docs/peripherals.md.
"""

import ast
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "bittty"
PERIPHERALS = SRC / "peripherals"

# What a peripheral is allowed to reach for in core: the ports and cables it
# plugs into, and the configuration the terminal offers it.
CORE_ALLOWED = {"connections", "printer_config", "constants"}


def _module_imports(path: Path) -> set[str]:
    """Absolute and relative module names imported by one source file."""
    tree = ast.parse(path.read_text())
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.add("." * node.level + (node.module or ""))
    return names


def _core_files():
    return [p for p in SRC.rglob("*.py") if PERIPHERALS not in p.parents and p.parent != PERIPHERALS]


def test_importing_bittty_does_not_load_any_peripheral():
    """A board with nothing plugged in must not pay for the peripherals."""
    code = "import bittty, sys; print([m for m in sys.modules if 'bittty.peripherals' in m])"
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert result.stdout.strip() == "[]"


def test_core_never_imports_a_peripheral():
    """The dependency edge runs peripheral -> core, never the reverse."""
    offenders = {}
    for path in _core_files():
        bad = {name for name in _module_imports(path) if "peripherals" in name}
        if bad:
            offenders[path.relative_to(SRC).as_posix()] = sorted(bad)
    assert offenders == {}


def test_peripherals_only_reach_for_ports_cables_and_configuration():
    """A peripheral knows about the cable it plugs into, not about the terminal."""
    offenders = {}
    for path in PERIPHERALS.rglob("*.py"):
        bad = set()
        for name in _module_imports(path):
            if not name.startswith("."):
                continue
            # Relative imports that climb out of the peripherals tree reach core.
            depth = len(name) - len(name.lstrip("."))
            target = name.lstrip(".")
            climbs = depth - 1  # one dot is "this package"
            reaches_core = climbs >= len(path.relative_to(PERIPHERALS).parts) - 1
            if reaches_core and target and target.split(".")[0] not in CORE_ALLOWED:
                bad.add(name)
        if bad:
            offenders[path.relative_to(PERIPHERALS).as_posix()] = sorted(bad)
    assert offenders == {}


def test_the_printer_peripheral_is_reachable_and_self_contained():
    """Importing the peripheral works and pulls its own internals with it."""
    code = (
        "from bittty.peripherals.printer import VirtualPrinter, PrinterModel; "
        "import sys; "
        "print(sorted(m for m in sys.modules if m.startswith('bittty.peripherals')))"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    loaded = result.stdout.strip()
    assert "bittty.peripherals.printer.languages" in loaded
    assert "bittty.peripherals.printer.pages" in loaded
