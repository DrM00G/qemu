# Phase 10I status — 2026-11-16

The preferred GPIO vertical slice is implemented and proven through the original
captured Linux driver. This is a local AI-assisted experiment, not eligible for
upstream contribution. No physical hardware was accessed. No proprietary FSW was
obtained or explicitly launched; existing captured-image boot services were not
changed and no approved FSW application workload was tested.

## State recovery and preservation

Branch cm5-rp1-hardware, unchanged HEAD872181e1de29acb4c13ffdd8937ee6c9fa7d11bd.
Read AGENTS.md, code provenance, relevant device/qtest/icount/replay documentation,
complete H handoff and G/F.2/F.1 boot/provenance records. The requested Downloads
prompt was missing; the exact assignment was found in the Windows projects
folder and copied privately with origin/hash metadata. All previous uncommitted
F.2/G/H work was preserved. Initial comparison matched all72 H final source hashes.

Private root: /home/aweso/cm5-v8-lab/phase10i/i-20261116T190606Z. Its initial
source/ checkpoint, staged/unstaged/status records and source-hashes.json predate
substantial edits. Additional per-run execution snapshots bind sources to actual
guests. A separately named pre-guest snapshot was taken after the first guest
had launched; its metadata says so. No commit, stage, push, reset, clean, stash,
pull, original-image write or production verification change was performed.
Builds used-j2; full Linux guests ran sequentially on fresh regular qcow2 overlays.

## Implemented hardware and DT contract

New rp1-gpio device implements GPIO20/21 in the physical RP1 BAR1 IO_BANK0,
SYS_RIO0 and PADS_BANK0 windows. It implements bounded line direction, output
latch, digital sample/readback, RW/XOR/SET/CLEAR aliases, raw edge/level enables,
acknowledgement, mask/force and bank0 interrupt state. GPIO state precedes its
native RP1 MSI-X vector0 notification, delivered through BCM2712 MIP/GIC. SPI
vector19 shares the existing source helper while retaining its diagnostics and
H edge sent-latch behavior. No direct-GIC bypass or new serializer/timing logic.

Machine rp1-gpio-lab defaults off and requires native PCIe. Only when enabled is
the GPIO child initialized/realized and mapped. Endpoint reset clears its state;
clock-off accesses and unsupported registers/lines/functions return explicit
errors. No broad provider success stub was added. See GPIO-SOURCE-CONTRACT.md and
reference-sources.json for pinned Linux driver/bindings/gpiolib and RP1 datasheet
sources, register details and documented reset/pull/zero-delay lab conventions.

The generator adds exactly one compatible GPIO provider and changes three
connector metadata properties. Standard gpio-reserved-ranges reserves52 of54
compiled descriptors, leaving only20/21. The physical reg/compatible/cell binding
is preserved, with only bank0 IRQ exposed and no physical hogs/alt-function
children imported. The existing generated fallback is byte-identical in the
no-op contract test. Arbitrary physical DT replacement remains rejected.

The contract records selected physical reference, base, target, specification and
executable hashes, exact allowlist and binding/range/phandle/IRQ postconditions.
Actual runtime GPIO property hashes match in every guest observation and the live
FDT hash is stable. Full generated snapshots precede ARM boot fixups, so live FDT
identity is recorded independently rather than claimed identical to a dumpdtb.
BOOT_ORDER0xf14 remains an UNCONFIRMED fixture/software firmware proxy.

## Focused regression results

- 39 hardware qtests PASS: RP1 22, CM5 8, MIP3, SDHCI6. Five are new GPIO tests.
- 141 host tests PASS across A/D/E/F/F.1/F.2/G/H/I; I adds five DT contract/negative
 cases and a real canonical-PTY upload/exact-byte/syntax test.
- 19 ordering cases repeat PASS with identical complete normalized event/protocol
 sequences. All14 earlier H event/protocol checksums match H exactly.
- The retained delayed-service qtest still validates withheld software service at
 a controlled virtual boundary; no production interrupt-delay knob was added.
- I-only hardware diff checkpatch:0 errors/0 warnings (sign-off check omitted
 because this work must not be submitted). Build succeeds with-j2.

New qtests assert initialization/aliases, direction/latch/sample, invalid lines,
edge/level/ack/rearm, vector/function masking and pending replay, reset/clock-off,
SPI IRQ isolation, bus-master blocking, native MIP/GIC pending and PCIe PERST.
The model processes MMIO/timer callbacks under QEMU's device locking; no test
claims arbitrary host-thread scheduling order. Controlled qtest clock values are
virtual ns, not host elapsed time or physical instruction timing.

## Original captured-kernel gates

The final host10k run i-native10k-03 is PASS: original6.18.50+rpt-rpi-2712 kernel,
original initramfs, same-overlay BOOT-selected exports, native eMMC, unchanged
roots2 OS/FSW dm-verity tables/mounts, systemd PID1, two independently active
multi-user observations, native RP1 [1de4:0001]/BARs/MFD/clock200MHz, original DW
SPI driver,90 messages/90 strict CS segments/69,210 correct bytes, normal shutdown
and host LOGS persistence. Early inactive and one systemctl timeout observation
were retained; active observations at368.33s and399.23s independently decide the
gate. Serial-only marker fields are not substituted for the stronger observers.

All five GPIO observations PASS through original builtin pinctrl-rp1 and cdev-v1:
GPIO20 output and GPIO21 input read1/0/1/0; edge IDs1/2/1/2; IRQ delta4 each;
no extra event; duplicate output ownership EBUSY; reserved19/22/28/53 and out-of-
range54 rejected EINVAL. Actual driver symlink and QOM realization are recorded.
Native trace records20 GPIO vector0 and2,378 SPI vector19 emissions/deliveries,
with no unsupported GPIO MMIO. G aggregate counters include both sources;
I reports per-vector counts to avoid calling GPIO events SPI events.

Fixed instruction-clock100k control i-fixed100k-01 is PASS:126 messages/126 strict
CS segments/96,894 correct bytes, original V8 provenance/verity/native gates,
seven GPIO observations all PASS with IRQ delta4 each, two active multi-user
observations, normal shutdown and host LOGS persistence. This is one extra
18-message observation compared with H's108/108 control; the workload definition
is unchanged. All13 vertical checks pass in both final guests. The fixed profile
uses tcg,thread=single and icount shift0; external observer launch and guest idle
warp make whole-run times/iteration counts unsuitable as a determinism claim.
OneMHz was not rerun. H's126 messages/134 CS segments PARTIAL and its historical
G single-pass qualification remain unchanged; no rate or CS-hold tuning occurred.

## Failed attempts and debug evidence

The first implementation initialized the optional child even when unrealized;
default qtests exposed QDEV's realized-child assertion. Initialization moved to
the enabled realize path; all default and opt-in regressions now pass. Private
first build/test failures remain preserved.

Guest i-native10k failed observer transport before any SPI/GPIO stimulus: a long
embedded Python source line was truncated by canonical tty handling. It was
normally shut down; this is INCONCLUSIVE, not a peripheral failure or gate pass.
Source is now sent as short adjacent literals; a real-PTY test proves exact
uploaded bytes and syntax without executing GPIO operations on the host.

Guest i-native10k-02 passed original V8/SPI90/90 but GPIO discovery reported two
chips and performed no line operations. The final attempt proves gpiochip0 and
gpiochip4 are aliases with the same st_rdev. Discovery now preserves both records
and deduplicates device identity; no hardware assertion was weakened. The second
attempt is driver-probe/SPI evidence, not functional GPIO evidence.

## Hardware correspondence and FSW readiness

The machine-readable manifest and matrix join selected/captured-live physical DT,
generated base/target, QOM realized queries/HMP qtree+mtree and actual Linux bus/
driver/IRQ evidence. They inventory179 compatible physical nodes and19 capability
rows; raw node counts are stage/path comparisons, not a target for importing
unsupported hardware. Selected-vs-generated base raw counts are315 physical-only,
30 runtime-only,8 common and7 changed; the added provider is one runtime-path node
because the physical tree has an /axi ancestor. Historical runtime counts include
ARM boot fixups and are not the same snapshot stage.

All six capability classes are represented. High-priority advertised-but-unvalidated
clock outputs remain explicit. QOM null means not established, not absent.
Platform/PCI/SPI/I2C bindings were enumerated; AMBA UART/RTC driver links were not,
so their binding field remains null despite realized devices and working console.
Actual mip_msi binding and native delivery are separately recorded. Static DT
assertions are not new physical functional measurements. Every FSW requirement is
UNKNOWN. The workday read-only plan and comparison-record schema prepare approval
and matching Linux-only/physical/QEMU evidence without touching the real board.

## Limits and next steps

Only20/21 cdev is validated. The original driver exposes54 compiled pinctrl
entries; bulk debug, alternate functions, filters, other banks and gpiomem are
unsupported. Pads are logical, loopback is synthetic zero-delay and SPI remains
independently logically wired. GPIO electrical/synchronizer/filter/reset timing,
full clock/reset providers, SPI DMA, Ethernet/USB/I2C and physical fixture behavior
are unproven or absent. Do not expose them just to reduce DT mismatch counts.

Four guest CPUs are online, but I did not rerun H's SMP worker stress. H's bounded
concurrency PASS remains historical; device qtests are deterministic, live Linux
host-clock execution is not. Icount uses single-thread TCG and is not physical
BCM2712 calibration or deterministic MTTCG. Record/replay remains unvalidated and
the custom devices are unmigratable. No new physical maximum-rate claim follows.
Prioritize supervisor-approved FSW API/fixture requirements, real provider-gap
audit, then one required unsupported vertical slice. See NEXT-SESSION.md.

## Final audit and evidence index

integration-results.json contains sanitized final guest identities, source and
executable hashes, selected-file hashes, boot/native/vertical checks, exact SPI
counts, per-vector interrupts, GPIO operation records and actual live FDT hashes.
failed-attempts.json preserves the distinct incomplete/control attempt meanings.
ordering-results.json and sequences-final/ retain repeated controlled-clock
qtest event/protocol evidence; test-results.json lists every suite/count.
The private root contains raw logs/images/exports and the initial checkpoint.
GIT-STATUS.md links the complete final private status and diff, records the
collapsed review view, and distinguishes inherited modifications from I changes.

The final preservation audit finds66/72 initial dirty-source files byte-identical;
six existing files were intentionally extended, none missing. All H files and
SPI core/header/trace sources remain identical. I-only hardware scope is10 files,
649 added/8 removed lines including new bounded device/header and five qtests;
the complete HEAD diff also contains the older preserved F.2/G/H changes.
Original golden identity and selected kernel/initramfs hashes pass before/after
checks; selected physical DT and accepted metadata were not modified. No full
Linux QEMU process remains after the completed gates.
