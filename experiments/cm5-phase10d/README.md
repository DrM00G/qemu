# Phase 10D: captured-kernel logical FEC recovery

AI-assisted local experiments only, not for upstream contribution under QEMU's
code-provenance policy. All commands run on the local WSL computer, working
directory `/home/aweso/projects/qemu`. No physical CM5 operation, host block
device, EEPROM access, golden write or metadata resealing is involved.

## Reproduction

Choose fresh names. Output directories must not already exist. Inputs are the
unchanged captured physical 6.18.50 kernel/initramfs and original golden user
area. Disk writes target fresh QCOW2 overlays outside the checkout, under
`/home/aweso/cm5-v8-lab/phase10c/OUTPUT_BASENAME`; only derived JSON/logs enter
ignored `artifacts/`. Read-only block/LOGS exports stay in that private lab.

```sh
ninja -C build-arm64-phase1 -j 8 qemu-system-aarch64 qemu-img qemu-io \
 tests/qtest/rp1-test tests/qtest/cm5io-test tests/qtest/bcm2712-mip-test \
 tests/qtest/bcm2712-sdhci-test tests/qtest/qos-test

python3 -m unittest discover -s experiments/cm5-phase10d -v
python3 -m unittest discover -s experiments/cm5-phase10a -v
python3 experiments/cm5-phase10a/matrix.py \
 --output experiments/cm5-phase10d/artifacts/synthetic-repro01

# Serial schedule, with CLEAN and OS0 gates before later guest cases:
python3 experiments/cm5-phase10d/matrix.py \
 --output experiments/cm5-phase10d/artifacts/matrix-repro01

# Individual case; choices clean, os0, os-far, fsw0, no-fec:
python3 experiments/cm5-phase10c/run.py --recovery-case os0 \
 --dma --batch --profile native --debug-shell --poweroff-after-validation \
 --timeout 420 --output experiments/cm5-phase10d/artifacts/os0-repro01

python3 experiments/cm5-phase10a/controls.py \
 --output experiments/cm5-phase10d/artifacts/phase9-repro01
```

For the no-FEC case use a 90-second bound; no full root scan or userspace is
attempted after the deliberately rejected read. Full successful original boots
retain the entire forty-chunk verified OS scan. The 420-second bound comes from
Phase 10C measured progress; increasing it alone establishes nothing.

Run the focused hardware tests (19 tests), with a new fixture directory:

```sh
mkdir -p experiments/cm5-phase10d/artifacts/qtests-repro01/images
export QTEST_QEMU_BINARY="$PWD/build-arm64-phase1/qemu-system-aarch64"
export CM5_PHASE8_IMAGE_DIR="$PWD/experiments/cm5-phase10d/artifacts/qtests-repro01/images"
for name in rp1 cm5io bcm2712-mip bcm2712-sdhci; do
 build-arm64-phase1/tests/qtest/$name-test \
  > experiments/cm5-phase10d/artifacts/qtests-repro01/$name.log 2>&1
done
build-arm64-phase1/tests/qtest/qos-test -p \
 /aarch64/xlnx-zcu102/generic-sdhci/sdhci/sdhci-tests/registers
build-arm64-phase1/tests/qtest/qos-test -p \
 /aarch64/virt/generic-pcihost/pci-bus-generic/pci-bus/sdhci-pci/sdhci/sdhci-tests/registers
```

Aggregate completed results to another fresh directory:

```sh
python3 experiments/cm5-phase10d/collect.py --output \
 experiments/cm5-phase10d/artifacts/report-repro01 --runs \
 experiments/cm5-phase10d/artifacts/matrix-repro01/matrix-repro01-clean \
 experiments/cm5-phase10d/artifacts/matrix-repro01/matrix-repro01-os0 \
 experiments/cm5-phase10d/artifacts/matrix-repro01/matrix-repro01-os-far \
 experiments/cm5-phase10d/artifacts/matrix-repro01/matrix-repro01-fsw0 \
 experiments/cm5-phase10d/artifacts/matrix-repro01/matrix-repro01-no-fec
```

`collect.py` needs the locally available Python jsonschema package. Schema
acceptance is a record-format check, not an experimental success criterion.
A runner exit zero only means collection finished: inspect `recovery-result.json`.
The sequential matrix stops if an expected outcome is not proven.

## Faults and recovery gates

Every injected block is replaced by exactly 4096 repetitions of byte `0x5a`.
Golden, pre-injection, post-injection and post-guest checksums are distinct.
QCOW2 backing chain and pre-guest allocation extents are recorded before QEMU
starts. No QEMU/card cache can contain pre-injection bytes from a previous run.

| Case | Partition | Data block | Absolute guest byte offset |
| --- | --- | ---: | ---: |
| CLEAN | OS p2, observed only | 0 | 545259520 |
| OS0 / NO-FEC | OS p2 | 0 | 545259520 |
| OS-FAR | OS p2 | 262144 (1 GiB into OS) | 1619001344 |
| FSW0 | FSW p5 | 0 | 11283726336 |

The public observer runs in guest RAM through stock systemd's debug UART shell.
It uses the captured OS Python and libc, not a replacement executable. It reads
the raw partition and mapper using aligned `O_DIRECT`/`preadv`, bypassing their
block page caches. No `check_at_most_once` option is added. The observer receives geometry, not golden data/digests. The mapper's returned
digest must equal golden while raw still equals the injected pattern. The kernel
must independently log correction for the correct device and interleaved RS byte base.
The log's error count is neither a physical error rate nor a distinct-fault count.

Both roots2 tables, both valid statuses, verified mounts, systemd PID 1,
independently active multi-user twice at least 20 guest seconds apart, library
and LOGS readback, normal poweroff and host-side LOGS persistence are required.
A missing correction message or failed direct read is not PASS_RECOVERED.
Recovery does not heal the backing block: its raw fault digest must persist.

The kernel logs the interleaver base `rsb`, not the absolute target offset.
For the captured OS, rounds = ceil(2642083 / 253) = 10444; the logged base for
block262144 is `(262144 % 10444)*4096 = 4276224`. This formula is source-backed
and corroborated by the captured module's division/remainder instructions and
actual kernel messages. Different blocks can share a base, so it is combined
with the controlled single fault, raw mismatch and explicit verified target
read. OS-FAR additionally requires correction before the verified root mount.

A retained OS-FAR evaluator mistake is corrected without rerunning the guest:
`python3 experiments/cm5-phase10d/recheck.py --run OLD_RUN --output NEW_REPORT`.
This creates separate provenance, original-evaluation and rechecked results;
it never overwrites the raw run or changes a fault.
Uncompleted/timeout evidence remains INCONCLUSIVE. Captured p5 has no executable;
FSW access is a verified block and filesystem read, not an application claim.

## Separate no-FEC diagnostic

Only this negative control changes the RAM initramfs, writing a separate gzip
archive. The original captured archive remains byte-for-byte unchanged. All
archive entries except `scripts/local-top/cm5-fsw-verity` retain their content.
That hook retains original RECOVERY/loop setup and FSW roots2. It removes OS FEC
options and replaces the FEC assertion/scan/handoff with a bounded block0 read,
error/table/status collection, explicit root refusal and forced poweroff.
The production full scan is never bypassed in a successful original-profile boot.
Original root hashes, hash trees and parity remain unchanged in every profile.
The diagnostic is not described as original production boot or recovered OS.

## Write attribution and limits

Harness fault allocations exist before the guest. Post-exit new allocations
must lie within LOGS, and the entire fault-containing QCOW2 cluster must have
no net guest content change. This distinguishes fault bytes from guest output;
it is not a trace proving the absence of transient same-value writes. The
LOGS test file is exported after normal shutdown and compared independently
without filesystem mounting or journal replay.

This is logical emulated corruption and software dm-verity/FEC behavior, not
physical eMMC ECC/FTL, wear, radiation, power-loss or performance measurement.
BOOT firmware remains bypassed by direct `-kernel`; Phase 10A stays separate.
Native RP1 remains disconnected; GPEX/6.18.62 controls remain the fallback.
`result.schema.json` can record future FEC root counts and distribution kinds,
but this campaign tests only captured roots2 and the labeled roots0 control.
Other configurations require separately approved matching metadata and new runs.
