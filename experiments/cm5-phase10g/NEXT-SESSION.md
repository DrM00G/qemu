# Phase 10G — self-contained continuation

LOCAL AI-assisted research only; not upstream-eligible. Read AGENTS.md and
`docs/devel/code-provenance.rst`. Keep branch cm5-rp1-hardware and HEAD
872181e1de29acb4c13ffdd8937ee6c9fa7d11bd. No commit/push/reset/clean/stash,
physical equipment, host block devices, EEPROM/OTP/RPMB or host settings.
Original media/kernel/initramfs/verity roots2 must remain unchanged. Use-j2,
fresh unique directories and only one full Linux guest at a time.

## Starting state and preserved work

Repository `/home/aweso/projects/qemu`. The uncommitted F.1/F.2 files from the
previous session are unchanged (f2-preservation.json verifies every checkpoint
hash). Old Phase8/9 untracked artifacts remain. Phase10G modifies eleven existing
files, plus its new experiment directory. Final Git status/source hashes and
session paths are linked in evidence-index.json; no changes are staged.

Private source-only pre-hardware checkpoint: `/home/aweso/cm5-v8-lab/phase10g/g-20261116T121845Z`.
It contains source/, source-hashes.json, initial status/diffs and RESUME.md.
Fresh ignored evidence root: `/home/aweso/projects/qemu/experiments/cm5-phase10g/artifacts/g-20261116T121845Z`.
`source-manifest-v1.json` is the final inventory, not a claim that every final
postprocessor was used at guest launch. Each run has a separate execution-source
snapshot/executable identity. analysis-final/manifest.json records final
postprocessing commands and exact input/output/helper hashes.

Changed existing sources:
- hw/ssi/dw-apb-ssi.c, include/hw/ssi/dw-apb-ssi.h and SSI trace-events:
  bounded drain/refill/threshold/IRQ/timer/CS metadata and conserved remaining
  serializer work across clock gates/live input-divider changes.
- hw/misc/rp1-pci.c +misc trace-events and hw/intc/bcm2712-mip.c +intc trace-events:
  timestamped source/ACK/mask/pending/notification/MIP state; routing unchanged.
- tests/qtest/rp1-test.c and cm5io-test.c: three new RP1 cases and a strengthened
  native clock-progress regression.
- experiments/cm5-phase10e/native_profile.py: opt-in diagnostic events.
- experiments/cm5-phase10c/run.py: explicit instruction-clock profiles and an
  opt-in cached, non-editing observer transport; default host profile retained.

New G tools: run.py, correlate.py, metrics.py, correlation/real-PTY tests, common
comparison-schema.json and README/STATUS/readiness/handoff docs. The original
strict trace_check.py/report.py, SPI workload and captured drivers are unchanged.

## Private inputs and identities

Golden `/home/aweso/cm5-v8-lab/golden/cm5-emmc-userarea.img`,15634268160 bytes,
SHA256 e2fb1a85c2652838793e58f8b13ef908e2e4a4c4295e27297ce742287f69cb87.
Captured assets `/home/aweso/cm5-phase10-private/physical-boot/boot-assets/`,
manifest `/home/aweso/cm5-phase10-private/physical-boot.sha256`.
Independent acceptance:
`/home/aweso/cm5-v8-lab/phase10f2/accepted-01/accepted-hashes.json`.
Never derive acceptance from a mutated/fault image. Final preservation passes;
runner gates fully hash backing identity, final inventory checks metadata
continuity for the large immutable golden and fresh SHA256 for five captures.

Selected kernel SHA256
154f0ea1e14bb1075077dfd1bdc63c1502bc0b17b0354628d515b4fbd3a4198d;
original initramfs SHA256
fcaade1e3aab0d79a51a170f556d25d0d1476bc17518099de54f5ebe16feab5b.
All actual guest inputs come from the same active disposable BOOT/eMMC image.
Private per-run disks/source snapshots are under this G private root; exact
exports/argv are under `/home/aweso/cm5-v8-lab/phase10c/RUN_BASENAME/`.
0xf14 remains an UNCONFIRMED EEPROM fixture, USB is declared unavailable, no
EEPROM instructions execute. Physical selected DT is validated/exported;
generated compatible lab DT executes instead.

## Verified outcomes

| Profile/rate | Messages /CS segments | Result |
| --- | ---: | --- |
| Host10k control |90/90 |PASS |
| Host100k diagnostic baseline |90/97 |PARTIAL |
| Adaptive icount100k, tested transport |126/204 |PARTIAL |
| Fixed1ns100k first cold run |126/126 |PASS |
| Fixed1ns100k independent cold confirmation |108/108 |PASS |
| Fixed1ns1MHz stretch |126/126 |PASS, one trial |

Every completed row above passes clean original captured-kernel V8 boot, both
roots2/V mappings, verified OS/FSW, original systemd, two active multi-user
observations, native BAR/IRQ operation, normal shutdown and persisted LOGS.
Passing SPI rows also pass all14 native and16 provenance checks. More than90
messages reflect extra readiness observations; none are discarded or merged.
The three high-rate passes pair3338/2861/3331 notifications with MIP delivery.
Configured clocks are genuinely200MHz/2000 at100k and200MHz/200 at1MHz.
No spurious idle SPI IRQ stream is observed. No physical timing claim follows.

Host units: G5/E3/F.1 23/F.2 47/F20/A24/D8 =130 PASS. Hardware-model qtests:
RP1 10/CM5IO7/MIP3/SDHCI6 =26 PASS. Build-j2, final Python/diff checks and
mechanical hardware checkpatch (0 errors/0 warnings) pass. Expected-before-fix
clock failure is in clock-before.log; final native clock test passes. No broad
FEC campaign was run.

Two extra attempts are INCONCLUSIVE: the old interactive upload under fixed
clock timed out at600s before SPI; a first adaptive transport diagnostic was
stopped BEFORE SPI when the real PTY test exposed a prompt-prefix parser bug.
Both are preserved and neither counts as a rate pass/failure. Fixed upload now
disables editing/echo, caches exact code in guest/run, prints a separating
newline and permits one outstanding invocation. The real Bash/PTY test proves
exact uploaded bytes and two parsed executions. Earlier test setup/cleanup and
reset-RAM assumptions remain in logs, not reported as hardware defects.

## Causal conclusion and remaining fidelity boundary

Default100k failures at messages0,1,5,11,12 show actual FIFO-empty completion,
CS deassertion and late same-epoch refill; all2313 native notifications are
paired with MIP delivery. Message0's first/second write gap is471156 virtual ns
against80000ns frame time. Fixed-profile gaps are24045/20032ns at100k and2029ns
against8000ns at1MHz. Adaptive early success does not generalize: long-message
service gaps later fragment the workload. causal-comparison.json and final
correlation reports retain full failure sequences, including focus0,3,32,35.
No capture exhausts. Virtual, host and physical times are distinct.

Pinned core driver:
`/home/aweso/cm5-v8-lab/phase10e1/reference/spi-dw-core.c`, revision
cff533aec2fa601846766b32ff57204e0a61bed7, SHA256
e40952a11124cb354a6a6ce86344d90845c85d39a5df39fc33201be3cf36fe9f.
It warns native CS drops if software cannot sustain FIFO supply. MMIO glue in
phase10e/reference confirms normal PSSI; CS_OVERRIDE is Alpine-specific.
Do not enable a foreign quirk, hold CS unconditionally, inflate FIFO, lower SPI
speed, patch the driver or weaken the strict oracle.

The genuine remaining-clock fix is independent of steady-rate framing. Queued
frames still rearm from callback time. The four-frame test passed old code,
because qtest visits intermediate deadlines; it is coverage, not evidence of a
late-dispatch fix. Fixed icount's single-thread TCG/SMP4 and1ns per aggregate
instruction are a generic execution convention, NOT a physical CPU calibration.
Host/adaptive profiles remain PARTIAL. GPIO/pinctrl, electrical timing, SPI DMA,
full RP1 coverage and physical fixture equivalence remain unsupported/unmeasured.

## Reproduce and next smallest work

Use README's fresh-path commands. For high rates:
`python3 experiments/cm5-phase10g/run.py --hz 100000 --diagnostics
--execution-clock icount-1ns --work PRIVATE_FRESH --output FRESH_ARTIFACTS`.
Choose1000000 only after independently confirmed100k. The wrapper handles exact
BOOT selection and unchanged full gates. `--timeout 900` is available when a
slower host needs an explicitly larger wall budget; it does not change device
rates or guest verification. Existing passing runs used600s. All task guests,
block readers, qtests and helper shells have finished; inspect process-audit.json.

1. Adopt the explicit fixed profile for bounded functional high-rate work while
   retaining host10k/default failure evidence. Do not claim physical throughput
   or an arbitrary maximum frequency.
2. Before changing global/device scheduling, build a deterministic delayed-
   dispatch/SMP-MMIO ordering reproduction. Inspect accel/tcg/tcg-accel-ops-
   icount.c and -rr.c; budgets and newly armed deadlines are relevant hypotheses,
   not a proven generic-core defect. No global TCG scheduler was changed here.
3. Calibrate CPU/MMIO/IRQ refill budgets against later approved physical
   measurements. PHYSICAL-VALIDATION-READINESS.md defines fixture/wiring,
   version/DT/BAR/vector/clock/CS/data requirements and the common schema. No
   physical collector or equipment access occurred. Preserve exact message
   sequence/count/hash comparability; no warmup failure may be removed.
4. Extend only evidenced clock/reset/threshold cases or a real DMA-capable
   peripheral with its own contract. No unrelated USB/multimedia/GPIO rewrite
   and no new broad FEC corruption campaign are justified by this checkpoint.
