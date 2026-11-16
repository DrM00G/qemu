# Phase 10A local BOOT failure/provenance experiment

AI-assisted local research only. This output must not be submitted upstream;
see `docs/devel/code-provenance.rst`. No changes to QEMU device models, GPEX,
the 6.18.62 fallback kernel, captured inputs, or physical devices are required.

This is the **bounded file-reader/validator** delivery permitted by the Phase
10A brief. It is explicitly NOT Raspberry Pi firmware and does not launch a
guest. Successful header checks end with `UNSUPPORTED`, stage
`HEADERS_VALIDATED`, because semantic image validation and the actual machine
handoff are not implemented. Phase 9 guest controls remain separate evidence.

## Reproduction

Run from `/home/aweso/projects/qemu`, with Python 3.11+ and GNU `cp`. Every
output directory must be fresh. Pick a new tag when repeating these commands.
Private disk copies default to `~/cm5-v8-lab/phase10a/OUTPUT_NAME`, outside the
checkout. Never point an input at a host device. No mounting is used.

```sh
python3 -m unittest discover -s experiments/cm5-phase10a -v
python3 experiments/cm5-phase10a/matrix.py \
  --output experiments/cm5-phase10a/artifacts/synthetic-repro01

python3 experiments/cm5-phase10a/preboot.py \
  --golden /home/aweso/cm5-v8-lab/golden/cm5-emmc-userarea.img \
  --output experiments/cm5-phase10a/artifacts/captured-repro01 \
  --boot-order emmc-only

# A separate disposable full-user-area copy, corrupting physical guest sector 0:
python3 experiments/cm5-phase10a/preboot.py \
  --golden /home/aweso/cm5-v8-lab/golden/cm5-emmc-userarea.img \
  --output experiments/cm5-phase10a/artifacts/mbr-repro01 \
  --boot-order emmc-only --xor-sector 0

ninja -C build-arm64-phase1 -j 8 qemu-system-aarch64 \
  tests/qtest/rp1-test tests/qtest/cm5io-test \
  tests/qtest/bcm2712-mip-test tests/qtest/bcm2712-sdhci-test

mkdir -p experiments/cm5-phase10a/artifacts/qtests-repro01/images
export QTEST_QEMU_BINARY="$PWD/build-arm64-phase1/qemu-system-aarch64"
export CM5_PHASE8_IMAGE_DIR="$PWD/experiments/cm5-phase10a/artifacts/qtests-repro01/images"
for name in rp1 cm5io bcm2712-mip bcm2712-sdhci; do
  "build-arm64-phase1/tests/qtest/$name-test" \
    > "experiments/cm5-phase10a/artifacts/qtests-repro01/$name.log" 2>&1
done

python3 experiments/cm5-phase10a/controls.py \
  --output experiments/cm5-phase10a/artifacts/controls-repro01
python3 experiments/cm5-phase10a/audit.py \
  --controls experiments/cm5-phase10a/artifacts/controls-repro01 \
  --output experiments/cm5-phase10a/artifacts/boot-coverage-repro01
```

The deliberate corrupt-MBR command exits 1 after recording `INVALID_LAYOUT`;
that is the expected proxy rejection. Exit 0 for `UNSUPPORTED` or
`SKIPPED_WITH_REASON` means the harness recorded its result, **not** that a guest
boot passed. Read `result.json` and `summary.txt`.

The controls wrapper calls the unchanged Phase 9 runner, preserves its success
criteria, and creates fresh qcow2 overlays in `~/cm5-v8-lab/phase9/`. It needs
the existing Phase 5 staging assets, cross compiler, modules, verity metadata,
kernel and golden image. To repeat only unfinished cases, use, for example:

```sh
python3 experiments/cm5-phase10a/controls.py \
  --output experiments/cm5-phase10a/artifacts/controls-retry01 \
  --cases os1 no-fec fsw0
```

## Selection and failure contract

`--boot-order` is mandatory. `emmc-only` is an explicit laboratory policy, not
the captured EEPROM boot policy. `0xf14` is recognized but returns
`UNSUPPORTED`: USB (low nibble 4) precedes SD/eMMC (1), with restart (f), and
USB/restart behavior is not implemented. No failed-device fallback is invented.

For eMMC the reader parses DOS MBR, bounded EBR chains and BOOT p1; FAT16 and
FAT32 with 512-byte sectors are supported. FAT12, subdirectory selection,
non-ASCII names, unhandled conditionals and unknown config directives stop
explicitly. VFAT long-name sequences and checksums are checked. Only the
active FAT is traversed; mirrored FAT consistency, backup BPB and FSInfo
recovery are not implemented. Root directory reads are bounded to 4 MiB,
individual files to 128 MiB, decompressed initramfs to 128 MiB, and chains to
262144 clusters. This is not a whole-volume consistency checker.

Selection precedence is documented CM5/V8 laboratory defaults, then supported
active `config.txt` overrides, then explicit CLI overrides. Supported overrides
are `kernel=`, `cmdline=`, `device_tree=`, and
`initramfs NAME followkernel`, with `[all]`, `[none]`, `[cm5]`, `[pi5]` sections.
CLI flags are `--kernel`, `--initramfs`, `--dtb`, `--cmdline`; they never bypass
an unsupported config directive. There are no implicit reads of clean host
boot files. Defaults are names supplied in the handoff, not newly observed
physical firmware selections. `selection_complete=false` means candidates
have not become selected files.

`READ_ERROR`, `INVALID_LAYOUT`, `INVALID_CONFIG`,
`SELECTED_FILE_UNAVAILABLE`, and `INVALID_IMAGE` describe the bounded proxy's
supported failures. They are not measurements of real firmware behavior.
Recognized unsupported compression/version/layout/config returns
`UNSUPPORTED`. Header checks cover uncompressed ARM64 Image magic/size, a
newc prefix with optional bounded gzip decoding, and DTB header bounds. They
do not validate kernel instructions, cpio entries, DT structure, signatures,
or bootability. Arbitrary payload corruption can pass header checks: the
`kernel-body-unvalidated` matrix case deliberately demonstrates that limit.

`--xor-sector N` modifies all 512 bytes only in the disposable copy and records
before/after hashes. `--read-error-sector N` injects a **proxy-only** read error;
it is not an emulated eMMC hardware error. Faults outside reads do not fail
automatically. Sectors are physical guest user-area LBAs, not OS logical
blocks or host storage addresses. Duplicate XOR sectors are rejected.

## Evidence semantics

JSON records include golden/overlay absolute path, device/inode, size,
mtime and whole-file SHA-256, parsed partition geometry, file content hashes
and extents, corruptions, selection, stage, and process/verity/diagnostic state.
No proprietary file content is emitted. Whole-file identity hashing and disk
copy I/O are separate from the proxy's byte-accurate `pread` ledger. The latter
records requested and actually returned bytes, including failures. An
interruption before `result.json` is inconclusive; `pending.json` is not a
completed run. Never reuse an interrupted directory.

For guest controls, `sdcard_read_block` is emitted **before** `blk_pread` in
`hw/sd/sd.c`. Provenance records attempted ranges/bytes and leaves successful
byte counts unknown. Verity digests, kernel FEC correction messages and the
unchanged Phase 9 evaluation establish those specific successful reads.
`audit.py` computes the exact complement of attempted BOOT ranges for each
completed run. An absence of attempted reads is not a simulation of firmware
reading that space. Generated runtime DTB bytes are not captured or hashed;
the source hash is explicitly labeled as a source hash.

Private reference files remain outside the repository. The interrupted
pre-change `golden-preboot-20261113a/emmc.raw` partial copy is preserved as
requested, ignored by Git, and is not usable evidence or an input. New
captured copies are rejected if their destination is inside the checkout.
