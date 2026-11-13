# Phase 9: native verified storage and erase-starvation diagnosis

AI-assisted local research, not an upstream contribution. No physical CM5
measurement is inferred. No commit, push, reset, clean, stash or branch change.
The eMMC-equipped CM5 on the official CM5 I/O Board remains the target.

## Reproduction

The existing Phase 6/8 runner, Phase 3 16 KiB kernel, unmodified Broadcom/MIP
modules, initramfs packer, V8 stage and diagnostic are reused. Phase 9 adds
profile hooks and evidence collection; it does not replace those frameworks.

```sh
ninja -C build-arm64-phase1 -j 8 qemu-system-aarch64 tests/qtest/bcm2712-sdhci-test
# Only once, to a fresh directory; reads complete captured OS/FSW and metadata:
python3 experiments/cm5-phase9/metadata-audit.py
sh experiments/cm5-phase9/run.sh clean fresh-clean
sh experiments/cm5-phase9/run.sh os0 fresh-os0
sh experiments/cm5-phase9/run.sh os1 fresh-os1
sh experiments/cm5-phase9/run.sh no-fec fresh-no-fec
sh experiments/cm5-phase9/run.sh fsw0 fresh-fsw0
```

Each run name must be new. `run.sh` accepts trailing runner options such as
`--qemu PATH` and diagnostic `--timeout SECONDS`. Timeouts remain bounded;
changing one is not a fix. `matrix.sh` is the exact serial schedule used here,
including a same-profile pre/post comparison. It expects retained baseline
evidence and is deliberately not an overwrite/retry command.

`command.json` records the expanded launch. Machine, kernel, modules, 4 A76
CPUs, 2 GiB RAM, native MIP, legacy PIO eMMC, console and controller traces are
the same throughout the full-verification matrix. QEMU/kernel/initramfs hashes
are recorded per run. No VirtIO block device is attached. VirtIO Ethernet remains
the existing substitute. No Linux MMC/SDHCI/interrupt driver is patched.

## Disk and metadata policy

Existing golden: `~/cm5-v8-lab/golden/cm5-emmc-userarea.img`, regular file,
15,634,268,160 bytes. Every run receives a fresh QCOW2 with this read-only
backing. Native card boot/RPMB sizes remain zero, preserving user-area offset0.
The runner records actual golden fd access mode. Disk images and initramfs
archives stay under the private lab directory. No host block devices are used.

`metadata-audit.py` first verifies that the existing RECOVERY extraction is
byte-identical to the captured p7. It extracts original OS/FSW hash/FEC/root
metadata into a fresh `~/cm5-v8-lab/phase9/metadata/`, verifies each complete
Merkle tree, and compares every data block against the **exact golden partition
range**. It generates no new parity, salt, hash tree or root. `audit.json` records
the checks and metadata digests. Captured root hashes are not independently
authenticated; this is not secure boot.

Guest stack:

* OS: actual mmcblk0p2 -> cm5-os dm-verity/FEC -> ro ext4 -> RAM OverlayFS.
* FSW: actual mmcblk0p5 -> cm5-fsw dm-verity/FEC -> independent ro ext4.
* Metadata: actual RECOVERY mmcblk0p7 mounted ro,noload, read-only Linux loop
  devices4/5 for FSW and6/7 for OS. No VirtIO metadata sidecars.
* LOGS: mmcblk0p6, writable only in the disposable full-disk overlay.
* BOOT, OS, FSW and RECOVERY partitions receive guest read-only flags. The
  golden descriptor remains read-only regardless of guest flags.

FSW geometry is the original 131,072 data blocks and1,033 hash blocks, 4096-byte
blocks, hash_start1, FEC roots2/fec_blocks132105/fec_start0. OS retains Phase 8's
2,621,440 data blocks and20,643 hash blocks, fec_blocks2642083. The header is
excluded from each FEC protected hash-block count.

## Bounded fault matrix

| Case | Deliberate change in fresh overlay | Required interpretation |
| --- | --- | --- |
| clean | None | Both original mappings, full V8/functions |
| os0 | OS block0 replaced with4096 bytes0x5a | Raw mismatch, original verified digest, real kernel correction, complete boot |
| os1 | OS block1 replaced with4096 bytes0x5a | Explicit raw and verified reads of this different block, correction, complete boot |
| no-fec | Same OS block0 fault; FEC options removed | Explicit verified read must return EIO; corrupt verity state; refuse root and power off; no successful boot claim |
| fsw0 | FSW block0 replaced with4096 bytes0x5a | Raw mismatch, original verified digest, FSW kernel correction and diagnostic read, complete boot |

`corruption.json` names exact offsets, lengths and overlay files. No unread block
counts as correction. Original OS0 fault offset545259520; OS1 offset545263616;
FSW0 offset11283726336. Full matrix outcomes live in the final report.

## Functional success and collection

For full profiles, the lab observer is a Type=simple service. It waits for real
multi-user.target, then launches the existing diagnostic with an optional verified
FSW block read, filesystem/fsync tests, actual SPI ioctl and20 one-second
heartbeats. Process PID/alive state is sampled while it runs. The pre-systemd
SPI/UART regression remains. This observer change makes the required order
observable; the separate same-profile reproduction retains the original observer
to isolate the hardware fix.

The diagnostic executable is the existing lab program injected into RAM, **not a
production executable authenticated by FSW verity**. Its optional FSW read uses
the real cm5-fsw device. FSW corrected-byte equality is independently checked by
the bounded block digest. Proprietary flight software is not inferred or read.

Each result reports kernel boot, OS/FSW verification, target, diagnostic process,
filesystem operations, persistent LOGS, SPI, heartbeat and clean collection
separately. After QEMU exits, a fresh sparse LOGS export is created in the lab;
only the newly-created deterministic diagnostic file is extracted and compared
on the host. This establishes persistence through emulator shutdown, beyond
same-process fsync/readback. It does not simulate physical power loss.

`host-samples.jsonl` contains per-second QEMU/thread scheduling, IO and host
pressure/memory observations. `timeline.jsonl` correlates serial arrivals and
guest monotonic timestamps. A bounded monitor records real interrupt counters,
diskstats, systemd jobs and process wait channels, and requests kernel sysrq
blocked-task/CPU backtraces. Missing/unfinished stack output stays incomplete.
All raw evidence is private; only nonsensitive results are summarized.

## Hardware change and validation

The actual card model `hw/sd/sd.c` batches high-capacity erase writes into1 MiB
operations while preserving0xff contents, inclusive sector boundaries and
partition offsets. It does not use discard, reveal backing bytes, or fake
completion. SDSC write-protect-group handling keeps its original path. Failed
backend writes set a card error. The exact-end out-of-range check is also fixed.
`hw/sd/trace-events` adds batch and elapsed-time evidence.

`tests/qtest/bcm2712-sdhci-test.c` adds an erase test: first/last erased sectors,
adjacent untouched sectors, inclusive boundaries, partial batch/state and invalid
exact-capacity address. Original reset, PIO, Auto CMD12/23, IRQ/error and backing
immutability tests remain. `hardware.sh` runs all14 hardware tests.
`regressions.sh` reuses the complete Phase 7 guest gate and Phase 8 native clean
profiles; all generated disks remain in the lab. No unrelated hardware work.

Read ROOT-CAUSE.md and STATUS.md for measured outcomes and remaining limitations.
