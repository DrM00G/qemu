# Restricted real V8 reproduction

Local AI-assisted research only; not eligible for upstream QEMU submission.
No commit or push is performed. Keep all physical artifacts and output outside
this repository. Only regular image files are accepted; never use host devices.
The lab directory must be writable by the current user and have at least 20 GiB
free for the initial raw disk plus sparse derived partitions/evidence. Check
`df -h ~/cm5-v8-lab` and `free -h` first. Scripts use a restrictive creation umask.

```sh
python3 experiments/cm5-phase4/import-v8.py
python3 experiments/cm5-phase4/boot-v8.py --inspect \
  --output "$HOME/cm5-v8-lab/runs/inspect-new"
python3 experiments/cm5-phase4/prepare-v8-fsw.py
python3 experiments/cm5-phase4/check-os-metadata.py --full
python3 experiments/cm5-phase4/boot-v8.py \
  --verified-fsw "$HOME/cm5-v8-lab/derived-fsw" \
  --output "$HOME/cm5-v8-lab/runs/clean-new"
python3 experiments/cm5-phase4/export-v8.py "$HOME/cm5-v8-lab/runs/clean-new"
python3 experiments/cm5-phase4/v8-report.py "$HOME/cm5-v8-lab/runs/clean-new"
```

The import verifies the compressed checksum, decompresses once with a streamed
raw hash, enforces exact size and records MBR/EBR filesystem metadata. Subsequent
imports reuse the recorded golden image. Interrupted `.partial` output is retained;
inspect it and use a fresh output directory rather than overwriting it.
`prepare-v8-fsw.py` creates sparse FSW and RECOVERY partition views and extracts
only original FSW verification metadata. It checks that metadata with host
veritysetup both with and without FEC. `check-os-metadata.py --full` verifies
all original OS tree/data blocks directly from the full golden disk, without
creating another 10 GiB OS image. Neither tool regenerates metadata.

After clean acceptance, run exactly one bounded fault pilot:

```sh
python3 experiments/cm5-phase4/boot-v8.py \
  --verified-fsw "$HOME/cm5-v8-lab/derived-fsw" --fault \
  --output "$HOME/cm5-v8-lab/runs/fault-new"
python3 experiments/cm5-phase4/export-v8.py "$HOME/cm5-v8-lab/runs/fault-new"
python3 experiments/cm5-phase4/v8-report.py "$HOME/cm5-v8-lab/runs/fault-new"
python3 experiments/cm5-phase4/audit-v8.py
```

Read `v8-result.json` rather than just the launcher marker report. It checks
mount policies, PID 1, page size, target, diagnostic exit, complete FSW digest
and, for a fault run, kernel correction evidence. Production unit failures are
reported separately. A profile PASS does not mean all production services pass.
Export only after the guest exits: `export-v8.py` creates a sparse LOGS view and
extracts only `/cm5-evidence`. It never exports captured personal logs. Guest
journals are retained there as restricted local evidence, not printed wholesale.
Directories must be fresh for each boot/export. Original Phase 1–3 scripts remain
unchanged. The Phase 3 kernel/initramfs and cross compiler must already exist.

## Boot policy and instrumentation

QEMU virt, two Cortex-A76 TCG CPUs, 2 GiB guest RAM; DTB is QEMU-generated.
The existing Phase 3 Image and its matching modules are repacked with a custom
`/init`; no Pi DTB or firmware is used. The full golden disk is readonly `/dev/vda`.
A disposable full-disk QCOW2 `/dev/vdb` exposes writable LOGS partition 6 only.
Physical UUIDs are duplicated across these disks; the RAM fstab deliberately
uses explicit simulator devices rather than ambiguous UUID resolution.

OS `/dev/vda2` is mounted `ro,noload` beneath RAM OverlayFS. FSW is independently
mounted `ro,noload` at `/opt/fsw`; with `--verified-fsw`, a derived byte-identical
FSW data device and original hash/parity devices feed `/dev/mapper/cm5-fsw`.
BOOT and RECOVERY are readonly at `/boot/firmware` and `/mnt/recovery`.
LOGS is writable at `/var/log/flight`. Original fstab is retained in evidence;
all simulator fstab/service/executable changes exist only in the RAM upper.
Root integrity was checked offline; root is **not** mounted through dm-verity.

A standalone diagnostic input is built from `diagnostic.c`, copied into the RAM
root, and linked against V8's own libc/libm at execution. Before systemd starts,
a chroot execution uses the same V8 libraries and exercises PL011 without other
console readers. The host records and echoes `10 20 30 40`; guest comparison must
pass. This early UART result is separate from the systemd diagnostic, which
leaves UART disabled to avoid console contention. No production unit is masked
in the final profile. Earlier attempts at UART during systemd timed out and are
preserved as failures.

The observer is injected as a systemd oneshot and defers final target observation
to a transient timer/service, avoiding a dependency cycle with multi-user.target.
The original default graphical.target is recorded; this profile explicitly
requests multi-user.target. It does not validate the desktop stack. Cloud-init
is not used to inject or observe tests and remains free to run/fail as installed.
The simulator selects only a virtio_net interface and assigns a QEMU-user-network
address/route. Deterministic host loopback TCP/UDP endpoints echo four bytes.
This is an explicit simulated networking policy, not the captured physical NIC
configuration. No physical pin assignment is activated.

`--diagnostic /path/to/mock` accepts a separately built ARM64 ELF implementing
the same four-argument diagnostic CLI. This substitution option is syntax checked;
the recorded runs used the launcher's default build. The executable and any
required libraries must be compatible with V8. No proprietary executable is
required. To aggregate already completed final reports without rerunning guests:

```sh
python3 experiments/cm5-phase4/regress-v8.py \
  --output "$HOME/cm5-v8-lab/regression-new" \
  "$HOME/cm5-v8-lab/runs/clean-new" "$HOME/cm5-v8-lab/runs/fault-new"
```
