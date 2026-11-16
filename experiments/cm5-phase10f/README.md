> Historical Phase 10F baseline. Phase 10F.1 extends the shared validator,
> adds an explicit captured-config lab profile and pipe transports. See
> [Phase 10F.1](../cm5-phase10f1/STATUS.md) for current outcomes and limitations.

# Phase 10F: bounded active-BOOT handoff experiment

AI-assisted local experiments only, **not for upstream contribution** under
`docs/devel/code-provenance.rst`. No EEPROM instructions or firmware execute.
This delivery provides a usable tested subset, not an operational captured V8
BOOT boot. Captured config and zstd archive handling remain fail-closed blockers.
See [STATUS.md](STATUS.md) for actual milestones and preserved failed attempts.

## Reader and handoff contract

`block_reader.py` supplies random-access length-bounded logical reads from the
**exact active QCOW2** through read-only `qemu-nbd` on a private Unix socket.
No kernel NBD device, mount, root privileges, physical device or raw-disk copy
is needed. A short socket path avoids the Unix pathname length limit; its
unique `/tmp/f10f-nbd-*` directory is recorded and retained. The server is
terminated and reaped before guest launch. No worker is left running.

Only local regular raw/QCOW2 backing files, explicitly specified backing
formats, and at most eight backing nodes are allowed. Each backing pathname is
validated before opening it; protocol backing names, cycles, encrypted images
and external data files are rejected. QEMU opens the selection graph read-only
with its normal locking. Every graph node has device/inode/size/mtime/hash
identity, compared before and after selection, and again before guest launch.
Whole-image identity hashes are separate host I/O, never selection-read coverage.
The runner requires exclusive ownership of its disposable overlay; it closes
the selection graph before opening QEMU's writable guest graph. It does not
protect against a hostile host changing files during that transition.

The Phase10A MBR/EBR and FAT16/FAT32 parser is reused without changing its source.
`StrictFAT` adds full selected-chain validation, including the final FAT link,
reserved/bad clusters, overlong chains and allocated FAT32 directory-chain
cycles. Limits remain 512-byte sectors, 128 MiB/file, 262144 chain clusters and
4 MiB/root directory. Root filenames, checksum-validated VFAT and an active
FAT are supported. FAT12, selected subdirectories, backup/FSInfo recovery,
mirrored-FAT agreement and whole-volume consistency are not implemented.

Each logical request records requested offset/length, status and bytes actually
returned to the selector. This is not QEMU backend metadata/cache/prefetch I/O
and not guest card reads; those observations remain unknown here. Extents record
exact returned file bytes and enclosing guest-sector intervals. A fault outside
these logical reads does not automatically fail selection. Backend alignment or
metadata I/O can still matter; the ledger is not a physical device I/O trace.
Real error tests use QEMU's block graph (`raw -> blkdebug -> exact qcow2`), with
`read_aio`/EIO targeting a logical sector. Python does not manufacture the error.
This is a host block-reader fault, not a modeled eMMC electrical error.

## Supported selection and validation

`emmc-only` is an explicit LAB policy selecting p1; it is not captured
`BOOT_ORDER=0xf14`. USB/network/restart fallback is absent; `0xf14` is rejected
before disk reads. No default filenames or model matches are inferred. All four
paths must be explicit in `config.txt`/supported includes:

```text
[all]
kernel=kernel.img
initramfs initrd followkernel
device_tree=board.dtb
cmdline=cmdline.txt
```

Supported config semantics: comments, last explicit assignment, `[all]`,
`[none]`, root-file textual `include`, and those four selectors. Includes have
cycle/depth checks (eight active files), 64 KiB cumulative config content and
98-character non-comment line limits. The laboratory subset rejects long lines
instead of implementing firmware truncation. Unknown filters are rejected even
in inactive sections; inactive ordinary settings are skipped. Unsupported
`dtparam`, `dtoverlay`, model filters, prefixes, auto-detection, auto-initramfs,
explicit load addresses and other directives stop selection. **No DT parameter
or overlay is accepted then silently ignored.**

Source grounding: Raspberry Pi's [config format and includes](https://www.raspberrypi.com/documentation/computers/config_txt.html#advanced-features),
[conditional filters](https://www.raspberrypi.com/documentation/computers/config_txt.html#conditional-filters),
and [boot options](https://www.raspberrypi.com/documentation/computers/config_txt.html#boot-options)
describe the supported selectors, textual inclusion, filtering and followkernel.
The documentation also distinguishes include handling from EEPROM bootloader
settings. This subset makes no claim about parsing every firmware setting.

Validation consumes the full selected data:

- Kernel: bounded single gzip stream including stream end/CRC, then ARM64 magic,
  file/memory bounds, nonzero `image_size`, supported offset and little endian.
  Both compressed and decoded hashes/lengths are recorded. As specified in the
  [ARM64 boot protocol](https://www.kernel.org/doc/html/latest/arch/arm64/booting.html),
  `image_size` describes memory footprint and can exceed stored file length.
  This is not instruction semantics or proof of Linux bootability.
- Initramfs: complete newc headers/hex fields/name and payload bounds/alignment,
  trailers, CRC-newc sums, zero padding and concatenated newc archives; optionally
  one outer bounded gzip stream. At most 128 archives/262144 entries and 128 MiB
  expanded data. Nothing is extracted. Arbitrary file payloads need the lab hash
  gate. **Zstd segments are UNSUPPORTED, never reported as validated.** Other
  compression and concatenated compressed-frame formats are unsupported.
- DTB: version/header/block bounds, nonoverlap, reserve-map terminator, complete
  balanced node/property/token tree and string references. Binding correctness,
  DT semantics and real overlay application are not validated.
- Cmdline: bounded single ASCII line without NUL.

In addition, **every config/include and selected file must match a separately
supplied, pre-existing filename-to-SHA256 JSON lab baseline**. Selection never
creates its own acceptance hashes from the active potentially faulted overlay.
This detects selected payload changes that remain structurally valid; it is a
laboratory integrity oracle, not firmware signature/authenticity verification.
The baseline must be established from independently accepted inputs before
fault injection. Synthetic fixtures generate it before any fault.

Only a fully successful selection exports exact original compressed kernel,
initramfs, DTB and cmdline bytes to exclusively created **private** per-run files,
mode 0400. Hashes are checked after export and before launch. Owner permissions
are not an OS-enforced immutable-file feature; tamper checks detect later edits.
Failure returns no buffers and cannot export or launch. There is no host-asset
fallback in the selected path.

The generated compatible machine DT is an **explicit non-firmware substitution**.
The selected DTB must still pass validation/integrity; its input hash is recorded,
but it is not executed. This does not implement its hardware bindings or overlays.
`run.py` strips surrounding cmdline whitespace and appends the existing lab
console/earlycon/logging flags (and optional debug UART flag), recording both the
original selected-file hash and the effective cmdline hash/append operation.
Actual final runtime DT bytes are not captured/hashed by this delivery.

## Reproduce with unique names

From `/home/aweso/projects/qemu`. Never reuse an output/work directory.
Private images, exports, manifests, audit contents and expanded selected guest
command lines stay outside the checkout. Only nonproprietary source/tests and
metadata-only evidence belong in this experiment directory.

```sh
ninja -C build-arm64-phase1 -j 8 qemu-nbd qemu-img qemu-io qemu-system-aarch64
python3 -m unittest discover -s experiments/cm5-phase10f -v

# Builds a tiny non-Linux ARM64 UART/PSCI program, then tests actual runner launch
# and a fresh faulted overlay that must stop before creating a guest process.
python3 experiments/cm5-phase10f/runner_smoke.py \
 --work /home/aweso/cm5-v8-lab/phase10f/f-repro01 \
 --output experiments/cm5-phase10f/artifacts/f-repro01

# Read-only full captured audit; creates a fresh private QCOW2. It never launches.
python3 experiments/cm5-phase10f/captured_audit.py \
 --work /home/aweso/cm5-v8-lab/phase10f/f-captured-repro01

# Selection/export only; existing overlay must be private and disposable.
# Expected file is a pre-established private JSON {"filename":"sha256", ...}.
python3 experiments/cm5-phase10f/handoff.py \
 --overlay /PRIVATE/RUN/emmc.qcow2 --work /PRIVATE/NEW/selection \
 --boot-order emmc-only --expected /PRIVATE/accepted-file-hashes.json --export

# Opt-in Phase10C/E runner. No flag preserves its previous direct-host profile.
# Current captured config stops with UNSUPPORTED; this is not a successful boot.
python3 experiments/cm5-phase10c/run.py \
 --dma --batch --profile native --debug-shell --poweroff-after-validation \
 --boot-selection-policy emmc-only --boot-overlay /PRIVATE/RUN/emmc.qcow2 \
 --boot-expected /PRIVATE/accepted-file-hashes.json --timeout 420 \
 --output experiments/cm5-phase10f/artifacts/f-selected-repro01
```

Without `--boot-overlay`, the opted-in runner creates its usual fresh overlay
backed by golden and performs the same selection gate. `--boot-overlay` uses the
exact supplied private QCOW2 and forbids recovery-case setup. Diagnostic/no-FEC
initramfs replacement is forbidden with BOOT selection. No-fault `clean` recovery
setup and native 10 kHz observation remain available on the default golden-backed
path once its selection is actually supported. Missing a lab baseline also stops
before launch; it cannot weaken the config/format checks.

`handoff.py` exits 1 on failed/unsupported selection. Final opted-in runner exits
1 for `BOOT_SELECTION_STOPPED`; its historical other profiles retain their prior
exit behavior. Read result JSON rather than interpreting exit zero as Linux PASS.
The first captured-stop record predates this exit-status correction and returned
zero while explicitly recording `launched=false`. Synthetic raw `OBSERVED_RUN`
records correctly have no Linux/systemd success; the smoke evaluator checks the
unique UART marker, selected launch arguments and normal synthetic PSCI poweroff.

Unit fixtures/overlays/reports are retained under unique
`/home/aweso/cm5-v8-lab/phase10f-tests-*` directories, including failed attempts.
The tests intentionally avoid automatic cleanup of experiment evidence.
