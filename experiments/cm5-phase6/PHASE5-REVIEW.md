# Phase 5 review and preservation

Reviewed the complete `rp1-pci.c`, `dw-apb-ssi.c`, `ssi-test-slave.c`, controller
header, five C qtests, guest init/diagnostic, DT generator, V8 runner, status
inventory and validation JSON. The successful path is real PCI/MMIO/IRQ/SPI;
there are no guest syscalls hidden in the model and no fabricated spidev files.

The following limitations matter to machine integration:

* RP1 uses 16 KiB BAR0, 4 MiB BAR1 and 61 advertised MSI-X vectors. Aperture
  sizes are corroborated by published physical boot logs; table/PBA locations,
  full PCI capability image, synthesis-specific defaults and vector count are
  not independently validated against silicon. BAR2/shared SRAM is absent.
* SPI0 is at the documented BAR1 offset 0x50000, with interrupt 19. Only that
  interrupt source is connected. The internal interrupt block implements a
  tested level/IACK subset; all edge/multi-source interactions are not verified.
* FIFO depth 64, IDR 0, reset CTRLR0 and 200 MHz timing input are experimental
  choices. Configuration and transfer progress do not model actual SPI edges,
  setup/hold, DMA timing, clock gating, or PCIe transport latency.
* Full duplex and transmit-only standard SPI are supported. Receive-only,
  EEPROM-read, multi-I/O and DMA are absent. Unsupported automatic modes can
  stall. Linux timeout/recovery after an injected hang has not been verified.
  Some unimplemented registers read zero. CSR masks are a subset, not a full
  synthesis-accurate register implementation. Three-bit frames are rejected
  by the real Linux SPI core, not an emulated error-register exercise.
* TX threshold IRQ is gated by enable. RX sample delay is stored without
  electrical effect. Native CS deasserts as the timed FIFO drains, including
  possible gaps between software refills. CPOL/CPHA configuration tests prove
  successful byte transfer under those settings, not waveform correctness.
* SSI CS lines connect directly to the fixture. No RP1 GPIO/pinmux, pads,
  pull-ups, voltage muxing or board routing registers are involved. The test
  slave is explicitly hypothetical and configurable (XOR/echo), not a sensor.
* The old virt DT hardcodes BAR1 at 0x10000000. The fixed 200 MHz clock replaces
  RP1's clock controller. Its `rp1` simple-bus node lives outside the PCI node
  because this kernel's driver finds it globally and expects its parent to
  have a platform_device. The new board generates this explicitly rather than
  patching the driver or requiring an externally rewritten DT.
* The guest uses driver_override to bind the experimental slave to spidev.
  This is protocol-driver selection through Linux's real SPI subsystem, not
  an emulation bypass. Device existence is not treated as transfer success.
* Migration is blocked by the model. PCIe hotplug, power states, full reset
  sequencing and firmware initialization are not validated.

Preserved the exact working Phase 5 binary as
`artifacts/qemu-phase5-known-good`, its validation record, and its hardware
sources in `artifacts/phase5-hardware.tar`. `summarize.py` checks that binary's
hash and proves all five Phase 5 C/header/qtest files remain byte-identical.
The original Phase 5 build declarations and original tests are retained.
The only qtest Meson addition in this phase registers the new board test.

`regress.py` adds a failure-returning regression gate using the known-good
Phase 5 initramfs, unmodified kernel/modules, real ioctl diagnostic and V8
stage. `check.sh` runs both qtest binaries and SPI/V8 on both virt and the new
board. Each run uses fresh artifacts and writable LOGS overlay; golden images
and verified FSW inputs remain read-only. It requires ioctl success, exact
byte/trace correspondence, RP1 driver binding/interrupt evidence for the
SPI matrix, and the original V8 diagnostic, added SPI diagnostic, multi-user
activation and four QEMU echo events for V8. Kernel panic, timeout or nonzero
QEMU exit fails the run. A boot alone does not pass the gate.

The final four runs all passed on the same binary. The old virt environment
continues to be supported and is not replaced by cm5io-dev.
