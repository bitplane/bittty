# Keyboard input measurements

Python 3.14.4 on the development Linux machine. Baseline: `6ca0dd1`, before
the keyboard changes. Median of five runs, 1,000 calls per run; each call
clears the recording connection. These are microbenchmarks, not CI thresholds.

| Workload | Before (µs/call) | After (µs/call) |
| :--- | ---: | ---: |
| Typed ASCII key | 2.49 | 2.28 |
| Stdio ASCII, 4 KiB | 249.00 | 231.04 |
| Paste, 64 KiB | 1.39 | 1.61 |
| Stdio CSI burst, 100 sequences, legacy mode | 153.28 | 159.51 |
| Decode and encode 100 enhanced repeat/text events | unavailable | 1207.87 |

Small differences vary between runs. The legacy CSI framing increase is about
0.06 µs per sequence; a fully decoded enhanced event takes about 12.1 µs.
Ordinary text and paste remain batched. The child-output parser is unchanged.

Run `python tests/performance/benchmark_keyboard.py` for current results.
For a baseline checkout, put its `src` directory on `PYTHONPATH` and use the
same script with `--baseline` to omit the unavailable enhanced-event workload.
