# Storage architecture and corruption boundaries

The source of truth is the regular-file golden eMMC user-area image. Read-only
MBR/EBR and filesystem metadata inspection is retained in
`artifacts/storage-inventory.json`. No golden image was rewritten or mounted
writable. All V8 launches specify `readonly=on` for the golden and FSW sidecars.
The only writable disk is a new QCOW2 LOGS overlay per run.

| User-area partition | Byte offset | Byte length | Meaning in this image |
| --- | ---: | ---: | --- |
| 1 | 8388608 | 536870912 | FAT32 BOOT, bootfs |
| 2 | 545259520 | 10737418240 | ext4 OS, rootfs |
| 3 | 11282677760 | 4350541824 | Extended partition container |
| 5 | 11283726336 | 536870912 | ext4 FSW |
| 6 | 11821645824 | 1073741824 | ext4 writable LOGS |
| 7 | 12896436224 | 2736782848 | ext4 RECOVERY |

The image length is 15,634,268,160 bytes. It is not a model of every eMMC
hardware area: boot0/boot1, RPMB, EXT_CSD, wear, ECC and controller error behavior
are not inferred from this user-area file.

Actual CM5 uses BCM2712 SDIO1/SDHCI at CPU address 0x1000fff000, with additional
configuration registers at 0x1000fff400 and SPI interrupt 273. Public CM5 DT
selects an 8-bit nonremovable eMMC interface and HS200/HS400 options.
**That controller is not implemented in cm5io-dev.** Current disks use
virtio-blk-pci on `cm5-expansion`. This keeps partition numbers and existing
software tests intact while making the substitution observable in sysfs and
its actual driver. It does not claim that eMMC transport, tuning or fault
responses are correct.

QEMU already has an `emmc` card model (`hw/sd/sd.c`, `TYPE_EMMC` in
`include/hw/sd/sd.h`) and common SDHCI infrastructure. A future BCM2712 host
should reuse those and implement the documented Broadcom configuration,
capability/reset/clock/interrupt/DMA behavior required by Linux
`sdhci-brcmstb`, rather than label a virtio disk as eMMC. Other SoC SDHCI/PHY
wrappers are references, not equivalent BCM2712 hardware.

| Corruption boundary | What this platform can currently test | What it cannot predict |
| --- | --- | --- |
| EEPROM/firmware and BOOT | Filesystem reads of BOOT after Linux starts; explicit test inputs | Boot ROM, EEPROM boot order, rpiboot, firmware parsing or firmware rejection. `-kernel/-initrd` bypass these stages. |
| Verified OS | Existing userspace and selected file behavior under a configured block stack | The current V8 regression mounts raw OS read-only under RAM OverlayFS; it does not activate OS dm-verity or prove OS FEC. A new verified-OS run must explicitly construct and record that mapping. |
| Verified FSW | Preserved Phase 4 mapping uses the existing verified FSW data/hash/FEC devices and scan | Physical eMMC ECC/transport faults and proprietary FSW behavior. No new corruption sweep ran in this phase. |
| Writable LOGS | Real fsync/readback on partition 6 of a fresh overlay | Physical flash endurance, power-loss ordering, controller cache or journaling behavior under unmodeled hardware faults. |
| RECOVERY metadata | Read-only mount and the existing metadata observation path | Physical bootloader recovery choice, fallback policy or secure-boot authenticity decisions. |

Fault domains should remain separate in future tests: name the disk, partition
or verified mapping, byte offset, injected overlay, affected boot stage and
observed hardware function. A successful Linux/SPI transfer cannot establish
that a corrupted physical EEPROM/BOOT would boot at all. This phase did not
alter the FEC framework or repeat corruption sweeps.
