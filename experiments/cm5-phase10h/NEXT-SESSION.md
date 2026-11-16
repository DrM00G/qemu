# Phase 10I continuation

Read AGENTS.md and docs/devel/code-provenance.rst. Local AI-assisted experiments
only; no upstream contribution eligibility. Branch cm5-rp1-hardware, HEAD
872181e1de29acb4c13ffdd8937ee6c9fa7d11bd must remain unchanged unless a later user
explicitly changes scope. No commit/push/reset/clean/stash, original media,
physical CM5/EEPROM/OTP/RPMB/host block devices or host settings changes.
Build-j2, fresh regular-file-backed disposable media, one full Linux guest.

## Recovery and actual evidence

Private H root `/home/aweso/cm5-v8-lab/phase10h/h-20261116T175856Z` contains the
pre-edit source-only checkpoint: source/, source-hashes.json, complete initial
status.txt, staged.txt, unstaged.txt. F.2/G began dirty and remain preserved.
`f2-preservation.json` verifies all12 checkpointed F.1/F.2 files unchanged.
Final source/status/diff/process inventories are stored in the same private root.
Raw Linux logs, exact per-run observers, source snapshots, accepted-media
provenance, disposable disks and all failed attempts stay private.

Read STATUS.md and guest-results.json for fresh final gate results. The fresh
fixed1ns1MHz stretch is PARTIAL (126 messages/134 segments); preserve
stretch-failure-analysis.json and its complete two failed-message sequences. Do not
substitute old G passes for a new run. `ordering-results.json` records fourteen
cases, each run twice, including source/executable hashes. `sequences-validated/`
has final combined command/device/reply sequences. The corresponding private
raw iteration is ordering-10/. Earlier raw iterations and normalized-iterations/
remain preserved; failures are documented in STATUS.md.

The G run wrapper still stores native/provenance/correlation/metrics reports
in each H baseline directory (baseline-a, baseline-b, baseline-c, smp-stress).
Private Phase10C exports live under
`/home/aweso/cm5-v8-lab/phase10c/<output-basename>-v8/`:
choose globally unused output basenames as well as fresh H directories.
Provenance is `provenance/provenance.json`, not provenance/result.json.

Original golden remains `/home/aweso/cm5-v8-lab/golden/cm5-emmc-userarea.img`,
SHA256 e2fb1a85c2652838793e58f8b13ef908e2e4a4c4295e27297ce742287f69cb87.
Accepted manifest `/home/aweso/cm5-v8-lab/phase10f2/accepted-01/accepted-hashes.json`.
Kernel SHA256154f0ea1e14bb1075077dfd1bdc63c1502bc0b17b0354628d515b4fbd3a4198d;
initramfs SHA256fcaade1e3aab0d79a51a170f556d25d0d1476bc17518099de54f5ebe16feab5b.
Never derive acceptance from a modified image. Selected original physical DT is
validated/exported; generated lab DT executes. BOOT_ORDER0xf14 is still an
unconfirmed proxy fixture. No physical firmware instructions execute.

## What changed in H

- `hw/misc/rp1-pci.c`: separate edge-source sent latch prevents held-edge source
  replay on unrelated PCI config/function-mask writes. Clear on source fall and
  reset. IACK outstanding remains a separate rearm contract. New regression
  fails old binary and passes corrected code. Actual Linux uses IACK mode.
- `hw/arm/bcm2712-pcie.c`, arm trace-events: actual inbound DMA transaction
  result trace. This is diagnostic; notification attempts are not delivery.
- `tests/qtest/rp1-test.c`: eight new boundary/interrupt/disable/BAR/BME/two-vector
  cases. Existing G cases remain. Native MSI case in cm5io-test.c now validates
  live other-controller isolation, preserved parent GIC pending on endpoint
  reset, and cancellation of masked PBA plus active shifter after PERST.
- `experiments/cm5-phase10h/`: repeat/normalization and semantic checks,
  optional guest SMP stress worker/wrapper, safe guest-summary export, source-
  backed invariants, timing limits and common event schema/examples.
- Phase10C/G runners: default-off `--phase10h-smp-stress`, early argument
  rejection without native mode, embedded/public worker source snapshots and
  existing cached observer transport. Ordinary execution profiles are unchanged.

No SSI serializer or global scheduler change occurred. G clock-progress and
FIFO/shifter corrections remain intact. No FIFO inflation, synthetic CS hold,
rate reduction, driver replacement or strict-oracle relaxation.

## Smallest next useful ordering work

1. Define a faithful delayed-serializer-dispatch contract before changing queued
   deadlines or adding MMIO catch-up. `util/qemu-timer.c` visits intermediate
   deadlines during qtest advancement and removes a timer before its callback.
   A large clock_step is not a late-dispatch reproduction. Need deterministic
   control over callback dispatch separately from software service/MMIO arrival.
2. Preserve tests at deadline-1ns, completion-first/refill-second, mask/unmask,
   RX reassertion before IACK, disable/reset, and live BAR/BME transitions. Extend
   with explicit equal-time order permutations; do not assert arbitrary host
   thread race winners. Keep actual bytes, thresholds, CS and GIC/PBA checks.
3. Current h-delayed-service delays software RX/IACK by24000 virtual ns, not
   hardware notification transport. It proves two queued words complete without
   duplicate RX, IACK retrigger works and late refill legitimately splits CS.
   A new dispatch-delay injection needs its own location, optional property,
   cancellation/reset semantics and default-off tests. Do not reinterpret this
   existing software delay as measured RP1 propagation latency.
4. Do not silently turn a blocked MSI write into success or invent automatic
   transport retry. QEMU generic MSI-X send returns void; outstanding source
   state is not acceptance. Native transaction trace distinguishes MemTxResult,
   while MIP delivery is separate. Current tested BME restore requires explicit
   IACK retry. Hardware-spec evidence is needed before changing that contract.
5. Use the optional host-clock SMP workload to stress shared MMIO with actual
   kernel CPUs. Check affinity and worker overlap/result fields; repeat with a
   new directory for different interleavings. Do not describe icount single-
   thread/SMP4 as deterministic MTTCG. Live SMP reset and IRQ-affinity stress
   remain further work; device-level reset tests are currently stronger.
6. Record/replay is unvalidated. Before an actual record/replay pair, audit
   custom machine reset, UART/control input, eMMC/block blkreplay completions
   and unmigratable devices. Snapshot VMState is unavailable. Do not advertise
   from-reset replay support merely because icount can launch the machine.

## Future physical comparison

COMPARISON.md and comparison-event.schema.json separate actual Linux/analyzer
observations from internal emulator snapshots and synthetic stress. No physical
measurements exist. First establish approved matching physical wiring/slave/
software/DT/clock fixture and whole-message hashes/CS segments, then calibrate
CPU/MMIO/IRQ service budgets. Keep unavailable FIFO/shifter/scheduler fields
null on physical logs. No electrical SCLK or BCM2712 cycle calibration follows
from current fixed instruction time. Do not interrogate physical hardware
without a later explicit task authorizing it.

Final fresh gate outcomes: host10k PASS90/90; fixed1ns100k PASS108/108;
fixed1ns1MHz PARTIAL126/134 (messages59,64); host10k MTTCG/SMP stress PASS90/90.
All four boots preserve verified OS/FSW, independent active multi-user, native
PCIe/BAR/IRQ operation, normal poweroff and LOGS readback. Fifteen worker
checksums/affinities/progress/whole-observer overlaps pass, with four online
CPUs. This does not establish arbitrary SMP reset/interleaving correctness.
Final qtests34 and host units135 pass; fourteen selected ordering cases each
pass twice with identical normalized traces. No task guest/worker remains at
completion; consult final process audit. No commit was made.
