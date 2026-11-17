# Reproduce Phase 10J on hsflpc04

Local-only experiment; no upstream contribution. This is a human-operated
procedure: no remote commands, installs, asset transfer or work-PC execution were
performed by the agent. Preserve separate recovery-root experiments; wait until
no full Linux guest is running. Do not reuse their directories or overlays.
Phase 10J was pushed on `cm5-rp1-hardware` at `bf5b2ce`
(full revision `bf5b2cef36fceb90a872f116c1462763492c3851`). The earlier
work-PC observation was `64b13da`; its current revision is unmeasured.
Use a checkout containing the pushed Phase10J harness and Phase10C runner;
review local differences before applying any later private diagnostic changes.
Do not commit/push it upstream or change hardware models.

Run in bash, stopping at every failed command. Paths below are private examples.

```sh
set -euo pipefail
cd /code/davidg/qemu
git branch --show-current
git rev-parse HEAD
git status --short
# Phase10J baseline: cm5-rp1-hardware at bf5b2cef36fceb90a872f116c1462763492c3851.
# Inspect rather than reset/checkout/clean any differences.
test -f experiments/cm5-phase10j/run.py
python3 experiments/cm5-phase10c/run.py --help | rg 'phase10j-workload|lab-root|golden'
```

For Debian/Ubuntu, these packages supply the build/runtime prerequisites. Have the
operator install only if missing, at an appropriate time for that machine:

```sh
sudo apt-get install build-essential ninja-build pkg-config python3 python3-venv python3-pip git libglib2.0-dev libpixman-1-dev libfdt-dev zlib1g-dev libzstd-dev zstd
```

The configured tree's Python environment supplies Meson through QEMU configure;
if offline, prepare the Python dependencies described by `pythondeps.toml` using
approved local packages. Host Python must support `hashlib.file_digest` (3.11+).
`libzstd.so.1` is needed for complete selected-initramfs validation. Shell tools
include util-linux, coreutils and procps. The guest needs its captured Python3,
findmnt, lsblk, dmsetup, systemctl, libc, mount and GNU timeout; do not replace its OS.
No cross compiler or libguestfs is required for this experiment.

These are the **actual successful BigDog configure arguments**, recovered from
`build-arm64-phase1/config.status`; do not run that file because it embeds BigDog
paths. Leave an existing differently configured build alone; inspect it first.
For the reported missing build, create a fresh directory:

```sh
test ! -e build-arm64-phase1
mkdir build-arm64-phase1
(cd build-arm64-phase1 && ../configure --target-list=aarch64-softmmu --disable-docs --disable-gtk --disable-sdl --disable-vnc --disable-werror)
ninja -C build-arm64-phase1 -j2 qemu-system-aarch64 qemu-img qemu-io
build-arm64-phase1/qemu-system-aarch64 --version
build-arm64-phase1/qemu-system-aarch64 -machine help | rg 'cm5io-dev'
build-arm64-phase1/qemu-system-aarch64 -M cm5io-dev,help | rg 'native-emmc|native-mip|native-pcie|emmc-dma|rp1-gpio-lab'
rg 'CONFIG_CM5IO_DEV=y|CONFIG_RP1_PCI=y' build-arm64-phase1/aarch64-softmmu-config-devices.mak
build-arm64-phase1/qemu-img --version
build-arm64-phase1/qemu-io --version
```

Default devices are enabled in the successful build; the custom fork's Kconfig
supplies CM5/RP1. No invented configure enable-device flags are necessary. The
installed `/usr/bin/qemu-img` alone is insufficient: existing readers expect
`qemu-img` and `qemu-io` in the checkout's `build-arm64-phase1`. With the explicit
qemu-io reader, qemu-nbd is not required. No new QEMU compilation was needed on
BigDog for Phase10J.

Use the compressed full-eMMC golden, never the standalone OS partition or healed
backup as a substitute. The archive is NOT a raw block image. First inspect
capacity on the destination filesystem (work-PC free capacity is unmeasured):

```sh
export CM5_J_ROOT=/home1/davidgie/cm5-phase10j
export CM5_J_ARCHIVE=/home1/davidgie/cm5-portable-reference/images/cm5-emmc-userarea.img.zst
export CM5_J_GOLDEN="$CM5_J_ROOT/golden/cm5-emmc-userarea.img"
export CM5_J_EXPECTED="$CM5_J_ROOT/acceptance/accepted-hashes.json"
export CM5_J_FSW=/code/davidg/hts1-flight-software-freertos/pobc-deployment/build/rpi-cm5-debug/fsw/RpiDeployment.elf
umask 077
mkdir -p "$CM5_J_ROOT/golden" "$CM5_J_ROOT/acceptance"
df -h "$CM5_J_ROOT"
python3 - <<'PY'
import os, shutil
# 15.6 GB raw plus 20 GB headroom for disposable overlays, build/evidence growth.
p = os.environ['CM5_J_ROOT']
assert shutil.disk_usage(p).free >= 15634268160 + 20_000_000_000, 'Insufficient capacity; choose a larger private filesystem'
PY
test -f "$CM5_J_ARCHIVE"
zstd -t -- "$CM5_J_ARCHIVE"
sha256sum -- "$CM5_J_ARCHIVE"  # retain privately; compare with its trusted inventory
# BigDog recorded compressed hash 72a55fb788293513fb4d85c8f8f294453f4bd213bc83340f4f0a377b6d158b96.
# An independently recompressed archive may differ; raw identity below is decisive.
test ! -e "$CM5_J_GOLDEN"
# noclobber prevents replacing an existing target; a failed partial stays for review.
(set -o noclobber; zstd -dc -- "$CM5_J_ARCHIVE" > "$CM5_J_GOLDEN")
python3 - <<'PY'
import hashlib, os, stat
from pathlib import Path
p = Path(os.environ['CM5_J_GOLDEN'])
assert stat.S_ISREG(p.lstat().st_mode), 'Require a new regular file'
assert p.stat().st_size == 15634268160
with p.open('rb') as f:
    assert hashlib.file_digest(f, 'sha256').hexdigest() == 'e2fb1a85c2652838793e58f8b13ef908e2e4a4c4295e27297ce742287f69cb87'
PY
chmod 0400 "$CM5_J_GOLDEN"
```

A different raw hash is BLOCKED: establish the correct authorized image identity,
not a new acceptance baseline from the suspect image. Do not overwrite, mount,
repair or decompress onto existing recovery artifacts. Preserve the archive,
`/home1/davidgie/cm5-qemu-unified/data/v8-os-golden.img` and
`/home1/davidgie/cm5-backups/cm5-v8-healed-candidate.img.gz` unchanged.

The accepted BOOT manifest is an additional prerequisite. Have the operator
locate an independently accepted matching filename-to-SHA256 JSON, or separately
arrange an authorized copy of BigDog's private
`/home/aweso/cm5-v8-lab/phase10f2/accepted-01/accepted-hashes.json` to
`$CM5_J_EXPECTED`. Do not generate acceptance hashes from a test overlay.
Retain its original provenance/inventory and verify the authorized copy's hash.
A limited local search, without touching running recovery artifacts:

```sh
find /home1/davidgie/cm5-portable-reference -type f \( -name 'accepted-hashes.json' -o -name '*manifest*.json' \) -print
test -f "$CM5_J_EXPECTED"
sha256sum "$CM5_J_EXPECTED"
```

The manifest must include selected config/cmdline/kernel/initramfs/DT and selected
BOOT overlays. Matching captured kernel and initramfs are inside the validated
full-eMMC BOOT; no separate external kernel directory is required on Phase10J's
BOOT-selected path. Expected identities are kernel `154f0ea1e14bb1075077dfd1bdc63c1502bc0b17b0354628d515b4fbd3a4198d`
and initramfs `fcaade1e3aab0d79a51a170f556d25d0d1476bc17518099de54f5ebe16feab5b`.
Original verity/FEC configuration is carried by the captured initramfs/cmdline
and full-eMMC verification partitions. All must match together. Do not rebuild
initramfs, switch to no-FEC diagnostics, edit metadata, or write the empty FSW
partition. Separate physical DT exports are references, not direct QEMU DT input.

Optional offline BOOT export/acceptance check, with a fresh regular-file-backed
overlay, no host mount and no guest:

```sh
CM5_J_CHECK=$(mktemp -d "$CM5_J_ROOT/boot-check-XXXXXXXX")
build-arm64-phase1/qemu-img create -f qcow2 -F raw -b "$CM5_J_GOLDEN" "$CM5_J_CHECK/emmc.qcow2"
build-arm64-phase1/qemu-img info --backing-chain --output=json "$CM5_J_CHECK/emmc.qcow2"
CM5_BOOT_READER=qemu-io CM5_BOOT_PREFETCH=65536 python3 experiments/cm5-phase10f/handoff.py --overlay "$CM5_J_CHECK/emmc.qcow2" --work "$CM5_J_CHECK/selection" --expected "$CM5_J_EXPECTED" --boot-order emmc-only --config-profile cm5-headless-lab --export
# Require SELECTED. Examine selection/selection.json and private selection/exports.
```

Never reuse that overlay for a different test. Phase10J creates and validates its
own fresh overlay, repeats acceptance checks, and binds actual exports to launch.
The `0xf14` policy is a lab proxy, not EEPROM firmware execution. Phase10G still
contains BigDog defaults; use Phase10J directly. Phase10C now accepts `--golden`
and `--lab-root`; Phase10J passes both, so its BOOT-selected launch never needs
BigDog's remaining legacy external-assets default. The old Phase10F.1 prepare
script also has BigDog paths: do not run it unmodified on hsflpc04.

After recovery-root experiments are idle, verify the ELF and run checks:

```sh
sha256sum "$CM5_J_FSW"
# Require b0b4dd5af15b4cbfd8005da10551cf4dc9f9ce45166299c4996d238a5362fbc3
python3 -m unittest discover -s experiments/cm5-phase10j -p 'test_*.py' -v
pgrep -af qemu-system || true
# Proceed only with no full Linux guest running; do not kill someone else's guest.
python3 experiments/cm5-phase10j/run.py --golden "$CM5_J_GOLDEN" --boot-expected "$CM5_J_EXPECTED" --fsw "$CM5_J_FSW" --duration 30 --work "$CM5_J_ROOT/fsw30-$(date -u +%Y%m%dT%H%M%S)-$$"
```

Review startup/output, mounts, application exit and normal shutdown first. Only
then run the optional longer test (never automatically after failure/uncertainty):

```sh
python3 experiments/cm5-phase10j/run.py --golden "$CM5_J_GOLDEN" --boot-expected "$CM5_J_EXPECTED" --fsw "$CM5_J_FSW" --duration 300 --work "$CM5_J_ROOT/fsw300-$(date -u +%Y%m%dT%H%M%S)-$$"
```

Each comparison is private. Compare `comparison.json`, `fsw-output.log`,
`v8/fsw-result.json`, `userspace.json`, `result.json`, kernel/selected-asset
identities and relevant `hardware.log`/serial lines between hosts. Compare physical
PTY transcripts, exit 124, version/topology, exact component/task names, repeated
housekeeping and packet generation/routing, warnings and fixture absence. Compare
page size/stack clamp observations explicitly. Retain native Linux's separate
binary/build identity. Do not equate host elapsed seconds, guest monotonic seconds
and virtual execution time, or infer hardware timing fidelity. Build success alone
does not establish accepted image/manifest/boot/verity/FSW readiness.

## Portable harness source bundle

The resumed experiment supplies a private `portability/harness-source.tar.gz`
and `portability/SHA256SUMS` beside its evidence. It contains only the local
Python harness dependencies and Phase10J instructions, with checkout-relative
paths, plus `SOURCE-SHA256.json` and `BASE-REVISION.txt`. It contains no ELF,
image, acceptance manifest, guest payload, logs, or build binaries. Transfer
these sources separately from the approved private assets through your approved
file-copy method. These AI-assisted sources are for local experiments only.

On the work PC, verify the archive against the separately retained SHA256SUMS,
then extract into a fresh staging directory outside the checkout. Compare
BASE-REVISION.txt with the checkout and review differences before copying files;
do not blindly extract over a working tree. For example, after setting
CM5_J_BUNDLE to the transferred portability directory:

```sh
(cd "$CM5_J_BUNDLE" && sha256sum -c SHA256SUMS)
CM5_J_STAGE=$(mktemp -d /tmp/cm5-j-source-XXXXXXXX)
tar -xzf "$CM5_J_BUNDLE/harness-source.tar.gz" -C "$CM5_J_STAGE"
python3 - "$CM5_J_STAGE" <<'PYVERIFY'
import hashlib, json, sys
from pathlib import Path
root = Path(sys.argv[1])
for name, digest in json.loads((root/'SOURCE-SHA256.json').read_text()).items():
    assert hashlib.sha256((root/name).read_bytes()).hexdigest() == digest, name
print('Source checksums verified')
PYVERIFY
cat "$CM5_J_STAGE/BASE-REVISION.txt"
git -C /code/davidg/qemu rev-parse HEAD
diff -ru /code/davidg/qemu/experiments/cm5-phase10j "$CM5_J_STAGE/experiments/cm5-phase10j" || true
```

Review/copy each required source from staging, preserving its `experiments/`
relative path. The bundle includes Phase10A/B/C/D/E/F/F.1/F.2 Python sources
and the Phase10I transport test because the runner imports across these
folders; transferring only Phase10J is insufficient. Existing hardware models
must already match the base revision and local lab configuration. Nothing in
this bundle patches or substitutes a hardware model. The BOOT-selected
Phase10J path does not invoke the separate physical-reference DT transformation
tools with BigDog paths. Do not run those unrelated tools as a portability fix.

Run both harness and transport checks from the checkout after the reviewed copy.
The harness intentionally returns exit code 1 for PARTIAL as well as failure;
inspect `comparison.json` and a separate reviewed comparison before interpreting
that shell status. A completed timeout alone does not establish physical parity.
No remote build was performed from BigDog; record the actual work-PC build,
capacity, asset identities, and workload result when that procedure is run there.

## Resumed harness compatibility requirements

Use the latest bundle, including the acknowledged transfer in Phase10C and the
Phase10J dedicated staging mount. The original unacknowledged upload produced a
truncated launcher on the emulated UART despite passing a host-only PTY test.
The revised receiver accepts one base64 line at a time and verifies compressed
and expanded SHA256 identities before executing the launcher.

Original V8 mounts `/run` with `noexec`. Phase10J leaves those options in place
and mounts a new 64 MiB `rw,nosuid,nodev,exec` tmpfs at a unique directory under
`/run`. Only the approved ELF and its disposable relative outputs go there.
The guest therefore needs `mount` and root's existing mount capability; no OS
package installation, protected partition write or parent remount is part of the
procedure. Staging disappears on guest poweroff. A failed prerequisite is recorded
as BLOCKED and never treated as application execution.

The latest runner also waits for the newline terminating the entire workload
completion JSON before decoding it. Older versions could parse a partial record
containing braces inside the partition-inventory string, raise JSONDecodeError,
and force guest cleanup after the FSW had already reached its timeout. Use all
three resumed corrections together; preserve earlier attempts as diagnostics.
