"""The engine: routes bytes to the active language and owns the switch."""

from __future__ import annotations

from collections.abc import Callable

from .crm import CrmDecoder
from .dec_ppl import DecPplParser
from .mechanism import PrinterMechanism
from .ppds import PpdsParser
from .state import (
    PrinterLanguage,
    VirtualPrinterState,
    _PrinterLayoutCommand,
    _PrinterReportCommand,
)


class _PrinterLanguageEngine:
    """Routes bytes to the decoder for the active language and owns the switch.

    The mechanism outlives the switch; each parser owns only its own state, so a
    new printer language is a new parser class rather than another branch here.
    """

    def __init__(
        self,
        initial_language: PrinterLanguage,
        *,
        supports_proprinter_switching: bool,
        on_printable: Callable[[bytes], None] | None = None,
        on_control: Callable[[int], None] | None = None,
        on_crm_token: Callable[[bytes, str], None] | None = None,
        on_layout: Callable[[_PrinterLayoutCommand, tuple[int, ...]], None] | None = None,
        on_report: Callable[[_PrinterReportCommand], None] | None = None,
        on_bit_image: Callable[[int, int, bool, bytes], None] | None = None,
        on_font_download: Callable[[bytes], None] | None = None,
        on_reset: Callable[[], None] | None = None,
    ) -> None:
        self._initial_language = initial_language
        self._supports_proprinter_switching = supports_proprinter_switching
        self._mechanism = PrinterMechanism(
            on_printable=on_printable,
            on_control=on_control,
            on_crm_token=on_crm_token,
            on_layout=on_layout,
            on_report=on_report,
            on_bit_image=on_bit_image,
            on_font_download=on_font_download,
            on_reset=on_reset,
        )
        self._language = initial_language
        self._saved_modes: tuple[object, ...] | None = None
        self._dec = DecPplParser(self._mechanism, self)
        self._crm = CrmDecoder(self._mechanism, self)
        self._ppds = PpdsParser(self._mechanism, self)

    # --- LanguageControl: what a parser may ask of the engine -------------- #

    @property
    def language(self) -> PrinterLanguage:
        return self._language

    @property
    def supports_proprinter_switching(self) -> bool:
        return self._supports_proprinter_switching

    def enter_ibm(self) -> None:
        """DECIPEM: park the physical settings and hand the stream to PPDS."""
        if self._language is PrinterLanguage.IBM_PROPRINTER:
            return
        self._saved_modes = self._mechanism.snapshot()
        self._ppds.reset()
        self._mechanism.layout(_PrinterLayoutCommand.IBM_LANGUAGE_ENTER)
        self._language = PrinterLanguage.IBM_PROPRINTER

    def leave_ibm(self) -> None:
        """Restore the parked settings and hand the stream back to DEC PPL."""
        if self._language is not PrinterLanguage.IBM_PROPRINTER:
            return
        self._mechanism.layout(_PrinterLayoutCommand.IBM_LANGUAGE_LEAVE)
        if self._saved_modes is not None:
            self._mechanism.restore(self._saved_modes)
        self._saved_modes = None
        self._language = PrinterLanguage.DEC_PPL
        self._dec.reset()

    # --- the printer's view ------------------------------------------------ #

    @property
    def state(self) -> VirtualPrinterState:
        ibm = self._language is PrinterLanguage.IBM_PROPRINTER
        return VirtualPrinterState(
            self._language,
            self._mechanism.direction,
            proportional_spacing=self._mechanism.proportional_spacing,
            pitch_from_font=self._mechanism.pitch_from_font,
            carriage_return_new_line=self._mechanism.carriage_return_new_line,
            autowrap=self._mechanism.autowrap,
            control_representation=self._mechanism.control_representation,
            line_feed_new_line=self._mechanism.line_feed_new_line,
            position_unit_mode=self._mechanism.position_unit_mode,
            rendition=self._mechanism.rendition,
            characters=self._mechanism.characters,
            double_width=self._ppds.double_width if ibm else False,
            double_height=self._ppds.double_height if ibm else False,
            ibm_character_set=self._ppds.character_set if ibm else 1,
            ibm_code_page=self._ppds.code_page,
            printer_selected=self._ppds.selected if ibm else True,
            ibm_downloaded_font=self._ppds.downloaded_font if ibm else False,
        )

    def reset(self) -> None:
        """Apply a power-on reset and discard any partial input sequence."""
        self._language = self._initial_language
        self._mechanism.reset_modes()
        self._mechanism.power_on_reset()
        self._dec.reset()
        self._crm.reset()
        self._ppds.reset()
        self._saved_modes = None

    def set_ibm_code_page(self, code_page: int) -> None:
        """Apply the code page selected by the physical printer adapter."""
        self._ppds.code_page = code_page

    def feed(self, data: bytes) -> None:
        """Consume one arbitrary stream fragment."""
        offset = 0
        size = len(data)
        while offset < size:
            if self._language is PrinterLanguage.IBM_PROPRINTER:
                offset = self._ppds.feed(data, offset)
            elif self._mechanism.control_representation:
                offset = self._crm.feed(data, offset)
            else:
                offset = self._dec.feed(data, offset)
