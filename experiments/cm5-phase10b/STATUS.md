# Phase 10B status — 2026-11-13 Hawaii

**Actual physical 6.18.50 kernel bring-up reaches native eMMC, partitions,
captured initramfs and the out-of-tree verity module. Verified V8 userspace is
not established.** RP1 BAR2 is implemented and tested. Native PCIe now has an
opt-in, tested driver-probe frontend with an explicit MDIO/PHY boundary, not
a working native host or RP1 link.

Local AI-assisted experiment only, not for upstream submission. Branch remains
`cm5-rp1-hardware`, starting HEAD
`1a6703a4bb1590aa98e6993474b0a0551d8d8f60`. Phase 10A sources match their prior
delivery hashes. Existing untracked files/artifacts were preserved. No commit,
push, reset, clean, physical access, golden overwrite, kernel/initramfs patch,
EEPROM change, root hash/tree/parity replacement or regeneration occurred.

## Physical inputs and provenance

All five actual boot assets were found in
`/home/aweso/cm5-phase10-private/physical-boot/boot-assets`. Exact identities:

| Name | Bytes | SHA-256 |
| --- | ---: | --- |
| kernel_2712.img | 10197590 | 154f0ea1e14bb1075077dfd1bdc63c1502bc0b17b0354628d515b4fbd3a4198d |
| initramfs_2712-osverified-v8 | 23455255 | fcaade1e3aab0d79a51a170f556d25d0d1476bc17518099de54f5ebe16feab5b |
| bcm2712-rpi-cm5-cm5io.dtb | 79751 | b297f9516345eb4eb22d22f4c364fcb3705970f28b6d87875583dadf37fbb3ac |
| config.txt | 1410 | c7fc03a8ed4da1493589823572f32a67bc2052090eaa06273fdd0a555cffae3d |
| cmdline_2712-osverified-v8.txt | 279 | 67ee4076a0fe8d3b81f49733d4d1a09d4ca2054f5cc84688acc06614ac06f09e |

The kernel is gzip-compressed; QEMU's loader decompresses it. Its serial
banner identifies **6.18.50+rpt-rpi-2712**. The existing successful 6.18.62
development Image remains intact and is still used by the Phase 9 runner.
This delivery does not substitute the separately built Windows unified kernel.

Both `/mnt/c/Users/aweso/projects/cm5-v8-reference.zip` and the extracted
`/mnt/c/Users/aweso/projects/cm5-v8-reference/` exist. That package contains a
different experimental unified kernel as well as the compressed user-area
capture. The adjacent compressed SHA-256 agrees with the WSL golden
`import.json`: compressed `72a55fb788293513fb4d85c8f8f294453f4bd213bc83340f4f0a377b6d158b96`,
raw `e2fb1a85c2652838793e58f8b13ef908e2e4a4c4295e27297ce742287f69cb87`,
exactly 15634268160 bytes. No reference was assumed missing or reimported.

`asset-audit-final2/result.json` contains asset identities, selected decoded
base/live/generated DT properties, import provenance and module evidence.
Private DTB exports remain in the private Phase 10B lab, not in tracked files.

## Actual physical-kernel milestones

The `physical-gpex-before` smoke uses the exact captured kernel and initramfs,
the existing generated DT, a fresh private qcow2 overlay and the original
root/verity command line plus only UART/earlycon/logging arguments.

| Milestone | Evidence in serial.log |
| --- | --- |
| Kernel entry | 6.18.50 banner at 0.000000 |
| Main native driver | SDHCI on 1000fff000.mmc using PIO at 2.840390 |
| eMMC detection | new MMC card at 2.871761; mmcblk0 at 2.876143 |
| Partitions | p1 p2 p3 < p5 p6 p7 > at 2.940904 |
| Captured initramfs | Run /init at 3.055656 |
| Actual external module | dm_verity: loading out-of-tree module at 8.589946 |
| Captured RECOVERY | mmcblk0p7 mounted ro at 8.735312 |
| Verity target initialization | sha256 messages at 11.480981 and 13.388442 |
| Verified OS root mount/userspace | Not observed before 100-second timeout |

The longer `physical-native-v1` run uses the new native probe profile and the
same unmodified physical assets. It reaches the same eMMC/partition/initramfs
and module milestones. It reached its **900-second execution limit**, was
killed by the harness (return code -9), and has `timeout=true`, no observed
kernel panic, no root mount and no userspace evidence. The reported 925.93
total wall seconds also include post-exit input hashing; it is not a boot or
FEC timing measurement. Both captured runs report all physical inputs and
golden unchanged. Absence of a root mount is not called a permanent hang.

No FEC correction, valid final dmsetup status, verified FSW mount, functional
flight software, or complete userspace survival is claimed for either smoke.
The original GPEX smoke also logs a deferred synthetic SPI probe; it cannot
bind the RP1 PCI parent because this physical kernel lacks generic PCI host
support. Native mode omits those RP1 child nodes entirely.

## Native PCIe result and unresolved boundary

`native-pcie=on,native-mip=on` exposes only controllers 1 and 2 at the physical
register addresses, with the native compatible, domains, lane counts and
physical interrupt/MIP topology. The third disabled controller is absent.
The default property value remains off, retaining GPEX.

The **actual 6.18.50 brcm-pcie executable** attempts both controllers:

- `1000110000.pcie`: native ranges/descriptor initialization, then probe error
  **-110** at guest time 2.505409.
- `1000120000.pcie`: same boundary, probe error **-110** at 2.512635.
- `hardware.log`: MDIO address write at `+0x1100` selects port0 register 0x1f;
  data `0x80001600` written to `+0x1104` remains busy through polling. The
  native source returns `-ETIMEDOUT` there during BCM2712 post-setup.

This is before host/root-port enumeration, MSI setup, link training, downstream
configuration or BAR accesses. It is **not an IRQ failure**. No PHY is modeled,
so no completion or link-up status is fabricated. The qtest verifies that
PERST release and writes to status cannot manufacture PHYLINKUP/DL_ACTIVE.

The new device implements bounded 32-bit register latches for bridge init,
SCB, window descriptors, private class/link descriptors, MDIO address/data and
config index, with deterministic system reset and trace events. Descriptor
readback is not address translation. Its unsupported transactions are logged.
No PCI bus or native RP1 endpoint is advertised. INTx/MSI DT descriptors and
external MIP nodes are present, but native PCIe IRQ delivery is unimplemented
and unexercised. Existing MIP tests cover the preserved GPEX path only.

The source contract was researched in the available pinned 6.18.62 Raspberry
Pi driver, not represented as exact 6.18.50 source. The physical executable's
trace independently validates this exercised prefix of the register sequence.

## BAR2, DT compatibility and verification stack

BAR0 remains 16 KiB and BAR1 4 MiB. BAR2 is registered as a normal **64 KiB
PCI memory BAR** with plain RAM access and a documented zero-on-system-reset
lab convention. It has no hardcoded assigned address. The qtest covers sizing,
first/last byte ranges, byte/word/dword access, unmapped boundary, relocation,
memory-decode disable/re-enable and complete reset clearing. RP1 remains
unmigratable; firmware shared-memory/mailbox semantics are not implemented.

The preserved Phase 9 6.18.62 clean guest actually probes and allocates BAR2:
`BAR 2 [mem 0x1f00400000-0x1f0040ffff]: assigned`. That is a Linux assignment,
not an internal hardcoded address. Actual BAR2 accesses are exercised by the
qtest, not claimed from that enumeration log. Neither physical-kernel smoke
exercised any RP1 BAR through PCI; native mode stops before PCI enumeration.

No external-DTB acceptance change was needed for kernel entry/eMMC. The
existing generated DT correctly describes the modeled GIC/UART/eMMC addresses
and interrupts. Its fixed clocks, RAM, PIO and optional substitutes differ
from physical firmware-provided clocks, resets and DMA. In particular the
main eMMC is SPI 273/8-bit, while the separate disabled 4-bit host is omitted.
The native profile generates explicit probe-subset nodes and disables metadata
for nonfunctional SPI/expansion connectors; it does not import captured live
DT nodes for hardware that does not exist. External `-dtb` is still rejected.

The initramfs audit handles its concatenated newc + zstd/newc structure. It
finds `usr/lib/modules/6.18.50+rpt-rpi-2712/updates/dm-verity.ko`, 63600 bytes,
SHA-256 `b1dca4c7c70d2df4ae778e7e1cde90471336ba494aa606fe574a909b2ebc4e37`,
matching vermagic, and `verity_fec_*` symbols. The actual guest loads this
external module. Its unchanged hook requests roots2 for OS/FSW and a **full
10 GiB verified OS read before root mount**, using original metadata on p7.
This identifies source behavior worth instrumenting; it does not prove which
instruction was active at timeout or attribute the physical 39.36-second gap
to FEC, scanning, or any single operation.

## Tests and evidence

| Suite | Result |
| --- | --- |
| Modified QEMU and affected qtest builds | PASS |
| RP1 qtests including BAR2 | 6 PASS |
| cm5io qtests including native boundary | 3 PASS |
| MIP qtests | 3 PASS |
| SDHCI qtests including erase/bounds | 4 PASS |
| Phase 10A unit suite | 24 PASS; prior source hashes unchanged |
| Phase 10A synthetic matrix | 10 PASS as bounded proxy tests, no guest claims |
| C checkpatch with --no-signoff | 0 errors, 0 warnings |
| Physical GPEX smoke | BLOCKED/inconclusive after initramfs/module at timeout |
| Physical native smoke | MDIO probe failures; root/userspace inconclusive after 900-second limit |
| Captured external DTB | EXPECTED_REJECTION, generated-DT requirement retained |
| Phase 9 clean / OS0 / OS1 / FSW0 | All PASS, normal QEMU exits |
| Phase 9 no-FEC | EXPECTED_FAILURE, damaged root rejected |

Evidence is ignored under `artifacts/`: `validation-final/`, `phase10a-v1/`,
`asset-audit-final2/`, both physical smoke directories, and
`phase9-controls-v1/`. Commands are in [README.md](README.md). The ordinary
checkpatch invocation only objected to missing Signed-off-by; no signoff was
invented for local AI-assisted work. The --no-signoff style check passed.
The five-case Phase 9 batch reports `PASS` overall with golden unchanged;
there were no skipped or incomplete preservation cases. The physical smokes
are separately recorded as `BLOCKED` with explicit timeout/inconclusive fields,
and the two native PCIe probe errors are definite failures at a known register.

The native run's exact executable inode was fingerprinted read-only through
`/proc/PID/exe` while it was running, preserving provenance across the final
metadata-only rebuild. The initial GPEX smoke's launch executable hash is
unknown. Its physical inputs and golden were checked before/after. These
limits are retained rather than replacing old evidence.

## Next smallest changes

1. Add read-stage observability to an opt-in lab run (e.g. QMP block statistics
   and serial stage capture), without changing the original initramfs. Establish
   whether the full verified scan completes, stalls, or is simply expensive in
   this PIO/TCG path. Do not skip it and call the original installation verified.
2. Implement a source-backed MDIO controller/PHY register transaction model
   with tested command, page, busy/completion and reset semantics; keep unknown
   PHY behavior unsupported. Completing a write alone must not assert link-up.
3. Add a real root-port/secondary PCI bus and indexed downstream config path,
   outbound/inbound window translation and host-specific MIP DMA routing. Then
   connect RP1 behind the bridge and test actual interrupt delivery. Do not
   expose GPEX registers as Broadcom registers or use driver bypass flags.
4. Only after native enumeration, validate the physical kernel's RP1 MFD,
   clocks, interrupts and BAR accesses. BAR2 scratchpad sizing does not establish
   real RP1 firmware/shared-memory protocol behavior.
5. Retain the 6.18.62/GPEX controls and keep Phase 10A BOOT selection a separate
   fidelity level. Direct `-kernel` loading is not firmware execution.
