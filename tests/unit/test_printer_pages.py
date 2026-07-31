from dataclasses import FrozenInstanceError

import pytest

from bittty import (
    LETTER_PAGE_GEOMETRY,
    PRINT_UNITS_PER_INCH,
    PrintDirection,
    PrinterLanguage,
    PrinterPage,
    PrinterPageGeometry,
    PrinterPageItem,
    PrinterRect,
    PrinterTextRun,
    PrinterType,
    VirtualPrinter,
    VirtualPrinterState,
)
from bittty.printer_pages import _PrinterPageStore


def _item(left: int) -> PrinterPageItem:
    return PrinterPageItem(PrinterRect(left, 20, left + 10, 30))


def test_letter_geometry_uses_exact_physical_units():
    assert PRINT_UNITS_PER_INCH == 21_600
    assert LETTER_PAGE_GEOMETRY == PrinterPageGeometry(
        width=183_600,
        height=237_600,
        printable_area=PrinterRect(0, 0, 183_600, 237_600),
    )
    assert LETTER_PAGE_GEOMETRY.printable_area.width == 183_600
    assert LETTER_PAGE_GEOMETRY.printable_area.height == 237_600


@pytest.mark.parametrize(
    "values, error",
    (
        ((2, 0, 1, 0), ValueError),
        ((0, 2, 0, 1), ValueError),
        ((0.0, 0, 1, 1), TypeError),
        ((False, 0, 1, 1), TypeError),
    ),
)
def test_rect_rejects_invalid_coordinates(values, error):
    with pytest.raises(error):
        PrinterRect(*values)


def test_rect_allows_unclamped_negative_display_list_bounds():
    rect = PrinterRect(-20, -10, 5, 5)
    assert rect.width == 25
    assert rect.height == 15


@pytest.mark.parametrize(
    "width, height, printable_area, error",
    (
        (0, 10, PrinterRect(0, 0, 0, 10), ValueError),
        (10, 0, PrinterRect(0, 0, 10, 0), ValueError),
        (10.0, 10, PrinterRect(0, 0, 10, 10), TypeError),
        (10, True, PrinterRect(0, 0, 10, 1), TypeError),
        (10, 10, PrinterRect(-1, 0, 10, 10), ValueError),
        (10, 10, PrinterRect(0, -1, 10, 10), ValueError),
        (10, 10, PrinterRect(0, 0, 11, 10), ValueError),
        (10, 10, PrinterRect(0, 0, 10, 11), ValueError),
        (10, 10, (0, 0, 10, 10), TypeError),
    ),
)
def test_geometry_rejects_invalid_dimensions_and_printable_areas(width, height, printable_area, error):
    with pytest.raises(error):
        PrinterPageGeometry(width, height, printable_area)


def test_public_page_records_are_frozen_and_validate_contents():
    rect = PrinterRect(0, 0, 10, 10)
    geometry = PrinterPageGeometry(10, 10, rect)
    item = PrinterPageItem(rect)
    page = PrinterPage(1, geometry, (item,))

    with pytest.raises(FrozenInstanceError):
        rect.left = 1
    with pytest.raises(FrozenInstanceError):
        geometry.width = 20
    with pytest.raises(FrozenInstanceError):
        item.bounds = PrinterRect(1, 1, 2, 2)
    with pytest.raises(FrozenInstanceError):
        page.number = 2

    with pytest.raises(ValueError):
        PrinterPage(0, geometry)
    with pytest.raises(TypeError):
        PrinterPage(1, geometry, [item])
    with pytest.raises(TypeError):
        PrinterPage(1, geometry, ("not an item",))


def test_text_run_validates_ascii_decoding_advance_and_state():
    state = VirtualPrinterState(PrinterLanguage.DEC_PPL, PrintDirection.BIDIRECTIONAL)
    bounds = PrinterRect(0, 0, 2160, 3600)
    run = PrinterTextRun(bounds, b"A", "A", 2160, state)
    assert run.text == "A"

    with pytest.raises(ValueError):
        PrinterTextRun(bounds, b"", "", 2160, state)
    with pytest.raises(ValueError):
        PrinterTextRun(bounds, b"A", "B", 2160, state)
    with pytest.raises(ValueError):
        PrinterTextRun(bounds, b"\xa0", "\xa0", 2160, state)
    with pytest.raises(ValueError):
        PrinterTextRun(bounds, b"A", "A", 1000, state)
    with pytest.raises(TypeError):
        PrinterTextRun(bounds, b"A", "A", 2160, "not state")


def test_current_page_snapshots_do_not_alias_the_mutable_store():
    store = _PrinterPageStore(LETTER_PAGE_GEOMETRY)
    first = _item(10)
    second = _item(30)

    before = store.current_page
    store.append(first)
    after_first = store.current_page
    store.append(second)
    after_second = store.current_page

    assert before.items == ()
    assert after_first.items == (first,)
    assert after_second.items == (first, second)
    assert before.number == after_first.number == after_second.number == 1


def test_conditional_and_forced_completion_preserve_order_and_numbering():
    store = _PrinterPageStore(LETTER_PAGE_GEOMETRY)
    first = _item(10)
    second = _item(30)

    assert store.complete() is None
    assert store.current_page.number == 1

    store.append(first)
    store.append(second)
    page_one = store.complete()
    assert page_one == PrinterPage(1, LETTER_PAGE_GEOMETRY, (first, second))
    assert store.current_page == PrinterPage(2, LETTER_PAGE_GEOMETRY)

    page_two = store.complete(force=True)
    assert page_two == PrinterPage(2, LETTER_PAGE_GEOMETRY)
    assert store.current_page == PrinterPage(3, LETTER_PAGE_GEOMETRY)
    assert store.completed_pages == (page_one, page_two)


def test_completed_pages_can_be_observed_then_drained_exactly_once():
    store = _PrinterPageStore(LETTER_PAGE_GEOMETRY)
    store.append(_item(10))
    page = store.complete()
    current_before = store.current_page

    assert store.completed_pages == (page,)
    assert store.completed_pages == (page,)
    assert store.take_completed_pages() == (page,)
    assert store.take_completed_pages() == ()
    assert store.completed_pages == ()
    assert store.current_page == current_before


def test_page_items_are_not_clamped_to_the_physical_sheet():
    item = PrinterPageItem(PrinterRect(200_000, 300_000, 200_010, 300_010))
    page = PrinterPage(1, LETTER_PAGE_GEOMETRY, (item,))
    assert page.items == (item,)


def test_virtual_printer_exposes_fixed_custom_geometry_and_empty_page():
    geometry = PrinterPageGeometry(
        width=1000,
        height=2000,
        printable_area=PrinterRect(100, 200, 900, 1800),
    )
    printer = VirtualPrinter(page_geometry=geometry)

    assert printer.page_geometry is geometry
    assert printer.current_page == PrinterPage(1, geometry)
    assert printer.completed_pages == ()
    assert printer.take_completed_pages() == ()
    with pytest.raises(AttributeError):
        printer.page_geometry = LETTER_PAGE_GEOMETRY


def test_virtual_printer_records_one_positioned_ascii_run():
    printer = VirtualPrinter()
    printer.write_bytes(b"hello")

    assert printer.current_page.items == (
        PrinterTextRun(
            PrinterRect(0, 0, 10_800, 3600),
            b"hello",
            "hello",
            10_800,
            VirtualPrinterState(PrinterLanguage.DEC_PPL, PrintDirection.BIDIRECTIONAL),
        ),
    )


def test_text_origin_uses_the_custom_printable_area():
    geometry = PrinterPageGeometry(
        20_000,
        30_000,
        PrinterRect(1000, 2000, 19_000, 29_000),
    )
    printer = VirtualPrinter(page_geometry=geometry)
    printer.write_bytes(b"A")

    run = printer.current_page.items[0]
    assert run.bounds == PrinterRect(1000, 2000, 3160, 5600)


def test_ignored_controls_are_not_recorded_as_printable_data():
    printer = VirtualPrinter()
    printer.write_bytes(b"A\x00B\x07C\x0aD\x7fE\x81F")

    assert bytes(printer.data) == b"A\x00B\x07C\x0aD\x7fE\x81F"
    assert len(printer.current_page.items) == 1
    run = printer.current_page.items[0]
    assert isinstance(run, PrinterTextRun)
    assert run.data == b"ABCDEF"
    assert run.text == "ABCDEF"
    assert run.advance == 6 * 2160


def test_non_ascii_printable_bytes_are_retained_without_decoding():
    printer = VirtualPrinter()
    printer.write_bytes(b"A\xa0\xffB")

    first, undecoded, last = printer.current_page.items
    assert (first.data, first.text) == (b"A", "A")
    assert (undecoded.data, undecoded.text) == (b"\xa0\xff", None)
    assert (last.data, last.text) == (b"B", "B")
    assert first.bounds.left == 0
    assert undecoded.bounds.left == 2160
    assert last.bounds.left == 6480


def test_fragmented_printable_input_coalesces_to_the_same_page_snapshot():
    payload = b"fragmented printable text"
    whole = VirtualPrinter()
    whole.write_bytes(payload)

    for boundary in range(len(payload) + 1):
        streamed = VirtualPrinter()
        streamed.write_bytes(payload[:boundary])
        streamed.write_bytes(payload[boundary:])
        assert streamed.current_page == whole.current_page


def test_bytewise_printable_input_uses_one_pending_run():
    payload = b"bytewise input remains linear"
    printer = VirtualPrinter()
    for byte in payload:
        printer.write_bytes(bytes((byte,)))

    assert len(printer.current_page.items) == 1
    assert printer.current_page.items[0].data == payload


def test_mode_changes_split_runs_and_capture_the_state_at_each_write():
    printer = VirtualPrinter()
    printer.write_bytes(b"A\x1b[?41hB")

    first, second = printer.current_page.items
    assert isinstance(first, PrinterTextRun)
    assert isinstance(second, PrinterTextRun)
    assert first.data == b"A"
    assert first.state.direction is PrintDirection.BIDIRECTIONAL
    assert second.data == b"B"
    assert second.state.direction is PrintDirection.UNIDIRECTIONAL
    assert second.bounds.left == first.bounds.right


def test_page_assembly_is_deferred_in_ibm_and_control_representation_modes():
    ibm = VirtualPrinter(PrinterType.PROPRINTER)
    ibm.write_bytes(b"not interpreted yet")
    assert ibm.current_page.items == ()

    crm = VirtualPrinter()
    crm.write_bytes(b"\x1b[3hnot represented yet")
    assert crm.current_page.items == ()


def test_printable_runs_advance_beyond_the_page_without_wrapping_yet():
    geometry = PrinterPageGeometry(3000, 4000, PrinterRect(0, 0, 3000, 4000))
    printer = VirtualPrinter(page_geometry=geometry)
    printer.write_bytes(b"AB")

    run = printer.current_page.items[0]
    assert run.bounds == PrinterRect(0, 0, 4320, 3600)


def test_spaces_advance_and_are_recorded_without_marking_the_page():
    printer = VirtualPrinter()
    printer.write_bytes(b"   ")

    assert printer.current_page.items[0].data == b"   "
    assert printer._page_store.complete() is None
    assert printer.current_page.number == 1


def test_draining_pages_does_not_change_language_state_raw_trace_or_current_page():
    printer = VirtualPrinter()
    printer.write_bytes(b"raw\x1b[?41h")
    printer._page_store.append(_item(10))
    completed = printer._page_store.complete()
    current_before = printer.current_page

    assert printer.take_completed_pages() == (completed,)
    assert printer.current_page == current_before
    assert bytes(printer.data) == b"raw\x1b[?41h"
    assert printer.state == VirtualPrinterState(
        PrinterLanguage.DEC_PPL,
        PrintDirection.UNIDIRECTIONAL,
    )


def test_reset_does_not_clear_or_complete_page_storage():
    printer = VirtualPrinter()
    printer._page_store.append(_item(10))
    current_before = printer.current_page

    printer.reset()

    assert printer.current_page == current_before
    assert printer.completed_pages == ()
