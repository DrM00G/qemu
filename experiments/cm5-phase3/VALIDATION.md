# Phase 3 observed validation record

This file records observations, not anticipated results. Work is local and no
commit or push is performed. The private V8 OS/kernel/FEC data/FSW are absent.

| Milestone | Final status | Actual validation |
| --- | --- | --- |
| A | PASS, implemented and tested | Native 16 KiB Pi-source kernel, Ubuntu systemd target and all Phase 2 health checks |
| B | PASS, implemented and tested | Real kernel OS/FSW verity/FEC maps, RAM OverlayFS, prescribed mount policies and sizes |
| C | PASS, implemented and tested | Proven XOR faults, kernel correction, complete logical digests, no-FEC EIO control |
| D | PASS, implemented and tested | Dynamically linked ARM64 service, seven real capability checks, advancing sustained heartbeats |
| E | PASS, implemented and tested | All five integrated matrix cases passed, JSON/CSV and exported logs retained |

Public kernel source: Raspberry Pi `rpi-6.18.y` commit
`62a56e350fcfd1c5e204c62dac4ea4ee205eb24e`, Linux 6.18.62.
Cross compiler: Ubuntu AArch64 GCC 15.2.0. QEMU remains the Phase 1 11.1.90 build
from source commit `9d7d057a558b9a1c232cea390b4481dd20d9c9ce`.
Host initial resources: approximately 7 GiB available RAM, 12 reported CPUs,
over 900 GiB free persistent disk. Kernel compilation uses four jobs.

Initial kernel configuration built successfully and requested 16 KiB pages,
VirtIO, ext4/OverlayFS, dm-verity/FEC, SHA-256 and Reed–Solomon encoder/decoder.
The conservative generic configuration pulled unrelated GPU drivers into the
first build; that build was interrupted and those large drivers were disabled.
The subsequent build completed. A RAM-backed `/tmp` workspace consumed about
3.6 GiB, so it was moved to `/home/aweso/cm5-phase3-kernel`, outside the repository.
Its old `/tmp/cm5-phase3-kernel` path is retained as a symlink for historical
logs. The scripts now default to persistent home-directory storage.

The first 16 KiB kernel boot reached real Ubuntu userspace but **did not pass**
Milestone A. Evidence is retained at
`artifacts/milestone-a/20261112-151449-eff7d392/`. Observations:

* Cloud-init could not mount the NoCloud seed and selected `DataSourceNone`.
* Kernel configuration had no `CONFIG_ISO9660_FS` for that ISO seed.
* SquashFS reported unsupported XZ compression; `CONFIG_SQUASHFS_XZ` was absent.
* `multipathd.service` failed; `CONFIG_DM_MULTIPATH` was absent.
* The attempt was deliberately interrupted after identifying those problems;
  the recorded host result is `FAIL_INFRASTRUCTURE` / operator interrupted.
  It is not clean systemd acceptance evidence.

Those Ubuntu support options were enabled in the next kernel revision. The
replacement matching initramfs and boot subsequently passed, as recorded below.

The unmodified public Ubuntu UEFI regression at
`artifacts/baseline-uefi/20261112-151232-7230eb85/` returned `FAIL_GUEST`:
all six health/root checks and cloud-init passed, but `snapd.seeded.service`
was failed. It ran concurrently with compilation and a large workspace move;
resource/timing pressure is a hypothesis, not a diagnosed cause. Extra guest
journal diagnostics were added in the Phase 3 wrapper for subsequent runs.
No failed units are masked or cleared to obtain PASS.

The host injection self-check first caught an incorrect readback command:
`qemu-img dd count` limits the input endpoint before applying skip. That attempt
was rejected, retained at `artifacts/injection-selfcheck/`, and did not count as
fault validation. After correcting the command, the 32 MiB disposable self-check
at `artifacts/injection-selfcheck-v2/` proved three complete 4096-byte XOR-FF
changes and unchanged source hash. This is host fault-injection proof only,
not guest FEC correction proof.

## Successful 16 KiB boot (Milestone A)

`boot-a.sh` completed PASS, exit 0, in 125.28 seconds at
`artifacts/milestone-a/20261112-153822-21c589f0/`. The guest reported
`SC_PAGE_SIZE=16384`, `6.18.62-cm5-surrogate-16k #2`, systemd PID 1,
`multi-user.target=active`, no failed units, successful cloud-init and all six
Phase 2 health/root checks. It powered off normally. The unchanged OS digest
was `ca882664d80a096cbcd25628383f18896da2e56868165815b5b3dc2036bddd8c`.
No failed units were cleared or masked.

The corrected build and its configuration were recorded at
`artifacts/kernel-record/record.json` with full config and compiler metadata:

| Artifact | SHA-256 |
| --- | --- |
| Public source archive | `9fbfda9a17c542cb30c52c98633427d60bdc2c8c4daf1f88ad64b654cd9c227a` |
| 16 KiB Image | `481d6d580d94e36ba26643e4e7f6e5f8cc1cae1a88c360cb6769136eaf4e87dc` |
| Kernel config | `3e9beb299795a9d27821329cb34023a5ad551674f5fd7740db9cf58f77e491a5` |
| Matching Ubuntu initramfs | `939910b8b3e5a08c51a894b4410492210d6ca376049e2ea8e3ad9ff7db362b64` |

All required built-in options in the record were observed enabled, including
16 KiB pages, VirtIO block/net, generic PCI, ext4/OverlayFS, verity/FEC, SHA-256,
Reed–Solomon encoder/decoder, ISO9660, multipath and SquashFS XZ.

The preserved unverified UEFI baseline passed on retry in 295.52 seconds at
`artifacts/baseline-uefi-retry/20261112-154417-80842cf4/`. It used the original
Ubuntu 4 KiB kernel, retained all six strict health checks and had no failed
units. Its source digest remained
`50e24e1fb79e89116e939d90aa7738f7af48c442fa1bc2510131e0b39c50348e`.
The earlier failure is retained; concurrency/resource pressure remains an
inference rather than a diagnosed cause of that individual snapd failure.

## Clean verified storage (Milestone B)

`prepare-storage.py` completed using cryptsetup/veritysetup 2.8.4, generated real
OS/FSW hash trees and FEC parity, and passed host verification. Host verification
was not counted as guest proof. `run.py --case clean` then completed PASS in
164.345 seconds at `artifacts/runs/20261112-154810-clean-a8061c3f/`.

The guest booted the OS from `/dev/mapper/v8-os`, mounted it read-only under the
RAM OverlayFS, mounted `/dev/mapper/v8-fsw` read-only at `/opt/fsw`, BOOT read-only
and LOGS writable. Live dm tables show SHA-256, 4096-byte data/hash blocks,
`use_fec_from_device`, and `fec_roots 2`. Both mappings reported status V.
The configured guest had four Cortex-A76 vCPUs and 8 GiB virtual RAM under TCG.

The storage service ran under systemd and read all 536870912 verified FSW bytes
in 12.93 seconds, matching golden digest
`44cfe23653d27b0d5e89d33deb6ccc5a53191406c65d14309452fe096d1322f9`.
All health checks, cloud-init, systemd target and normal poweroff passed; golden
hashes matched before/after. The OS full scan was not requested in this clean
case. No corruption was injected and no FEC correction activity was observed,
so this clean run is not correction evidence.

Pinned experimental roots for this initial storage generation:

* OS: `c0d02f3eabab794fec95c889cdab264c39c6f254d694fc71fb85cb1614c8e398`
* FSW: `711eba264e4e669cc8dce9b0ce37769246a3062b55d7283030f33936b06e3508`

Guest mapping tables/status, cmdline, fstab, mountinfo, sizes, complete config,
service journals, logical digests and source hashes are retained in the run
directory. These roots are pinned in an experimental initramfs; no secure
hardware boot chain is claimed.

## Controlled correction pilots (Milestone C)

The initial four-case storage series completed successfully before prototype
development began:

| Case and artifact directory under `artifacts/runs/` | Result | Boot success | Complete OS recovery | Complete FSW recovery | FEC activity | Elapsed |
| --- | --- | --- | --- | --- | --- | --- |
| `20261112-154810-clean-a8061c3f` | PASS | true | not attempted | true | false | 164.345 s |
| `20261112-155229-os-fec-cf421810` | PASS | true | true | true | true | 457.961 s |
| `20261112-160244-fsw-fec-92d20b26` | PASS | true | not attempted | true | true | 192.436 s |
| `20261112-160630-fsw-no-fec-fdf5a4ea` | PASS: detection control | true | not attempted | **false** | false | 149.967 s |

Each corrupted case used three full 4096-byte XOR-FF faults with seed 7303.
Readback proved all 4096 bytes in each block changed; the golden source hash
was unchanged. Recorded OS byte offsets were 4986658816, 7410016256 and
3311521792. Recorded FSW offsets were 159895552, 235622400 and 107544576.
The offsets were selected into distinct RS interleaving groups.

The OS case returned known-clean bytes for all selected logical reads. Kernel
logs explicitly reported `corrected 4096 errors` for every injected block;
the full scan caused a second correction/read of each still-damaged raw block.
All 10737418240 OS bytes were read through the verified mapper in 296.651 s and
the digest matched the golden OS digest above. Its complete FSW scan also
matched. This is actual kernel FEC correction plus complete logical recovery,
not merely a successful boot.

The FSW FEC case likewise returned known-clean bytes, recorded six correction
messages across targeted reads and the full scan, and matched the complete
536870912-byte FSW digest. These counts describe correction events, not six
distinct injected blocks or physical writeback repairs.

The no-FEC case created actual verity tables without FEC parameters. Every
selected corrupted read returned errno 5 / EIO, FSW dm status changed to C while
OS remained V, and the complete FSW read attempt stopped after 106954752 bytes
with `dd` exit 1. No correction messages were observed. Its scenario PASS means
that detection behaved correctly; it explicitly did **not** recover the data.

All cases retained normal systemd target/service acceptance, guest diagnostics,
normal poweroff and unchanged golden image hashes. Full OS recovery was checked
only in the OS FEC case; other OS metrics remain null instead of inferred true.

## Prototype and integrated regression progress

After all storage pilots passed, the synthetic C executable and its shared
library were cross-compiled with warnings treated as errors. `file` identified
both as ARM64 ELF, and readelf showed 64 KiB load-segment alignment. Required
glibc symbol versions were 2.17/2.34/2.38, compatible with the public Ubuntu
2.39 userspace; runtime validation is still required.

A new `storage-v2-prototype` generation includes the executable, dynamically
loaded FSW library and configuration. It reuses OS metadata only after checking
the prior OS and RECOVERY digests and re-verifying the OS tree; FSW metadata and
its pinned initramfs were regenerated. Older storage images remain unchanged.
## Prototype service (Milestone D)

The first prototype-equipped full-system run completed PASS, exit 0, in
165.246 seconds at `artifacts/runs/20261112-161912-clean-ad85e930/` using the
new storage generation. It retained real 16 KiB pages, verified OS/FSW mounts,
the complete FSW digest, all baseline health checks and normal poweroff.

The actual `prototype-fsw.service` MainPID was 883. Its report identified the
same PID and a systemd invocation. Configuration, real dynamic library loading,
deterministic computation, page-aware allocation/readback, Linux timerfd,
approved LOGS writes/readback and actual TCP/HTTP over VirtIO all passed.
The service produced 50 callbacks in 4.999935 seconds, continued running, and
was independently observed alive with the same PID across 15.449 seconds.
Its later heartbeat reached 176 at 17.599859 seconds. The observer checked
advancing heartbeat data as well as process liveness and function results.
Both SPI and mission UART adapters reported `unsupported`.

Prototype-generation FSW data digest:
`6b783b903076adfebd0bcf32abed8a707f8230d02dbd2a8b234eafa55db58e72`.
Its pinned verity root was
`e1d77815c7672249d7d12dc756566e9225616e385bb856c0e27b3a19b33cae1d`.
The OS root/data bytes stayed unchanged. BOOT and both matching pinned
initramfs variants were generated for the new FSW root.

Executable SHA-256:
`68e8bd868d9a105db0f9da78619839453ca9a538a0610d5b4da90a50ef1d30ec`.
FSW-resident library SHA-256:
`820be8ccafc045a6671ffafd74d5a77e03735daa4f62454704141d42b55c7d99`.
Build headers and symbol-version needs are retained in `artifacts/prototype-build/`.

## Integrated regression (Milestone E)

Executed command, exit 0:

```sh
python3 experiments/cm5-phase3/regress.py \
  --storage experiments/cm5-phase3/artifacts/storage-v2-prototype/manifest.json \
  --require-prototype
```

All five cases passed under
`artifacts/regression-20261112-162417-63d6471d/`. Authoritative aggregate
[JSON](artifacts/regression-20261112-162417-63d6471d/regression.json) and
[CSV](artifacts/regression-20261112-162417-63d6471d/regression.csv) link to the
unchanged child acceptance/result files.

| Case | Result | Elapsed | Prototype functions / sustained | Complete OS bytes | Complete FSW bytes | Kernel FEC activity |
| --- | --- | --- | --- | --- | --- | --- |
| Original Ubuntu UEFI | PASS | 279.930 s | not present | unverified baseline | not present | not present |
| Clean prototype storage | PASS | 170.495 s | true / true | not scanned | true | false |
| OS XOR faults + FEC | PASS | 434.790 s | true / true | true, 10 GiB | true, 512 MiB | true, six observed messages |
| FSW XOR faults + FEC | PASS | 163.849 s | true / true | not scanned | true, 512 MiB | true, six observed messages |
| FSW XOR faults, no FEC | PASS: detection | 159.527 s | true / true | not scanned | **false, EIO detected** | false |

The four surrogate cases all reported 16384-byte pages, healthy baseline
services, active multi-user target, actual verified mounts and normal poweroff.
The original UEFI case intentionally used its original 4096-byte Ubuntu kernel;
it was a separately named regression, never a fallback for the 16 KiB cases.
All recorded golden before/after hashes matched.

The OS-corrupted prototype case independently observed the same running
systemd-owned FSW process for 290.844 seconds while all 10 GiB recovered to the
golden digest. Kernel correction messages and targeted known-clean reads were
again required. Complete FSW recovery also passed in both FEC-corrupted cases.
In the no-FEC control, all selected corrupted reads returned EIO and complete
FSW recovery remained false even though unaffected application functions and
boot succeeded. This demonstrates why those outcomes are separate metrics.

`export-logs.py` was executed on all four completed prototype matrix runs.
Their `log-export/files/` directories contain actual heartbeat JSONL, final
prototype results/state and storage result files. Parsed heartbeat counts were
409 (clean), 3110 (OS/FEC), 400 (FSW/FEC) and 287 (no-FEC). Each file had one PID,
contiguous beat numbers starting at one and monotonically increasing elapsed
time; all exceeded the required 50 callbacks. Exported final daemon snapshots
can be later than the HTTP report because the service continues until shutdown.

A minor aggregate-only baseline diagnostic message was synchronized from its
authoritative child result after a formatting bug was fixed in the driver.
`regression.before-diagnostic-fix.json` retains the original aggregate; no status
or validation outcome changed, and all child logs/results were preserved.

Final Python compilation, shell syntax checks, strict C cross-compilation,
Phase 2 preflight tests (four passed), `git diff --check`, artifact-ignore checks,
source-hash checks and exported-heartbeat consistency checks passed. No QEMU
chipset source changed. About 937 GiB persistent disk remained free, and `/tmp`
was no longer occupied by the kernel workspace. No commit or push was made.

## Remaining limits and historical failures

There are no remaining failed acceptance cases in the final matrix. Earlier
failed/aborted attempts above remain part of the evidence and were not relabeled
as passed. The physical CM5, private V8 OS, experimental 6.18.50 kernel, actual
FEC layout and real flight software remain untested. This public kernel is
6.18.62; its configuration, userspace, service identities and security policies
are not asserted identical to production.

VirtIO disks/virt firmware interfaces replace eMMC/BCM2712/RP1. BOOT is an ext4
component container and boot uses host-pinned Image/initramfs plus generated
virt DTB. No authenticated hardware boot chain, physical I/O timing, full-RAM
stress, power-loss endurance, real-time guarantees, mission UART/SPI, sensors or
hardware watchdog behavior was validated. Root FEC recovery is logical read
correction, not physical writeback repair. See [LAB-MIGRATION.md](LAB-MIGRATION.md)
for the component replacement and physical comparison checklist.
