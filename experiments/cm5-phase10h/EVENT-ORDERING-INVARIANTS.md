# Phase 10H event contracts

Local AI-assisted experiments, ineligible for upstream submission. These are
executable model contracts. Linux source establishes driver expectations;
it does not establish undocumented silicon reset, transport retry or electrical
behavior. All time below is QEMU virtual ns unless another clock is named.

## Reference basis

Pinned Raspberry Pi Linux revision `cff533aec2fa601846766b32ff57204e0a61bed7`:

- `drivers/spi/spi-dw-core.c`: `dw_spi_tx_max`, `dw_writer`, `dw_reader`,
  `dw_spi_irq`, `dw_spi_irq_setup`; shift registers are outside FIFO occupancy.
  Native CS depends on continuous FIFO supply. Private exact reference remains
  in `/home/aweso/cm5-v8-lab/phase10e1/reference/`, SHA256
  `e40952a11124cb354a6a6ce86344d90845c85d39a5df39fc33201be3cf36fe9f`.
- `drivers/spi/spi-dw-mmio.c`: RP1 compatible uses PSSI setup; Alpine CS override
  is not an RP1 contract.
- `drivers/mfd/rp1.c`: `rp1_irq_set_type`, `rp1_chained_handle_irq`,
  `rp1_mask_irq`, `rp1_unmask_irq`. Bit3 selects IACK mode; bit2 acknowledges;
  bit1 TEST requests an interrupt. Linux services child before RP1 IACK.
- `drivers/irqchip/irq-bcm2712-mip.c`: `mip_compose_msi_msg`,
  `mip_middle_domain_alloc`, `mip_init_domains`. Data is hwirq, allocation uses
  controller offset, parent is rising edge, EOI/masking go to parent GIC.
- [PCI MSI implementation](https://raw.githubusercontent.com/raspberrypi/linux/cff533aec2fa601846766b32ff57204e0a61bed7/drivers/pci/msi/msi.c):
  mask callbacks and masked message-table programming. SHA256
  `c68235b3bda27258905524b854ed5aa671d9e3de1fb88bf58b15e5a4e2a24cc8`.
  Linux PCI MSI API SHA256
  `df58f076dea2260ca91740e98bf7a0e465232a80a0760921a8baad5bb152b82b`.

Existing E reference `sources.json` pins RP1/MIP/MMIO/clock files. New MSI
reference copies and manifest are in the private H checkpoint's `reference/`.
QEMU sources: `hw/ssi/dw-apb-ssi.c`, `hw/misc/rp1-pci.c`, `hw/pci/msix.c`,
`hw/pci/pci.c:pci_msi_trigger`, `hw/intc/bcm2712-mip.c`,
`hw/arm/bcm2712-pcie.c` and `hw/arm/cm5io-dev.c`. Developer basis:
`docs/devel/{reset,memory,multiple-iothreads,tcg-icount,replay}.rst`,
`docs/system/replay.rst`, `docs/devel/testing/qtest.rst`,
`system/qtest.c` and `include/qemu/main-loop.h`.

## SPI invariants

| ID | Contract and regression observation |
| --- | --- |
| S1 | Loading the shifter removes one TX FIFO entry before TX-empty IRQ. BUSY remains set while shifting, even when TXFLR=0. Existing `tx-fifo-shifter-irq-lead` checks status and IRQ. |
| S2 | RXFLR remains zero at 7999ns; at 8000ns exactly one completed 8-bit/1MHz word is readable. A queued second word moves to shifter and keeps BUSY=1. `h-refill-before-completion` checks FIFO, status and both XOR responses. |
| S3 | Refilling at 7999ns keeps one continuous CS segment; refilling after the 8000ns empty completion starts a second. `h-refill-before-completion` and `drain-refill-deadline` traces distinguish the cases. Native CS is not held indefinitely by SER. |
| S4 | SSIENR=0 at 7999ns flushes FIFO and cancels shifter; advancing beyond both old deadlines produces zero RX, empty TX and BUSY=0. A subsequent fresh word completes once. `h-disable-abort-boundary`. |
| S5 | Controller/RP1/system reset cancels timer, clears RX, masks/clears MSI-X state and removes active CS. `reset-active-pending-msix`, `fifo-errors-reset`, native PERST extension. |
| S6 | A paused shifter preserves remaining work across clock gate/divider changes; native clock test checks the remaining-half-word boundary and live divider retiming. Aggregate work only; no bit-edge claim. |
| S7 | A 24000ns delay before software servicing permits queued hardware completion, preserves two ordered RX words, suppresses extra IACK-mode notifications, and leaves a level eligible for rearm. `h-delayed-service`. RX overflow retains the existing explicit error policy. |

Serializer completion writes RX and FIFO/shifter state before calling IRQ
update. Next-word load and CS decisions occur in the same synchronous callback;
intermediate trace state is not an extra guest MMIO observation. Tests inspect
actual status at command barriers. Late callbacks still schedule subsequent
words from callback time: no absolute-deadline catch-up guarantee is claimed.
No late-dispatch fix was made without a faithful reproduction.

## RP1 and MSI-X invariants

| ID | Contract and regression observation |
| --- | --- |
| R1 | One held source in edge mode emits once; unrelated PCI config writes and function mask/unmask do not synthesize another source edge. `h-edge-config-no-duplicate` fails before the H latch correction, passes after. Falling source rearms; a second RX word sends again. |
| R2 | Function or vector masking retains notification in PBA; unmask emits pending once and clears PBA. Existing vector-mask test plus `h-function-pending-ack`. A PBA bit coalesces notifications; it is not an event counter. |
| R3 | In IACK mode a second RX assertion before acknowledgement is retained as device state. IACK while RX pending emits again; drain RX then IACK emits nothing. `h-function-pending-ack` and delayed-service test. |
| R4 | Source/FIFO updates precede the notification attempt. `sequence` places actual MMIO request, completion/IRQ traces and replies in one ordered stream. |
| R5 | Two independent TEST vectors retain separate PBA bits and message data while function-masked; repeated TEST on one vector coalesces. `h-two-pending-vectors`. This is synthetic IRQ competition, not two physical SPI engines. |
| R6 | Reset clears edge latch, outstanding IACK latch, PBA, table and source state. Generic reset and native PERST tests check cancellation rather than requiring a missing callback merely not to crash. |

`irq_outstanding` records the source notification/rearm lifecycle, **not confirmed
DMA acceptance or guest service**. QEMU `msix_notify`/`msi_send_message` return
void. `rp1_spi_notify` is an attempt. A masked request may be pending and an
unmasked attempt may be blocked downstream. Do not count attempts as successful
MIP deliveries. No automatic retry after blocked DMA is promised. In particular,
BME/window reenable alone is not proven to replay a previously blocked attempt;
the native regression uses explicit RP1 IACK for retry.

## MIP and PCIe invariants

| ID | Contract and regression observation |
| --- | --- |
| M1 | Only connected controller's doorbell offset0 and in-range data reaches its mapped GIC SPI. Invalid offset, wrong-controller inbound mapping and invalid vector cannot create unrelated pending GIC state. Existing native MSI and MIP range tests. |
| M2 | Supported MIP host edge mode emits a pulse; parent pending can be cleared and a successive event can set it again. Host mask blocks delivery. Tests read actual GIC pending and clear registers. MIP status/level mode are not fully implemented. |
| M3 | MIP reset masks all host/VPU outputs, clears mode and lowers outputs; system reset clears parent pending. This is the documented conservative model policy, not measured silicon reset state. |
| P1 | CPU MMIO uses current BAR/bridge/outbound decode. A relocated old BAR or disabled memory decode cannot write SSIENR or abort an in-flight word. `h-bar-decode-inflight`. Memory decode does not itself reset an autonomous serializer. |
| P2 | MSI DMA uses PCI bus-master address space and programmed native inbound windows, only RAM or that host's connected MIP. BME-off, disabled inbound RAM, out-of-range RAM, invalid doorbell and other-controller MIP do not change GIC/sentinel state. `native-ssi-msix-inbound-mip`; `h-bme-inflight` also disables BME at7999ns and proves RX completion continues without a successful MSI write, followed by explicit IACK retry. |
| P3 | `bcm2712_pcie_dma_write` records the actual inbound MemTxResult, address, data, size and controller. Nonzero is transaction failure; zero is accepted memory transaction, which still need not mean MIP delivered (mask/vector may reject). BME-off can stop before this trace; absence is not success. |
| P4 | PERST with masked PBA plus active next frame clears endpoint state. After 1ms logical link recovery, RX=0, PBA=0, BUSY=0 and GIC pending=0. Native test extension also proves an already-latched GIC edge survives endpoint reset; it is explicitly cleared before checking for phantom future events. No fabricated direct-GIC fallback is used. |

All tested MMIO and virtual timer callbacks execute under existing QEMU BQL
serialization. Request/reply barriers order qtest accesses; explicit clock steps
visit intermediate timer deadlines. Equal virtual timestamps are resolved by
the commanded access sequence. Tests make no assertion about which arbitrary
host thread wins a race. Real SMP stress is reported separately.

Endpoint/MIP reset cannot retroactively withdraw an edge already latched by the
parent GIC. Parent acknowledgement/clear and full-system reset are separate
operations. Cross-controller negative testing now unmasks MIP1, uses valid data8
and checks its actual GIC pending bit, with a successful direct MIP1 positive
control before testing that RP1 native inbound DMA cannot reach it.
