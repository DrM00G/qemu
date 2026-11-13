# Phase 2 executed public-image validation

Executed 2026-11-12 on the existing x86-64 WSL2 environment using the Phase 1
QEMU 11.1.90 binaries from source commit
`9d7d057a558b9a1c232cea390b4481dd20d9c9ce`. No QEMU C/device/machine source
was changed or rebuilt for Phase 2. This remains a local research experiment.

**The laboratory V8 OS, its production kernel and its 16 KiB page configuration
have not been booted or validated.**

| Public boot | Result | Elapsed time | Evidence |
| --- | --- | --- | --- |
| Ubuntu AAVMF UEFI, updated root checks | PASS, exit 0 | 285.86 s | [acceptance](artifacts/regress-20261112-143844-ed880ca7/uefi/20261112-143845-703c0d0f/acceptance.json) |
| Ubuntu direct Image/initramfs, partitioned disk `/dev/vda1` | PASS, exit 0 | 299.80 s | [acceptance](../cm5-phase1/artifacts/20261112-143256-aba30075/acceptance.json) |
| Ubuntu direct Image/initramfs, 10 GiB raw ext4 `/dev/vda`, immutable lower + tmpfs OverlayFS upper | PASS, exit 0 | 258.32 s | [acceptance](artifacts/regress-20261112-143618-78a447c3/overlay/20261112-143618-7775c427/acceptance.json) |

UEFI and overlay cases were executed through `regress.py --case uefi` and
`regress.py --case overlay`. The direct case was executed with
`../cm5-phase1/accept.sh --kernel artifacts/public/Image --initramfs artifacts/public/initrd
--kernel-config artifacts/public/kernel.config --root-device /dev/vda1
--expected-page-size 4096 --dump-dtb --timeout 900` from this directory.
Its manually extracted public inputs have the same hashes as the reproducible
`prepare-public.py` outputs. `regress.py --case direct` automates this case with
the latter paths. The complete matrix was not run in a single `--case all`
invocation; the three boot paths above were each executed separately.

All three guest reports show Ubuntu 24.04.5 LTS ARM64, kernel
`6.8.0-147-generic`, real systemd PID 1, active `multi-user.target`, no failed
units, successful test service, valid cloud-init schemas and completed cloud-init
without errors. All six functional/root-contract checks passed. Each guest
powered off normally with Linux `reboot: Power down` and QEMU exit 0.

The public Image header and runtime both report **4096-byte pages**. The
direct-boot artifacts include `virt.dtb`, DTB-dump log, initramfs file listing,
kernel/config/initramfs hashes and selected driver configuration. Guest results
also include `/proc/cmdline`, mountinfo and block-device layout/read-only state.

The OverlayFS [guest result](artifacts/regress-20261112-143618-78a447c3/overlay/20261112-143618-7775c427/guest-result.json)
records:

* Source virtual size `10737418240` bytes (10 GiB), preserved without resize.
* `/sys/block/vda/ro = 1`.
* `/media/root-ro`: `/dev/vda`, ext4, `ro,relatime,norecovery`.
* `/`: overlay, writable; upper at `/media/root-rw/overlay`, work directory on
  the same writable tmpfs.
* A lower-root write rejected with EROFS; a merged-root file found in the upper
  and absent from the lower, followed by cleanup.

The UEFI guest independently records writable ext4 `/dev/vda1` and block
read-only flag 0, demonstrating that the baseline policy was retained.

Original cloud-image SHA-256, before and after extraction and all applicable
boot attempts:

```text
50e24e1fb79e89116e939d90aa7738f7af48c442fa1bc2510131e0b39c50348e
```

Derived 10 GiB root-only fixture SHA-256, before and after its boot:

```text
ca882664d80a096cbcd25628383f18896da2e56868165815b5b3dc2036bddd8c
```

`prepare-public.py` finished PASS with matching original-image hashes. Its
[manifest](artifacts/public-inputs/manifest.json), filesystem check/resize logs
and original/adjusted fstab are retained. It edits only the derived public copy.

Additional checks:

* A real public 4 KiB Image with `--expected-page-size 16384` was refused before
  QEMU launch: `FAIL_INFRASTRUCTURE`, exit 2, unchanged original hash. Evidence:
  `artifacts/negative-page-size/20261112-143625-9e62b2c1/acceptance.json`.
* Four preflight unit tests passed: absent/ambiguous root and policy rejection,
  read-only overlay argument construction, ARM64/gzip header granule decoding
  and invalid header rejection, and preservation of quoted extra arguments.
  Synthetic 16 KiB headers in these tests are not boot evidence.
* Python compilation, `git diff --check` and generated-artifact ignore checks
  passed. The original Phase 1 UEFI pre-change run also passed and was retained
  at `../cm5-phase1/artifacts/20261112-143009-688a688e`.

Remaining limits: no laboratory V8 artifacts, real 16 KiB kernel boot,
dm-verity/FEC, production service dependencies or physical CM5 behavior were
tested. Pure read-only root without an overlay is a diagnostic launch option;
it has not demonstrated a clean Ubuntu systemd boot. Persistent OverlayFS upper
storage is not implemented. The configurable MMIO transport was not boot-tested;
all successful cases above used VirtIO PCI. No SPI/RP1 models were added.
