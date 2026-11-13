# Friday, November 13, 2026 — CM5 measurements to prioritize

Run the read-only collector first. Store output on an approved evidence location;
keep `raw/` private until reviewed. Missing utilities or permissions mean
**UNAVAILABLE**, not a guessed value. Do not reflash, reboot, remount, enable
tracing/debugfs, change outputs, open spidev, scan I2C addresses or run FSW code
for this collection. Existing normal workload may continue with its owner's
approval. Register reads are not automatically harmless.

## P0 — Interrupt and PCIe uncertainties

1. **What are the live MIP0/MIP1 ranges and actual MIP1 parent IRQ numbers?**
   Why: public DT specifies MIP1 range base 247/count 8 and offset 8; the driver
   allocates GIC SPI `base + MSI data`, so data 8 maps to SPI 255. Confirm the
   running firmware/kernel combination, not just an old source tree.
   Read-only method: collector's live DT, `/proc/interrupts` twice, platform
   driver symlinks, and already available `/sys/kernel/debug/irq/irqs/<IRQ>`
   descriptor reads for active RP1/expansion IRQs. Do not mount debugfs or change
   affinity. Compare native DT `msi-ranges`/`brcm,msi-offset` and QEMU MIP traces.
   Source: `hw/intc/bcm2712-mip.c`, `hw/arm/cm5io-dev.c`.
   Reboot/connector/equipment: none for software descriptors; an existing active
   expansion device helps. Safety: passive kernel views only; raw IRQ names stay private.

2. **What RP1 revision, BAR sizes, MSI-X vector capacity/table placement and link
   configuration does this exact module expose?**
   Why: current endpoint omits shared SRAM BAR2 and uses an experimental table
   layout and driver-required vector count. Read-only method: collector's
   `lspci -Dnnvv` and sysfs `vendor/device/revision/resource/driver`, restricted
   raw output. Compare `hw/misc/rp1-pci.c` against the device's actual resources.
   Reboot/equipment: none. Safety: no `setpci`, resource mapping, BAR writes or
   raw MMIO; do not publish unique PCI capabilities/serial fields.

3. **Can we obtain actual cached MSI message address/data for both links without
   touching a live device's MSI-X table?**
   Why: both published PCI links target bus address `0xfffffff000`, but route to
   different CPU-side MIPs. The new QEMU code implements that per-host aperture.
   Method: review any already exposed kernel IRQ/MSI debug descriptors; if the
   kernel does not expose message contents, record UNAVAILABLE. Do not use
   `/dev/mem`, mmap PCI resources or read vendor-specific unknown registers.
   A passive PCIe analyzer is a separate possible measurement, not part of the
   collector. Compare QEMU `bcm2712_mip_raise` events and inbound mappings.
   Source: `hw/arm/cm5io-dev.c` PCI DMA spaces and `hw/intc/bcm2712-mip.c`.
   Reboot/equipment: none for existing debug views; analyzer insertion may require
   a separately approved power-down/external fixture. Safety: operator-controlled
   instrumentation only; never alter MSI configuration to provoke a measurement.

4. **What are MIP reset values, status/clear semantics and masked-event behavior?**
   Why: Linux's edge path establishes only six configuration writes and MSI data;
   it does not establish level/VPU delivery, INT_CLEAR format, full reset state,
   or whether masked events latch. Current QEMU reset is conservative and those
   extra semantics are not claimed accurate.
   Safe method tonight/Friday: vendor-authorized documentation or an already
   available, reviewed non-destructive driver snapshot. Otherwise UNAVAILABLE.
   Ordinary collector output cannot answer this. Do not force reset, write
   INT_RAISE/INT_CLEAR, or poke raw registers on a running board.
   Compare model limitations in STATUS.md, not an invented expected value.
   Source: `hw/intc/bcm2712-mip.c`.
   Reboot/equipment: reset-state measurement would need a separately approved
   ordinary cold-boot capture or instrumented driver/lab setup. Safety: deferred
   beyond read-only scope unless that procedure is explicitly authorized.

## P1 — Storage, boot and board routing

5. **Which driver and host transport actually access eMMC, with what partition
   geometry and logical sector size?**
   Why: QEMU currently uses VirtIO, not physical SDHCI/eMMC; user-area corruption
   offsets must match the real image. Read-only commands: collector's `lsblk`
   geometry, `/sys/class/mmc_host/*` links and kernel boot log. Review host/card
   metadata locally; do not publish card CID/serial. Do not run `mmc` write,
   sanitize, boot-partition or EXT_CSD-changing commands.
   Compare STORAGE.md and the preserved image inventory, then public
   `sdhci-brcmstb` requirements. Source: future BCM2712 SDHCI wrapper under
   `hw/sd/`, existing `hw/sd/sd.c` card model, machine wiring.
   Reboot/equipment: none. Safety: no raw block writes, mounts or filesystem repair.

6. **Are OS and FSW actually protected by active dm-verity mappings, and where do
   LOGS and RECOVERY sit in the running block stack?**
   Why: a named partition or RECOVERY metadata file does not prove a mapping is
   active. Read-only commands: `dmsetup status`, `dmsetup info -c`, `findmnt --json`
   and `lsblk --json`; correlate privately. Do not dump arbitrary dm tables:
   crypt targets can contain secrets. Do not read proprietary FSW source or
   executable contents. Compare the active mappings with the recorded V8 command
   and initramfs: emulator OS uses a read-only lower/RAM overlay, FSW uses the
   preserved verified sidecars. Source: existing experiment boot/storage code,
   `experiments/cm5-phase6/STORAGE.md`.
   Reboot/equipment: none. Safety: no remount, verity verification sweep, fsck or
   corruption injection. Mapping names and paths stay restricted until reviewed.

7. **Which EEPROM/firmware versions and configured boot order are present, and
   what boot path is actually observed?**
   Why: direct `-kernel` boot cannot predict EEPROM/BOOT corruption survival.
   Read-only commands: `vcgencmd bootloader_version`, `vcgencmd bootloader_config`,
   `vcgencmd version` when installed; collector retains output privately. Configured
   BOOT_ORDER is not proof of the path used this boot. Compare with QEMU's absent
   ROM/EEPROM/firmware model and available PSCI/firmware-service nodes.
   Source: `hw/arm/cm5io-dev.c`, future boot/firmware implementation.
   Reboot/equipment: none for configuration. Capture the next independently planned
   operator boot if needed; do not reboot for collection. Optional passive debug
   UART capture requires a voltage-verified adapter, RX and ground only, no power
   injection or host TX. Safety: no EEPROM updater/apply flags or firmware changes.

8. **Which SPI/UART/I2C/GPIO routes are actually enabled, and is Vref assembled for
   3.3 V or 1.8 V?**
   Why: current emulator SPI wires directly to SSI and bypasses pinmux; its header
   UART is a generic substitute. Read-only commands: collector's `/dev`/sysfs
   exposure, `pinctrl get` or `raspi-gpio get`, and `gpioinfo` if available. Inspect
   the actual R4/R5 assembly visually against the official schematic; do not infer
   voltage from a DT property. Compare board-profile.json and generated connector
   metadata. Source: RP1 GPIO/pads/pinmux, UART and clock models still to implement.
   Reboot/equipment: none for software; visual access/photo for resistors. Optional
   voltage measurement needs a qualified operator and high-impedance instrument.
   Safety: no GPIO set/get line requests, output drive, spidev transfer, I2C address
   scan, pull-up change or unverified-voltage cable connection.

9. **Can existing traffic reveal SPI clock, CS gaps and native FIFO configuration?**
   Why: QEMU uses an experimental 64-entry FIFO and approximate 200 MHz input;
   successful ioctl bytes do not establish timing/electrical equivalence.
   Method: preserve existing driver logs; read a driver's debug register set only
   after confirming it excludes DR (FIFO pop), ICR/clear registers and unsafe
   clock-gated accesses, with the owner's approval. Otherwise UNAVAILABLE.
   A passive logic analyzer on already-running traffic is separate optional work;
   do not start a transfer for this read-only plan. Compare QEMU CS/transfer trace
   and the exact driver configuration. Source: `hw/ssi/dw-apb-ssi.c`.
   Reboot/equipment: none for safe existing logs; voltage-checked external analyzer
   for waveform capture. Safety: avoid read side effects, loading signals, ground
   shorts and contention; no claimed reset image from a live configured device.

## P2 — Execution and recovery context

### Phase 8 eMMC follow-up (on the physical CM5, no reboot)

Run the existing collector from `physical-probes/README.md` on the physical
8 GiB CM5 mounted on the official CM5 I/O Board. It writes only a fresh private
evidence directory; it does not change hardware or storage configuration.
No microSD/CM5Lite conclusion applies to this eMMC-equipped module.

Review `raw/mmc-passive.json`: host `device/driver`, `device/of_node`, sysfs
topology, exposed `f_min/f_max/actual_clock/caps/caps2`, and already-readable
debugfs `ios`. Correlate with existing live-DT `reg`, `compatible`, clocks,
8-bit/nonremovable/high-speed properties, `lsblk` START/SIZE/LOG-SEC, and the
existing boot-log MMC initialization lines. `ios` negotiation is an observation;
DT capabilities are declarations. No reboot or active stimulus is required.
Do not mount debugfs, change clocks, run `mmc extcsd`, read raw filesystem
contents, or alter boot0/boot1/RPMB/write-protect/EXT_CSD/EEPROM/OTP.

Compare against `../cm5-phase8/FIDELITY.md`: QEMU uses actual `sdhci-brcmstb`
and an 8-bit logical eMMC path, but only legacy PIO. Physical HS200/HS400,
DMA, tuning, controller errors and flash-internal behavior remain unvalidated.
Partition equality and sampled digest equality are separate tests; initial
Friday collection intentionally provides geometry without logical content reads.

10. **What CPU topology, RAM holes, kernel page size, boot delays and failed units
    are specific to this board/image?**
    Why: distinguish emulator transport gaps from CPU/ABI or production-service
    prerequisites. Collector uses `uname -r`, `getconf PAGESIZE`, `lscpu`, live DT,
    `/proc/iomem`, boot log and read-only systemd timing/failure queries. Compare
    four A76 affinities, 16 KiB test kernel and generic RAM layout; match causes
    rather than requiring identical elapsed times or unit names.
    Source: CPU/RAM/GIC machine initialization and matching guest-kernel config.
    Reboot/equipment: none. Safety: no workload benchmark, service changes, clock
    changes or reboot; redact serials, addresses and private unit/log contents.

11. **What recovery mechanisms are evidenced this boot rather than merely
    configured?**
    Why: RECOVERY contents, EEPROM fallback policy and successful physical recovery
    are different claims. Read only current mounts, dm status, boot logs and
    already exposed boot-state metadata. Keep any manual RECOVERY metadata review
    limited to approved metadata files; no FSW source, credential or secret read.
    Compare emulator direct-kernel limitations and the experiment's explicit
    recovery policy. Source: future firmware/eMMC boot path and recovery test logic.
    Reboot/equipment: none for current evidence. Power-fail/corruption/fallback
    trials require a later separately authorized plan and disposable images.
    Safety: do not simulate a fault or touch golden media during this collection.
