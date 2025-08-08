"""Test UTF-8 handling through PTY layer."""

import os
from unittest.mock import patch


def test_utf8_through_pty_small_buffer(parser, terminal):
    """Test that UTF-8 characters work correctly through PTY with small buffer."""
    from bittty.pty.unix import UnixPTY

    print("Creating PTY...")
    # Create a PTY
    pty = UnixPTY(rows=24, cols=80)

    print("PTY created")
    # Test data: toilet, plunger, poop emojis repeated
    # Each emoji is 4 bytes in UTF-8
    test_string = "🚽🪠💩" * 10

    print(f"Writing {len(test_string.encode('utf-8'))} bytes to PTY slave...")
    # Write to PTY slave (what a program would output)
    os.write(pty.slave_fd, test_string.encode("utf-8"))

    print("Starting read loop...")
    # Read from PTY master with tiny buffer (7 bytes)
    # This guarantees UTF-8 sequences will be split mid-emoji
    result = ""
    with patch("bittty.constants.DEFAULT_PTY_BUFFER_SIZE", 7):
        read_count = 0
        while True:
            print(f"Reading chunk {read_count}...")
            chunk = pty.read(7)
            print(f"Got chunk: {repr(chunk)}")
            if not chunk:
                break
            result += chunk
            parser.feed(chunk)  # Feed each chunk to parser
            read_count += 1
            if read_count > 100:  # Safety break
                print("Too many reads, breaking")
                break

    print("Checking output...")
    # Verify all the emojis made it through intact
    output = terminal.capture_pane()
    assert "🚽🪠💩" * 10 in output

    pty.close()
