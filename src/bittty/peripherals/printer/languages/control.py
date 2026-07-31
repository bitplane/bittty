"""The narrow interface a language parser may use to reach its engine."""

from __future__ import annotations

from typing import Protocol

from .state import PrinterLanguage


class LanguageControl(Protocol):
    """What a language parser may ask of the engine that owns it."""

    @property
    def language(self) -> PrinterLanguage: ...

    @property
    def supports_proprinter_switching(self) -> bool: ...

    def enter_ibm(self) -> None: ...

    def leave_ibm(self) -> None: ...
