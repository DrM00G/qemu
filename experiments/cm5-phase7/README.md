# Phase 7: native BCM2712 MIP edge path and Friday measurement tools

The real Linux `mip_msi` driver now initializes on `cm5io-dev,native-mip=on`.
RP1 interrupts traverse PCI MSI-X, the per-host inbound MSI aperture, the new
MIP model and GICv2. All 72 SPI messages pass and actual V8 reaches systemd
with its existing SPI diagnostic passing. No GICv2m is instantiated on that path.

The overall MIP register model is **PARTIALLY_IMPLEMENTED**: the public-driver
host-edge path is **IMPLEMENTED_AND_GUEST_VALIDATED**, but full reset/status/
INT_CLEAR/level/VPU and masked-event retention semantics are not physically
validated. No physical CM5 data has been collected. Do not equate this with
complete BCM2712 or physical timing fidelity.

This is AI-assisted local research, not for upstream submission. QEMU's
[provenance policy](../../docs/devel/code-provenance.rst) applies. Nothing is
committed or pushed. Original golden images, kernel and Phase 5 hardware sources
remain unchanged. The Phase 6 binary is retained separately.

* [Hardware implementation and evidence](STATUS.md)
* [Friday questions and safe measurement methods](FRIDAY-HARDWARE-QUESTIONS.md)
* [Physical collector and privacy rules](physical-probes/README.md)

## Build and driver preparation

```sh
ninja -C build-arm64-phase1 qemu-system-aarch64 \
  tests/qtest/rp1-test tests/qtest/cm5io-test tests/qtest/bcm2712-mip-test
sh experiments/cm5-phase7/build-mip-module.sh \
  experiments/cm5-phase7/artifacts/new-mip-module
```

The module is the unchanged public Raspberry Pi `irq-bcm2712-mip.c`, compiled
against the preserved matching kernel build's exported IRQ/MSI interfaces.
The kernel's original config did not select the physical architecture-gated
MIP option; external Kbuild enables the driver as a loadable module without
replacing the kernel, changing its config or patching any driver checks.
`-DDEBUG` changes debug output only. The original source/module-source hashes
are checked. Matching original kernel/modules and userland stay intact.

The already-built module is at `artifacts/mip-module/irq-bcm2712-mip.ko`.
The build helper refuses source replacement; choose a fresh output directory.
The preserved kernel image hash matches the Phase 5 record. This method avoids
a large unrelated kernel rebuild and uses the actual public driver.

## Run native MIP

```sh
python3 experiments/cm5-phase6/regress.py --platform cm5io-dev --mode spi \
  --native-mip \
  --mip-module experiments/cm5-phase7/artifacts/mip-module/irq-bcm2712-mip.ko \
  --output experiments/cm5-phase7/artifacts/new-native-spi

python3 experiments/cm5-phase6/regress.py --platform cm5io-dev --mode v8 \
  --native-mip \
  --mip-module experiments/cm5-phase7/artifacts/mip-module/irq-bcm2712-mip.ko \
  --output experiments/cm5-phase7/artifacts/new-native-v8
```

These small optional extensions to the Phase 6 runner copy the module into a
fresh initramfs stage and load it after sysfs mounts, before V8 waits for disks.
The old SPI diagnostic, mock FSW, V8 observer and boot/storage framework are
preserved. Golden inputs are read-only; only fresh LOGS overlays are writable.
Network tests require local sockets outside the restricted sandbox.

Native checks require two actual platform-driver bindings, both sets of the
public driver's six MMIO initialization writes, MIP0 vector-19 delivery, no
GICv2m initialization, and the original byte/trace/SPI or V8 requirements.
V8 console loglevel suppresses dev_dbg, so MMIO evidence is used rather than
assuming driver initialization from a compatible string or log absence.

`-M cm5io-dev,native-mip=off` (the existing default) preserves the Phase 6
GICv2m fallback and original qtests. `virt` remains unchanged. Native MIP is
explicitly opt-in until its partial semantics are better characterized.

Full regression gate:

```sh
sh experiments/cm5-phase7/check-regressions.sh \
  experiments/cm5-phase7/artifacts/new-regression-set
```

This runs ten hardware qtests and SPI/V8 on all three configurations. The final
six guest runs were also executed individually and checked against the same
QEMU binary hash by `summarize.py`. No FEC or corruption sweeps were added.

## Describe QEMU and compare Friday data

Generate the real native-MIP board DT through QMP:

```sh
python3 experiments/cm5-phase6/dump-board.py \
  --machine cm5io-dev,native-mip=on \
  --output experiments/cm5-phase7/artifacts/new-native.dtb
python3 experiments/cm5-phase7/qemu-description.py \
  --dtb experiments/cm5-phase7/artifacts/new-native.dtb \
  --guest-run experiments/cm5-phase7/artifacts/native-spi-final \
  --v8-run experiments/cm5-phase7/artifacts/native-v8-final \
  --output experiments/cm5-phase7/artifacts/new-qemu-facts.json
```

The descriptor combines generated DT values with clearly labeled implementation
inventory and actual guest-validation evidence. It does not invent missing
runtime dm-verity target counts or physical measurements.

After read-only physical collection and manual review:

```sh
python3 experiments/cm5-phase7/compare-hardware.py \
  --physical /approved/private-evidence/cm5-friday/facts.json \
  --qemu experiments/cm5-phase7/artifacts/new-qemu-facts.json \
  --output experiments/cm5-phase7/artifacts/new-physical-comparison
```

Without `--physical`, the tool produces a planning matrix with every physical
value UNAVAILABLE. Tonight's such matrix is
`artifacts/friday-planning-matrix/{capabilities.json,CAPABILITIES.md}`.
It has six categories: CPU/software, boot firmware, eMMC/storage, interrupts/
PCIe, RP1/IO Board, and fault/recovery. JSON rows contain evidence pointer and
kind, source implementing the QEMU feature, impact and recommended action.
Raw collection files are never read by the comparison tool. Do not publish raw
serial numbers, credentials, addresses or secret configuration/log contents.

Parser/privacy tests:

```sh
python3 -m unittest discover -s experiments/cm5-phase7 -p test_tools.py
```

These use synthetic fixtures only and are not physical validation. They check
secret-property exclusion, missing observations, untrusted facts, topology
comparison independent of DT naming/cell widths and translated bus addresses,
partition privacy and malformed DT input.

## Authoritative inputs and remaining physical questions

* [Raspberry Pi public MIP driver](https://github.com/raspberrypi/linux/blob/rpi-6.12.y/drivers/irqchip/irq-bcm2712-mip.c)
  and [mainline MIP driver](https://github.com/torvalds/linux/blob/master/drivers/irqchip/irq-bcm2712-mip.c): register offsets, host/VPU initialization, MSI data and GIC-parent allocation.
* [Public BCM2712 DT](https://github.com/raspberrypi/linux/blob/rpi-6.12.y/arch/arm64/boot/dts/broadcom/bcm2712.dtsi): MIP0/1 addresses, PCI inbound aperture, MSI ranges and offset.
* The actual module uses the existing pinned local public source revision
  `62a56e350fcfd1c5e204c62dac4ea4ee205eb24e`, preserving driver/kernel compatibility.
* Existing QEMU `arm_gicv2m.c`, GPEX, PCI MSI-X, per-host PCI DMA address-space
  APIs, GICv2 model and Phase 5/6 hardware infrastructure supply the integration.

The public driver does not establish full register semantics. In particular,
MIP1's DT range base/offset and the driver's resulting GIC allocation are
recorded separately; the model follows the actual driver formula, pending
physical comparison. Do not guess a silicon reset image from driver init writes.
