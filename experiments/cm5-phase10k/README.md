# Private Phase10K assessment

Local analysis/debugging only; no upstream contribution. Reports and captured
observations belong outside the checkout in a fresh private Phase10K directory.
No hardware model changed. No timing or full hardware equivalence is claimed.

Reanalyze without running the FSW or a guest:

```sh
umask 077
python3 experiments/cm5-phase10k/analyze.py --source "$CM5_K_SOURCE" --output "$CM5_K_FRESH_OUTPUT"
CM5_PHASE10K_REFERENCE="$CM5_K_SOURCE" python3 -m unittest discover -s experiments/cm5-phase10k -p 'test_*.py' -v
```

The physical counts are supplied complete-transcript observations, not a raw
physical transcript inspected by this tool. Ordered normalized records preserve
all nonempty QEMU lines, including unknown lines and errors. Count agreement
does not imply payload, timing, scheduling, or external communication parity.

The updated Phase10J classifier requires its adjacent `events.py`; retain it
with private harness copies. Its success classification remains PARTIAL pending
physical comparison. Raw FSW output is untouched.

On the next normally needed 30-second Phase10J experiment, diagnostic additions
record outer golden hashing/preflight stages and inner BOOT acceptance/export,
QEMU launch, console milestones, userspace validation, upload verification, FSW
start/result, exit, and postrun identities. `host-timeline.jsonl` uses offsets
from runner setup; `observations.jsonl` uses offsets from the QEMU loop start.
The timeline's launch event relates these origins approximately; do not add or
subtract offsets from different origins blindly. Console milestones are host
receipt times. `serial-chunks.jsonl` and `debug-chunks.jsonl` map byte offsets in
unchanged logs to host receipt offsets, including upload ACKs. CPU tick counters
and their tick rate accompany the existing ten-second host I/O samples.
`P10K_FSW_START` contains guest monotonic time, printed outside the raw FSW PTY
capture. It is not a QEMU virtual timestamp.

No original kernel/initramfs, verification metadata, scan, timeout, transfer ACK,
or hash check is removed. Instrumentation has unit/transport validation; it has
not yet been exercised in a new Linux guest. Private FINAL-SUMMARY.md records
the measured baseline and this limitation. Use `ninja -j2` if a later change
requires rebuilding; this diagnostic-only change requires no QEMU rebuild.
