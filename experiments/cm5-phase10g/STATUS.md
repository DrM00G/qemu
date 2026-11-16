# Phase 10G — verified results and limits

**100kHz strict framing passes in two independent cold runs;1MHz passes one full
stretch run under the explicit fixed instruction-clock profile. Default host
clock and adaptive instruction time still fragment and remain PARTIAL.** This
is local AI-assisted research, not upstream-eligible QEMU content and not a
physical CPU/SPI timing-equivalence claim.

Branch cm5-rp1-hardware; HEAD872181e1de29acb4c13ffdd8937ee6c9fa7d11bd unchanged.
All uncommitted F.2 sources and prior artifacts are preserved. No commit, push,
reset, clean, stash, physical-device/EEPROM/OTP/RPMB access, original-input write,
or Windows/system setting change. Builds use-j2; full Linux guests ran serially.
Source-only checkpoint: `/home/aweso/cm5-v8-lab/phase10g/g-20261116T121845Z`.
Fresh ignored evidence: `/home/aweso/projects/qemu/experiments/cm5-phase10g/artifacts/g-20261116T121845Z`.

## Actual original-kernel guest results

Every completed row below uses original captured6.18.50 kernel/initramfs selected
from the same fresh disposable golden-backed eMMC used by its guest, native
BCM2712 PCIe/RP1/clock/MSI-X/MIP, original roots2 metadata and the unchanged strict
CS oracle. All completed rows pass clean verified OS/FSW, systemd, two active
multi-user observations, normal shutdown and persisted LOGS. SPI status is
independent of those OS gates.

| Run / execution clock | Strict SPI | Messages | CS segments |
| --- | --- | ---: | ---: |
| control-10k / host | PASS |90 |90 |
| baseline-100k / host | PARTIAL |90 |97 |
| adaptive-fixed-100k-01 / adaptive icount | PARTIAL |126 |204 |
| fixed-upload-100k-01 / fixed1ns icount | PASS |126 |126 |
| fixed-upload-100k-02 / fixed1ns icount, cold confirmation | PASS |108 |108 |
| fixed-upload-1m / fixed1ns icount | PASS |126 |126 |

Each passing row passes all14 native hardware and16 selected-byte/runtime
provenance checks. More than90 messages occur when OS readiness requires more
observer batches; every early/failed message remains in validation. No first
message is discarded. Each run has exact commands, launch executable identity,
private source snapshots, input/selection provenance, independent reports and
LOGS readback. See run-totals.json for actual wall times and observed uptimes.
Legacy serial-marker-only multi_user/full_scan_complete booleans remain as
recorded, not rewritten to hide missing markers.

Fixed100kHz really programs input200MHz/BAUDR2000.1MHz programs BAUDR200, not a
silently reduced rate. All3338/2861/3331 recorded notifications in the three
passing high-rate runs pair with native MIP delivery. The independent report
checks actual driver/BAR/IRQ operation, repeated SPI after multi-user and stable
idle IRQ counts. No electrical waveform or physical throughput is measured.

## Causal diagnosis and measured boundary evidence

The new bounded capture is independent of the old first256 events. It records
FIFO/shifter completion before/after, empty refill, raw thresholds/masks/IRQ,
SER/SSIENR/BUSY/CS, timer arm/deadline/callback entry, native notification and
MIP delivery. RP1 source/ACK/MSI-X mask/pending state is recorded too. SSI enable
epochs and byte/segment positions join to submitted messages. Capture does not
exhaust; requested indices3,32,35 are covered even when those old failure indices
pass in the fresh run. Full sequences for every newly failed message remain.

Fresh default100kHz fails at zero-based messages0,1,5,11,12 (97 segments).
Message0's first/second DR observations are471156 virtual ns apart against an
80000ns word period. The first word completes with TX FIFO0/RX1, CS deasserts,
and the later same-epoch write starts another segment. Completion-after to
refill is272249 virtual ns; callback entry is69978ns late. Message11 also drains
after words1077/2922 with1.418ms/2.572ms virtual refill gaps. TX-empty is already
asserted and all2313 notifications pair with delivered MIP events. The observed
failure is genuine modeled FIFO starvation/service latency, not demonstrated
lost MIP delivery or a CS line that should be held unconditionally.

Adaptive time passes early batches but later long transfers fragment:126
messages/204 segments, with3181 notifications paired. This is why one early
pass cannot establish a successful rate. Fixed instruction time yields first
DR gaps24045ns and20032ns at100kHz, before80000ns deadlines; the1MHz gap is2029ns
before8000ns. causal-comparison.json and analysis-final/ contain exact inputs,
source hashes, complete sequences, configured rates and independent joins.

These observations support a CPU service-budget/timebase explanation. Default
TCG virtual time includes host translation/preemption/tracing costs; fixed icount
counts guest instructions and idle warp instead. The pinned driver explicitly
warns about native CS deassertion when FIFO supply cannot keep up. The MMIO glue
uses normal PSSI setup for this compatible; the CS override is an Alpine-specific
quirk, not a defensible RP1 substitute. No FIFO inflation, driver patch, CS hold,
segment merging, payload recognition, clock lowering or oracle weakening occurred.

## Implemented hardware correction and regressions

A separate real clock-progress defect is fixed: pausing an active word no longer
restarts its entire frame, and changing its live input divider reschedules only
remaining serializer work. Scaled input-cycle work uses saturating arithmetic
and ceiling-to-ns scheduling. Same-frequency updates preserve the timer. This
is aggregate logical progress, not measured electrical phase. The strengthened
native clock test fails before the fix (RXFLR0 instead of1 at the remaining
half-frame boundary) and passes afterward, including200MHz-to100MHz retiming.
The fixed-clock high-rate success is not falsely attributed to this steady-rate-
unrelated correction alone.

New qtests cover real drain/refill/CS split and active-reset masked pending
MSI-X cancellation. A genuine qtest trace correlates an expected two-segment
failure with a1ns empty/refill gap. The four-queued-word test passed old code:
qtest visits intermediate deadlines, so it is coverage, not proof of corrected
late-callback drift. Queued frames still rearm from callback execution time;
absolute deadlines/MMIO catch-up need a separate delayed-dispatch contract/test.

| Fresh validation | Result |
| --- | --- |
| QEMU / focused target builds-j2 | PASS |
| RP1 / CM5IO / MIP / SDHCI qtests |10 /7 /3 /6 PASS =26 |
| G transport/correlation / E host units |5 /3 PASS |
| F.1 / F.2 / F / A / D units |23 /47 /20 /24 /8 PASS |
| Total host units |130 PASS |
| Mechanical hardware checkpatch |0 errors /0 warnings; no upstream eligibility |
| Final Python syntax / diff checks |PASS |
| Original input / preexisting F.1/F.2 preservation |PASS |
| Physical measurements |NONE |

## Preserved inconclusive attempts and limitations

The initial fixed-clock run reached kernel, verified root and systemd, but its
interactive observer upload stalled;600s timeout, no SPI observations and no
normal shutdown. Raw wrapper PARTIAL is superseded for SPI classification by
fixed-clock-classification.json: INCONCLUSIVE. A first adaptive diagnostic was
stopped before SPI (frame count0) after a real PTY test exposed an echo-off
prompt-prefix parse bug. adaptive-transport-abort.json records it. These are
transport evidence, not failed SPI messages or successful OS-survival runs.

An opt-in upload-once path now disables editing/echo, caches exact public code
in guest/run, prints a separating newline and waits for each result before
another invocation. Real Bash/PTY testing verifies exact bytes and two cached
executions. Old default transport remains available. Initial test import/PTY
cleanup failures and a reset-test RAM-zero assumption are retained separately;
board reset rewrites its generated DT, so the scratch sentinel is now cleared
before the no-phantom-write assertion.

Fixed icount uses tcg,thread=single with SMP4 and
shift=0,align=off,sleep=off. It is NOT a physical ARM cycle calibration. Adaptive
and default clocks remain PARTIAL; no arbitrary maximum physical SPI frequency
is declared. GPIO/pinctrl, SPI DMA, electrical timing, full RP1 register coverage
and physical fixture comparability remain unsupported/unmeasured. Runtime DT is
the explicit generated lab substitution; selected physical DT was not executed.
0xf14 remains an UNCONFIRMED EEPROM fixture; no ROM/EEPROM instructions execute.

PHYSICAL-VALIDATION-READINESS.md and comparison-schema.json define the small
future measurement/fixture contract. metrics.py exports actual virtual data,
with electrical SCLK left null. No physical collector/framework was built.
The next smallest fidelity work is calibrating the virtual CPU/MMIO service
budget against approved physical observations and a deterministic delayed-timer/
SMP ordering experiment. Keep strict CS and the lower-rate profile intact.

Final source manifest, complete Git status/diffs, input preservation, process
audit and evidence-index.json accompany NEXT-SESSION.md. Original protected OS,
FSW, kernel/initramfs, golden and roots2 data remain unchanged. No broad FEC
campaign or unrequested peripheral rewrite was performed.
