# Physical versus QEMU: Phase 8

All physical observations remain **UNAVAILABLE / NOT_RUN_PHYSICAL**. Public DT
and driver source are design inputs, not laboratory measurements.

| Dimension | QEMU evidence/scope | Physical comparison still required |
| --- | --- | --- |
| Partition geometry | Exact MBR/EBR starts; p1,p2,p3,p5,p6,p7 enumerated | Collector START/SIZE; extended container's Linux node size may be only 2 sectors |
| Logical read results | Seven bounded 4 KiB ranges match captured image digests | Initial Friday collector intentionally performs no raw content reads |
| Host/driver family | Actual unchanged sdhci-brcmstb binds BCM2712 compatible | Driver link, live compatible, sysfs topology |
| Addresses/IRQ | Physical published host/cfg ranges, GIC SPI273; qtest IRQ | Live DT translated ranges, interrupts, safe boot log |
| Bus width | Logical 8-bit negotiation/card bus-test commands | Existing debugfs ios, if readable; no electrical validation |
| Clocks | Fixed simulated 200 MHz base, <=25 MHz legacy | Declared clock source versus observed negotiated clock |
| High speed | HS200/HS400/DDR/tuning not advertised or implemented | Physical declared caps and observed ios timing |
| DMA/CQE/SD Express | Not implemented by this profile | Physical capabilities do not imply modeled support |
| Card identity/EXT_CSD | Existing QEMU synthetic card, no boot/RPMB areas | No physical CID/EXT_CSD/RPMB content inferred |
| Controller errors | Invalid commands/ranges, auto-command failure, W1C/reset qtests | Silicon timeout/CRC/retention behavior unvalidated |
| Internal eMMC errors | Not modeled | ECC/wear/FTL/power-loss/radiation behavior unvalidated |
| 8 GiB RAM | Contiguous simulated RAM at zero; guest validated, lazy host allocation | Physical reserved holes, firmware reservations and DMA limits still differ |
| Native MIP/RP1 SPI | Real guest driver path, byte trace regression preserved | Physical timing, pins and other peripherals still pending |
| PCIe | Two GPEX host domains remain | BCM2712 PCIe host-register driver still absent |
| Boot | Preserved direct kernel/external initramfs | EEPROM/ROM/firmware and physical boot survival absent |
| OS policy | Plain native profile ro+RAM overlay; optional actual OS verity/FEC | Physical active mapping/authenticated root must be observed separately |
| Other substitutes | PL011 header UART, PL031 RTC, VirtIO Ethernet, empty pinctrl states | RP1 UART/PMIC RTC/Ethernet/pads remain absent |

Friday uses the existing Phase 7 collector. Added MMC observations are passive
sysfs links/descriptors and existing readable debugfs ios only. Whole live DT,
lsblk geometry and boot dmesg already cover the other requested measurements.
Run on the physical CM5; write only a fresh approved private evidence directory.
No reboot, raw sector read, MMC command, EXT_CSD/boot partition/RPMB/OTP/EEPROM
change, debugfs mount, clock adjustment or active probe is required.

The Phase 7 structured comparison now also distinguishes translated MMC resources,
declared speed/width capabilities, and runtime logical sector sizes. Descriptor
equality is not timing or fault-behavior equivalence. See the targeted addition
to `../cm5-phase7/FRIDAY-HARDWARE-QUESTIONS.md`.

Public references checked during this phase:

* https://github.com/raspberrypi/linux (default rpi-6.18.y at inspection)
* https://raw.githubusercontent.com/raspberrypi/linux/rpi-6.18.y/arch/arm64/boot/dts/broadcom/bcm2712.dtsi
* https://raw.githubusercontent.com/raspberrypi/linux/rpi-6.18.y/drivers/mmc/host/sdhci-brcmstb.c
* https://www.qemu.org/docs/master/system/devices/emmc.html

The DT ranges, sizes, SPI and clock name also match the local pinned Linux tree.
The guest module is byte-identical in source to that pinned tree, rather than a
moving web branch. Current QEMU source was inspected for zero boot/RPMB offsets,
card capacity alignment, command/data and write-permission behavior.
