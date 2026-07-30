"""Stable mode capability identifiers and built-in positive repertoires.

Mode numbers are not globally unique across terminal families.  Models select
semantic capability IDs; the mode device resolves those IDs to the appropriate
numbered implementation and rejects collisions within one model.
"""

from __future__ import annotations

# ANSI modes
ANSI_INSERT = "ansi.insert"
ANSI_NEWLINE = "ansi.newline"

# DEC and xterm private modes
DEC_CURSOR_APPLICATION = "dec.cursor-application"
DEC_COLUMN_MODE = "dec.column-mode"
XTERM_COLUMN_MODE = "xterm.column-mode"
TMUX_COLUMN_MODE = "tmux.column-mode"
KITTY_COLUMN_MODE = "kitty.column-mode"
DEC_REVERSE_SCREEN = "dec.reverse-screen"
DEC_ORIGIN = "dec.origin"
DEC_AUTOWRAP = "dec.autowrap"
XTERM_MOUSE_X10 = "xterm.mouse-x10"
XTERM_CURSOR_BLINK = "xterm.cursor-blink"
DEC_PRINT_FORM_FEED = "dec.print-form-feed"
DEC_PRINT_EXTENT = "dec.print-extent"
DEC_CURSOR_VISIBLE = "dec.cursor-visible"
DEC_NATIONAL_CHARSET = "dec.national-charset"
XTERM_REVERSE_WRAP = "xterm.reverse-wrap"
XTERM_ALT_SCREEN_47 = "xterm.alt-screen-47"
DEC_NUMERIC_KEYPAD = "dec.numeric-keypad"
DEC_BACKARROW = "dec.backarrow"
DEC_LEFT_RIGHT_MARGINS = "dec.left-right-margins"
DEC_NO_CLEAR_COLUMN = "dec.no-clear-column"
DEC_IGNORE_NULL = "dec.ignore-null"
XTERM_MOUSE_NORMAL = "xterm.mouse-normal"
XTERM_FOCUS = "xterm.focus"
XTERM_MOUSE_BUTTON = "xterm.mouse-button"
XTERM_MOUSE_ANY = "xterm.mouse-any"
XTERM_MOUSE_UTF8 = "xterm.mouse-utf8"
XTERM_MOUSE_SGR = "xterm.mouse-sgr"
XTERM_ALTERNATE_SCROLL = "xterm.alternate-scroll"
URXVT_MOUSE = "urxvt.mouse"
XTERM_EIGHT_BIT_INPUT = "xterm.eight-bit-input"
XTERM_SPECIAL_MODIFIERS = "xterm.special-modifiers"
XTERM_META_ESCAPE = "xterm.meta-escape"
XTERM_DELETE = "xterm.delete"
XTERM_ALT_ESCAPE = "xterm.alt-escape"
XTERM_ALT_SCREEN_1047 = "xterm.alt-screen-1047"
XTERM_SAVE_CURSOR_1048 = "xterm.save-cursor-1048"
XTERM_ALT_SCREEN_1049 = "xterm.alt-screen-1049"
XTERM_ALLOW_COLUMN = "xterm.allow-column"
XTERM_EXTENDED_REVERSE_WRAP = "xterm.extended-reverse-wrap"
XTERM_ALLOW_ALT_SCREEN = "xterm.allow-alt-screen"
XTERM_BRACKETED_PASTE = "xterm.bracketed-paste"
XTERM_SYNC_OUTPUT = "xterm.sync-output"
UNICODE_GRAPHEME_CLUSTERING = "unicode.grapheme-clustering"
UNICODE_AMBIGUOUS_WIDTH = "unicode.ambiguous-width"

ANSI_MODE_CAPABILITIES = frozenset({ANSI_INSERT, ANSI_NEWLINE})

# Hardware profiles are the intersection of the model's documented repertoire
# and the mode semantics bittty currently implements.
VT100_MODE_CAPABILITIES = ANSI_MODE_CAPABILITIES | frozenset(
    {
        DEC_CURSOR_APPLICATION,
        DEC_COLUMN_MODE,
        DEC_REVERSE_SCREEN,
        DEC_ORIGIN,
        DEC_AUTOWRAP,
    }
)
VT220_MODE_CAPABILITIES = VT100_MODE_CAPABILITIES | frozenset(
    {
        DEC_PRINT_FORM_FEED,
        DEC_PRINT_EXTENT,
        DEC_CURSOR_VISIBLE,
        DEC_NATIONAL_CHARSET,
    }
)
VT510_MODE_CAPABILITIES = VT220_MODE_CAPABILITIES | frozenset(
    {
        DEC_NUMERIC_KEYPAD,
        DEC_BACKARROW,
        DEC_LEFT_RIGHT_MARGINS,
        DEC_NO_CLEAR_COLUMN,
        DEC_IGNORE_NULL,
    }
)

XTERM_MODE_CAPABILITIES = frozenset(
    {
        ANSI_INSERT,
        ANSI_NEWLINE,
        DEC_CURSOR_APPLICATION,
        XTERM_COLUMN_MODE,
        DEC_REVERSE_SCREEN,
        DEC_ORIGIN,
        DEC_AUTOWRAP,
        XTERM_MOUSE_X10,
        XTERM_CURSOR_BLINK,
        DEC_PRINT_FORM_FEED,
        DEC_PRINT_EXTENT,
        DEC_CURSOR_VISIBLE,
        DEC_NATIONAL_CHARSET,
        XTERM_REVERSE_WRAP,
        XTERM_ALT_SCREEN_47,
        DEC_NUMERIC_KEYPAD,
        DEC_BACKARROW,
        DEC_LEFT_RIGHT_MARGINS,
        DEC_NO_CLEAR_COLUMN,
        XTERM_MOUSE_NORMAL,
        XTERM_FOCUS,
        XTERM_MOUSE_BUTTON,
        XTERM_MOUSE_ANY,
        XTERM_MOUSE_UTF8,
        XTERM_MOUSE_SGR,
        XTERM_ALTERNATE_SCROLL,
        URXVT_MOUSE,
        XTERM_EIGHT_BIT_INPUT,
        XTERM_SPECIAL_MODIFIERS,
        XTERM_META_ESCAPE,
        XTERM_DELETE,
        XTERM_ALT_ESCAPE,
        XTERM_ALT_SCREEN_1047,
        XTERM_SAVE_CURSOR_1048,
        XTERM_ALT_SCREEN_1049,
        XTERM_ALLOW_COLUMN,
        XTERM_EXTENDED_REVERSE_WRAP,
        XTERM_ALLOW_ALT_SCREEN,
        XTERM_BRACKETED_PASTE,
    }
)

LINUX_MODE_CAPABILITIES = frozenset(
    {
        ANSI_INSERT,
        ANSI_NEWLINE,
        DEC_CURSOR_APPLICATION,
        DEC_COLUMN_MODE,
        DEC_REVERSE_SCREEN,
        DEC_ORIGIN,
        DEC_AUTOWRAP,
        XTERM_MOUSE_X10,
        DEC_CURSOR_VISIBLE,
        XTERM_MOUSE_NORMAL,
    }
)

SCREEN_MODE_CAPABILITIES = frozenset(
    {
        ANSI_INSERT,
        ANSI_NEWLINE,
        DEC_CURSOR_APPLICATION,
        DEC_COLUMN_MODE,
        DEC_REVERSE_SCREEN,
        DEC_ORIGIN,
        DEC_AUTOWRAP,
        XTERM_MOUSE_X10,
        DEC_CURSOR_VISIBLE,
        XTERM_ALT_SCREEN_47,
        XTERM_MOUSE_NORMAL,
        XTERM_MOUSE_BUTTON,
        XTERM_MOUSE_ANY,
        XTERM_MOUSE_SGR,
        XTERM_ALT_SCREEN_1047,
        XTERM_SAVE_CURSOR_1048,
        XTERM_ALT_SCREEN_1049,
        XTERM_BRACKETED_PASTE,
    }
)

TMUX_MODE_CAPABILITIES = frozenset(
    {
        ANSI_INSERT,
        DEC_CURSOR_APPLICATION,
        TMUX_COLUMN_MODE,
        DEC_ORIGIN,
        DEC_AUTOWRAP,
        XTERM_CURSOR_BLINK,
        DEC_CURSOR_VISIBLE,
        XTERM_ALT_SCREEN_47,
        XTERM_MOUSE_NORMAL,
        XTERM_FOCUS,
        XTERM_MOUSE_BUTTON,
        XTERM_MOUSE_ANY,
        XTERM_MOUSE_UTF8,
        XTERM_MOUSE_SGR,
        XTERM_ALT_SCREEN_1047,
        XTERM_ALT_SCREEN_1049,
        XTERM_BRACKETED_PASTE,
        XTERM_SYNC_OUTPUT,
    }
)

URXVT_MODE_CAPABILITIES = frozenset(
    {
        ANSI_INSERT,
        ANSI_NEWLINE,
        DEC_CURSOR_APPLICATION,
        XTERM_COLUMN_MODE,
        DEC_REVERSE_SCREEN,
        DEC_ORIGIN,
        DEC_AUTOWRAP,
        XTERM_MOUSE_X10,
        XTERM_CURSOR_BLINK,
        DEC_CURSOR_VISIBLE,
        XTERM_ALT_SCREEN_47,
        DEC_NUMERIC_KEYPAD,
        DEC_BACKARROW,
        XTERM_MOUSE_NORMAL,
        XTERM_FOCUS,
        XTERM_MOUSE_BUTTON,
        XTERM_MOUSE_ANY,
        XTERM_MOUSE_UTF8,
        XTERM_MOUSE_SGR,
        URXVT_MOUSE,
        XTERM_ALT_SCREEN_1047,
        XTERM_SAVE_CURSOR_1048,
        XTERM_ALT_SCREEN_1049,
        XTERM_ALLOW_COLUMN,
        XTERM_BRACKETED_PASTE,
    }
)

VTE_MODE_CAPABILITIES = frozenset(
    {
        ANSI_INSERT,
        DEC_CURSOR_APPLICATION,
        XTERM_COLUMN_MODE,
        DEC_REVERSE_SCREEN,
        DEC_ORIGIN,
        DEC_AUTOWRAP,
        XTERM_MOUSE_X10,
        DEC_CURSOR_VISIBLE,
        XTERM_ALT_SCREEN_47,
        DEC_NUMERIC_KEYPAD,
        DEC_LEFT_RIGHT_MARGINS,
        XTERM_MOUSE_NORMAL,
        XTERM_FOCUS,
        XTERM_MOUSE_BUTTON,
        XTERM_MOUSE_ANY,
        XTERM_MOUSE_SGR,
        XTERM_ALTERNATE_SCROLL,
        XTERM_META_ESCAPE,
        XTERM_ALT_SCREEN_1047,
        XTERM_SAVE_CURSOR_1048,
        XTERM_ALT_SCREEN_1049,
        XTERM_ALLOW_COLUMN,
        XTERM_BRACKETED_PASTE,
    }
)

KITTY_MODE_CAPABILITIES = frozenset(
    {
        ANSI_INSERT,
        ANSI_NEWLINE,
        DEC_CURSOR_APPLICATION,
        KITTY_COLUMN_MODE,
        DEC_REVERSE_SCREEN,
        DEC_ORIGIN,
        DEC_AUTOWRAP,
        XTERM_CURSOR_BLINK,
        DEC_CURSOR_VISIBLE,
        XTERM_ALT_SCREEN_47,
        XTERM_MOUSE_NORMAL,
        XTERM_FOCUS,
        XTERM_MOUSE_BUTTON,
        XTERM_MOUSE_ANY,
        XTERM_MOUSE_UTF8,
        XTERM_MOUSE_SGR,
        URXVT_MOUSE,
        XTERM_ALT_SCREEN_1047,
        XTERM_SAVE_CURSOR_1048,
        XTERM_ALT_SCREEN_1049,
        XTERM_BRACKETED_PASTE,
        XTERM_SYNC_OUTPUT,
    }
)

# The native model keeps bittty extensions separate from the xterm profile.
BITTTY_MODE_CAPABILITIES = XTERM_MODE_CAPABILITIES | frozenset(
    {
        XTERM_SYNC_OUTPUT,
        UNICODE_GRAPHEME_CLUSTERING,
        UNICODE_AMBIGUOUS_WIDTH,
        DEC_IGNORE_NULL,
    }
)

# Registry catalogue, including mutually exclusive same-number semantics.
ALL_MODE_CAPABILITIES = (
    BITTTY_MODE_CAPABILITIES
    | VT100_MODE_CAPABILITIES
    | VT220_MODE_CAPABILITIES
    | VT510_MODE_CAPABILITIES
    | LINUX_MODE_CAPABILITIES
    | SCREEN_MODE_CAPABILITIES
    | TMUX_MODE_CAPABILITIES
    | URXVT_MODE_CAPABILITIES
    | VTE_MODE_CAPABILITIES
    | KITTY_MODE_CAPABILITIES
)
