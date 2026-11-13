# Native MIP hardware status

## Exact hardware/test source changes

* `hw/intc/bcm2712-mip.c` — new QOM/sysbus MIP host-edge model.
* `include/hw/intc/bcm2712-mip.h` — model state and type declaration.
* `hw/intc/Kconfig`, `hw/intc/meson.build`, `hw/intc/trace-events` — build/tracing.
* `hw/arm/cm5io-dev.c` — opt-in native devices, DT and per-host MSI translation.
* `include/hw/arm/cm5io-dev.h` — public physical MIP0/MIP1/MSI address constants.
* `hw/arm/Kconfig` — select new model.
* `tests/qtest/bcm2712-mip-test.c`, `tests/qtest/meson.build` — three focused tests.

No Phase 5 controller/endpoint/slave C source was changed. The only regression
runner changes are optional module/native-MIP support and evidence checks;
the existing fallback behavior and original seven hardware qtests are preserved.
No commit or push was made.

## Implemented path

```text
real Linux SPI driver -> RP1 SPI IRQ19 -> RP1 MSI-X vector19
 -> per-host PCI DMA address space, bus MSI address 0xfffffff000
 -> MIP0 INT_RAISE host-edge model -> GICv2 SPI147 (INTID179)
 -> real Linux MIP/PCI/RP1 interrupt domains -> SPI completion
```

Two native MIP devices are created only with `native-mip=on`; no GICv2m device
or DT node is created in that configuration. Default/off retains Phase 6.

| Component | Status | Scope |
| --- | --- | --- |
| Native MIP driver initialization | IMPLEMENTED_AND_GUEST_VALIDATED | Unchanged `mip_msi` external module binds both physical-address nodes and programs the actual MMIO model |
| MIP0 host edge delivery | IMPLEMENTED_AND_GUEST_VALIDATED | 64 MSI values 0..63, SPI base128, real RP1 SPI transfers through vector19 |
| MIP1 host edge delivery | IMPLEMENTED_AND_GUEST_VALIDATED | Eight MSI values 8..15; V8 expansion-device traffic observed on vectors9,10,11,12,14 |
| Per-host inbound MSI translation | IMPLEMENTED_AND_GUEST_VALIDATED | Both PCI links share bus address but map to different MIP doorbells; no CPU-global alias |
| Host mask/config storage and range rejection | IMPLEMENTED_QTEST_ONLY beyond init writes | Low/high halves, vector bounds, mask suppresses delivery; masked-event retention behavior remains an explicit experimental choice |
| Parent GIC edge clearing and system reset | IMPLEMENTED_QTEST_ONLY | Edge deasserts, GIC pending clears, system reset resets MIP model/GIC state |
| Full MIP reset/status/INT_CLEAR semantics | PARTIALLY_IMPLEMENTED | Conservative masked startup, quiescent status for supported pulses, unknown INT_CLEAR writes logged; not a silicon reset/status claim |
| Level and VPU IRQ delivery | NOT_IMPLEMENTED | VPU masks are stored for real driver init; no VPU output or level engine |
| Native BCM2712 PCIe host configuration | NOT_IMPLEMENTED | GPEX still supplies ECAM/ordinary DMA; fixed published inbound MSI routing is the implemented subset |
| Physical CM5 comparison | NOT_IMPLEMENTED / NOT_RUN_PHYSICAL | Read-only tools and questions prepared; all physical matrix values UNAVAILABLE |

## Register/software contract

The public driver maps resource0, then writes these 32-bit offsets:

| Offset | Driver operation |
| --- | --- |
| 0x40 / 0x50 | Host mask low/high = 0 |
| 0x60 / 0x70 | VPU mask low/high = 0xffffffff |
| 0x20 / 0x30 | Host config low/high = 0xffffffff, selecting edge delivery |

MSI messages use resource1's address and `irq_data.hwirq` as message data.
INT_RAISE at 0x00 consumes that vector index. The model supports the used host
edge contract and bounds-checks vector data. The driver masks/acknowledges at
its parent GIC rather than using INT_CLEAR; qtests clear the GIC pending bit.
Unknown writes, including INT_CLEAR 0x10, are logged and not assigned invented
hardware semantics. Status registers return a quiescent value for the supported
pulse-only model; no full pending/status engine is claimed.

The model starts with host/VPU masks all ones and config zero as a conservative
experimental reset. Those are not documented silicon reset values. Masked MSI
writes currently drop rather than retaining events; that policy is unverified
and is specifically a Friday question. No correctness claim extends to level,
VPU, latch/retention, precise timing or all reset/clear interactions.

| Mapping | Public DT value | Implemented driver routing |
| --- | --- | --- |
| MIP0 regs | CPU 0x1000130000, length0xc0 | GIC SPI base128 + MSI data0..63 |
| MIP1 regs | CPU 0x1000131000, length0xc0 | DT base247, count8, offset8; driver formula gives SPI255..262 for data8..15 |
| MSI aperture, each PCI host | PCI 0xfffffff000, length0x1000 | Internal RP1 host routes to MIP0; expansion host routes to MIP1 |

The MIP1 base/offset arithmetic follows the unchanged Linux driver and passes
qtests/guest traffic. Its physical relationship is not guessed as base247
through254; verify the actual live DT and allocated parent IRQs on Friday.

A CPU-global doorbell alias would incorrectly conflate the two hosts. Each
host therefore has a PCI DMA address space with the documented MSI aperture
mapping. Ordinary DMA remains the earlier identity substitute. This is a fixed
programmed-inbound MSI subset, not implementation of Broadcom host registers,
firmware link/reset programming or complete inbound/outbound translation.

## Real guest evidence

Final native SPI run: `artifacts/native-spi-final/`.

```text
MIP: MSI-X count: 64, base: 128, offset: 0, msg_addr: fffffff000
MIP: MSI-X count: 8, base: 247, offset: 8, msg_addr: fffffff000
... bus/platform/drivers/mip_msi   (both nodes)
SPI_DIAGNOSTIC=PASS failures=0
```

The independent gate validates all 72 ioctl messages and 5,448 SSI word events.
The trace recorded 240 delivered MIP0 vector19 messages in that run. That count
is not a physical performance or interrupt-coalescing equivalence claim.

Final native V8 run: `artifacts/native-v8-final/`.

```text
V8_RP1_SPI_DIAGNOSTIC_EXIT=0
... spi_loopback PASS, bytes4 ...
V8_DIAGNOSTIC_EXIT=0
V8_TARGET=active
```

Four actual QEMU echo word events match the unchanged diagnostic contract.
The trace recorded MIP0 vector19 and real MIP1 expansion MSI traffic. Default
GICv2m is absent. Module initialization is proved by both sysfs bindings and
both copies of the six programming writes; dev_dbg need not be visible at V8's
console loglevel. The first V8 run completed but its initial overly narrow log
check failed; that evidence is retained as `native-v8-1/`. The final gate uses
MMIO plus binding proof, not a compatible-string assumption.

Public driver C is byte-identical to the pinned kernel source. The original
kernel image hash is unchanged. The external module uses existing exported
IRQ/MSI framework APIs and matching vermagic; it does not remove hardware
checks, alter allocation counts or rewrite the Linux driver. `-DDEBUG` only
exposes its existing debug message in logs. Native load is explicit and occurs
before V8 waits for disks.

## Final verification

All final guest runs use the same QEMU binary hash; see `artifacts/validation.json`.

* Five original RP1 qtests: PASS.
* Two original CM5IO qtests: PASS.
* Three new MIP qtests: PASS — edge/mask/parent-clear/reset, vector ranges/high
  half/MIP1 offset, real RP1 MSI-X through PCI inbound aperture.
* SPI matrix on native MIP, GICv2m fallback and virt: 72/72 messages each PASS.
* Actual V8 plus original diagnostics/SPI on all three configurations: PASS.
* Seven parser/privacy tests: PASS; synthetic fixtures only.
* Generated native DT and structured QEMU description produced successfully.
* Planning matrix has no fabricated physical measurements.
* `git diff --check` clean; new MIP source/header/qtest checkpatch has zero errors
  and warnings. The board integration file has one 80-column formatting warning.

No new FEC/corruption sweep, physical traffic, firmware flash, reboot, GPIO output,
I2C scan or proprietary flight-software source access occurred. Actual eMMC,
firmware/EEPROM boot, pinmux, clocks/resets, physical timing and recovery behavior
retain the Phase 6 limitations. The prepared read-only measurements distinguish
those from successful CPU/software/SPI execution under the emulator.
