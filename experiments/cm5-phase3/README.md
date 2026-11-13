# Public CM5 flight-computer storage surrogate

Local research only; not an upstream contribution. Follow the QEMU
[provenance policy](../../docs/devel/code-provenance.rst). This uses QEMU `virt`,
Cortex-A76 ISA emulation and VirtIO. It is not a BCM2712/RP1 hardware emulator.
All input OS data is public Ubuntu; mission data and hardware interfaces are
synthetic or explicitly unsupported. No private V8 OS or flight software is
claimed to have booted. See [VALIDATION.md](VALIDATION.md) for observed results.

## Dependencies and kernel build

Use the working Phase 1 QEMU build and Phase 2 public-input preparation first.
On WSL Ubuntu:

```sh
sudo apt-get install -y gcc-aarch64-linux-gnu g++-aarch64-linux-gnu flex bison \
  libssl-dev libelf-dev bc dwarves cryptsetup-bin libcryptsetup-dev pkg-config \
  rsync cpio initramfs-tools-core zstd e2fsprogs cloud-image-utils
./experiments/cm5-phase1/build.sh
./experiments/cm5-phase3/build-kernel.sh
python3 experiments/cm5-phase3/prepare-initramfs.py
./experiments/cm5-phase3/boot-a.sh
```

The source is [Raspberry Pi Linux rpi-6.18.y](https://github.com/raspberrypi/linux/tree/rpi-6.18.y),
pinned to commit `62a56e350fcfd1c5e204c62dac4ea4ee205eb24e` (Linux 6.18.62).
The custom release suffix is `-cm5-surrogate-16k`. It differs from the physical
system's reported `6.18.50+rpt-rpi-2712`. This is a virt-compatible configuration
of public Pi sources, not a copy of the laboratory experimental configuration.

Kernel source/build/modules default to `$HOME/cm5-phase3-kernel`, outside this
repository. `PHASE3_KERNEL_ROOT` overrides the location; use persistent Linux
storage outside the checkout, not a small RAM-backed `/tmp` filesystem. The
initial build used `/tmp`, then moved to persistent storage when its RAM use
became significant. An alias at `/tmp/cm5-phase3-kernel` retained old log paths.
Allow several GiB of disk for source and object files and tens of minutes for
the conservative configuration at `JOBS=4`. Additional image assets are sparse
where practical. Check `free -h`, `df -h . /tmp`, and `nproc` before building.

The build checks resolved `.config` values for native 16 KiB pages, VirtIO block
and net, generic PCI host, ext4, OverlayFS, Device Mapper, verity/FEC, SHA-256 and
Reed–Solomon. Additional Ubuntu boot requirements include ISO9660/Joliet for
NoCloud seeds, SquashFS XZ for installed snaps and Device Mapper multipath.
No failed unit is hidden to claim acceptance. Source commit, compiler version,
kernel release and Image/config hashes are recorded in the build directory.

`prepare-initramfs.py` extracts a new copy of the public Ubuntu initramfs,
replaces its modules with the matching kernel's installed modules, and strips
debug sections from that disposable copy. Ubuntu's `copymods` hook exposes
these matching modules after switch-root. The original Ubuntu initramfs is
never rewritten. Output directories refuse overwrite; use `--output` for new
revisions and `boot-a.sh --initramfs /path/to/revision/initrd.gz` to test one.

Milestone A uses the original Phase 2 acceptance contract with extra journal
diagnostics. It requires actual `SC_PAGE_SIZE=16384`, systemd PID 1, active
`multi-user.target`, no failed units, all health/root checks, cloud-init and
normal guest poweroff. A 4 KiB fallback is refused.

## Synthetic storage preparation

After the kernel passes Milestone A:

```sh
python3 experiments/cm5-phase3/prepare-storage.py
python3 experiments/cm5-phase3/run.py --case clean
```

The script reads the Phase 2 public 10 GiB raw ext4 image without altering it.
It creates a fresh `artifacts/storage-v1/`; choose a new `--output` for another
generation. It operates on regular files and does not partition host devices.

| Volume | Size | Guest device | Policy |
| --- | --- | --- | --- |
| OS | 10 GiB | vda → `/dev/mapper/v8-os` | verity/FEC, ext4 ro+noload, RAM OverlayFS above it |
| FSW | 512 MiB | vdb → `/dev/mapper/v8-fsw` | verity/FEC, `/opt/fsw` ro+noload |
| LOGS | 1 GiB | vdc | `/var/log/flight` rw, no verity |
| RECOVERY | 2.5 GiB | vdd | read-only raw container for trees, parity and metadata |
| BOOT | 512 MiB | vde | `/boot` ro+noload, public kernel/config/initramfs components |

These are separate VirtIO disks, not an eMMC controller or physical CM5
partition table. They total 14.5 GiB; remaining space in a nominal 16 GiB layout
is not modelled. BOOT is an ext4 component container; actual boot uses the pinned
host kernel/initramfs directly and QEMU's generated virt device tree.

`veritysetup format` creates real SHA-256 Merkle trees and RS(255,253) parity
with 4096-byte data/hash blocks and `fec_roots=2`. The deterministic public salt
is recorded, along with roots, block counts, offsets, data digests and tool
version. A userspace verify is only a preparation check, not kernel/FEC proof.
RECOVERY reserves the first MiB for metadata, OS hashes at 1 MiB, OS parity at
128 MiB, FSW hashes at 256 MiB and FSW parity at 272 MiB. It is not mounted as
an ext4 filesystem. The embedded metadata does not include a self-referential
RECOVERY digest; the external manifest records the final complete image hash.

Two matching initramfs variants embed the pinned OS/FSW verity tables: FEC and
no-FEC. The local-top hook creates actual kernel dm-verity mappings before the
root mount and refuses to fall back to an unverified root. Trees and parity are
read from RECOVERY; the root digests come from the pinned initramfs, not from
untrusted guest recovery metadata. **This is an experimental trust anchor, not
an authenticated or secure hardware boot chain.** Keep the host manifest and
initramfs hashes with the experiment record. A checksum beside an image is not
secure boot.

OS/FSW/BOOT/RECOVERY devices are also read-only at QEMU's block layer. Writable
LOGS gets a per-run QCOW2 overlay. The RAM root uses Ubuntu `overlayroot`; its
upper/work directories live on tmpfs and disappear at poweroff. ext4 journal
replay is disabled on sealed filesystems, and no repairs are attempted on them.
Prepare clean filesystems before sealing. Root hashes do not replace the need
to retain production verity/FEC layout and boot parameters at the laboratory.

## Controlled corruption pilots

```sh
python3 experiments/cm5-phase3/run.py --case clean
python3 experiments/cm5-phase3/run.py --case os-fec --full-os-scan
python3 experiments/cm5-phase3/run.py --case fsw-fec
python3 experiments/cm5-phase3/run.py --case fsw-no-fec
```

The injector creates a new QCOW2 overlay and uses seed 7303 to select three
scattered full 4 KiB blocks. Distinct FEC interleaving groups keep this a bounded
roots=2 pilot. Each byte is XORed with `0xff`, then the overlay is read back and
all 4096 changed bytes are checked. Exact block numbers, byte offsets, original
and corrupted block digests and unchanged golden hashes are retained. Faults
are not written into golden data or metadata.

The guest explicitly reads the selected verified logical blocks. Correction
requires matching known-clean block digests **and actual kernel `FEC ...
corrected ... errors` messages**. Booting through unrelated intact blocks is
insufficient. The guest scans all 512 MiB of the verified FSW device; the OS
pilot's `--full-os-scan` additionally reads all 10 GiB. These scans use direct
block I/O and compare the complete SHA-256 digest with the golden file. A partial
scan, timeout or failed read never counts as complete recovery. The no-FEC case
requires EIO on corrupted block reads and failed complete FSW readback.

FEC corrects returned logical bytes; it does not repair the underlying immutable
disk. Keep the corrupted QCOW2 overlay and its injection record. To export a
recovered device later, copy the verified mapper to a separate sufficiently
large writable recovery destination and compare its complete digest. Do not
write back into the sealed lower or try to fit a 10 GiB export into 1 GiB LOGS.

Each run keeps serial, commands, cloud-init inputs, kernel config, mapping
tables/status, mountinfo, sizes, journals, targeted reads, whole-device digests,
FEC evidence and JSON/CSV metrics. Kernel boot, verified root mount, systemd
target, prototype state, essential functions, sustained operation and complete
logical recovery are independent fields. `null` means not observed or not
attempted. An expected no-FEC detection can pass its scenario while complete
FSW recovery remains false. Infrastructure failures and timeouts are separate
from observed guest failures. Stop a pilot series on an inconclusive run.

Default integrated launches request four Cortex-A76 vCPUs and 8 GiB virtual
guest RAM. This is lazy allocated under TCG, not preallocated 8 GiB host memory;
the WSL host has less physical RAM available than the physical CM5. The bounded
workload and direct I/O avoid a whole-device page-cache stress test. Override
`--memory`, `--cpus` and `--timeout` when necessary and record the change. This
does not validate real-time performance, full-memory stress, thermal behavior
or eMMC timing/endurance.

## Prototype FSW and integrated regression

Build the independent dynamically linked ARM64 program and its real FSW-resident
shared library, then seal a new storage generation. Do this after the initial
storage/FEC pilots have passed:

```sh
./experiments/cm5-phase3/build-fsw.sh
python3 experiments/cm5-phase3/prepare-storage.py \
  --output experiments/cm5-phase3/artifacts/storage-v2-prototype \
  --reuse-os-from experiments/cm5-phase3/artifacts/storage-v1/manifest.json \
  --fsw-binary experiments/cm5-phase3/artifacts/prototype-build/prototype-fsw
python3 experiments/cm5-phase3/run.py \
  --storage experiments/cm5-phase3/artifacts/storage-v2-prototype/manifest.json --case clean
python3 experiments/cm5-phase3/regress.py \
  --storage experiments/cm5-phase3/artifacts/storage-v2-prototype/manifest.json --require-prototype
```

`--reuse-os-from` checks the old OS digest, whole RECOVERY digest, format and salt,
extracts the previously generated tree/parity regions and performs a new OS tree
verification. It records reuse explicitly rather than fabricating a new format
operation. The FSW image, its metadata, BOOT and pinned initramfs are newly built.
Use another output directory for later revisions; old images are not rewritten.

The prototype runs `/opt/fsw/prototype-fsw` as `prototype-fsw.service`. It reads
configuration and `libflightmath.so` from verified FSW, dynamically loads that
library and system libm, computes known results, allocates/touches/verifies
memory using the runtime page size, and performs an actual Linux TCP/HTTP probe
over VirtIO to the deterministic host endpoint. It writes state, atomic JSON
results and timer-driven heartbeat JSONL only under `/var/log/flight`.
The timer uses `timerfd` with a 100 ms period. After at least 50 callbacks and
about five seconds, it reports the sustained interval and continues as a daemon
through the storage scans until normal systemd shutdown. No hard real-time
latency or flight correctness is claimed.

The guest observer requires the actual systemd MainPID to remain alive, verifies
that its report identifies that PID and systemd invocation, checks every
capability, and checks subsequent heartbeat progress with the same live process
after the scans. A live process alone cannot satisfy the function contract.
`interfaces.h` provides future SPI/UART call boundaries returning `-ENOSYS`;
both adapters are reported unsupported, never as emulated capability passes.

For independent diagnosis inside a prepared guest:

```sh
PHASE3_ENDPOINT=http://10.0.2.2:PORT/probe/RUN_ID /opt/fsw/prototype-fsw --once
```

Use the actual per-run host port and ID from that run's service definition.
This exits after the initial 50-callback interval; the normal systemd service
omits `--once`. Stop that normal service first to avoid sharing its output files.
It needs FSW and LOGS mounts and the deterministic endpoint.
Its `systemd_service` field truthfully differs when launched manually.

`regress.py` runs the original unverified Ubuntu UEFI baseline followed by clean,
OS/FEC, FSW/FEC and no-FEC boots with the selected storage generation. It records
JSON/CSV and links each row to its unmodified authoritative child result.
It stops immediately after a failed/inconclusive case. `--cases` selects a
unique bounded subset; `kernel-a` is available as another explicit baseline.
The OS FEC case performs a full OS scan by default; `--skip-full-os-scan` leaves
that recovery metric unobserved rather than calling it passed. `--require-prototype`
refuses storage without the real synthetic executable.

The LOGS QCOW2 overlay retains all heartbeat/state files after shutdown. To
export a completed run without a privileged mount:

```sh
python3 experiments/cm5-phase3/export-logs.py /path/to/completed/run-directory
```

This creates a new `log-export/` containing a sparse raw filesystem, extracted
files and a heartbeat summary. It refuses overwrite. The HTTP report is a
pre-shutdown snapshot; the exported daemon result can contain later heartbeats
written during normal service termination. Existing images remain unchanged.
Fresh builds can have different timestamps/UUIDs and therefore different Image
or filesystem hashes. Reproduce the pinned source/configuration and generate a
coherent new manifest; the observed hashes in VALIDATION identify this run's
actual artifacts rather than promising bit-identical outputs on every host.

## Laboratory migration

Replace public components one at a time while retaining these regression cases:

Use [LAB-MIGRATION.md](LAB-MIGRATION.md) as the component-by-component checklist.

* Replace the public kernel/config/modules/initramfs with the experimental
  16 KiB kernel, adding virt/GIC/PSCI/PL011/VirtIO support where necessary.
  Preserve its exact version and patches; recheck page size in the running guest.
* Replace the public 10 GiB ext4 root with an immutable copy of actual V8 data.
  Inspect filesystem/partition layout, fstab, `/usr`, initramfs and systemd
  dependencies before changing root selectors.
* Replace synthetic FSW with actual binaries, libraries, config and service
  definitions. Validate their 16 KiB ELF/mmap assumptions and real functions;
  a successful surrogate is not evidence that flight software works.
* Import trusted laboratory roots, salts, protected block counts, hash/FEC
  offsets and parity. Do not regenerate roots or disable verification merely
  to make an incompatible production image boot. Retain the 4 KiB block and
  roots=2 cases where they match the production experiment.
* Adjust BOOT and RECOVERY contents from authoritative laboratory metadata.
  Do not pass the CM5 physical DTB or firmware to `virt` unchanged, or mistake
  the experimental host-side trust anchor for the production boot chain.
* Validate LOGS permissions, persistence and service startup ordering. Keep
  verity below OverlayFS, establish writable state before consumers start, and
  separate hardware-dependent services explicitly in the simulator profile.
* Bring physical CM5 access, known-good boot logs, reference bus/API traces and
  FSW interface specifications. SPI, mission UART, RP1, sensors, watchdog
  hardware and physical timing remain unvalidated and are not faked here.
