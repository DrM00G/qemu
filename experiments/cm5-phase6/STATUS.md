# CM5IO development-machine implementation inventory

The implemented machine is `cm5io-dev`, with its own `MachineState` initializer,
not inherited ARM virt initialization. Its DT root compatible is deliberately
`qemu,cm5io-dev`, not `brcm,bcm2712` or the physical CM5 board compatible.
Physical/electrical equivalence has not been independently validated.

## Exact source changes in Phase 6

| Path | Change |
| --- | --- |
| `hw/arm/cm5io-dev.c` | New independent machine; CPUs, RAM, GIC, clocks, UART, two PCI domains, auto RP1, generated DT, connector options/metadata and boot |
| `include/hw/arm/cm5io-dev.h` | BCM2712-informed and explicitly experimental address constants shared with qtests |
| `hw/arm/Kconfig` | `CM5IO_DEV` build selection and dependencies |
| `hw/arm/meson.build` | Compile board source |
| `hw/pci-host/gpex.c` | Optional `x-bus-name` and `x-root-bus-path`; original defaults preserved |
| `include/hw/pci-host/gpex.h` | Storage for those optional per-host strings |
| `tests/qtest/cm5io-test.c` | Two new machine-level qtests |
| `tests/qtest/meson.build` | Register the new AArch64 test |

The working Phase 5 RP1/DW/SSI C sources, controller header and original qtest
source were not modified. They remain required hardware models used by this
machine. New Python, shell, JSON and Markdown files only support reproduction,
regression checks and inventory; they are not counted as machine implementation.

## Hardware and fidelity

| Function | Status | What was achieved / remaining approximation |
| --- | --- | --- |
| Machine registration and initialization | IMPLEMENTED_AND_GUEST_VALIDATED | `-M cm5io-dev`, independent QOM machine, initializes and boots |
| Cortex-A76 CPUs | IMPLEMENTED_AND_GUEST_VALIDATED | Four CPUs default; affinities 0, 0x100, 0x200, 0x300. Existing QEMU CPU model; no physical cache/coherency/timing validation |
| RAM | IMPLEMENTED_AND_GUEST_VALIDATED | Starts at physical 0; 1 GiB SPI and 2 GiB V8 boots. Generic RAM; no DRAM controller/training; 8/16 GiB layout absent |
| BCM2712 GICv2 address placement | IMPLEMENTED_AND_GUEST_VALIDATED | Distributor 0x107fff9000, CPU interface 0x107fffa000; existing architectural GIC model. 512 IRQs is an experimental allocation, not a silicon IRQ-count claim |
| Generic timer and PSCI | IMPLEMENTED_AND_GUEST_VALIDATED | Fixed 54 MHz counter, architectural PPIs, QEMU-emulated SMC PSCI and secondary CPU startup. No physical firmware execution |
| Internal RP1 connection | IMPLEMENTED_AND_GUEST_VALIDATED | Automatic RP1 endpoint, own domain 2 / `cm5-rp1` bus, CPU window 0x1f00000000 |
| BCM2712 PCIe host registers/link | NOT_IMPLEMENTED | GPEX ECAM at experimental 0x1200000000/0x1201000000; `pci-host-ecam-generic`, not `brcm,bcm2712-pcie` |
| BCM2712 MIP interrupt controller | NOT_IMPLEMENTED | Existing generic GICv2m at 0x1202000000 instead; no physical MIP register semantics claimed |
| RP1 PCI/MSI-X/SPI0 | IMPLEMENTED_AND_GUEST_VALIDATED | Actual RP1 and DW driver path, IRQ 19, SPI0 physical MMIO 0x1f00050000; unchanged Phase 5 subset |
| Header SPI route | IMPLEMENTED_AND_GUEST_VALIDATED | Fixed SPI0 logical connection, two DT chip selects, explicit SSI fixture; no GPIO/pad/pinmux driver involved |
| Debug UART10 | IMPLEMENTED_AND_GUEST_VALIDATED | PL011 at documented 0x107d001000 and SPI interrupt 121; console and preinit loopback pass. Clock is an experimental fixed 48 MHz DT input, not the physical DT's UART clock tree |
| Header UART0 | PARTIALLY_IMPLEMENTED | Separate generic PL011 at experimental 0x1203000000, `serial1`; Linux driver binds. No RP1 UART0 register model or header external exchange test |
| Header I2C/GPIO/pinmux | NOT_IMPLEMENTED | Routing inventory only; no I2C bus/gpiochip, no fake APIs or pads |
| R4/R5 Vref | PARTIALLY_IMPLEMENTED | Selectable 1800/3300 mV metadata, default 3300; no electrical effect |
| PCIe expansion connector | PARTIALLY_IMPLEMENTED | Independent GPEX host/domain 1 and configurable `cm5-expansion` bus. VirtIO disks/network work; actual x1 controller/link training unmodeled |
| Ethernet | PARTIALLY_IMPLEMENTED | Virtio-net substitute on expansion works with real network driver and TCP/UDP test; RP1 MAC/PHY and magjack electrical behavior absent |
| USB | NOT_IMPLEMENTED | Existing qemu-xhci can be attached as a generic substitute; not guest validated. Preserved kernel has `CONFIG_USB_SUPPORT` disabled |
| RTC | PARTIALLY_IMPLEMENTED | Optional generic PL031 at 0x1203010000 binds as rtc0; no physical RTC firmware/PMIC/battery model |
| eMMC host/controller | NOT_IMPLEMENTED | Real partitioned user-area image is attached through VirtIO; no SDHCI/eMMC-driver claim |
| EEPROM/boot ROM/BOOT firmware | NOT_IMPLEMENTED | QEMU direct kernel loader; physical firmware boot and recovery behavior cannot be inferred |
| Actual V8 systemd + existing mock FSW | IMPLEMENTED_AND_GUEST_VALIDATED | Real V8 root/loader, multi-user target, SPI and existing diagnostic checks pass on fresh overlay |
| Full BCM2712/CM5 compatibility | NOT_IMPLEMENTED | GPU/VideoCore, PMIC, power, thermal, clocks/resets/pads, wireless, display/camera/audio and other RP1 peripherals remain absent |

## Address-space and DT choices

RAM is at zero, rather than virt's 0x40000000. Internal RP1 and expansion CPU
windows begin at the physical DT's 0x1f00000000 and 0x1b00000000. Each current
window is only 256 MiB. PCI bus memory begins at experimental 0x10000000, so the
GPEX translation differs from physical BCM2712 outbound mappings. PCI BAR1 is
allocated at bus 0x10000000 and maps to CPU 0x1f00000000. This was checked in
actual guest boot logs. RP1 is directly on the root bus slot 1, not behind a
modeled x4 link/root-port train sequence. The internal host is reserved for RP1;
adding other devices there can invalidate the fixed DT translation.

The separate expansion bus prevents temporary disks/network from moving RP1's
BAR allocation. GPEX's original hardcoded migration path caused a duplicate-root
assertion; the optional per-host name/path properties fix that while preserving
the single-host defaults used by virt. Both complete virt regressions passed.
The RP1 model still explicitly blocks migration; unique host paths are not a
claim of board migration support.

The machine constructs all supported DT nodes itself. The RP1 driver creates its
real IRQ domain and the real DesignWare driver probes its MMIO. The 200 MHz SPI
clock and 48 MHz UART clock are fixed substitutes, not clock-controller emulation.
QEMU device reset supplies the supported reset behavior, not BCM2712/RP1 hardware
power/clock/reset registers. Unsupported blocks are omitted from active DT.
No Linux essential checks were bypassed or patched.

Connector routing metadata lives under `/cm5io-connectors` and is not a hardware
binding. `board-profile.json` gives physical connector context, hypothetical
attachment examples and explicit unsupported statuses. Disabling header SPI
removes its DT exposure; it does not implement electrical disconnection or reset
the internal controller. Machine options are boot-time configuration, not live
pinmux controls. Generic attachments on expansion are not RP1 Ethernet/USB.

## Validation that actually ran

All final runs use one SHA-256-identified QEMU binary. See
`artifacts/validation.json`, checked by `summarize.py`.

| Check | Actual result / evidence |
| --- | --- |
| Build | PASS, `build-final.log` |
| Machine/help and options | PASS, `machine-help.txt`, `machine-options.txt` |
| Original Phase 5 qtests | 5 PASS, `qtest-rp1-final.log` |
| New machine qtests | 2 PASS, `qtest-cm5io-final.log`; low RAM, high GIC/UART, both PCI domains, MSI_TYPER, RP1 BAR translation, real SSI transfer/reset; disabled UART/RTC/expansion absence |
| Generated default/minimal DT | Checked by `dump-board.py`/`summarize.py`; correct root compatible, SPI/expansion omission and Vref values. Two known `rp1` node-name dtc warnings retained |
| New-machine SPI | 72/72 ioctl messages; 5,448 QEMU SSI frames match all TX/RX bytes, `cm5-spi-verified/` |
| Preserved virt SPI | Same 72/72 / 5,448-frame result, `virt-spi-final/` |
| New-machine V8 | PASS, `cm5-v8-final/`: systemd target, original diagnostic, actual SPI loopback and four QEMU echo frames |
| Preserved virt V8 | PASS, `virt-v8-final/`: same requirements, separate fresh overlay |
| Phase 5 preservation | Original binary hash and all five original hardware/header/qtest source hashes unchanged |
| Style/whitespace | `git diff --check` clean; checkpatch zero errors with `--no-signoff`, one new-files/MAINTAINERS warning |

Real drivers observed on the new machine: `pci-host-generic` for each temporary
host; `rp1` bound at `0002:00:01.0`; `dw_spi_mmio`/`spi_dw` for
`1f00050000.spi`; spidev for spi0.0; ARM GICv2/GICv2m IRQ handling;
`uart-pl011` for ttyAMA0 and ttyAMA1; `rtc-pl031` for rtc0; VirtIO block and
network drivers for the temporary expansion devices. BCM2712 PCIe, physical MIP,
RP1 GPIO/pinctrl, physical eMMC, RP1 Ethernet/USB drivers were not validated.

Concrete new-machine result:

```text
rp1 0002:00:01.0: bar1 len 0x400000, start 0x1f00000000
SPI_IOC_MESSAGE(1) mode=0 hz=100000 len=4 TX=10203040
SPI_RESULT ret=4 errno=0 RX=b58595e5
SPI_DIAGNOSTIC=PASS failures=0
... rp1_irq_chip 19 ... 1f00050000.spi
V8_RP1_SPI_DIAGNOSTIC_EXIT=0
... "test":"spi_loopback","status":"PASS","errno":0,"bytes":4 ...
V8_DIAGNOSTIC_EXIT=0
V8_TARGET=active
```

In V8 the fixture is deliberately configured to echo, preserving the old
unchanged diagnostic contract. The standalone matrix uses XOR 0xa5. This is a
configurable simulated device, not an assertion about any real sensor or wiring.
UART console loopback, TCP/UDP, fsync/readback and userspace checks also passed,
but those demonstrate their respective generic interfaces, not additional RP1
peripheral implementations. No new fault injection or FEC sweep was run.

Failed intermediate launches remain under artifacts: two GPEX hosts initially
collided on their migration path; an initial HVC/EL2 combination disabled PSCI
and overlapped the secondary boot stub; a misplaced GICv2m DT node deferred PCI
probes. These were fixed in QEMU/DT construction, not by altering Linux drivers.
The successful kernel start without PCI was not counted as RP1 compatibility.

## Next implementation step

Implement BCM2712 MIP at its documented register block using the public Linux
`irq-bcm2712-mip.c` contract, with focused qtests and the same SPI/V8 gate. This
replaces a central generic interrupt substitute while retaining working RP1.
Then implement the BCM2712 PCIe host bridge registers, outbound/inbound windows
and reset/link behavior required by `brcm,bcm2712-pcie`. These are the main
blockers to binding the physical host driver and using a substantially physical
DT. Native eMMC can then reuse QEMU's eMMC card and SDHCI infrastructure with a
BCM2712 host/config wrapper. See STORAGE.md for the distinct firmware, OS, FSW,
LOGS and RECOVERY corruption boundaries; a direct-kernel boot cannot validate
physical EEPROM/firmware boot survival.
