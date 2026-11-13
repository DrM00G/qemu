# Phase 8: native eMMC local experiment

AI-assisted local laboratory work, not for upstream submission. No commit,
push, stash, branch change, golden write or physical measurement was performed.
The target is the eMMC-equipped CM5 on the official CM5 I/O Board, not CM5Lite.

## Build and launch

Use the existing configured build and preserved 16 KiB kernel. No guest driver
source patch is required. The pinned local Linux source directory is
`~/cm5-phase3-kernel/linux-62a56e350fcfd1c5e204c62dac4ea4ee205eb24e`.
`build-mmc-module.sh` copies its public driver and adjacent headers unchanged.
The CQHCI and SDHCI platform/core symbols already exist in this kernel.

```sh
ninja -C build-arm64-phase1 -j 8 qemu-system-aarch64 tests/qtest/bcm2712-sdhci-test
sh experiments/cm5-phase8/build-mmc-module.sh /tmp/cm5-mmc-module-fresh
python3 experiments/cm5-phase6/regress.py --platform cm5io-dev --mode spi \
  --native-mip --mip-module experiments/cm5-phase7/artifacts/mip-module/irq-bcm2712-mip.ko \
  --native-emmc --mmc-module /tmp/cm5-mmc-module-fresh/sdhci-brcmstb.ko \
  --output experiments/cm5-phase8/artifacts/fresh-emmc-read
```

For V8 change `--mode spi` to `--mode v8`, choose a fresh output name, and add
`--timeout 300`. `command.json` records the exact expanded launch for each run;
`inputs.json` identifies QEMU/kernel/initramfs by SHA-256. `--memory 8192` selects
the larger guest; smaller default regressions remain 1/2 GiB.

Core attachment (an already-created disposable lab overlay is required):

```sh
build-arm64-phase1/qemu-system-aarch64 \
  -M cm5io-dev,native-mip=on,native-emmc=on -m 2048 -smp 4 \
  -drive file=/home/aweso/cm5-v8-lab/phase8/FRESH/emmc.qcow2,format=qcow2,if=none,id=native \
  -device emmc,drive=native,boot-partition-size=0,rpmb-partition-size=0 \
  -kernel /home/aweso/cm5-phase3-kernel/build/arch/arm64/boot/Image \
  -initrd PATH_TO_GENERATED_INITRD -append 'console=ttyAMA0 rdinit=/init panic=-1' \
  -display none -monitor none -serial stdio
```

The reproduction runner supplies the MIP/MMC modules and SPI fixture. Omitting
`native-emmc=on` preserves the old machine/storage profile. No native run silently
falls back to VirtIO block. VirtIO network remains an explicit Ethernet substitute.

## Storage protection

The existing regular-file golden image is exactly 15,634,268,160 bytes. The
archive was not decompressed again. The runner checks its type/size and free
space, then creates a fresh QCOW2 under `~/cm5-v8-lab/phase8/<run>/`. QEMU opens
the backing read-only. `block-backend-protection.json`, where present, measures
the actual golden descriptor access mode from QEMU's `/proc/PID/fdinfo`.
Full golden SHA-256 before/after records are separate from sampled read digests.
No host block device is used. Retain failed-run overlays as evidence.

QEMU's card model rejects a directly read-only backend. Consequently the card
sees a writable overlay. No change to `hw/sd/sd.c` was needed. Boot0, boot1 and
RPMB sizes are explicitly zero: **user-area byte zero remains backing byte zero**.
CID/EXT_CSD are QEMU-generated simulated identities/capabilities, not physical
measurements. No RPMB keys or absent physical areas are invented.

Native V8 mounts OS p2, FSW p5, BOOT p1 and RECOVERY p7 read-only; p1/p2/p5/p7
also receive Linux partition read-only flags. OS is `ro,noload` below RAM
OverlayFS. LOGS p6 is writable only in the disposable eMMC overlay. No native
profile attaches a VirtIO disk. The native profile mounts **original FSW p5**;
it does not claim active FSW verity. The preserved fallback profile retains
its existing FSW verity sidecars and tests.

The read helper uses a single 4096-byte `pread`, validates a block-device input,
and emits bytes only into SHA-512. Seven ranges cover MBR, BOOT, OS, extended
partition metadata, FSW, LOGS and RECOVERY. No filesystem content is printed.

## Source and Device Tree inventory

| Path | Phase 8 change |
| --- | --- |
| `hw/sd/bcm2712-sdhci.c` | New BCM2712 cfg wrapper and embedded existing SDHCI core |
| `include/hw/sd/bcm2712-sdhci.h` | Wrapper state/type |
| `hw/sd/sdhci.c`, `include/hw/sd/sdhci.h` | Opt-in PIO Auto CMD23, default off for other hosts |
| `hw/sd/Kconfig`, `hw/sd/meson.build`, `hw/sd/trace-events` | Build and cfg traces |
| `hw/arm/cm5io-dev.c` | Host creation, IRQ, generated DT, native option, 8 GiB RAM limit |
| `include/hw/arm/cm5io-dev.h` | Physical eMMC address/IRQ constants |
| `hw/arm/Kconfig` | Select wrapper |
| `tests/qtest/bcm2712-sdhci-test.c`, `tests/qtest/meson.build` | Three hardware tests |

DT: `/mmc@1000fff000`, host `(0x1000fff000,0x260)`, cfg
`(0x1000fff400,0x200)`, GIC SPI273 level-high, compatible
`brcm,bcm2712-sdhci`, `brcm,sdhci-brcmstb`, `sw_sdio` fixed 200 MHz input,
8-bit nonremovable, maximum 25 MHz, no SD/SDIO, alias mmc0. No HS200/HS400,
CQE, SD Express or DMA capability is advertised. Explicit empty default and
sd-express pinctrl states stand in for unmodeled pads. The driver otherwise
dereferences its error pointer when no pinctrl handle exists; the failed probe
is retained in `native-read-2`. No Linux driver was modified.

The cfg subset stores/masks CTRL forced-presence bits, SD_PIN_SEL, CQ_CAPABILITY
timer descriptor and MAX_50MHZ_MODE override. Reset values are simulated. Clock
selection writes have no modeled PHY effect. The standard core supplies command,
PIO FIFO, reset and level interrupt behavior. Auto CMD23 sends the count from
Argument2 before the main transfer; failures raise the auto-command error. It
is enabled only by the BCM2712 wrapper. Migration is explicitly unsupported.

`artifacts/native-emmc.dtb` and `.dts` are the actual generated board tree.
`artifacts/*/peripheral.log` contains cfg, host commands and card block reads.
RP1/DW/SSI/MIP hardware source hashes remain identical to the initial baseline.

## Optional original OS verification

Add `--os-verity` to a native V8 run. The initramfs reads original `os.hash` and
`os.fec` from captured RECOVERY p7 through read-only Linux loop devices; the
captured root hash is taken from the preserved Phase 4 extraction. It constructs
`cm5-os` over mmcblk0p2, then mounts that verified device beneath RAM OverlayFS.
No metadata is regenerated and no VirtIO metadata sidecar is attached.

Geometry: 2,621,440 data blocks, 20,643 hash blocks, 4096-byte blocks, hash start
1, FEC roots2, fec_blocks2,642,083, fec_start0. The superblock is excluded from
the FEC protected hash-block count. The preserved Phase 4 full-tree check is
historical evidence; this phase uses bounded reads and runtime root access.
The captured root hash is not independently authenticated; no secure-boot claim.

`--os-corrupt-block-zero` is permitted only with that profile. It writes a
4096-byte 0x5a pattern at user-area offset545259520 in a **fresh overlay only**.
The raw-sector digest must show the injected bytes; the verified read must
match the original OS block and the kernel must report FEC correction. This
does not repair the backing or predict physical ECC, wear, power loss or radiation.

## Validation and retained failures

`sh experiments/cm5-phase8/check.sh` reuses Phase 7's complete preserved gate
(three SPI matrices and three V8 boots), runs all hardware tests, then native
eMMC SPI/V8. Use a fresh run tree for reproduction. `--hardware-only` runs the
13 hardware qtests. Disk outputs stay under the lab, including fallback overlays.
Per-run result JSON files and the final validation inventory report actual
results; source/DT existence alone is never a compatibility claim.

Retained failures: direct read-only card backend rejection; missing pinctrl
state probe oops; minimal initramfs missing hash/DD applets; absent Auto CMD23
causing unfinished transfers; unsupported minimal `losetup -r`; initial FEC
count incorrectly including the hash superblock. These are separately recorded
integration failures, not fabricated physical observations or evidence of an
original metadata mismatch. See STATUS.md and FIDELITY.md for final outcomes.
