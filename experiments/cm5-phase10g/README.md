# Phase 10G native SPI experiments

AI-assisted local research only, not for upstream contribution. Preserve the
Phase10F.2 dirty tree, captured kernel/initramfs, golden backing and roots2 data.
Use fresh names, regular disposable QCOW2 media and one full Linux guest at a
time. No physical hardware, host block devices, EEPROM/OTP/RPMB or system settings.
Build with `-j2`. [STATUS.md](STATUS.md) identifies actual completed outcomes;
[NEXT-SESSION.md](NEXT-SESSION.md) identifies any remaining blocker.

## Reproduce

From `/home/aweso/projects/qemu`:

```sh
ninja -C build-arm64-phase1 -j2 qemu-system-aarch64 \
 tests/qtest/rp1-test tests/qtest/cm5io-test \
 tests/qtest/bcm2712-mip-test tests/qtest/bcm2712-sdhci-test
export QTEST_QEMU_BINARY="$PWD/build-arm64-phase1/qemu-system-aarch64"
# SDHCI additionally requires CM5_PHASE8_IMAGE_DIR = a fresh private directory.
build-arm64-phase1/tests/qtest/rp1-test
build-arm64-phase1/tests/qtest/cm5io-test
python3 -m unittest discover -s experiments/cm5-phase10g -v
```

A full selected captured-kernel run uses existing accepted media and loaders:

```sh
python3 experiments/cm5-phase10g/run.py --hz 10000 \
 --work /home/aweso/cm5-v8-lab/phase10g/FRESH-control \
 --output experiments/cm5-phase10g/artifacts/FRESH-control
python3 experiments/cm5-phase10g/run.py --hz 100000 --diagnostics \
 --work /home/aweso/cm5-v8-lab/phase10g/FRESH-host100k \
 --output experiments/cm5-phase10g/artifacts/FRESH-host100k
```

The wrapper creates a fresh golden-backed image, records source snapshots and
exact commands, and invokes Phase10C with native PCIe/MIP/eMMC, original selected
kernel/initramfs, strict SPI and clean LOGS persistence. USB is declared absent;
`0xf14` is still an UNCONFIRMED EEPROM fixture. No EEPROM instructions execute.
Selected physical DT is validated/exported; runtime uses the generated lab DT.
No original host-kernel/initrd fallback, scan bypass or metadata replacement.

The separate `--execution-clock icount-1ns` profile selects QEMU's documented
`-accel tcg,thread=single -icount shift=0,align=off,sleep=off`. It retains four
guest CPUs, the requested BAUDR/SPI speed, FIFO depth, CS semantics and unchanged
strict oracle. The virtual clock counts aggregate guest instructions at one ns
per instruction and can advance over idle intervals. This is an explicit generic
execution-time convention, **not physical ARM cycle calibration**. Host-clock and
instruction-count results must be reported separately. Never describe a pass
in that profile as a hardware-only fix for default host-clock starvation.

`--execution-clock icount-adaptive` instead uses
`shift=auto,align=off,sleep=on`, retaining the same single-thread/SMP4 setup.
It lets QEMU adapt the instruction time scale against host time; it is still
not a physical CPU calibration. Both instruction profiles opt into
`--observer-upload-once`: public observer code is uploaded once to guest /run,
terminal editing/echo are disabled, and each short invocation must complete
before another is sent. This avoids repeated large interactive here-documents
and terminal cursor-query waits. The original default transport stays available.

To reproduce the passing fixed instruction-clock experiment, use fresh paths
and repeat independently (confirmation status is in STATUS.md):

```sh
python3 experiments/cm5-phase10g/run.py --hz 100000 --diagnostics \
 --execution-clock icount-1ns \
 --work /home/aweso/cm5-v8-lab/phase10g/FRESH-fixed100k \
 --output experiments/cm5-phase10g/artifacts/FRESH-fixed100k
```

Use independently initialized runs to confirm 100kHz before scheduling 1MHz.
A failed rate remains PARTIAL even when every byte is correct. No arbitrary
maximum physical SPI frequency is inferred from these experiments.

## Diagnostic contract

`--diagnostics` enables the independent Phase10G boundary/timer events alongside
the preserved old first-256 state capture and strict CS/byte trace. The new SSI
capture allows 65,536 selected events per cold reset and emits CAPTURE_EXHAUSTED
if consumed. It does not expire after the first 256 per-frame events.

Each boundary records virtual ns, SSI enable epoch, completed-word count,
monotonic CS segment identity, FIFO counts, raw IRQ and IMR. `state` encodes
SER[3:0], SSIENR bit4, active shifter/BUSY bit5, IRQ level bit6, TX threshold
bits8..13 and RX threshold bits16..21. Timer records contain actual arm-call
time, deadline, callback entry time, BAUDR and input clock. Completion before/
after and refill events are selected near empty FIFO; threshold/mask/IRQ/CS
transitions retain context. A completion-after record precedes the next internal
shifter load: its transient BUSY=false is not a guest-visible register read
between two callbacks. RP1 source/config/ACK/MSI-X mask/pending state and
MIP delivery have separate timestamped events. This metadata never delays a
transfer deliberately or changes queue capacity or payload handling.

The boundary and its paired timer record use separate clock samples. Their
difference is diagnostic execution time, not device latency. In host-clock TCG,
translation, BQL scheduling, tracing and host preemption contribute to the
observed virtual timeline. Callback-minus-deadline is scheduler/observer lateness,
not physical interrupt latency. Host runner wall seconds are a separate clock.

`correlate.py --run RUN --output FRESH_JSON` joins actual CS segments and byte
positions with submitted messages, then SSI epochs and device/IRQ events. It
retains event sequences for every failed message plus indices 3,32,35, even when
those particular indices pass. Concatenated-byte hash checks are diagnostic
only; they never merge segments or relax `trace_check.py`. Its four unit tests
ensure split messages remain failures and exhausted/empty captures cannot pass.

A deterministic real qtest trace can be collected with:

```sh
QTEST_QEMU_ARGS='-trace enable=dw_apb_ssi_boundary -trace enable=dw_apb_ssi_timer -trace enable=dw_apb_ssi_cs -trace enable=dw_apb_ssi_transfer -D PRIVATE_FRESH_TRACE' \
 build-arm64-phase1/tests/qtest/rp1-test -p /aarch64/rp1/drain-refill-deadline
```

This deliberately drains after the first word, refills at 8001ns and proves two
CS segments. It is an expected framing failure with correct bytes, not a Linux
pass. Reset/pending-MSI-X, FIFO/shift lead, masking/rearm and native clock tests
remain separate hardware tests.

## Hardware correction and scope

The clock input setter previously restarted a paused word from its beginning
and left a pending timer unchanged after a live input-rate change. Remaining
serializer clock work is now conserved across gates/dividers, with saturating
arithmetic and checked ceiling-to-ns scheduling. This models aggregate progress,
not electrical bit-edge phase or arbitrary physical clock-glitch behavior.
The strengthened native-clock qtest fails before the fix and passes afterward.
Ordinary unchanged-frequency transfers retain their existing scheduling.

Queued words are still scheduled from callback execution time. The diagnostic
shows callback lateness, but ordinary qtest clock stepping dispatches through
intermediate deadlines and does not reproduce it. The four-queued-word qtest is
therefore coverage, not a failing-before/passing-after deadline-drift test.
Any future continuous-deadline correction needs deterministic delayed-dispatch
coverage and an explicit MMIO ordering contract before being called validated.

`metrics.py` exports the small common envelope in `comparison-schema.json` from
actual virtual evidence. It reports requested and observed divider-derived rates
separately from unavailable measured SCLK. See
[PHYSICAL-VALIDATION-READINESS.md](PHYSICAL-VALIDATION-READINESS.md) for later
physical measurement/fixture requirements. No physical collector was implemented.
