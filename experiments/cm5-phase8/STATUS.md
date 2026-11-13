# Phase 8 completion record

Local experimental implementation; no commit or push. No physical CM5
observations are available. Read README.md for the reproduction commands,
implementation inventory, storage policy and retained failed attempts.

| Required question | Status | Actual evidence |
| --- | --- | --- |
| QEMU exposes native SDHCI/MMC | IMPLEMENTED_AND_GUEST_VALIDATED | BCM2712 host/cfg at physical addresses; legacy PIO subset; actual GIC SPI273 |
| Linux binds sdhci-brcmstb | IMPLEMENTED_AND_GUEST_VALIDATED | Unchanged pinned driver module; sysfs binding and BCM2712 config MMIO writes |
| Virtual eMMC enumerates | IMPLEMENTED_AND_GUEST_VALIDATED | `mmc0: new MMC card`, `mmcblk0`, 30,535,680 sectors, 512-byte logical sector |
| Reads original eMMC sectors | IMPLEMENTED_AND_GUEST_VALIDATED | Seven bounded 4096-byte SHA-512 comparisons; controller and card trace |
| Original partitions visible | IMPLEMENTED_AND_GUEST_VALIDATED | p1,p2,p3,p5,p6,p7 starts/sizes checked; raw MBR/EBR unchanged |
| V8 boots with mmcblk backing | IMPLEMENTED_AND_GUEST_VALIDATED | Native plain and clean OS-verity profiles reach systemd/multi-user; no VirtIO block device; 16,384-byte pages; diagnostic and SPI pass |
| Native MIP preserved | IMPLEMENTED_AND_GUEST_VALIDATED | Original MIP qtests, preserved SPI/V8 and native eMMC runs |
| RP1 SPI preserved | IMPLEMENTED_AND_GUEST_VALIDATED | 72 messages / 5,448 traced frames match; V8 diagnostic echo passes |
| OS actually protected by dm-verity/FEC | IMPLEMENTED_AND_GUEST_VALIDATED | Optional profile only: original metadata from RECOVERY via eMMC/RO loops, active `verity V`, original block digest and real FEC correction |
| Generic substitutes still present | PARTIALLY_IMPLEMENTED | Two GPEX PCIe hosts, VirtIO Ethernet, generic PL011 header UART/PL031 RTC, fixed clocks and empty pinctrl states; existing standard SDHCI/card engine under new wrapper |

The native plain profile remains explicitly **without OS verity**. Native
FSW mounts original p5 read-only; it is not a verified FSW mapping. The preserved
VirtIO profile retains its previous FSW verity/FEC path. No claim extends to
physical ECC, wear, FTL, RPMB, EEPROM/ROM boot, radiation or electrical timing.

## Validation records

* `artifacts/validation.json`: final machine-readable inventory, checks and paths.
* `artifacts/qtest-{rp1,cm5io,bcm2712-mip,bcm2712-sdhci}-final.log`: all 13 tests.
* `~/cm5-v8-lab/phase8/preserved-regressions/`: existing Phase 7 gate, all three
  72-message SPI matrices and three clean V8 diagnostic boots PASS.
* `artifacts/native-spi-final/result.json`: native eMMC + MIP + full SPI PASS.
* `artifacts/native-v8-final/result.json`: complete original V8 through eMMC PASS.
* `artifacts/native-8g/result.json`: 8 GiB guest + eMMC reads + full SPI PASS;
  guest MemTotal 8,248,672 KiB. Default remains 2 GiB (SPI regression uses 1 GiB).
* `artifacts/os-verity-clean-validated/result-rechecked.json`: clean original
  OS verity/FEC boot PASS, with golden fd access_mode0/read_only=true.
* `artifacts/os-fec-pilot/result-rechecked.json`: **complete boot FAIL/TIMEOUT**;
  kernel FEC correction, restored original digest, verified mount, diagnostic,
  MIP and SPI pass. No final target marker; RCU stall appears at timeout.
* `golden-before.sha256` versus `golden-final.sha256`: complete-file digest equal.
* Checkpatch: zero errors; new-file/MAINTAINERS warnings and a preexisting long
  Phase 7 MIP line in the complete machine-file review. `git diff --check` clean.
* Physical tool tests: seven PASS. Physical collector was not run on hardware.

## Corruption pilot scope and unresolved issue

One disposable overlay's original OS block0 was replaced by 4096 bytes of 0x5a.
The raw-sector digest matches that injected pattern. Reading the verified device
returns the original digest and the real kernel reports:

```text
device-mapper: verity-fec: 179:2: FEC 0: corrected 4096 errors
0 20971520 verity V
```

It subsequently mounts verified ext4 and executes the 16 KiB userspace/FSW
diagnostic and RP1 SPI successfully. It reaches systemd and diagnostic exit0,
but the bounded 300-second workload times out before multi-user target evidence;
the retained log contains an RCU stall. **Complete corrupted-boot behavior is
PARTIALLY_IMPLEMENTED/validated only through those stages**, not a successful
full corruption boot. No retry/sweep is presented as statistical evidence.
The stall's cause is unresolved; do not attribute it to physical eMMC or claim
that it proves an original metadata mismatch. The clean verified boot passes.

Original `result.json` files remain intact. The optional-run parser initially
expected a longer dmsetup status and failed to allow interleaved kernel FEC
messages between marker/digest. `verification.py` rechecks those exact retained
logs, writes separate `result-rechecked.json`, and preserves every other failed
check, including the pilot timeout. No guest workload or evidence was invented.

## Limits and next steps

BCM2712 cfg is a functional driver-contract subset, not complete silicon.
Only legacy PIO, single/multi-block reads/writes, Auto CMD12/23, supported reset
and IRQ/error paths are exercised. No DMA, CQE, high-speed timing, tuning,
SD Express, physical clock/pad/reset trees or flash-internal fault model.
8 GiB is contiguous simulated RAM at physical0, without physical firmware holes;
DMA above4 GiB is not validated. Both PCI domains and original devices remain.

Friday's collector additions are limited to passive MMC descriptors/topology,
already-readable ios, translated DT resources/capabilities and logical sector
size. Boot log and partition measurements reuse the existing collection.
All physical matrix values remain unavailable. Investigate the corrupted-boot
RCU stall before claiming full verified-root boot recovery under this fault.
