# Phase 10E.1 — completed bounded checkpoint

**A real FIFO/shifter accounting defect is corrected and tested. The mandatory
10kHz native control remains PASS. Higher-rate framing is NOT resolved:100kHz
is PARTIAL, with93 CS segments for90 messages.** No1MHz guest was scheduled.
No Phase10F work began, and no new full FEC campaign was run.

Branch `cm5-rp1-hardware`, HEAD
`1a6703a4bb1590aa98e6993474b0a0551d8d8f60`. All earlier uncommitted/untracked
work, failed traces and original media/boot assets remain. No commit, push,
stash, reset, clean, physical-device access or production input modification.
Private pre-change source snapshots:
`/home/aweso/cm5-v8-lab/phase10e1/source-initial/`.

## Exact code state and why it changed

Before this turn, the model left the active transmitting word counted in TXFLR
until its completion timer fired. A new deterministic regression fails against
the pre-change binary: TXFLR is1 when it must already be0 with a word in flight.
The [pinned 6.18.50 Linux source](https://raw.githubusercontent.com/raspberrypi/linux/cff533aec2fa601846766b32ff57204e0a61bed7/drivers/spi/spi-dw-core.c)
explicitly accounts for data outside the FIFOs in shift registers in
`dw_spi_tx_max()`. The private exact downloaded source and SHA are in
`~/cm5-v8-lab/phase10e1/reference/`.

The current implementation adds `shift_tx`, `shift_bits`, `shift_busy` and
separates FIFO dequeue/IRQ notification from frame completion. It loads the
shifter at frame start, updates TX-empty/threshold IRQ then, and keeps SR.BUSY
independent of FIFO empty. Completion emits the shifted frame, queues RX and
loads a next word if present. CS remains asserted between queued frames and
still deasserts on a genuine empty-at-completion gap. It is NOT held indefinitely
until SER/SSIENR clears. No kernel/driver change, FIFO-size inflation, fixture
warmup discard or strict-validator relaxation occurred.

Disable/deselect/reset abort an active frame without a phantom RX completion.
The modeled clock-pause path preserves the active word and restarts its full
frame timer when resumed. That is a tested logical convention, not bit-level
clock-pause or electrical timing fidelity. Existing mode/width/FIFO-overflow,
MSI-X, reset and native-clock tests still pass.

Changed implementation/test files in this turn:

- `hw/ssi/dw-apb-ssi.c`
- `include/hw/ssi/dw-apb-ssi.h`
- `hw/ssi/trace-events`
- `tests/qtest/rp1-test.c`
- `tests/qtest/cm5io-test.c`
- `experiments/cm5-phase10c/run.py` (optional diagnostic flag only)
- `experiments/cm5-phase10e/native_profile.py` (optional trace arguments only)

This checkpoint and fresh `e1-*` ignored evidence are additional files. Existing
Phase10E STATUS/README/strict reports retain their historical results.

## Bounded diagnostics and concrete observations

`--native-spi-diagnostics` enables `dw_apb_ssi_state`. The counter allows256
state records per device cold reset, containing virtual timestamp, FIFO counts,
shift state, CS, raw/masked IRQ and pending timer deadline. This is not a delay
or scheduling control; trace I/O can perturb wall-clock TCG execution. There
are257 records/run here because an earlier reset emitted one record before
the budget restarted. Normal existing CS/byte traces still cover every message.

Deterministic qtest trace (`e1-pipeline-trace.log`):

- At virtual0, the first word is in the shifter, TXFLR0, BUSY1 and TX-empty IRQ1.
- At4000ns, software refills while that frame is active; FIFO count1, IRQ0,
  deadline8000ns.
- At8000ns, RX gets the first word and the second moves to the shifter. FIFO0,
  BUSY1, IRQ1, with no intermediate CS deassertion.
- At16000ns, the second completes and CS deasserts normally. The unchanged
  independent validator confirms one correct two-byte CS segment.
- Disabling halfway through another word cancels it without manufacturing RX.
  A native-clock qtest also pauses/resumes an in-flight word coherently.

The100kHz guest's first4-byte message frames correctly in this run, but later
messages do not. This is not a proven rate improvement: the previous failures
and this run used different host/timing/instrumentation conditions. Actual
splits, using zero-based submitted-message indices:

| Message | Intended bytes | Actual CS segments |
| --- | ---: | --- |
| 3 | 128 | 1 +127 |
| 32 | 65 | 1 +64 |
| 35 | 4096 | 1 +4095 |

All69,210 bytes and native IRQ completion remain correct. Fragmented messages
are still failures of strict framing, even though concatenated bytes match.
`e1-100khz-failure-detail.json` is diagnostic only; it does not relax the oracle.

**Observation limit:** the256-event window ends at frame69; the first bad
message starts at frame133. Thus it does not capture the exact failing refill
gap. The first (successful) message shows a shift-done diagnostic95,793ns after
an earlier recorded deadline; this includes callback and trace costs and cannot
be called a measured host-dispatch delay. A raw TX-write gap alone is also
misleading because CS callbacks/logging occur before timer arm.

## Actual test outcomes and evidence levels

| Test | Outcome |
| --- | --- |
| New FIFO/shifter/IRQ-lead qtest before fix | EXPECTED_FAILURE, TXFLR1 versus0 |
| Modified QEMU and affected qtest build | PASS |
| RP1 qtests | 7 PASS, including new pipeline/abort case |
| cm5io/native PCIe/MSI/clock qtests | 7 PASS, including paused shifter |
| MIP qtests | 3 PASS |
| Unchanged strict trace-validator units | 3 PASS |
| Deterministic continuous two-byte trace | PASS, one CS segment |
| Hardware patch checkpatch --no-signoff | 0 errors/0 warnings |
| Original-kernel10kHz control | PASS,90 messages/90 CS segments |
| Original-kernel100kHz regression | PARTIAL,90 messages/93 CS segments |
| 1MHz guest | NOT_RUN:100kHz unresolved and this session bounded |

Strict guest results:

- `artifacts/e1-report-10khz/result.json`: all14 checks true.
- `artifacts/e1-report-100khz/result.json`: only CS-framing check false; all
  other13 checks true, including real driver, native IRQs and idle-IRQ stability.
- Raw runs: `e1-10khz-01` and `e1-100khz-01`, both original captured6.18.50
  kernel/initramfs, fresh regular-file-backed QCOW2 overlays, no fault injection.
- Both preserve original full verified OS scan, both roots2/V, systemd,
  independent multi-user, guest diagnostics, host LOGS persistence and exit0
  with no whole-guest timeout. Recorded wall times405.56s and393.19s include
  final identity checks; these are not physical performance measurements.
- Original golden and all captured boot identities compare unchanged before/
  after, and match Phase10C input identities. No new FEC recovery claim.

Other evidence: `e1-pipeline-before.log`, `e1-pipeline-strict.json`,
`e1-timing-summary.json`, `e1-validation/` and `e1-initial/`. Executable identities,
exact expanded commands and the actual submitted public observer are retained
per guest. Prior10kHz/100kHz/1MHz failures remain untouched.

## Unresolved hypotheses and the next smallest step

The separate-shifter correction is supported by source, deterministic tests and
a preserved low-rate guest control; it is insufficient to fix high-rate CS.
The same pinned Linux source's memory-transfer discussion describes native-CS
sensitivity to FIFO starvation, preemption and slow CPU/bus service. That
supports a remaining service-timing hypothesis, not proof of its exact cause
in these guests. No physical CM5 timing instrumentation occurred.

Immediate next session, before any broader SPI claim:

1. Keep this shifter state and the unchanged strict oracle. Add a small,
   separately capped **FIFO-drain / next-refill** diagnostic: at completion when
   FIFO is empty, and on the next DR write from idle, record virtual timestamp,
   last deadline, FIFO/shift/IRQ/SER state. Call it drain, not automatically
   starvation; the message oracle supplies that interpretation. This targets
   gaps across all90 messages without thousands of per-frame timing records.
2. Capture timer-arm time/deadline before/after callbacks separately. Correlate
   CS segments and expected message indices, especially message3/128 bytes.
   Do not infer underflow merely from a TX-write interval spanning logging or
   CS setup. Current state capture ended before that failure.
3. Use one bounded diagnostic guest window for controlled cold/repeated probes,
   preserving original initramfs scan and normal shutdown. Compare carefully
   labeled virtual-clock/CPU scheduling variants only if the captured gap
   warrants them. Do not change the physical kernel/driver, invent unconditional
   CS hold, hide failed messages, or substitute physical throughput claims.
4. Real GPIO-CS or vendor CS-override semantics require independent source-backed
   implementation/reference evidence; do not pretend that SER is an arbitrary
   software-held CS line. No1MHz retry until100kHz is defensible.

Do not start Phase10F in this checkpoint session. A separate new session may
later follow the existing BOOT handoff; no BOOT code was changed here.

## Exact reproduction commands

From `/home/aweso/projects/qemu`, local WSL, fresh names only. Host writes go to
local build/evidence and disposable private overlays; no physical devices:

```sh
ninja -C build-arm64-phase1 -j 8 qemu-system-aarch64 \
 tests/qtest/rp1-test tests/qtest/cm5io-test tests/qtest/bcm2712-mip-test
QTEST_QEMU_BINARY="$PWD/build-arm64-phase1/qemu-system-aarch64" \
 build-arm64-phase1/tests/qtest/rp1-test
QTEST_QEMU_BINARY="$PWD/build-arm64-phase1/qemu-system-aarch64" \
 build-arm64-phase1/tests/qtest/cm5io-test
QTEST_QEMU_BINARY="$PWD/build-arm64-phase1/qemu-system-aarch64" \
 build-arm64-phase1/tests/qtest/bcm2712-mip-test
python3 experiments/cm5-phase10c/run.py --native-rp1-test \
 --native-spi-diagnostics --native-spi-hz 10000 --recovery-case clean \
 --dma --batch --profile native --debug-shell --poweroff-after-validation \
 --timeout 420 --output experiments/cm5-phase10e/artifacts/e1-control-repro01
python3 experiments/cm5-phase10e/report.py \
 --run experiments/cm5-phase10e/artifacts/e1-control-repro01 \
 --output experiments/cm5-phase10e/artifacts/e1-control-report-repro01
# Use a new output name and --native-spi-hz 100000 for the high-rate case.
# The strict high-rate report is expected to remain PARTIAL with current code.
```

## Processes at completion

No QEMU, experiment runner, test or build from this task remains running. Both
new guests shut down normally; no background retry/1MHz campaign is scheduled.
The process audit still observes Codex app-server services PIDs517/616 and a
pre-existing `codex resume --last` client PID895 (parent332, about7h old). This
tool session's shell ancestry goes through app-server517, not895; ownership/
activity of that terminal client is not established. None was interrupted or
terminated. They are not evidence of a still-running QEMU/test. See
`artifacts/e1-processes-final.json` and the final Git/process evidence.
