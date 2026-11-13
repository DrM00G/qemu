# Phase 5: RP1 PCIe / DesignWare SPI local hardware experiment

This phase adds C hardware models, builds QEMU, and transfers bytes using
unmodified Raspberry Pi Linux RP1, DesignWare SPI, and spidev drivers.
This is AI-assisted local research, **not for upstream submission**, under
[QEMU's provenance policy](../../docs/devel/code-provenance.rst).
No commit or push is made. Phases 1–4, original kernels and golden disks are
inputs; new initramfs files, device trees and writable overlays live separately.

The host is ARM `virt`, explicitly a provisional PCI integration platform.
It is not a CM5/BCM2712 machine. See [STATUS.md](STATUS.md) for scope and fidelity.

## Hardware source

| Path | Purpose |
| --- | --- |
| `hw/misc/rp1-pci.c` | QOM PCIe endpoint, BARs, chip/platform ID, interrupt configuration, MSI-X routing |
| `hw/ssi/dw-apb-ssi.c` | Register MMIO, timed PIO FIFOs, IRQs and chip selects |
| `include/hw/ssi/dw-apb-ssi.h` | Controller state and internal interface |
| `hw/ssi/ssi-test-slave.c` | SSI peripheral with configurable TX XOR response |
| `tests/qtest/rp1-test.c` | Five focused hardware qtests |
| `hw/{misc,ssi}/{Kconfig,meson.build,trace-events}` | Build selection and configurable traces |
| `tests/qtest/meson.build` | AArch64 qtest registration |

There was no DW_apb_ssi model in the existing SSI models. PL022 and BCM2835 SPI
use different register interfaces. The implementation reuses QEMU PCI, PCIe,
MSI-X, MemoryRegion, qdev, IRQ, timer and SSI infrastructure.

## Build and test

Existing configured build (AArch64 system target):

```sh
ninja -C build-arm64-phase1 qemu-system-aarch64 tests/qtest/rp1-test
build-arm64-phase1/qemu-system-aarch64 -device help | rg 'rp1-pci|ssi-test-slave'
QTEST_QEMU_BINARY=./build-arm64-phase1/qemu-system-aarch64 \
  ./build-arm64-phase1/tests/qtest/rp1-test
```

`CONFIG_RP1_PCI` defaults on with `ARM_VIRT`, depends on PCI and selects the
new `CONFIG_DW_APB_SSI`, which selects SSI. The tests require local Unix sockets;
the restricted execution sandbox required escalation for this test invocation.
The source is not enabled for targets without the appropriate PCI host.

The device invocation is:

```sh
-device rp1-pci,id=rp1,addr=1 \
-device ssi-test-slave,bus=spi,cs=0,xor-mask=0xa5
```

There is one SSI bus per RP1. Use a fully qualified bus path if instantiating
multiple endpoints. All four CS lines can address SSI peripherals; only CS0 is
populated in the guest experiment. `xor-mask=0` makes an echo fixture for the
existing Phase 4 diagnostic; the main SPI test uses `0xa5`.

The model is explicitly unmigratable. Migration and savevm are not validated.

## Reproduce ARM64 Linux SPI transfers

Prerequisites are the preserved Phase 3 16 KiB kernel and installed modules
under `~/cm5-phase3-kernel/`, its original initramfs stage, the ARM64 cross
compiler, and cpio/gzip. No guest-kernel patch or rebuild was needed.

```sh
python3 experiments/cm5-phase5/prepare-guest.py
python3 experiments/cm5-phase5/generate-dt.py \
  --output experiments/cm5-phase5/artifacts/spi.dtb
python3 experiments/cm5-phase5/boot-spi.py \
  --dtb experiments/cm5-phase5/artifacts/spi.dtb \
  --initrd experiments/cm5-phase5/artifacts/guest/spi-initrd.gz \
  --label spi-verified
python3 experiments/cm5-phase5/report.py
```

Output paths refuse accidental replacement. For a later run choose fresh output
paths/labels. In this workspace the DT and initramfs already exist; use them
without repeating preparation. Generated DT warnings are saved beside the DT.
Warnings from numeric phandles in QEMU's decompiled base DT and the deliberate
`rp1` node name are retained, not hidden. The Raspberry Pi driver searches for
that exact node name.

The DT describes only SPI0 behind a minimal `rp1` interrupt domain. A fixed
200 MHz clock substitutes for the unimplemented RP1 clocks. Its address
translation assumes BAR1 at `0x10000000`, which is verified in the boot logs.
Use `virt,highmem=off,gic-version=3`, slot 1, and no other PCI devices for the
standalone test. Changes to PCI topology require checking this assumption.
QEMU dumps the matching CPU/RAM/GIC host DT; nothing pretends to describe BCM2712.

The guest init loads existing `spi-dw.ko`, `spi-dw-mmio.ko`, and `spidev.ko`.
It binds the experimental SPI peripheral using Linux's `driver_override` and
`bind` sysfs interface. This selects the ordinary spidev protocol driver;
it does not create a fake device node or bypass PCI, MMIO, IRQ or SPI drivers.
The guest kernel creates `/dev/spidev0.0` through devtmpfs.

`spi-diagnostic.c` logs the original `SPI_IOC_MESSAGE(1)` request and response.
The independent report checks every returned byte against the 5,448 actual
QEMU SSI transfer events, plus RP1 binding, interrupts and all five qtests.
It records source/binary/kernel/initramfs/DT/evidence SHA-256 hashes.
Modes 0–3 and requested rates 100 kHz, 1 MHz, 5 MHz pass at lengths
1, 4, 63, 64, 65, 257 (72 messages). These are configuration tests, not an
oscilloscope validation of phase or clock edges. Three-bit words return EINVAL
from Linux. DMA initialization reports failure as expected with no DMA channel
in the DT; PIO then works. That driver message is preserved in the evidence.

Tracing with this build's log backend:

```sh
-trace 'enable=dw_apb_ssi_*' -trace enable=rp1_msix \
-d unimp,guest_errors -D peripheral.log
```

`boot-spi.py` records these in `LABEL.unimplemented.log` because `-D` selects
the shared log destination. That file contains both trace events and unsupported
operation messages. `LABEL.command.json` preserves the exact command. The
initial probe write of all ones to CTRLR0 is logged as unsupported while the
Linux driver detects the frame-size field; its later supported configuration
is what performs transfers.

## Existing V8 userspace and Phase 4 diagnostic

```sh
python3 experiments/cm5-phase5/generate-dt.py --ram 2048 \
  --output experiments/cm5-phase5/artifacts/v8.dtb
python3 experiments/cm5-phase5/boot-v8-rp1.py \
  --output /home/aweso/projects/qemu/experiments/cm5-phase5/artifacts/v8-new-run
```

This reuses the previously validated `v8-verified-clean-1` initramfs stage and
boot configuration, fresh LOGS QCOW2 overlay, original read-only golden image
and original read-only verified FSW devices. It fixes PCI slots explicitly and
uses the 2 GiB virt DT. The RAM-only initramfs gains a SPI hook after the V8
root is mounted. That hook invokes the **existing, unchanged** dynamic Phase 4
diagnostic through V8's real loader with `/dev/spidev0.0`. The SSI fixture is
configured as echo because that diagnostic verifies equality of TX and RX.
Phase 4's observer and tests remain unchanged; their UART, network, storage,
verity scan and multi-user target markers are retained. New-run local TCP/UDP
listeners require sandbox escalation. The script returns failure if its target,
existing diagnostic, or added SPI diagnostic does not pass.

The full V8 serial log is kept locally; only selected diagnostics and boot
status are summarized. There is no proprietary FSW dependency.

## References and derivation

* [Official RP1 peripheral datasheet](https://datasheets.raspberrypi.com/rp1/rp1-peripherals.pdf),
  sections 2.3 and 3.6: BAR1 peripheral mapping, SPI0 at peripheral offset
  `0x50000`, DW_apb_ssi v4.02a, SPI0 master with four native chip selects.
* [Official RP1 overview](https://www.raspberrypi.com/documentation/computers/io-controllers.html)
  and [SPI documentation](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html):
  platform context and Linux userspace interface.
* [Raspberry Pi Linux RP1 driver](https://github.com/raspberrypi/linux/blob/rpi-6.12.y/drivers/mfd/rp1.c)
  and [RP1 address/IRQ definitions](https://github.com/raspberrypi/linux/blob/rpi-6.12.y/include/dt-bindings/mfd/rp1.h):
  PCI IDs/revision, BAR1 checks, MSI-X allocation, atomic SET/CLR configuration,
  IACK and interrupt 19. The local kernel's corresponding files are authoritative
  for this run; the local header defines `RP1_INT_END=61`.
* The local kernel's `include/linux/rp1_platform.h` supplies C0 chip ID
  `0x20001927` and ASIC platform bit 1.
* [DesignWare register definitions](https://github.com/raspberrypi/linux/blob/rpi-6.12.y/drivers/spi/spi-dw.h),
  [controller driver](https://github.com/raspberrypi/linux/blob/rpi-6.12.y/drivers/spi/spi-dw-core.c)
  and [MMIO frontend](https://github.com/raspberrypi/linux/blob/rpi-6.12.y/drivers/spi/spi-dw-mmio.c):
  register offsets/fields, FIFO/DFS detection and actual transfer contract.
* [RP1 DT](https://github.com/raspberrypi/linux/blob/rpi-6.12.y/arch/arm64/boot/dts/broadcom/rp1.dtsi):
  SPI binding, clock and IRQ wiring. This experiment uses a smaller, explicit DT.
* [Physical boot log reported in raspberrypi/linux #6656](https://github.com/raspberrypi/linux/issues/6656):
  corroborates BAR0 size `0x4000` and BAR1 size `0x400000`. This is observed
  user-supplied hardware evidence, not a normative PCI configuration specification.

The PDF and logs are local reference artifacts, not proposed upstream content.
The public RP1 datasheet does **not** specify the full SPI register reset image,
FIFO synthesis depth or MSI-X table placement. Experimental choices are documented
in STATUS.md; no physical-equivalence claim depends on them.
