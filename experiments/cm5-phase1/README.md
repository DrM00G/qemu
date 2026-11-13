# ARM64 clean boot experiment (Phase 1)

Local research only. AI-assisted experiment output must not be submitted upstream;
see [QEMU provenance policy](../../docs/devel/code-provenance.rst). No QEMU device
or machine implementation is modified. Existing experiments and golden images
are inputs only.

See [VALIDATION.md](VALIDATION.md) for the executed boot results and retained
evidence, including two corrected clean-boot passes.
Phase 2 root policies, public regressions and laboratory handoff are documented
in [../cm5-phase2/README.md](../cm5-phase2/README.md).

Run these commands from the QEMU checkout in WSL Ubuntu on the x86-64 host:

```sh
sudo apt-get update
sudo apt-get install -y build-essential ninja-build pkg-config libglib2.0-dev \
  libpixman-1-dev zlib1g-dev python3-venv libslirp-dev \
  qemu-efi-aarch64 cloud-image-utils
./experiments/cm5-phase1/build.sh
./experiments/cm5-phase1/accept.sh
# Independent repeat: fresh disk, firmware variables and cloud-init instance ID
./experiments/cm5-phase1/accept.sh
```

The build uses this checkout, `aarch64-softmmu`, and unprivileged slirp networking.
Configure may fetch Python dependencies and subprojects; it needs network access.
`JOBS=4` is the default build parallelism; override it as needed. Build products
are in ignored `build-arm64-phase1/`. Runtime defaults: `virt`, Cortex-A76,
multithreaded TCG, 2 CPUs, 2048 MiB RAM, VirtIO block/network/RNG, and AAVMF UEFI.
Hardware acceleration is not used on this x86-64 host.

The default input is
`~/vm-images/ubuntu-arm64/ubuntu-24.04-server-cloudimg-arm64.img`.
The runner discovers its format with the locally built `qemu-img`, requires a
standalone base, and creates an 8 GiB QCOW2 overlay referencing its absolute path.
It never mounts or writes the base. SHA-256 values before and after must match.
Keep the base at the same path while retaining overlays. Increase `--disk-size`
for larger future images. Seeds and per-run AAVMF variables are disposable.

No password, authorized SSH key, or user account is provisioned. A fresh Ed25519
SSH host identity is generated inside each disposable guest, never in the repo.
Ubuntu cloud-init installs
two units in the overlay and queues their execution after cloud-final completes.
Provisioning requests no guest package downloads. The test unit verifies:

* A 1 MiB filesystem write, fsync, reopen/readback and removal.
* Loading libc, libm, libpthread and libdl, with actual libc/libm function calls.
* A deterministic integer calculation.
* Allocation and write/read checks across 32 MiB of memory.
* HTTP payload integrity over VirtIO networking to a host-local test server.
* The root mount contract: writable baseline root, or the Phase 2 read-only
  lower and writable OverlayFS upper checks when requested.

The report unit runs after the test unit, cloud-final and `multi-user.target`.
It verifies `/proc/1/comm` is `systemd`, the target is active, the test unit has
`Result=success` and `ExecMainStatus=0`, and there are no failed systemd units.
It also requires valid cloud-init schema and successful completed cloud-init
status, and records kernel identity, OS release and actual page size. It writes guest
`/var/lib/phase1/result.json`, emits `PHASE1_RESULT` to serial, POSTs structured
JSON to the host, and requests a normal poweroff. A failed test still allows
the reporter to run and describe the failure.

The host requires all functional and root-contract checks, target/PID 1/service evidence, an HTTP report
matching the unique run ID, a successful QEMU exit and Linux's `reboot: Power down`
serial evidence following guest poweroff,
and unchanged base hash for PASS. A serial banner or `init --version` cannot
satisfy acceptance. Result classes and exit codes:

| Status | Exit | Meaning |
| --- | --- | --- |
| PASS | 0 | Guest checks and clean shutdown succeeded |
| FAIL_GUEST | 1 | Guest reported failed checks, target or units |
| FAIL_BOOT | 1 | Boot/report timeout, missing report, or shutdown timeout |
| FAIL_INFRASTRUCTURE | 2 | Missing tools/files, QEMU invocation failure, changed base, interruption, or serial report without HTTP delivery |
| STOPPED | 0 | Unprovisioned guest exited; no acceptance claim |

Timeout without a report is an observed boot failure, not a diagnosis of its
cause: inspect serial for panic, emergency mode, cloud-init or network errors.
QEMU errors are captured in the same log. If the guest reports only on serial,
the run fails as a reporting infrastructure failure instead of passing.

Each attempt prints its directory under ignored `experiments/cm5-phase1/artifacts/`.
It retains `acceptance.json`, `serial.log`, `command.json`, `guest-result.json`
(when delivered), `http.log`, cloud-init inputs/seed, overlay and variable store.
`acceptance.json` is the authoritative host result; it includes the exact command,
image hashes, QEMU version, firmware hashes and elapsed time. Failed preparation
may not create all of these files. No artifacts are automatically removed.

Use `python3 experiments/cm5-phase1/launch.py --help` for all options. Example:

```sh
./experiments/cm5-phase1/accept.sh \
  --disk "$HOME/vm-images/ubuntu-arm64/ubuntu-24.04-server-cloudimg-arm64.img" \
  --memory 3072 --cpus 4 --timeout 1200 --shutdown-timeout 120
```

`--firmware-code` and `--firmware-vars` select installed AAVMF templates.
`--serial-log PATH` changes serial output; an existing path is refused to
preserve previous files. `--network user|none` and `--net-options` configure user
networking; acceptance requires user networking and the host probe. The server
binds only host loopback on a dynamically assigned port and uses no public
Internet. The default exposes no guest ports. Optional host forwarding belongs
in `--net-options hostfwd=tcp:127.0.0.1:2222-:22`; it does not create credentials.
Custom artifact or serial locations should be outside Git or explicitly ignored.

## Replacing Ubuntu at the laboratory

First reproduce the validated laboratory launch command and save its logs and
artifact hashes. Do not replace its golden media with these experiment outputs.
Provide the complete ARM64 OS/root disk (including its partition layout), kernel,
matching initramfs and modules, kernel config, boot arguments, and any firmware
or device-tree requirements. A CM5 kernel/DTB is not automatically compatible
with QEMU `virt`. A kernel supporting `virt`, GIC, PL011, VirtIO block/network,
the root filesystem and required init/systemd features is needed. Use QEMU's
generated virt DTB for that kernel instead of blindly supplying the CM5 DTB.

To try a compatible disk with UEFI but no Ubuntu provisioning:

```sh
python3 experiments/cm5-phase1/launch.py --no-provision \
  --disk /path/to/lab-os.img --timeout 1200
```

To boot a compatible lab kernel directly (bypasses UEFI):

```sh
python3 experiments/cm5-phase1/launch.py --no-provision \
  --disk /path/to/lab-os.img --kernel /path/to/Image \
  --initramfs /path/to/initramfs --root-device UUID=REPLACE --root-mode rw \
  --append 'console=ttyAMA0' \
  --memory 4096 --cpus 4 --timeout 1200
```

`--no-provision` deliberately makes no automated acceptance claim. For a lab OS
with compatible cloud-init, omit it to run the Ubuntu-style checks; otherwise
integrate the same service/report contract into a derived disposable lab image.
Additional FSW shared libraries must be specified and checked when available.

This milestone does not emulate BCM2712/RP1, SPI, FSW, sensor/electrical behavior,
real-time scheduling guarantees, or CM5 boot firmware. Ubuntu's kernel, page size,
drivers, and filesystem are not evidence of production 16 KiB pages, dm-verity,
FEC, or Raspberry Pi driver support. Bring the production kernel configuration,
verity/FEC metadata and boot chain details where applicable; do not bypass them
to claim production equivalence. Bring the FSW binaries/services/dependencies,
device-node/API inventory, bus/protocol specifications, and physical CM5 access
with repeatable reference traces. Use those to choose and validate the next
required interfaces after the clean userspace milestone.
