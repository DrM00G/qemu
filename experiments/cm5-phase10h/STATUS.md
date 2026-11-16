# Phase 10H — deterministic ordering and native guest evidence

Local AI-assisted experiments only; not eligible for upstream contribution.
Branch `cm5-rp1-hardware`, HEAD `872181e1de29acb4c13ffdd8937ee6c9fa7d11bd`
remain unchanged. The original dirty F.2/G work is preserved. No commit, push,
reset, clean, stash, original-media/metadata write, physical hardware access or
host settings change. Builds use-j2; full Linux guests ran serially.

Private source-only pre-edit checkpoint and raw evidence root:
`/home/aweso/cm5-v8-lab/phase10h/h-20261116T175856Z`.
It includes34 source hashes/copies, complete initial staged/unstaged/untracked
status, source diffs, all failed attempts and private per-run disks/logs. All12
checkpointed F.1/F.2 source files remain byte-identical. Earlier normalized
iterations are retained in private normalized-iterations/. Final normalized
qtest evidence is sequences-validated/ and private ordering-10/.

## Demonstrated correction

RP1 edge-mode held sources no longer emit duplicate MSI-X notifications on
unrelated PCI configuration writes or function mask/unmask transitions. A
separate sent-edge latch clears on source fall/reset. IACK outstanding remains
a separate rearm lifecycle. The regression fails against the pre-H executable
(message RAM is rewritten without a new source edge), then passes corrected
code and checks a second genuine RX edge. Actual Linux uses IACK mode cfg9;
the new edge guard is bypassed in that mode.

Native PCIe DMA diagnostics now expose actual inbound transaction result. They
change no transport/retry policy. An RP1 attempt, MSI-X PBA pending bit, accepted
bus write, MIP pulse, parent GIC pending bit and Linux IRQ service are distinct.
The native qtest records14 attempts,8 accepted inbound writes,4 decode failures;
two attempts stop before inbound dispatch with BME off. MIP decisions include
an explicit MIP1 positive control and a blocked host-mask case. Acceptance of a
bus write alone is never reported as successful interrupt delivery.

No SSI serializer, global scheduler, clock profile, FIFO depth, CS hold policy,
original driver or strict-oracle change occurred. G FIFO/shifter and remaining-
clock-work fixes remain intact. No clock tuning or stretch retry erased failure.

## Newly tested contracts

Eight new RP1 cases exercise held-edge duplicate suppression, refill at7999ns
before an8000ns completion, function-mask pending replay plus RX reassertion
before IACK,24000ns delayed software service, disable at7999ns, live BAR/decode
changes, two independent TEST vectors and BME-off before completion.

The native CM5IO MSI test now establishes a live/unmasked MIP1 vector8 positive
control before proving endpoint DMA cannot signal it; preserves an already-
latched GIC edge across endpoint reset; and cancels masked PBA plus the next
active SPI frame on PERST. After parent clear and link recovery, no phantom RX
or GIC event appears. Existing vector/range/clock/error/storage tests remain.

Fourteen selected ordering cases pass twice with identical normalized device,
MMIO command/reply and combined event sequences, including QMP reset handler
entry/exit. Semantic checks require exact TX/RX order, CS segments and selected
notification counts. Empty captures, extra completions and extra CS segments
cannot pass. Reset-handler return is not treated as reset-completed evidence;
actual post-reset state assertions establish outcomes.

Fresh full hardware suites: RP1 18 +CM5IO7 +MIP3 +SDHCI6 =34 passing cases.
Fresh host units: existing130 +H evidence guards5 =135 PASS. The strengthened
native case is also rerun twice by the final trace harness after its last test
assertion additions. Build-j2, Python syntax and diff checks pass. Final H
hardware/test mechanical checkpatch:0 errors/0 warnings. Its automatic submission
wording grants no upstream eligibility to AI-assisted content.

## Actual original-kernel integration

Every row uses fresh disposable golden-backed eMMC, BOOT-selected original
6.18.50 kernel/initramfs, native BCM2712 PCIe/RP1/MSI-X/MIP/DesignWare SPI, both
original roots2/V mappings, systemd PID1, independent active multi-user checks,
normal poweroff and persisted host-read LOGS. SPI framing is a separate gate.
No old G result is counted as fresh.

| Fresh run | Strict messages/CS segments | Result |
| --- | --- | --- |
| A: default host clock10kHz |90/90 |PASS,14 native +16 provenance checks |
| B: fixed1ns instruction clock100kHz |108/108 |PASS,14 native +16 provenance checks |
| C: fixed1ns instruction clock1MHz |126/134 |PARTIAL, strict framing fails; other13 native and15 provenance checks pass |
| Separate host-clock10kHz SMP stress |90/90 |PASS,14 native +16 provenance checks;15 worker validations PASS |

A pairs2381 notifications with2381 MIP deliveries. C pairs all3322 notifications
with3322 MIP deliveries, with no exhausted capture. See guest-results.json for
actual per-run hashes, observations, checks, exact message counts and explicit
host wall seconds. Legacy serial-marker flags are retained privately; they do
not override independent active multi-user/verity/runtime observations.

C fragments zero-based message59 (4096 bytes) into192+575+701+602+672+634+480+240,
and message64 (257 bytes) into189+68. All96894 bytes retain correct concatenated
identity; this does not pass CS framing. Eight recorded empty completion/refill
gaps are322324..1132657 virtual ns against8000ns word periods; callback lateness
at each drain is zero. Complete joined failure sequences are published in
stretch-failure-analysis.json, with all original traces private.

This proves modeled FIFO starvation/late service and changes the stretch
assessment from the historical single G pass. Its underlying software-service
delay is not fully isolated, and no matched pre-H executable control was run.
All notifications pairing with MIP does not prove every GIC servicing detail.
The unchanged SSI and cfg9 IACK control path, on-time callbacks and actual empty
FIFO/late refill support starvation rather than a demonstrated lost/duplicate
notification defect. Do not describe the single prior1MHz pass as robust or
physical timing calibration. No new1MHz retry or clock search was performed.

## Delayed service and concurrency

The separately selected qtest withholds RX reads and RP1 IACK for24000 virtual
ns after first completion. Hardware continues, preserving two ordered RX words;
IACK while RX remains pending retriggers; servicing RX then IACK quiesces.
A subsequent late refill starts another CS segment with the correct byte.
This is controlled delayed software service, not measured controller dispatch
latency. It requires no hardware timing knob and affects no ordinary guest run.

Optional --phase10h-smp-stress is default-off. It uses bounded guest CPU1/2/3
workers for private-RAM hashing and read-only RP1 chip-ID MMIO during native SPI,
with readiness, affinity, progress, checksums and guest-monotonic intervals.
The completed host-clock stress run has separate CPU0/1/2/3 TCG threads;
fixed-clock B instead has ALL CPUs/TCG. All15 workers across five observations
pass host-recomputed checksum, affinity, positive progress and overlap checks.
Every worker covers its full native-observer interval; loop counts range27008
to96192. All four guest CPUs are online. Strict framing remains90/90 and all2383
notifications pair with MIP delivery. Independent active observations occur at
368.61 and399.5 guest-uptime seconds. This is one bounded SMP stress experiment,
not deterministic SMP, exhaustive interleaving/reset coverage or timing calibration.
The initial serial coordinator skipped stress after C returned PARTIAL; after
causal review found no demonstrated ordering blocker, stress was launched
separately, retaining the failed stretch and unchanged strict oracle.

## Failed attempts and remaining limits

Private evidence preserves the expected pre-fix duplicate assertion; a masked
notification test initially assumed scratch RAM zero despite generated DT
contents (fixed initialization); combined regular-file stderr capture suffered
overlapping file offsets (fixed with one pipe); a parser initially matched
printed command-line trace names (fixed by anchoring actual trace lines).
An incidental inspection used provenance/result.json instead of the actual
provenance/provenance.json; no guest evidence was changed. Four initial style
warnings were fixed. These are harness/development failures, not hardware fixes.

No physical CM5 measurements, physical CPU calibration, deterministic MTTCG or
record/replay validation. Interactive fixed-icount guests retain external input
and background-service variability. Late serializer-dispatch catch-up, blocked
MSI automatic retry, full MIP level/VPU semantics, GPIO/pinctrl, SPI DMA and
electrical timing remain unproven/unimplemented. BOOT_ORDER0xf14 is an unconfirmed
fixture; generated lab DT substitutes for the selected/exported physical DT.
Original golden/kernel/initramfs/verity metadata remain protected and unchanged.
COMPARISON.md and the schema/examples separate observable metrics, internal
snapshots, synthetic stress and uncollected physical quantities. NEXT-SESSION.md
hands off the delayed-dispatch contract and controlled concurrency work.

## Final repository and process audit

All initial status paths remain present; no source/artifact was discarded.
Nothing is staged. The full tracked diff (including pre-existing F.2/G changes)
is19 files,806 insertions and22 deletions. H changes six already-tracked files,
extends the already-untracked G runner and adds this experiment directory.
Full staged/unstaged/untracked status, source manifests, diffs and preservation
proof are private; git-summary.json and evidence-index.json point to them.
No QEMU guest, block helper, experiment runner or guest worker remains running.
Branch and HEAD remain unchanged; no commit/push was made.
