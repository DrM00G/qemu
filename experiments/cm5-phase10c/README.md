# Phase 10C: observed verified V8 boot and native PCIe progression

AI-assisted local research only; not an upstream contribution. Original kernel,
initramfs, golden image, roots, trees, parity and physical hardware remain
unchanged. Artifacts are ignored. Private disk/ramdisk/source exports stay in
`/home/aweso/cm5-v8-lab/phase10c/`.

## Reproduce from the repository root

Use fresh output names each time. Dependencies are the existing configured build,
Python 3.11+, zstd, debugfs and the private assets already present locally.

```sh
ninja -C build-arm64-phase1 -j 8 qemu-system-aarch64 \
  tests/qtest/rp1-test tests/qtest/cm5io-test tests/qtest/bcm2712-mip-test \
  tests/qtest/bcm2712-sdhci-test tests/qtest/qos-test

mkdir -p experiments/cm5-phase10c/artifacts/qtests-repro01/images
export QTEST_QEMU_BINARY="$PWD/build-arm64-phase1/qemu-system-aarch64"
export CM5_PHASE8_IMAGE_DIR="$PWD/experiments/cm5-phase10c/artifacts/qtests-repro01/images"
for name in rp1 cm5io bcm2712-mip bcm2712-sdhci; do
  "build-arm64-phase1/tests/qtest/$name-test" \
    > "experiments/cm5-phase10c/artifacts/qtests-repro01/$name.log" 2>&1
done

python3 -m unittest discover -s experiments/cm5-phase10a -v
python3 experiments/cm5-phase10a/matrix.py \
  --output experiments/cm5-phase10c/artifacts/synthetic-repro01
python3 experiments/cm5-phase10a/controls.py \
  --output experiments/cm5-phase10c/artifacts/phase9-repro01

# Read-only diagnostic copy: bounded process/stack/diskstats/table observations.
python3 experiments/cm5-phase10c/run.py --diagnostic --timeout 60 \
  --output experiments/cm5-phase10c/artifacts/pio-diagnostic-repro01

# Actual physical kernel AND ORIGINAL captured initramfs; no scan bypass.
python3 experiments/cm5-phase10c/run.py --dma --batch --profile native \
  --debug-shell --poweroff-after-validation --timeout 420 \
  --output experiments/cm5-phase10c/artifacts/original-repro01

python3 experiments/cm5-phase10c/fsw_audit.py \
  --output experiments/cm5-phase10c/artifacts/fsw-repro01
python3 experiments/cm5-phase10c/report.py \
  --run experiments/cm5-phase10c/artifacts/original-repro01 \
  --fsw-audit experiments/cm5-phase10c/artifacts/fsw-repro01 \
  --controls experiments/cm5-phase10c/artifacts/phase9-repro01 \
  --output experiments/cm5-phase10c/artifacts/report-repro01
```

`report.py` checks post-exit LOGS persistence and virtual COW extent bounds as
well as independently collected userspace evidence. Use its normalized report
for milestones: early raw run records contain serial-marker-only booleans,
which can be false even when the independent userspace query proves a target.
Missing serial output is not a failed guest operation.

Additional generic SDHCI checks actually run in this phase:

```sh
QTEST_QEMU_BINARY=./build-arm64-phase1/qemu-system-aarch64 \
 ./build-arm64-phase1/tests/qtest/qos-test -p \
 /aarch64/xlnx-zcu102/generic-sdhci/sdhci/sdhci-tests/registers
QTEST_QEMU_BINARY=./build-arm64-phase1/qemu-system-aarch64 \
 ./build-arm64-phase1/tests/qtest/qos-test -p \
 /aarch64/virt/generic-pcihost/pci-bus-generic/pci-bus/sdhci-pci/sdhci/sdhci-tests/registers
```

## Boot profiles and evidence

`run.py` opens the captured physical `kernel_2712.img` and original matching
initramfs directly, creates a fresh full-user-area qcow2 overlay, and records
input/executable/overlay identities. It does not execute EEPROM/boot firmware
or use Phase 10A selection as a claim of firmware fidelity.

`--diagnostic` creates a **separate diagnostic ramdisk**, gzip-repacking the
original newc/zstd-newc contents with a labeled init wrapper and bounded monitor.
The original hooks and full verified scan remain. It adds a guest `/dev/null`
node needed for early shell background execution and a diagnostic UART node in
devtmpfs; placing that UART node in nodev `/run` was a retained failed attempt.
The diagnostic layer is not the original production boot. It observes tables,
valid status, first 4096-byte reads, original `/run` stage logs, process states,
kernel stacks, diskstats and mounts. It does not replace metadata or skip reads.

`--debug-shell` adds `systemd.debug_shell=ttyAMA1` and a second local UART socket.
This is stock systemd's [documented debug-shell interface](https://www.freedesktop.org/software/systemd/man/257/systemd-debug-generator.html),
not an initramfs/OS patch. Console/earlycon/log-level arguments are also appended;
the captured root/verity arguments and default target remain. No guest network
is attached. The public `observe.py` is submitted over that debug UART after
systemd starts. It reads PID 1, targets, tables, mounts, the verified FSW block,
root Python ELF and libc; its only disk write is a new test file under mounted
LOGS. With `--poweroff-after-validation`, two passing observations at least
20 guest seconds apart cause `systemctl poweroff`.

The 420-second budget follows measured forty-chunk scan progress after tested
storage changes, followed by userspace validation and shutdown. It is not an
unexplained repetition of the old 900-second timeout. Current successful evidence
uses the original ramdisk and finishes normally within that bound.

QMP status and block statistics are sampled every ten host seconds. The existing
card backend does not account its `blk_pread` calls in QMP block accounting:
zero QMP byte counters do **not** mean no I/O. Guest diskstats, stacks, original
hook progress and a bounded 20–22 host-second card-read trace establish progress.
`sdcard_read_block` is a card-block attempt; with batching it may hit cache.
`sdcard_read_batch` records actual backend batch address, length and return code.
No proprietary block contents are logged.

## Storage changes and limits

Default machine/card profiles remain PIO with batching off. `emmc-dma=on`
advertises only the existing SDHCI core's ADMA2/64-bit descriptor capability;
it does not advertise HS400, CQE or physical timing. SDHCI previously cleared
DMA enable unless **SDMA** was set, incorrectly rejecting ADMA-only controllers.
The gate now recognizes all implemented DMA capability types.

CMD18 now returns the available requested portion of a block instead of forcing
one bus callback per byte. The bus API already supports partial/multiple-byte
returns. Exact block boundaries, state changes and CMD23 decrement are preserved.

`--batch` sets the explicitly experimental eMMC property
`x-cmd23-read-batch=on`. Only CMD18 with an explicit nonzero CMD23 count,
512-byte blocks and zero boot/RPMB hardware areas can use it. Reads are bounded
by the count, card capacity and 128 KiB maximum, with no speculation beyond the
requested command. Cache is cleared on every command, reset and migration load.
A failed batch falls back to the **same active backend** for the requested block,
not to a pristine host image. Card data consumption and backend prefetch are
different observations. General host-media error propagation remains the card
model's pre-existing subset; no broad physical read-error claim is made here.

The new qtests cover ADMA scatter/gather descriptors and buffers above 4 GiB,
read/write, invalid descriptors, a 128 KiB batch plus short tail, guard bytes,
and command completion. Existing PIO, erase, fault and backing-immutability
controls are retained. The successful run's allocated virtual COW extents are
entirely within p6 LOGS; this is observed write coverage, not a universal hardware
partition-write-protection model.

## Native PCIe and source provenance

The actual 6.18.50 source was retrieved from official Raspberry Pi
[`stable_20260911`, commit cff533aec2fa601846766b32ff57204e0a61bed7](https://github.com/raspberrypi/linux/tree/cff533aec2fa601846766b32ff57204e0a61bed7).
Its Makefile identifies 6.18.50. Driver/Makefile URLs and SHA-256 values are stored
outside the repository in `~/cm5-v8-lab/phase10c/reference-stable-20260911/sources.json`.
The exact distro build provenance beyond that source tag is not independently
established; actual captured-kernel register traces corroborate the exercised
initialization path.

MDIO port0 address/read/write transactions now complete after a modeled 1 us,
with bank selection, coherent register readback and reset cancellation. Only
documented 0x1600 reference-clock registers and the bounded 0x1100 PLL/SSC bank
are supported. The logical PLL state depends on the seven programmed reference
values; it does not imply a trained PCIe link. Invalid ports/pages/commands remain
observable as noncompletion/logs. The delay is a lab scheduling convention,
not a measured physical MDIO latency.

Native root ports now use QEMU's PCI core, correct vendor/device/type-1 config,
BCM2712 capability offsets, byte/word/dword access and real bus-number/reset
semantics. INTx outputs are wired to their controller-specific GIC inputs.
The actual captured driver enumerates both `[14e4:2712]` root ports and proceeds
past MDIO into link startup. Both links remain down. Downstream configuration
routing, functional window translation, RP1 attachment and native PCIe MSI
delivery remain unimplemented. Existing GPEX/RP1/MSI/SPI tests are the explicit
fallback. BAR2 sizing/reset remains covered there.

Captured p5 contains only an empty `lost+found` directory. No suitable captured
FSW executable exists in this image. No synthetic executable, resealed partition
or replacement parity was introduced. See [STATUS.md](STATUS.md) for outcomes.
