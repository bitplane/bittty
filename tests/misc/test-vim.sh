#!/bin/bash

# Test script to capture vim escape sequences in both terminals
# Usage: ./test-vim.sh 1  (for our terminal)
#        ./test-vim.sh 2  (for tmux terminal)

if [ "$#" -ne 1 ]; then
    echo "Usage: $0 <pane_number>"
    echo "  1 = our terminal (main:1.1)"
    echo "  2 = tmux terminal (main:1.2)"
    exit 1
fi

PANE=$1
PANE_NAME="main:1.$PANE"
OUTPUT_FILE="$PANE.strace"

echo "Testing vim in pane $PANE_NAME, output to $OUTPUT_FILE"

# Start strace with vim - only trace file descriptors 0,1,2
tmux send-keys -t "$PANE_NAME" "strace -e trace=read,write -s 1000 -o $OUTPUT_FILE vim README.md" Enter

# Wait for vim to start
sleep 2

# Press down arrow
tmux send-keys -t "$PANE_NAME" Down

# Wait a moment
sleep 1

# Quit vim
tmux send-keys -t "$PANE_NAME" ":q" Enter

grep -v 'read([3-9]' "$OUTPUT_FILE" > "$OUTPUT_FILE.tmp"
mv "$OUTPUT_FILE.tmp" "$OUTPUT_FILE"
