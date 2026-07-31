from dataclasses import FrozenInstanceError

import pytest

from bittty import (
    LETTER_PAGE_GEOMETRY,
    PRINT_UNITS_PER_INCH,
    PrintDirection,
    PrinterControlToken,
    PrinterLanguage,
    PrinterPage,
    PrinterPageGeometry,
    PrinterPageItem,
    PrinterRect,
    PrinterRenditionSpan,
    PrinterTextRun,
    PrinterType,
    PrinterUnderline,
    VirtualPrinter,
    VirtualPrinterState,
)
from bittty.printer_pages import _PrinterPageStore


def _item(left: int) -> PrinterPageItem:
    return PrinterPageItem(PrinterRect(left, 20, left + 10, 30))


def _cell_geometry(columns: int, lines: int, *, left: int = 0, top: int = 0) -> PrinterPageGeometry:
    right = left + columns * 2160
    bottom = top + lines * 3600
    return PrinterPageGeometry(right + left, bottom + top, PrinterRect(left, top, right, bottom))


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


def test_control_token_validates_source_text_advance_and_state():
    state = VirtualPrinterState(
        PrinterLanguage.DEC_PPL,
        PrintDirection.BIDIRECTIONAL,
        control_representation=True,
    )
    bounds = PrinterRect(0, 0, 8640, 3600)
    token = PrinterControlToken(bounds, b"\x08", "<BS>", 8640, state)
    assert token.text == "<BS>"

    with pytest.raises(ValueError):
        PrinterControlToken(bounds, b"", "<BS>", 8640, state)
    with pytest.raises(ValueError):
        PrinterControlToken(bounds, b"\x08", "", 8640, state)
    with pytest.raises(ValueError):
        PrinterControlToken(bounds, b"\x08", "<BS>", 2160, state)
    with pytest.raises(TypeError):
        PrinterControlToken(bounds, b"\x08", "<BS>", 8640, "not state")


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


def test_ignored_nonpositioning_controls_are_not_recorded_as_printable_data():
    printer = VirtualPrinter()
    printer.write_bytes(b"A\x00B\x07C\x0aD\x7fE\x81F")

    assert bytes(printer.data) == b"A\x00B\x07C\x0aD\x7fE\x81F"
    first, second = printer.current_page.items
    assert (first.data, first.text, first.advance) == (b"ABC", "ABC", 3 * 2160)
    assert (second.data, second.text, second.advance) == (b"DEF", "DEF", 3 * 2160)
    assert second.bounds.top == 3600


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


def test_page_assembly_is_deferred_in_ibm_mode():
    ibm = VirtualPrinter(PrinterType.PROPRINTER)
    ibm.write_bytes(b"not interpreted yet")
    assert ibm.current_page.items == ()


def test_printable_runs_delay_wrap_until_the_next_character():
    geometry = _cell_geometry(3, 2)
    printer = VirtualPrinter(page_geometry=geometry)
    printer.write_bytes(b"ABC")

    run = printer.current_page.items[0]
    assert run.bounds == PrinterRect(0, 0, 6480, 3600)

    printer.write_bytes(b"D")
    wrapped = printer.current_page.items[-1]
    assert (wrapped.data, wrapped.bounds) == (b"D", PrinterRect(0, 3600, 2160, 7200))


def test_wrapping_batches_runs_by_line_and_is_stream_fragment_invariant():
    geometry = _cell_geometry(3, 2)
    payload = b"ABCDEFGHIJ"
    whole = VirtualPrinter(page_geometry=geometry)
    whole.write_bytes(payload)

    assert [item.data for item in whole.completed_pages[0].items] == [b"ABC", b"DEF"]
    assert [item.data for item in whole.current_page.items] == [b"GHI", b"J"]

    for boundary in range(len(payload) + 1):
        streamed = VirtualPrinter(page_geometry=geometry)
        streamed.write_bytes(payload[:boundary])
        streamed.write_bytes(payload[boundary:])
        assert streamed.completed_pages == whole.completed_pages
        assert streamed.current_page == whole.current_page


def test_deccawm_reset_truncates_overflow_until_an_absolute_return():
    printer = VirtualPrinter(page_geometry=_cell_geometry(3, 2))
    printer.write_bytes(b"\x1b[?7lABCD\bEF\rG")

    first, returned = printer.current_page.items
    assert (first.data, first.bounds.left, first.bounds.top) == (b"ABC", 0, 0)
    assert (returned.data, returned.bounds.left, returned.bounds.top) == (b"G", 0, 0)


def test_enabling_autowrap_consumes_a_retained_right_margin_flag():
    printer = VirtualPrinter(page_geometry=_cell_geometry(3, 2))
    printer.write_bytes(b"\x1b[?7lABCD\x1b[?7hE")

    first, wrapped = printer.current_page.items
    assert first.data == b"ABC"
    assert (wrapped.data, wrapped.bounds.left, wrapped.bounds.top) == (b"E", 0, 3600)


def test_backspace_after_an_exact_fill_allows_overstrike_without_wrapping():
    printer = VirtualPrinter(page_geometry=_cell_geometry(2, 2))
    printer.write_bytes(b"AB\bC")

    first, overstrike = printer.current_page.items
    assert first.data == b"AB"
    assert (overstrike.data, overstrike.bounds.left, overstrike.bounds.top) == (b"C", 2160, 0)


def test_horizontal_tab_beyond_the_last_stop_sets_the_right_margin_flag():
    printer = VirtualPrinter(page_geometry=_cell_geometry(10, 2))
    printer.write_bytes(b"A\tB\tC")

    first, tabbed, wrapped = printer.current_page.items
    assert first.data == b"A"
    assert (tabbed.data, tabbed.bounds.left, tabbed.bounds.top) == (b"B", 8 * 2160, 0)
    assert (wrapped.data, wrapped.bounds.left, wrapped.bounds.top) == (b"C", 0, 3600)


def test_implicit_vertical_overflow_completes_the_physical_page():
    printer = VirtualPrinter(page_geometry=_cell_geometry(2, 2))
    printer.write_bytes(b"ABCDE")

    page = printer.completed_pages[0]
    assert [item.data for item in page.items] == [b"AB", b"CD"]
    assert page.number == 1
    assert printer.current_page.number == 2
    assert printer.current_page.items[0].data == b"E"
    assert printer.current_page.items[0].bounds.top == 0


def test_line_feeds_over_the_bottom_complete_even_an_unmarked_page():
    printer = VirtualPrinter(page_geometry=_cell_geometry(2, 2))
    printer.write_bytes(b"\n\nA")

    assert printer.completed_pages == (PrinterPage(1, printer.page_geometry),)
    assert printer.current_page.number == 2
    assert printer.current_page.items[0].data == b"A"
    assert printer.current_page.items[0].bounds.top == 0


def test_wrapping_uses_the_custom_printable_area_as_logical_margins():
    geometry = PrinterPageGeometry(
        20_000,
        20_000,
        PrinterRect(1000, 2000, 1000 + 2 * 2160, 2000 + 2 * 3600),
    )
    printer = VirtualPrinter(page_geometry=geometry)
    printer.write_bytes(b"ABC")

    first, wrapped = printer.current_page.items
    assert first.bounds == PrinterRect(1000, 2000, 1000 + 2 * 2160, 5600)
    assert wrapped.bounds == PrinterRect(1000, 5600, 3160, 9200)


def test_printable_area_narrower_than_one_cell_discards_text_without_feeding_pages():
    geometry = PrinterPageGeometry(2000, 7200, PrinterRect(0, 0, 2000, 7200))
    printer = VirtualPrinter(page_geometry=geometry)
    printer.write_bytes(b"ignored")

    assert printer.current_page.items == ()
    assert printer.completed_pages == ()


def test_spaces_advance_and_are_recorded_without_marking_the_page():
    printer = VirtualPrinter()
    printer.write_bytes(b"   ")

    assert printer.current_page.items[0].data == b"   "
    assert printer._page_store.complete() is None
    assert printer.current_page.number == 1


def test_backspace_and_carriage_return_move_without_erasing_marks():
    printer = VirtualPrinter()
    printer.write_bytes(b"AB\bC\rD")

    first, overstrike, returned = printer.current_page.items
    assert first.data == b"AB"
    assert first.bounds.left == 0
    assert overstrike.data == b"C"
    assert overstrike.bounds.left == 2160
    assert returned.data == b"D"
    assert returned.bounds.left == 0


def test_backspace_is_constrained_to_the_left_printable_edge():
    geometry = PrinterPageGeometry(20_000, 20_000, PrinterRect(1000, 2000, 19_000, 19_000))
    printer = VirtualPrinter(page_geometry=geometry)
    printer.write_bytes(b"\bA")

    assert printer.current_page.items[0].bounds.left == 1000


def test_lf_respects_lnm_and_cr_respects_deccrnlm():
    printer = VirtualPrinter()
    printer.write_bytes(b"A\nB\x1b[20hC\nD\x1b[?40hE\rF")

    a, b, c, d, e, f = printer.current_page.items
    assert (a.bounds.left, a.bounds.top) == (0, 0)
    assert (b.bounds.left, b.bounds.top) == (2160, 3600)
    assert (c.bounds.left, c.bounds.top) == (4320, 3600)
    assert (d.bounds.left, d.bounds.top) == (0, 7200)
    assert (e.bounds.left, e.bounds.top) == (2160, 7200)
    assert (f.bounds.left, f.bounds.top) == (0, 10_800)


@pytest.mark.parametrize("nel", (b"\x85", b"\x1bE"))
def test_nel_returns_to_line_home_and_advances_one_line(nel):
    printer = VirtualPrinter()
    printer.write_bytes(b"A" + nel + b"B")

    first, second = printer.current_page.items
    assert (first.bounds.left, first.bounds.top) == (0, 0)
    assert (second.bounds.left, second.bounds.top) == (0, 3600)


def test_horizontal_and_vertical_tabs_use_dec_initial_stops():
    printer = VirtualPrinter()
    printer.write_bytes(b"A\tB\vC")

    first, second, third = printer.current_page.items
    assert (first.bounds.left, first.bounds.top) == (0, 0)
    assert (second.bounds.left, second.bounds.top) == (8 * 2160, 0)
    assert (third.bounds.left, third.bounds.top) == (9 * 2160, 3600)


def test_decshorp_changes_hai_rounds_forward_and_resets_horizontal_margins():
    printer = VirtualPrinter(page_geometry=_cell_geometry(12, 3))
    printer.write_bytes(b"\x1b[2;5sA\x1b[2wB")

    first, second = printer.current_page.items
    assert first.bounds == PrinterRect(2160, 0, 4320, 3600)
    assert second.bounds == PrinterRect(5400, 0, 7200, 3600)

    printer.write_bytes(b"\rC")
    assert printer.current_page.items[-1].bounds.left == 0


@pytest.mark.parametrize(
    "parameter, expected",
    (
        (0, 2160),
        (2, 1800),
        (3, 1635),
        (4, 1308),
        (11, 1260),
        (13, 1200),
    ),
)
def test_decshorp_uses_dec_centipoint_pitch_table(parameter, expected):
    printer = VirtualPrinter()
    printer.write_bytes(f"\x1b[{parameter}wA".encode())

    assert printer.current_page.items[0].advance == expected


def test_decverp_changes_vai_and_defers_grid_alignment_until_vertical_motion():
    printer = VirtualPrinter()
    printer.write_bytes(b"\n\x1b[2zA\nB")

    first, second = printer.current_page.items
    assert first.bounds == PrinterRect(0, 3600, 2160, 6300)
    assert second.bounds == PrinterRect(2160, 8100, 4320, 10_800)


def test_decslpp_limits_logical_pages_without_changing_physical_geometry():
    geometry = _cell_geometry(2, 4)
    printer = VirtualPrinter(page_geometry=geometry)
    printer.write_bytes(b"\x1b[2tABCDE")

    assert printer.page_geometry is geometry
    assert [item.data for item in printer.completed_pages[0].items] == [b"AB", b"CD"]
    assert printer.current_page.items[0].data == b"E"
    assert printer.current_page.items[0].bounds.top == 0


def test_no_forms_mode_treats_ff_vpa_and_vt_as_line_feeds():
    printer = VirtualPrinter(page_geometry=_cell_geometry(20, 2))
    printer.write_bytes(b"\x1b[0tA\fB\x1b[99dC\vD")

    assert printer.completed_pages == ()
    assert [item.bounds.top for item in printer.current_page.items] == [0, 3600, 7200, 10_800]


def test_decslrm_preserves_zero_parameters_and_clamps_to_printable_width():
    printer = VirtualPrinter(page_geometry=_cell_geometry(8, 2, left=1000, top=2000))
    printer.write_bytes(b"\x1b[3;99sA\x1b[;4s\rB")

    first, second = printer.current_page.items
    assert first.bounds.left == 1000 + 2 * 2160
    assert second.bounds.left == 1000 + 2 * 2160
    assert second.bounds.right == 1000 + 3 * 2160


def test_decstbm_constrains_vertical_positioning_and_implicit_page_feed():
    printer = VirtualPrinter(page_geometry=_cell_geometry(4, 5))
    printer.write_bytes(b"\x1b[2;4r\x1b[99dA\nB")

    first = printer.completed_pages[0].items[0]
    second = printer.current_page.items[0]
    assert first.bounds.top == 3 * 3600
    assert second.bounds.top == 3600


def test_hpa_hpr_vpa_and_vpr_position_in_character_cells():
    printer = VirtualPrinter(page_geometry=_cell_geometry(10, 10))
    printer.write_bytes(b"\x1b[3`A\x1b[2aB\x1b[3dC\x1b[2eD\x1b[1dE")

    a, b, c, d, e = printer.current_page.items
    assert (a.bounds.left, a.bounds.top) == (2 * 2160, 0)
    assert (b.bounds.left, b.bounds.top) == (5 * 2160, 0)
    assert (c.bounds.left, c.bounds.top) == (6 * 2160, 2 * 3600)
    assert (d.bounds.left, d.bounds.top) == (7 * 2160, 4 * 3600)
    assert e.bounds.top == 4 * 3600  # VPA cannot move backwards.


def test_lining_attributes_materialize_hpa_and_hpr_motion_as_page_spans():
    printer = VirtualPrinter()
    printer.write_bytes(b"\x1b[4m\x1b[4a\x1b[2`")

    relative, absolute = printer.current_page.items
    assert isinstance(relative, PrinterRenditionSpan)
    assert isinstance(absolute, PrinterRenditionSpan)
    assert relative.bounds == PrinterRect(0, 0, 4 * 2160, 3600)
    assert absolute.bounds == PrinterRect(2160, 0, 4 * 2160, 3600)
    assert relative.state.rendition.underline is PrinterUnderline.SINGLE


def test_unlined_hpa_and_hpr_remain_mark_free_positioning_operations():
    printer = VirtualPrinter()
    printer.write_bytes(b"\x1b[4a\x1b[2`")

    assert printer.current_page.items == ()


def test_position_unit_mode_uses_decipoints_for_absolute_and_relative_motion():
    printer = VirtualPrinter()
    printer.write_bytes(b"\x1b[11h\x1b[73`A\x1b[73aB")

    first, second = printer.current_page.items
    assert printer.state.position_unit_mode is True
    assert first.bounds.left == 2160
    assert second.bounds.left == 2160 + 2160 + 73 * 30

    printer.write_bytes(b"\x1b[11l")
    assert printer.state.position_unit_mode is False


def test_programmable_horizontal_tabs_and_tbc_use_page_relative_positions():
    printer = VirtualPrinter(page_geometry=_cell_geometry(10, 2))
    printer.write_bytes(b"\x1b[3g\x1b[3;5u\tA\tB\x1b[3g\r\tC")

    first, second, wrapped = printer.current_page.items
    assert first.bounds.left == 2 * 2160
    assert second.bounds.left == 4 * 2160
    assert (wrapped.bounds.left, wrapped.bounds.top) == (0, 3600)


@pytest.mark.parametrize("setter", (b"\x88", b"\x1bH", b"\x1b1"))
def test_hts_and_legacy_dechts_set_a_tab_at_the_active_position(setter):
    printer = VirtualPrinter(page_geometry=_cell_geometry(10, 2))
    printer.write_bytes(b"\x1b[3g\x1b[4`" + setter + b"\r\tA")

    assert printer.current_page.items[0].bounds.left == 3 * 2160


@pytest.mark.parametrize("setter", (b"\x8a", b"\x1bJ", b"\x1b3"))
def test_vts_and_legacy_decvts_set_a_vertical_tab_at_the_active_line(setter):
    printer = VirtualPrinter(page_geometry=_cell_geometry(10, 5))
    printer.write_bytes(b"\x1b[4g\x1b[3d" + setter + b"\f\vA")

    assert printer.current_page.items[0].bounds.top == 2 * 3600


def test_pitch_changes_rescale_programmed_tab_stops_by_logical_column_and_line():
    printer = VirtualPrinter(page_geometry=_cell_geometry(20, 10))
    printer.write_bytes(b"\x1b[3;4g\x1b[5u\x1b[4v\x1b[2w\x1b[2z\tA\vB")

    first, second = printer.current_page.items
    assert first.bounds.left == 4 * 1800
    assert second.bounds.top == 3 * 2700


def test_layout_command_assembly_is_invariant_across_every_stream_boundary():
    payload = b"\x1b[2w\x1b[2z\x1b[2;8s\x1b[2;6r\x1b[3`\x1b[3dA\x1b[2aB"
    whole = VirtualPrinter()
    whole.write_bytes(payload)

    for boundary in range(len(payload) + 1):
        streamed = VirtualPrinter()
        streamed.write_bytes(payload[:boundary])
        streamed.write_bytes(payload[boundary:])
        assert streamed.current_page == whole.current_page
        assert streamed.completed_pages == whole.completed_pages
        assert streamed.state == whole.state


@pytest.mark.parametrize("reset", (b"\x1bc", b"\x1b[!p"))
def test_dec_resets_restore_layout_defaults_without_discarding_page_marks(reset):
    printer = VirtualPrinter()
    printer.write_bytes(b"\x1b[2w\x1b[2z\x1b[3;20s\x1b[3;20rA" + reset + b"B")

    first, second = printer.current_page.items
    assert (first.bounds.left, first.bounds.top, first.advance, first.bounds.height) == (3600, 5400, 1800, 2700)
    assert second.bounds == PrinterRect(0, 0, 2160, 3600)
    assert printer.completed_pages == ()


def test_public_printer_reset_restores_layout_defaults_without_clearing_pages():
    printer = VirtualPrinter()
    printer.write_bytes(b"\x1b[2w\x1b[2zA")
    printer.reset()
    printer.write_bytes(b"B")

    first, second = printer.current_page.items
    assert (first.advance, first.bounds.height) == (1800, 2700)
    assert second.bounds == PrinterRect(0, 0, 2160, 3600)


def test_explicit_form_feed_completes_even_a_blank_page_and_preserves_x():
    printer = VirtualPrinter()
    printer.write_bytes(b"\fA\fB")

    blank, marked = printer.completed_pages
    assert blank.number == 1
    assert blank.items == ()
    assert marked.number == 2
    assert marked.items[0].data == b"A"
    assert printer.current_page.number == 3
    assert printer.current_page.items[0].data == b"B"
    assert marked.items[0].bounds.left == 0
    assert printer.current_page.items[0].bounds.left == 2160


def test_form_feed_preserves_nonzero_horizontal_position():
    printer = VirtualPrinter()
    printer.write_bytes(b"A\fB")

    assert printer.completed_pages[0].items[0].data == b"A"
    assert printer.current_page.items[0].bounds.left == 2160


def test_basic_controls_remain_active_inside_an_incomplete_csi():
    printer = VirtualPrinter()
    printer.write_bytes(b"A\x1b[\n?41hB")

    first, second = printer.current_page.items
    assert second.bounds.top == first.bounds.top + 3600
    assert printer.state.direction is PrintDirection.UNIDIRECTIONAL


def test_crm_images_named_and_hex_control_tokens_among_normal_text():
    printer = VirtualPrinter()
    printer.write_bytes(b"\x1b[3hA\x00\x08\x80\xa0")

    text, nul, backspace, reserved, high = printer.current_page.items
    assert text.data == b"A"
    assert [(nul.source, nul.text), (backspace.source, backspace.text), (reserved.source, reserved.text)] == [
        (b"\x00", "<NUL>"),
        (b"\x08", "<BS>"),
        (b"\x80", "<X80>"),
    ]
    assert all(isinstance(item, PrinterControlToken) for item in (nul, backspace, reserved))
    assert all(item.state.control_representation for item in (nul, backspace, reserved))
    assert (high.data, high.text) == (b"\xa0", None)


def test_crm_lf_is_imaged_then_executes_carriage_return_line_feed():
    printer = VirtualPrinter()
    printer.write_bytes(b"\x1b[3hA\nB")

    first, token, second = printer.current_page.items
    assert (token.source, token.text) == (b"\n", "<LF>")
    assert (token.bounds.left, token.bounds.top) == (2160, 0)
    assert (second.bounds.left, second.bounds.top) == (0, 3600)
    assert first.data == b"A"


def test_crm_ff_is_imaged_then_ejects_the_page_without_returning_x():
    printer = VirtualPrinter()
    printer.write_bytes(b"\x1b[3h\fA")

    completed = printer.completed_pages[0]
    token = completed.items[0]
    assert isinstance(token, PrinterControlToken)
    assert (token.source, token.text) == (b"\f", "<FF>")
    assert printer.current_page.items[0].bounds.left == len("<FF>") * 2160


@pytest.mark.parametrize("reset", (b"\x1b[3l", b"\x9b3l"))
def test_crm_reset_is_imaged_as_csi_then_exits(reset):
    printer = VirtualPrinter()
    printer.write_bytes(b"\x1b[3h" + reset + b"A")

    token, text = printer.current_page.items
    assert isinstance(token, PrinterControlToken)
    assert (token.source, token.text) == (reset, "<CSI>3l")
    assert token.state.control_representation is True
    assert text.state.control_representation is False
    assert printer.state.control_representation is False


def test_crm_shields_other_commands_while_imaging_their_bytes():
    printer = VirtualPrinter()
    printer.write_bytes(b"\x1b[3h\x1b[?41h")

    token, text = printer.current_page.items
    assert (token.source, token.text) == (b"\x1b", "<ESC>")
    assert text.data == b"[?41h"
    assert printer.state.direction is PrintDirection.BIDIRECTIONAL


def test_crm_tokens_wrap_as_graphic_text_even_when_deccawm_is_reset():
    printer = VirtualPrinter(page_geometry=_cell_geometry(5, 2))
    printer.write_bytes(b"\x1b[?7l\x1b[3h\x00A")

    token, wrapped = printer.current_page.items
    assert isinstance(token, PrinterControlToken)
    assert (token.source, token.text, token.bounds.top) == (b"\x00", "<NUL>", 0)
    assert (wrapped.data, wrapped.bounds.left, wrapped.bounds.top) == (b"A", 0, 3600)


def test_long_crm_tokens_split_across_lines_without_losing_the_source():
    printer = VirtualPrinter(page_geometry=_cell_geometry(5, 2))
    printer.write_bytes(b"\x1b[3h\x9b3l")

    first, second = printer.current_page.items
    assert isinstance(first, PrinterControlToken)
    assert isinstance(second, PrinterControlToken)
    assert (first.source, first.text, first.bounds.top) == (b"\x9b3l", "<CSI>", 0)
    assert (second.source, second.text, second.bounds.top) == (b"\x9b3l", "3l", 3600)
    assert printer.state.control_representation is False


def test_crm_assembly_is_invariant_across_every_stream_boundary():
    payload = b"\x1b[3hA\x1b[?41h\nB\x9b3lC"
    whole = VirtualPrinter()
    whole.write_bytes(payload)

    for boundary in range(len(payload) + 1):
        streamed = VirtualPrinter()
        streamed.write_bytes(payload[:boundary])
        streamed.write_bytes(payload[boundary:])
        assert streamed.current_page == whole.current_page
        assert streamed.completed_pages == whole.completed_pages
        assert streamed.state == whole.state


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
