# Observed validation — 2026-11-12

This is partial Phase 4 work; real V8 integration is blocked by absent input.
No archive was found in the repository through depth three, or home through
depth two. Initial resources: 937 GiB free disk, about 7 GiB available RAM.

Final smoke command (exit 0):

```sh
python3 experiments/cm5-phase4/smoke.py --output /tmp/cm5-phase4-smoke-3
python3 experiments/cm5-phase4/report.py /tmp/cm5-phase4-smoke-3/result.json
```

Actual ARM64 TCG execution used two Cortex-A76 vCPUs, 512 MiB RAM, the existing
Phase 3 6.18.62 kernel, matching initramfs base and cross-compiler libc runtime.
Runtime page size was 16384. QEMU source HEAD recorded by the runner was
`784f3e1570d67cede6a01a393bb91994138e741e`; the pre-existing executable was not
rebuilt, so that HEAD is not a new build provenance assertion.

Passed: process startup/exit, dlopen(libm)/sqrt, deterministic 1 MiB memory
readback, 4096-byte file write/fsync/readback in RAM, missing-file ENOENT, and
three advancing one-second heartbeats. Linux PL011 `/dev/ttyAMA0` transmitted
`10 20 30 40`, host echoed the same bytes, and guest received/compared all four.
`serial.log`, `peripheral.jsonl`, command, result JSON, CSV and Markdown reside
in `/tmp/cm5-phase4-smoke-3/`. SPI/I2C/GPIO explicitly reported UNSUPPORTED.
This has no OS disk, systemd, verified storage or V8 userspace.

Earlier smoke-1 reached successful guest exit/poweroff but the host EOF loop
incorrectly waited until its timeout. That failed infrastructure run remains
preserved. The EOF selector handling was corrected; smoke-2 and smoke-3 exited
normally with PASS. Smoke-3 also corrects the misleading earlier test name
`logs_fsync_readback` to `file_fsync_readback` because its storage is RAM.

Host FSW pilot, exit 0, `/tmp/cm5-phase4-pilot/pilot.json`: reused Phase 3
injection on the public surrogate FSW partition, seed 7303. Changed offsets:
159895552, 235622400, 107544576; 4096 bytes per block, every byte XOR ff and
readback verified. Source SHA-256 before/after was
`6b783b903076adfebd0bcf32abed8a707f8230d02dbd2a8b234eafa55db58e72`.
Selected fraction was 0.00002288818359375 of all partition blocks (0.0022888%).
Guest detection, FEC configuration/correction, recovery and boot were NOT_TESTED.

Three synthetic inventory tests passed (regular-file enforcement, MBR/EBR
chain plus cycle rejection, malformed signature). Python compilation and strict
native/ARM64 C compilation passed. Existing Phase 1–3 files remain unchanged;
their full regressions were not rerun. No commit or push occurred.

| Capability | Implemented | Tested | Real V8 or surrogate | Physical fidelity |
|---|---|---|---|---|
| Read-only MBR/EBR inventory | Yes | Synthetic tests | Neither | File metadata only |
| Actual V8/systemd boot | No: missing archive | No | V8 absent | Unknown |
| Portable diagnostic subset | Yes | ARM64 initramfs | Public runtime | Linux APIs |
| JSON config/systemd template | Initial | Not in guest | Neither | Unvalidated |
| PL011 byte exchange | Yes, existing model | PASS | Diagnostic initramfs | UART register/driver path |
| SPI ioctl adapter | Yes | Compile only | Neither | No bound controller/slave |
| I2C/GPIO | Unsupported | No | Neither | None |
| Disposable fault pilot | Host subset | PASS | Public FSW image | Logical block XOR only |
| V8 verity/FEC integration | No | No | V8 absent | Unknown |
| JSON/CSV/Markdown reports | Preliminary | Smoke export | Diagnostic initramfs | Functional observations |

# Real V8 continuation — observed 2026-11-12 HST

The missing-input blocker above is resolved. The package was supplied at
`~/cm5-v8-lab/import/cm5-v8-reference/`. Source and golden files remain outside
Git. Available space before import was 933 GiB; approximately 917 GiB remains.
The compressed SHA-256 matched its supplied checksum:
`72a55fb788293513fb4d85c8f8f294453f4bd213bc83340f4f0a377b6d158b96`.
The decompressed image is exactly **15,634,268,160 bytes**. Its streamed import
SHA-256 and final read-only audit both equal
`e2fb1a85c2652838793e58f8b13ef908e2e4a4c4295e27297ce742287f69cb87`.

The MBR/EBR partitions were confirmed as FAT32 BOOT 512 MiB, ext4 OS 10 GiB,
extended container, ext4 FSW 512 MiB, LOGS 1 GiB, RECOVERY 2,736,782,848 bytes.
V8 `/etc/os-release` identifies Debian 13 (trixie), version 13.7. Original fstab
uses Pi PARTUUID `61a2cb94` for BOOT/OS plus filesystem UUIDs for FSW/LOGS/RECOVERY.
Original default target is graphical.target; the explicit simulator profile
requests multi-user.target. No desktop/GPU acceptance is claimed.

## Actual V8 boot and diagnostic

Authoritative local evidence:

* `~/cm5-v8-lab/runs/v8-verified-clean-1/v8-result.json` and `.csv`/`.md`.
* `~/cm5-v8-lab/runs/v8-fsw-fault-1/v8-result.json` and `.csv`/`.md`.
* Each run retains serial log, launch command, initramfs, disposable LOGS overlay,
  TCP/UDP byte trace, PL011 byte trace, and extracted simulator-created reports,
  mounts, kernel messages, production journal and failed-unit lists.

Both runs returned PASS for the defined profile. Actual PID 1 was systemd,
multi-user.target was active, runtime pages were 16384 bytes, and kernel release
was **6.18.62-cm5-surrogate-16k**. This is the existing Phase 3 Pi-source kernel,
Image SHA-256
`481d6d580d94e36ba26643e4e7f6e5f8cc1cae1a88c360cb6769136eaf4e87dc`.
It is neither production `6.18.50+rpt-rpi-2712` nor the imported experimental
unified 6.18.50 Image. Matching Phase 3 modules and initramfs userland were reused
with `v8-init.sh`; no cloud-init injection was used. The clean initramfs hash was
`2714ceae9ac1b3bd0f3bb2eff7304030384e73885a6cfe2888ee8516c0f38391`;
the fault run hash was
`c3fcb53d211ce384e952b1f1d9b9e254b1da3f1b33b010b33e87a4e1ef5a81f4`.

Confirmed mounts: OS ext4 readonly/norecovery under RAM OverlayFS; RAM tmpfs upper;
actual FSW readonly/norecovery through dm-verity; actual BOOT FAT readonly;
RECOVERY ext4 readonly/norecovery; LOGS ext4 writable through disposable QCOW2.
Root data is host-verified but is **not** a runtime dm-verity mount.

The dynamically linked mock executable used the captured V8 libc/libm, not a
substitute Ubuntu runtime. Systemd execution passed shared-library loading/sqrt,
1 MiB deterministic memory, actual OS file read, sealed-lower EROFS, 4096-byte
persistent LOGS write/fsync/readback, controlled ENOENT, TCP echo, UDP echo, and
ten advancing one-second heartbeats. PL011 TX/RX `10 20 30 40` passed in a separate
pre-systemd chroot execution using the same V8 libraries, avoiding console
reader contention. The systemd diagnostic leaves UART disabled. SPI/I2C/GPIO
remain UNSUPPORTED. Network endpoints and UART echo are synthetic devices.

`rpi-eeprom-update.service` remained failed and unmasked in both final runs.
Its journal reported an arithmetic-expression error involving `0x >> 23`.
The simulator does not supply the physical EEPROM/firmware interface. A profile
PASS is not all-production-unit PASS. Captured journals remain restricted local
evidence. Earlier runs also recorded cloud-init and swap-resize failures.

## Original metadata and one bounded real-image fault

The original RECOVERY `cm5-verity-v2` FSW hash and FEC files verified with host
veritysetup both with and without FEC. A separate read-only OS Merkle verifier
validated the entire original tree and all 2,621,440 captured OS blocks in one
scan, without copying the OS partition. Neither metadata set was regenerated.
Captured roots are not independently authenticated; this is not secure boot.

The real FSW data SHA-256 is
`8cac7148c9cc4cbcea5d3759cc09250cc11539da7a117cded493aea526589802`.
Both final guest runs read all 536,870,912 logical FSW bytes and matched it.
In the fault run, Phase 3's injector selected block **39037**, partition-relative
byte offset **159895552** (full-disk offset **11443621888**), seed 7303. All 4096
bytes were XORed with ff and overlay readback proved the change. This selects
1/131072 partition blocks: **0.000762939453125%** of FSW blocks, not a probability
of independent physical bit errors. The derived FSW golden hash was unchanged.

The fault guest's dmesg recorded:

```
device-mapper: verity-fec: 254:32: FEC 1372160: corrected 4096 errors
```

The complete logical digest matched, demonstrating that the damaged block was
actually encountered and corrected. V8 boot, mock functions, network and the
early UART transfer still passed. This is logical read recovery, not physical
writeback repair. No real-V8 OS fault or no-FEC guest control was run. Those
remain distinct from earlier Phase 3 public-surrogate controls.

## Preserved failures and verification limits

`v8-inspect-1` failed before switch-root due to missing proc/sys directories;
fixed in `v8-inspect-2`. `v8-boot-1` reached systemd and passed its original
subset, but an early host parser missed journal-prefixed markers and reported
INCONCLUSIVE. That original report remains intact. `v8-boot-2` had no-route
TCP/UDP failures and a UART timeout; `v8-boot-3` passed TCP/UDP after explicit
virtio network setup but UART RX still timed out during production console
activity. These failed functions remain recorded; moving the UART test before
systemd resolved contention without masking production services in final runs.

Final Python compilation, shell syntax, strict native/ARM64 C compilation,
three metadata safety/MBR/EBR tests and `git diff --check` passed. Phase 1–3 source
was unchanged; their full long-running regressions were not repeated. Later
observer additions for separate OverlayFS file and SHA artifacts are syntax
checked but are not evidence from these two final runs. No commit/push occurred.

| Capability | Implemented | Tested | Real V8 or surrogate | Physical fidelity |
|---|---|---|---|---|
| Full-image import/checksum/partitions | Yes | PASS | Real V8 | Captured bytes/layout |
| Systemd + 16 KiB + RAM root overlay | Yes | PASS | Real V8 | Linux userspace; virt hardware |
| Real FSW and disposable LOGS mounts | Yes | PASS | Real V8 | Filesystem semantics |
| Mock FSW core functions | Subset | PASS | Real V8 | Actual Linux APIs/libraries |
| TCP/UDP echo | Yes | PASS | Real V8 | VirtIO + user networking |
| PL011 transfer | Yes, early userspace | PASS | Real V8 | Real driver/model byte path |
| UART during systemd console activity | Attempted | FAIL, preserved | Real V8 | Console contention unresolved |
| Original OS/FSW metadata validation | Yes | PASS | Real V8 data | No independent root authentication |
| Runtime FSW dm-verity/FEC | Yes | PASS | Real V8 | Actual kernel verification |
| One FSW block logical recovery | Yes | PASS | Real V8 | Actual correction, no writeback |
| Runtime verified OS root | No | NOT_TESTED | Real V8 | Host integrity check only |
| SPI/I2C/GPIO integration | No | UNSUPPORTED | Neither | RP1 absent |
| Full CM5 firmware/RP1 fidelity | No | NOT_TESTED | Neither | Not modeled |
