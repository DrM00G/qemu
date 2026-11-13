# Phase 4 local research work

AI-assisted local experiment only; never submit this output upstream. See
[QEMU provenance](../../docs/devel/code-provenance.rst).

**Actual V8 boot now passes.** The imported Debian 13 V8 root reaches systemd
multi-user.target under the existing Phase 3 6.18.62 simulator kernel, with
16384-byte pages, immutable lower/RAM OverlayFS and separate FSW/LOGS mounts.
The imported experimental unified 6.18.50 kernel and physical production
6.18.50+rpt-rpi-2712 kernel were not used. See [V8-REPRODUCTION.md](V8-REPRODUCTION.md).
Selected system/recovery metadata inspection was authorized; credentials and
private files were excluded. No physical hardware or golden image was modified.

This is a partial implementation. See [VALIDATION.md](VALIDATION.md) and
[LIMITATIONS.md](LIMITATIONS.md) for observed results and remaining work.

## Reproduce the tested diagnostic and peripheral exchange

Using the existing Phase 3 build/kernel/initramfs:

```sh
python3 experiments/cm5-phase4/smoke.py --output /tmp/cm5-phase4-new-run
python3 experiments/cm5-phase4/report.py /tmp/cm5-phase4-new-run/result.json
python3 -m unittest discover -s experiments/cm5-phase4 -p 'test_*.py'
```

The smoke compiles a dynamic ARM64 executable with 64 KiB ELF segment alignment,
reuses the Phase 3 initramfs packer and matching 16 KiB kernel, and copies matching
cross-compiler libc/libm/loader into its disposable initramfs. Two TCG CPUs and
512 MiB guest RAM suffice. It never attaches an OS disk. All output is outside
the repository. `/tmp` is volatile and has only about 3.9 GiB capacity here;
move evidence to an approved persistent laboratory directory for retention.

The diagnostic executes actual Linux system calls, emits timestamped JSONL and
continues after individual failures. Host serial capture detects the four-byte
PL011 transmission and echoes the bytes into the QEMU serial backend. The guest
reads and compares them through `/dev/ttyAMA0`. This is an emulated UART test;
there is no mission sensor or timing model. The serial console is dedicated to
this smoke: do not run it on an active physical console.

Build separately:

```sh
aarch64-linux-gnu-gcc -O2 -Wall -Wextra -Werror -Wl,-z,max-page-size=65536 \
  experiments/cm5-phase4/diagnostic.c -ldl -o /tmp/cm5-diagnostic
```

`run-diagnostic.py` provides a JSON frontend (`config.schema.json`, `profile.json`).
The executable itself accepts four positional arguments: new test-file path,
UART device or `-`, SPI device or `-`, and duration seconds. Use a unique file
name per invocation: O_EXCL prevents overwriting prior evidence. The JSON wrapper
requires explicit approval of a hardware mapping before enabling transfers.
The low-level CLI assumes its caller has approved the supplied mapping.
Physical execution has not been tested. The systemd unit is an installation
template, not validated service integration; install files under `/opt/cm5`
and create an approved LOGS directory first. The JSON frontend needs Python 3.

## Image inspection and migration

After the archive is located, preserve it and extract once into an approved
external work directory. Check disk/RAM first, reject unsafe archive member
paths and verify the supplied checksum locally. Do not extract all files into
this repository or expose unrelated contents to the assistant.

```sh
python3 experiments/cm5-phase4/disk_inventory.py /approved/lab/golden.img --sha256
```

This tool reads regular files only, parses MBR and chained EBR entries, checks
extents/cycles and invokes read-only blkid probes for filesystem metadata. It
never mounts or extracts files. Synthetic table tests passed; real V8 inspection
has not run. Expected full-device size is 15,634,268,160 bytes.

Next, inspect only approved fstab, systemd/boot configuration and recovery
metadata locally. Compare authoritative roots/parity against captured bytes.
Reuse Phase 3's matching kernel and initramfs builders and Phase 2's OverlayFS
contract only after checking the real mount requirements. Preserve original
fstab in evidence and apply explicit simulator policy in RAM. Instrument via
initramfs service injection, independent of cloud-init. Do not mask production
hardware failures. The reusable V8 launcher and its explicit RAM mount policy are now supplied in
`boot-v8.py` and `v8-init.sh`; see the reproduction guide.

## Bounded host corruption pilots

`pilot.py` reuses Phase 3's proven injection function on an explicitly derived
raw partition image. Outputs must be outside the repo. Cases: clean, os-small,
fsw-small and no-fec. Three scattered 4096-byte blocks are fully XORed with ff;
fraction means selected blocks divided by all blocks of that supplied partition,
not physical bit-error probability or filesystem allocated-data percentage.
The tool records exact offsets, readback and golden hashes. It does not mount,
boot, or configure FEC. `fec_requested` is experiment intent only. All guest
outcomes remain NOT_TESTED. Use existing Phase 3 run/regress for its validated
surrogate FEC experiments; do not equate this host pilot with guest correction.
