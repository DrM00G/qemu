# Phase 2: direct boot and immutable lower-root preparation

Local research only, subject to [QEMU provenance policy](../../docs/devel/code-provenance.rst).
This extends the existing Phase 1 launcher; it does not add chipset models.
**The laboratory V8 OS and its 16 KiB kernel have not been booted.** Public
Ubuntu tests use a 4 KiB kernel. A public 10 GiB root-only fixture tests capacity
and layout, not V8 compatibility. Keep all laboratory originals and previous
experiment outputs unchanged.

## Reproduce public tests

From the checkout, keep using the Phase 1 build and its AAVMF Ubuntu baseline.
Additional host tools inspect/extract images without loop mounts or root access:

```sh
sudo apt-get install -y e2fsprogs cpio initramfs-tools-core zstd
./experiments/cm5-phase1/build.sh
python3 experiments/cm5-phase2/prepare-public.py
python3 experiments/cm5-phase2/test_preflight.py
python3 experiments/cm5-phase2/regress.py
```

The extractor creates a new `artifacts/public-inputs/` and refuses to overwrite
it. To prepare again, choose another `--output` and pass it to the regression
runner with `--public-inputs`. It expects the public Ubuntu cloud image's GPT,
ext4 `BOOT` and `cloudimg-rootfs` partitions; it is not a laboratory-image editor.
It extracts the matching public kernel, initramfs and config, decompresses the
kernel to `Image`, and creates a sparse **10 GiB raw ext4 root-only** copy. Only
that derived filesystem is edited: `/boot` and `/boot/efi` fstab entries are
removed because those partitions are absent, then the filesystem is checked
and enlarged offline. Source hashes and derived hashes are saved in
`manifest.json`. Intermediate raw disk/partition copies are retained and ignored.
Allow several GiB of actual storage in addition to the sparse 10 GiB fixture.

`regress.py --case uefi|direct|overlay|all` saves its own result directory and
returns zero only when all selected full-system boots pass. Cases are:

| Case | Boot path and root | Required evidence |
| --- | --- | --- |
| uefi | Original Ubuntu disk through AAVMF | Existing systemd/service checks plus writable root contract |
| direct | Extracted Image/initramfs, `/dev/vda1`, writable disposable disk | Same checks, actual 4096-byte pages, generated virt DTB |
| overlay | Extracted Image/initramfs, raw 10 GiB `/dev/vda`, read-only VirtIO block device | Writable OverlayFS `/`, read-only lower mount, EROFS on lower writes, file in upper only, all systemd checks |

All cases require systemd PID 1, active `multi-user.target`, successful test
service, zero failed units, valid completed cloud-init, functional tests,
HTTP report, normal poweroff and unchanged source hash. Each run keeps serial,
command, acceptance and guest JSON, along with overlay and firmware state.
`regression.json` points to authoritative per-boot `acceptance.json` files.
Runtime output remains excluded from Git. See [VALIDATION.md](VALIDATION.md)
for actually executed results, including any failures investigated.

## Launch controls

The original command remains the UEFI baseline:

```sh
./experiments/cm5-phase1/accept.sh
```

Direct boot bypasses UEFI. Supply a Linux ARM64 `Image` (plain or gzip), its
matching initramfs, and an explicit root selector:

```sh
./experiments/cm5-phase1/accept.sh \
  --kernel experiments/cm5-phase2/artifacts/public-inputs/Image \
  --initramfs experiments/cm5-phase2/artifacts/public-inputs/initrd \
  --kernel-config experiments/cm5-phase2/artifacts/public-inputs/kernel.config \
  --root-device /dev/vda1 --root-mode rw --expected-page-size 4096 --dump-dtb
```

`--root-device` can name a whole filesystem (`/dev/vda`), a partition
(`/dev/vda1`), `PARTUUID=...`, or an initramfs-resolved `UUID=...`. Filesystem
UUID/LABEL resolution generally needs initramfs tooling; without an initramfs,
use a kernel-supported selector and build every pre-root driver into the kernel.
Device numbering changes with attached disks/transports, so use stable selectors
after inspecting the real layout. The launcher never invents a root partition.

`--root-fstype` and `--root-flags` set `rootfstype=` and `rootflags=`. The default
`--append` is `console=ttyAMA0`; use it for additional boot parameters, including
`systemd.unit=multi-user.target`, production verity parameters or diagnostic
`break=` points supported by the chosen initramfs. `rootwait` and the selected
ro/rw policy are appended. Conflicting root selectors or explicit `ro`, `rw`,
`overlayroot=` in `--append` are rejected. `--earlycon` adds DT-derived early
console and `ignore_loglevel`. These direct-boot controls are rejected with UEFI
rather than being silently ignored; UEFI boot arguments belong to the guest's
bootloader configuration.

`--virtio-transport pci` is the baseline; `mmio` selects `virtio-*-device` and
requires `CONFIG_VIRTIO_MMIO`. PCI requires the generic PCI host and VirtIO PCI
drivers. Both expose block disks as `/dev/vd*`. The network MAC remains stable
for the supplied cloud-init network configuration. `--dump-dtb` saves QEMU's
generated `virt.dtb` and its dump log using the selected machine/devices/kernel.
No physical CM5 DTB or boot firmware is supplied.

`--disk-size 12G` is a minimum for writable disposable disks, not a shrink
request. `--disk-size keep` preserves geometry. Read-only modes never resize,
even if the default 8G minimum is larger than the source. Thus a 10 GiB input
stays at least 10 GiB. No code reformats laboratory inputs.

### Read-only versus OverlayFS

`--root-mode ro --no-provision` attaches the root disk read-only at QEMU's block
layer and requests a read-only root mount. This is a diagnostic launch, not
automated clean-boot acceptance. Ubuntu cloud-init cannot provision an entirely
read-only `/etc` and `/var`; the launcher refuses that combination. `ro` alone
on a writable disk would only request the initial mount policy and could later
be undone by systemd/fstab, which is why this mode also protects the block device.

`--root-mode overlay` selects **Ubuntu initramfs-tools overlayroot semantics**:
`overlayroot=tmpfs:recurse=1 overlayroot_cfgdisk=disabled`. The public initramfs
already has the hook and matching `overlay.ko`; arbitrary laboratory initramfs
implementations do not. The hook moves the lower root to `/media/root-ro`,
creates a tmpfs upper/work filesystem under `/media/root-rw`, mounts merged `/`,
and rewrites fstab in the writable view. Recursive overlays cover other fstab
mounts where supported. The lower disk remains read-only. The upper is volatile,
bounded by guest tmpfs/RAM limits, and is lost on poweroff; the QCOW2 disk overlay
is **not** an OverlayFS upper. Persistent upper storage is not implemented here.

```sh
./experiments/cm5-phase1/accept.sh \
  --disk experiments/cm5-phase2/artifacts/public-inputs/rootfs-10g.ext4 \
  --kernel experiments/cm5-phase2/artifacts/public-inputs/Image \
  --initramfs experiments/cm5-phase2/artifacts/public-inputs/initrd \
  --root-device /dev/vda --root-fstype ext4 --root-flags noload \
  --root-mode overlay --disk-size keep --expected-page-size 4096 --dump-dtb
```

Read-only ext4 can still need journal recovery; the public immutable-lower test
uses a clean filesystem plus `rootflags=noload` and `fsck.mode=skip`. Skipping
recovery on a dirty filesystem can expose inconsistent data. Do not apply
`noload` to other filesystem types or use it as a substitute for preparing a
consistent golden image. Repair only a disposable working copy. A production
verity-protected filesystem must retain its verification policy and metadata.

OverlayFS needs a writable upper supporting the required extended attributes
and valid directory types; upper and work directories must share a filesystem.
The mounted lower and upper/work mounts must survive switch-root. Creating the
overlay after systemd starts is too late for services requiring writable `/`.
The [kernel OverlayFS documentation](https://docs.kernel.org/filesystems/overlayfs.html)
describes these constraints.

## Laboratory kernel/initramfs checklist

There is no QEMU switch that turns a 4 KiB kernel into a 16 KiB kernel.
`--expected-page-size 16384` checks the ARM64 Image header before launching and
the runtime `SC_PAGE_SIZE` during provisioned acceptance. An unspecified header
page size fails an explicit expectation. Header agreement is a preflight check,
not evidence that the OS booted. See the [ARM64 boot protocol](https://docs.kernel.org/arch/arm64/booting.html).
`--kernel-config` records driver options and its hash; `initramfs-files.txt`
records archive contents when `lsinitramfs` is available. These diagnostics do
not prove module compatibility. Inspect actual dependencies and run a boot.

| Component | Required adjustment or validation |
| --- | --- |
| Kernel base | ARM64, `CONFIG_ARM64_16K_PAGES=y`, `CONFIG_ARCH_VIRT`, `CONFIG_OF`, `CONFIG_ARM_GIC`/`CONFIG_ARM_GIC_V3`, `CONFIG_ARM_ARCH_TIMER`, `CONFIG_ARM_PSCI_FW`, compatible physical address range |
| Console | `CONFIG_SERIAL_AMBA_PL011` and console support built in for early logs; `console=ttyAMA0`; `earlycon` for pre-userspace failures |
| Root disk | VirtIO core/block plus selected PCI host/PCI transport or MMIO transport; partition parser for GPT/MBR disks; actual root filesystem driver |
| Early userspace | `CONFIG_BLK_DEV_INITRD`, matching `CONFIG_RD_GZIP`/`CONFIG_RD_ZSTD` or other archive compression support, runnable ARM64 `/init`, shell/tools, device discovery/devtmpfs, root resolution tools |
| Modules | Built into kernel or included with dependencies in initramfs before root is needed; modules must match exact release/config/16 KiB kernel, not the public 4 KiB modules |
| Overlay | `CONFIG_OVERLAY_FS`, tmpfs and xattrs, mount/modprobe tools and an early root-overlay hook; upper/work lifetime and switch-root ordering |
| Network | VirtIO net, IPv4/DHCP userspace and a virt interface configuration; replace CM5 Ethernet-specific matches with simulator transport/MAC matches |
| Userspace | Validate executable/shared-library ELF segment alignment and mmap assumptions for 16 KiB pages, native modules and binaries; check all FSW dependencies later |
| systemd | Kernel features required by that systemd release (proc/sysfs/devtmpfs, tmpfs, cgroups, namespaces as configured), genuine init at `/sbin/init`, valid machine-id policy |

The kernel receives QEMU's generated virt DTB. CM5 firmware, BCM2712/RP1 DT
addresses, interrupts, clocks, mailbox services, SD/eMMC and PCI topology cannot
be carried across unchanged. Retain the production configuration separately;
build or provide a simulator kernel with these additional virt requirements.
Match its initramfs and `/lib/modules`, including separate `/usr` dependencies.

## Mount and service handoff

Before switching the laboratory filesystem, inspect `/etc/fstab`, initramfs
scripts, crypttab/verity setup, systemd mount units, generators and service
dependencies. Adjust a derived simulator profile, preserving originals:

* Change physical root names/UUIDs only after inspecting the supplied filesystem
  and partition map. A 10 GiB filesystem blob uses the whole VirtIO disk; a
  10 GiB disk image may contain several partitions.
* Remove or replace absent `/boot`, EFI, Raspberry Pi firmware and CM5 data
  mounts in the simulator view. Ensure `/usr` is available before switch-root.
  For a raw root-only image, absent boot-partition requirements can otherwise
  force emergency mode even after `/` mounts successfully.
* Establish writable `/run`, `/tmp`, `/var` and any required `/etc` state before
  their consumers start. Without a full-root overlay, use explicit tmpfs/bind
  mounts and an already-provisioned service configuration. Handle journals,
  machine-id, random seed, resolver state and application data deliberately.
* Ensure `systemd-remount-fs` and generated fstab units operate on merged root,
  not the immutable lower. Keep cloud-init or equivalent guest provisioning
  after the overlay is established and before acceptance services.
* Identify services requiring physical `/dev/mmcblk*`, GPIO, SPI, RP1, I2C,
  watchdog, RTC or board identity. In a documented simulator profile, separate
  hardware-dependent startup from baseline userspace. Do not clear failed units
  or globally mask dependencies to fabricate a clean production boot.
* Preserve verity/FEC root hashes, data/hash offsets, signing/boot arguments and
  initramfs mapping order when applicable. Construct the overlay above the
  verified mapping. Include device mapper, `CONFIG_DM_VERITY`, and
  `CONFIG_DM_VERITY_FEC` plus matching early userspace when required. The public
  fixture exercises neither verity nor FEC.

Example **diagnostic** laboratory launch once artifacts are available:

```sh
python3 experiments/cm5-phase1/launch.py --no-provision \
  --disk /path/to/v8-rootfs-10g.ext4 --kernel /path/to/Image-16k \
  --initramfs /path/to/matching-initramfs --kernel-config /path/to/kernel.config \
  --root-device /dev/vda --root-fstype ext4 --root-mode ro --disk-size keep \
  --expected-page-size 16384 --memory 4096 --cpus 4 --earlycon --dump-dtb \
  --append 'console=ttyAMA0 systemd.unit=multi-user.target' --timeout 1200
```

Choose rootflags and verification arguments from the real production format.
Use `--root-mode overlay` only after adapting and validating the laboratory
initramfs to the supported overlayroot contract, or integrate its native overlay
mechanism explicitly in the diagnostic boot path. Provisioned acceptance still
requires Python/cloud-init/systemd tooling from Phase 1; a non-cloud-init V8
image needs an equivalent guest test/report installation in a derived image.
`--no-provision` reports STOPPED on normal exit and never claims acceptance.

Bring the actual V8 disk/layout, 16 KiB kernel/config, matching initramfs/modules,
boot/verification metadata, mount/service definitions, FSW dependency inventory
and laboratory boot logs. SPI/RP1 and physical CM5 validation remain later work.
