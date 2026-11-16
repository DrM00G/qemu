# Phase 10E — native RP1 primary target and bounded SPI stretch reached

**Actual captured 6.18.50 Linux now enumerates RP1 behind native BCM2712 PCIe,
assigns/accesses all three BARs and uses DesignWare SPI through native MSI-X/MIP.
Complete CS framing passes at the tested 10 kHz rate. Higher-rate framing fails
and remains an explicit limitation.** This is a local AI-assisted experiment,
not an upstream contribution or a physical timing/electrical-fidelity claim.

Branch/HEAD remain `cm5-rp1-hardware` /
`1a6703a4bb1590aa98e6993474b0a0551d8d8f60`. No commit, push, stash, reset,
clean, golden write, physical-device/EEPROM operation or original boot/metadata
modification occurred. Existing uncommitted work/artifacts were preserved.
Initial source snapshots are outside the checkout in the private Phase 10E lab;
initial Git status/source hashes are in `artifacts/initial/`. The final rebuild
after the accepted guest run changes only equivalent expression formatting,
diagnostic DT/QOM labels and qtest assertions; per-run executable hashes remain
separate from the final compiled-binary identity.

## Outcome by evidence level

| Item | Outcome | Evidence level |
| --- | --- | --- |
| RP1 logical link | Gen2 x4, gated by endpoint/clock/reset state | qtest and actual 6.18.50 driver |
| Expansion controller | Distinct domain0001; no endpoint, link down | qtest and actual driver |
| RP1 enumeration | 0002:01:00.0 [1de4:0001], behind 0002:00:00.0 [14e4:2712] | actual captured kernel |
| BAR0/1/2 | 16KiB /4MiB /64KiB, Linux assigned | kernel resource log and independent sysfs |
| BAR access | chip ID0x20001927, restored BAR2 scratch; MSI-X table works | actual kernel/userspace plus relocation qtests |
| Outbound translation | programmed windows, PCI bridge/BAR decode | 32/64-bit CPU aperture qtests; actual BAR traffic |
| Inbound translation | programmed RAM/MIP windows, bounds and master gating | qtests; actual MSI to MIP |
| MSI-X/MIP | 61 vectors allocated; vector19 delivered through MIP0 to SPI driver | qtests, trace, /proc/interrupts and completed ioctl |
| RP1 MFD and clock | original drivers bind; SYS clock200MHz observed | actual guest |
| DesignWare SPI | 90 correctly framed messages /69,210 eight-bit frames at 10kHz | original kernel/OS drivers and strict trace check |
| SPI repeat/idle IRQs | 2,292 delivered native events/handled IRQs; idle counts stable | actual trace and independent guest counters |
| Original verified boot | both roots2/V, systemd, multi-user twice, LOGS persisted, exit0 | actual original initramfs/kernel/golden overlay |
| GPIO/pinctrl, SPI DMA, other RP1 devices | unimplemented/unvalidated | no broad availability claim |
| BOOT proxy handoff | actionable Phase10F boundary documented | source inspection only |

Authoritative final result: `artifacts/report-final/result.json` (all 14 checks
true). Raw run: `e-native-spi-03`. The exact submitted public observer is saved
as `guest-observer.py`. Early `native-result.json` versions checked bytes/IRQs
without full framing and must not override the strict report. Early post-run
source inventories are labeled as inventories, not immutable execution snapshots.
Every run records its actual launch executable/private input identities.

## Actual final boot and functional evidence

All successful physical-kernel profiles use the **original captured kernel and
initramfs**, original roots2 metadata/module, OS/FSW and RECOVERY. No scan bypass,
resealing, production driver patch or verification disable was introduced.
The debug UART and synthetic SSI slave are explicit lab additions. SPI0 is
intentionally enabled in the generated lab DT; the captured live SPI0 node was
disabled. The physical DT is a reference, not blindly supplied to the emulator.

| Transition in e-native-spi-03 | Guest seconds |
| --- | ---: |
| Native RP1 link up, 5.0GT/s x4 | 3.154750 |
| Original RP1 MFD reads chip ID | 3.262713 |
| Captured /init executes | 3.551828 |
| Verified OS ext4 root mounts | 251.067423 |
| Independent active multi-user queries | 363.13, 394.11 |
| Normal Power down | 413.840626 |

QEMU returned0 without timeout; recorded wall time409.20s includes final identity
checks. Host and guest clocks differ; these are not physical performance or
FEC-correction timings. Both verity tables retain original roots2 and statusesV.
Captured OS Python/libc, verified FSW reads, guest LOGS fsync/readback and host
post-shutdown LOGS recovery pass. FSW remains only lost+found, with no executable.
All overlay disk allocations are confined to LOGS; virtual BAR2 scratch writes
are MMIO, not eMMC writes. The original full verified OS scan remains intact.
Inherited serial-marker-only `multi_user/full_scan_complete` booleans may be
false; independent saved userspace observations establish the real milestones.

Linux independently reports these resources:

| BAR | CPU resource | Size | Access evidence |
| --- | --- | ---: | --- |
| 0 | 0x1f00410000–0x1f00413fff | 16KiB | actual MSI-X vector programming/delivery; qtest table/PBA |
| 1 | 0x1f00000000–0x1f003fffff | 4MiB | original MFD + userspace chip ID; clock and SPI driver accesses |
| 2 | 0x1f00400000–0x1f0040ffff | 64KiB | userspace first/last word write/read/restore; qtest relocation/reset |

These addresses were assigned by PCI configuration. No guest-assigned BAR
address was inserted into RP1's device-relative implementation.

## Native model and tested scope

The RP1 host owns a real root/secondary PCI hierarchy and endpoint. The empty
expansion host remains separate. Link requires endpoint realization, supported
MDIO reference-clock state, bridge/PERST release, forced-reset clear, secondary
bus reset clear and Link Disable clear. A 1ms virtual completion timer is a
logical scheduling convention, not PHY training measurement. Reset cancels
training and resets the endpoint; invalid/absent config returns absence, without
claiming successful link/access. Qtests exercise reconnection delay, Link Disable,
secondary-bus reset, PERST and global reset.

Indexed BDF configuration uses +0x9000/+0x8000 and PCI-core bus numbers. Four
outbound descriptors decode CPU base/limit and PCI base inside measured platform
apertures. PCI-core memory/bridge/command gating still applies. Tests relocate
all BARs, use both CPU apertures and reject window ends/overflow. The actual
Linux driver uses the non-prefetchable RP1 window; no endpoint-prefetchable DMA
workload is claimed merely from the64-bit aperture qtest.

Ten inbound descriptors decode supported nonlinear sizes and UBUS remaps into
modeled installed RAM or the host's connected MIP doorbell. MSI is not a generic
identity-DMA alias. RAM exact-end/disabled-window and bus-master tests reject
invalid traffic; another host's MIP is isolated. The physical peripheral/peer
DMA alias is omitted/unsupported, as are non-RAM/non-MIP destinations. No native
SPI DMA engine, peer DMA, ATS, full AER/error reporting, hotplug or migration
fidelity is claimed. Bus range remains the bounded lab0..15. Linux still reports
unassignable legacy bridge I/O windows because no I/O-port aperture is modeled;
this does not imply a successful I/O mapping.

The outbound region is a forwarding aperture: a CPU SSI register write can
synchronously cause endpoint MSI through inbound. Only this forwarding region
is marked reentrancy-safe, following QEMU's forwarding-aperture convention;
inbound destinations cannot recurse into it. The actual native address/data
translation and MIP decode remain active. The initial guard failure was retained
and corrected before interrupt success was claimed.

MSI-X table/PBA placement remains the existing experimental layout, not a
measured physical PCI configuration dump. The RP1 level IRQ ACK state is independent of
MIP's address/data-to-edge logic. A real SSI event is the new qtest source,
not direct GIC injection. Tests cover vector/function gating, pending replay,
ACK rearm, MIP masks, invalid doorbell offsets, other-MIP isolation, reset and
translated RAM writes. Existing GPEX/MIP tests also pass.

The bounded clock subset supports the exercised SYS/SLOW/PLL paths, coherent
readback, derived lock, parent status, gate and reset. SYS feeds the serializer
frequency; the original clk-rp1 provider reports200MHz. Lab boot PLL presets
are not captured firmware state. Other clock registers remain unimplemented and
logged; audio/video functionality and general clock programming are not validated.
The original DesignWare driver reports unavailable DMA and uses PIO normally.
Its optional reset and pinctrl properties are not falsely advertised as providers;
logical SSI wiring is fixed. No RP1 firmware/mailbox/shared-SRAM protocol executes.

## SPI validation and the higher-rate limitation

Each observer submits18 real ioctl messages: three repetitions of lengths
4/64/65/128/257/4096 at 10kHz, mode0, eight bits. Across five observations all 90
messages and 69,210 frames match MOSI XOR0xa5. The strict independent validator
also requires one CS-delimited segment per submitted message, exact lengths and
both hashes. Wrong CS, fragmented messages, incorrect bytes or empty evidence
fail. It checks the original dw_spi_mmio driver, actual IRQ counts and active
multi-user after the SPI child completes. BAR and clock observations are separate.

The final trace has 2,292 `rp1_msix vector=19` events and 2,292 delivered MIP0
vector19 events, matching the guest's final handled SPI IRQ count. Linux's
dynamic child IRQ97 is labeled `rp1_irq_chip 19 Level 1f00050000.spi`.
Counts remain unchanged between completed test batches. This establishes bounded
repeated completion and no observed idle interrupt stream, not long-duration
peripheral reliability or an electrical waveform measurement.

Retained `e-native-spi-01` at 1MHz has correct bytes/IRQs but 1,737 CS segments for
90 messages. `e-native-spi-02` at 100kHz has 91 segments for90 messages, including
an initial4-byte message split 1+3. Both strict reports are PARTIAL. The model
explicitly deasserts native CS when TX FIFO empties; wall-clock TCG service/timer
scheduling is implicated, but no physical maximum rate or measured causal timing
is inferred. FIFO-starvation/framing at higher rates remains unresolved. It was
not hidden by holding CS unconditionally, changing the driver or discarding an
initial failed transfer. The final10kHz test preserves every message in validation.

## Builds, regressions and preserved failures

- Final QEMU and affected qtest build PASS; source-level hardware checkpatch
  --no-signoff:0 errors/0 warnings. No signoff/commit was invented.
- Focused hardware tests: cm5io7 + RP1 6 + MIP3 + SDHCI6 =22 PASS.
- Two generic SDHCI register checks PASS.
- Phase10E trace-validator units:3 PASS, including fragmented-message rejection.
- Phase10A24 unit tests +10 synthetic cases PASS; Phase10D8 host units PASS.
- One targeted Phase9 clean 6.18.62/GPEX/SPI regression PASS; golden unchanged.
  Prior complete Phase9/10D corruption results remain preserved. They were
  intentionally **not rerun** as another FEC campaign.
- Enumeration-gate original boot `e-enumeration-01` also completed cleanly. Its
  first capability defaults reported2.5GT/s x1; subsequent native runs use coherent
  endpoint/root Gen2 x4 capabilities. All three SPI runs preserved clean V8 boot.

Initial compile include-name/FDT duplicate-node errors, a missing-device NULL
configuration-helper call caught by qtest, the forwarding reentrancy failure and
a missing GIC CPU-target setup in the first new IRQ test remain in separate build/
qtest logs. None counts as a passed guest or a vulnerability classification.
Final tests exercise absent configuration safely. The first coarse native
byte/IRQ-only PASS labels are superseded only by separate strict reports, never
by overwriting the original evidence. The submitted observer is captured for the
final run; initial post-run source inventories retain their provenance limits.

## Source references, fidelity limits and next priorities

Pinned Raspberry Pi source remains commit
`cff533aec2fa601846766b32ff57204e0a61bed7` /6.18.50. The PCI driver is the prior
private pinned copy; MFD, clk-rp1, DW MMIO, MIP and rp1.dtsi files with URLs/hashes
are in `~/cm5-v8-lab/phase10e/reference/`. Exact distro-build provenance beyond
that pin remains independently unestablished; the actual captured executable's
probes/operations are the guest evidence. Physical reference DT/measurements stay
private and were not edited/copied into the public source tree.

Next smallest work: isolate high-rate FIFO/refill/virtual-clock timing with
bounded timestamped traces; implement real pinctrl/GPIO-CS only if source-backed
and needed, without masking native-CS underflow. Then extend bounded RP1 reset/
clock coverage, validate additional inbound/DMA/error cases and a real DMA-capable
peripheral. Treat analog link training, signal timing, electrical pins and physical
performance as unmeasured. BAR2 remains a lab scratchpad, not RP1 firmware SRAM
protocol emulation. BOOT still bypasses firmware via direct -kernel; the separate
[Phase10F handoff](PHASE10F-BOOT-HANDOFF.md) identifies the fail-closed reader,
selected-byte export and DT compatibility work required next.

Exact commands and scope: [README.md](README.md). Fresh ignored artifacts preserve
all completed, partial and failed attempts. No production or physical input changed.
