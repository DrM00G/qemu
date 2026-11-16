# Phase 10H local event-ordering laboratory

AI-assisted local experiments only; no output is eligible for upstream QEMU
contributions. Read AGENTS.md and docs/devel/code-provenance.rst. Preserve the
uncommitted F.2/G work. No commit/push/reset/clean/stash, physical hardware,
original-media or host settings changes. Build with two jobs, one full guest at
a time, and fresh disposable regular-file virtual media only.

`STATUS.md` gives actual fresh outcomes; `NEXT-SESSION.md` is the handoff.
`EVENT-ORDERING-INVARIANTS.md` maps contracts to source and executable tests.
`TIMING-AND-CONCURRENCY-LIMITATIONS.md` separates controlled device tests,
software-service delay, SMP stress and physical timing.

## Build and focused tests

```sh
ninja -C build-arm64-phase1 -j2 qemu-system-aarch64 \
 tests/qtest/rp1-test tests/qtest/cm5io-test \
 tests/qtest/bcm2712-mip-test tests/qtest/bcm2712-sdhci-test
export QTEST_QEMU_BINARY="$PWD/build-arm64-phase1/qemu-system-aarch64"
build-arm64-phase1/tests/qtest/rp1-test
build-arm64-phase1/tests/qtest/cm5io-test
build-arm64-phase1/tests/qtest/bcm2712-mip-test
# SDHCI needs a fresh private directory:
mkdir /home/aweso/cm5-v8-lab/phase10h/FRESH-sdhci
CM5_PHASE8_IMAGE_DIR=/home/aweso/cm5-v8-lab/phase10h/FRESH-sdhci \
 build-arm64-phase1/tests/qtest/bcm2712-sdhci-test
python3 -m unittest discover -s experiments/cm5-phase10h -v
```

The new C cases are in `tests/qtest/rp1-test.c` (names prefixed `h-`), and the
native MSI test in `tests/qtest/cm5io-test.c` now asserts PERST cancellation of
masked PBA and an active serializer. Tests assert register values, FIFO contents,
RAM message sentinels and GIC pending state. No Linux guest is launched by them.

For a fresh repeat/trace run, choose unused private/public output paths:

```sh
python3 experiments/cm5-phase10h/ordering.py \
 --output /home/aweso/cm5-v8-lab/phase10h/FRESH-ordering \
 --sequences /home/aweso/cm5-v8-lab/phase10h/FRESH-sequences \
 --summary /home/aweso/cm5-v8-lab/phase10h/FRESH-ordering-summary.json
```

The harness runs fourteen selected tests twice; compares normalized device,
command/reply and combined event order; checks expected TX/RX, CS segments and
notification-attempt counts for boundary cases; and hashes output. One pipe
captures qtest requests, synchronous device traces and replies in execution
order. Only host elapsed timestamps and TAP/process chatter are removed.
An empty capture fails. Sequence directories must not already exist.
`ordering-results.json` and `sequences-validated/` are the final verified capture;
earlier normalized sequence directories are preserved privately under the session
`normalized-iterations/` archive. Earlier raw/failing captures stay private.

The separately selected `h-delayed-service` test withholds software RX reads
and RP1 IACK for24000 virtual ns. It needs no device timing property, is absent
from ordinary guest operation and leaves serialization running. This tests
controlled late software service, not delayed timer callback dispatch.

## Captured V8 integration

The existing G wrapper creates a new golden-backed overlay, selects original
BOOT kernel/initramfs, and runs unchanged native/verity/LOGS/strict-SPI oracles.
Raw output must remain private:

```sh
python3 experiments/cm5-phase10g/run.py --hz 10000 --diagnostics \
 --work /home/aweso/cm5-v8-lab/phase10h/FRESH-a-work \
 --output /home/aweso/cm5-v8-lab/phase10h/FRESH-a
python3 experiments/cm5-phase10g/run.py --hz 100000 --diagnostics \
 --execution-clock icount-1ns \
 --work /home/aweso/cm5-v8-lab/phase10h/FRESH-b-work \
 --output /home/aweso/cm5-v8-lab/phase10h/FRESH-b
# Schedule 1MHz only after the earlier gates pass, using fresh paths.
```

The new optional `--phase10h-smp-stress` flag wraps the native guest observer
with bounded guest workers on CPUs1/2/3 doing RAM hashing and read-only BAR reads.
Use a separate host-clock10k run and fresh paths. It enables cached observer
upload, records embedded worker source, and captures readiness, affinity,
iterations/digests and guest-monotonic intervals. This is default-off and
classifies competing software service; it changes no hardware clock or oracle.
No deterministic MTTCG or physical latency claim follows.
A full stress invocation, after the prior guest has stopped, is:

```sh
python3 experiments/cm5-phase10g/run.py --hz 10000 --diagnostics \
 --execution-clock host --phase10h-smp-stress --timeout 900 \
 --work /home/aweso/cm5-v8-lab/phase10h/FRESH-smp-work \
 --output /home/aweso/cm5-v8-lab/phase10h/FRESH-smp
```
The larger bound is a host wall-time budget, not a hardware clock change.
The exporter independently recomputes worker hashes from loop counts and checks
CPU affinity, progress and overlap in the guest-monotonic clock domain.

`summarize_guests.py --private-root PRIVATE_SESSION --output FRESH_JSON` exports
selected acceptance fields for the standard names baseline-a, baseline-b,
baseline-c and smp-stress without raw proprietary logs. Keep source/executable
manifests, actual argv and private guest observers with their original runs.
BOOT_ORDER0xf14 remains an unconfirmed fixture; generated lab runtime DT is an
explicit substitution; physical firmware/EEPROM instructions do not execute.

`COMPARISON.md`, `comparison-event.schema.json` and actual qtest
`comparison-events.jsonl` define the small future physical comparison envelope.
No physical measurements were collected.
