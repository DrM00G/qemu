# Phase 10I reproduction

Local AI-assisted experiments only; not for upstream submission. Preserve all
uncommitted F.2/G/H work. See STATUS.md for measured results and failed attempts,
GPIO-SOURCE-CONTRACT.md for the deliberately bounded hardware contract, and
HARDWARE-CAPABILITY-MATRIX.md/capability-manifest.json for the three-way census.
No physical device or proprietary FSW operation is authorized by these commands.

Run from the checkout, with the existing configured AArch64 build and private
captured environment. Build with two jobs:

```sh
ninja -C build-arm64-phase1 -j2 qemu-system-aarch64 qemu-img tests/qtest/rp1-test tests/qtest/cm5io-test tests/qtest/bcm2712-mip-test tests/qtest/bcm2712-sdhci-test
QTEST_QEMU_BINARY=build-arm64-phase1/qemu-system-aarch64 build-arm64-phase1/tests/qtest/rp1-test
QTEST_QEMU_BINARY=build-arm64-phase1/qemu-system-aarch64 build-arm64-phase1/tests/qtest/cm5io-test
QTEST_QEMU_BINARY=build-arm64-phase1/qemu-system-aarch64 build-arm64-phase1/tests/qtest/bcm2712-mip-test
SDHCI_TEST_DIR=$(mktemp -d /home/aweso/cm5-v8-lab/phase10i/sdhci-repro-XXXXXX)
CM5_PHASE8_IMAGE_DIR="$SDHCI_TEST_DIR" QTEST_QEMU_BINARY=build-arm64-phase1/qemu-system-aarch64 build-arm64-phase1/tests/qtest/bcm2712-sdhci-test
python3 -m unittest discover -s experiments/cm5-phase10i -p 'test_*.py' -v
```

Create a fresh private artifact root (never reuse an earlier directory):

```sh
I_RUN=/home/aweso/cm5-v8-lab/phase10i/repro-$(date -u +%Y%m%dT%H%M%SZ)
mkdir "$I_RUN"
python3 experiments/cm5-phase10i/dt_contract.py --work "$I_RUN/contract"
python3 experiments/cm5-phase10i/ordering_i.py --output "$I_RUN/ordering" --sequences "$I_RUN/sequences" --summary "$I_RUN/ordering.json"
```

The DT audit checks the selected physical reference hash, generated fallback,
exact one-node/three-property allowlist, GPIO bank0 IRQ, resource/range/valid-line
semantics, phandles, and a byte-identical disabled/no-op case. Negative unit tests
reject unsupported additions and mutations. It uses the F.2 libfdt tree reader;
it never installs the physical DT. Generated snapshots precede ARM boot fixups;
live-node property hashes and actual /sys/firmware/fdt hash are separate evidence.

Run these full Linux commands strictly sequentially. Each creates its own regular
qcow2 overlay, exports kernel/initramfs from that overlay's BOOT, uses unchanged
captured verification metadata, and shuts down before the next run:

```sh
python3 experiments/cm5-phase10g/run.py --hz 10000 --diagnostics --phase10i-gpio-lab --timeout 900 --work "$I_RUN/host10k-work" --output "$I_RUN/host10k"
python3 experiments/cm5-phase10i/evaluate.py --directory "$I_RUN/host10k" --contract-dir "$I_RUN/contract" --output "$I_RUN/host10k-gpio.json"
python3 experiments/cm5-phase10i/census.py --contract-dir "$I_RUN/contract" --run "$I_RUN/host10k/host10k-v8" --output "$I_RUN/capabilities.json" --markdown "$I_RUN/capabilities.md"
python3 experiments/cm5-phase10g/run.py --hz 100000 --execution-clock icount-1ns --diagnostics --phase10i-gpio-lab --timeout 900 --work "$I_RUN/fixed100k-work" --output "$I_RUN/fixed100k"
python3 experiments/cm5-phase10i/evaluate.py --directory "$I_RUN/fixed100k" --contract-dir "$I_RUN/contract" --output "$I_RUN/fixed100k-gpio.json"
```

Publish only reviewed normalized field selections after both completed runs:

```sh
python3 experiments/cm5-phase10i/results.py --directory "$I_RUN/host10k" --directory "$I_RUN/fixed100k" --contract-dir "$I_RUN/contract" --output "$I_RUN/integration-results.json"
```

The profile is default-off: machine `rp1-gpio-lab=on` requires native PCIe.
The runner flag enables it and installs the public observer in disposable guest
RAM. Do not run guest_gpio.py directly on the host or physical CM5. It requests
GPIO ownership and toggles outputs; it is a functional stimulus, not a read-only
census. The original builtin pinctrl-rp1 driver supplies the cdev API. The wrapper
records all chip aliases and deduplicates them by device identity, then validates
reserved-line rejection, exclusive ownership, both values and edge interrupts.

Keep raw observer/QOM/mtree/kernel/trace/LOGS/image data private. Publish reviewed
normalized results only. See test-results.json and ordering-results.json for
focused-suite outcomes and sequences-final/ for complete normalized qtest events.
H's delayed-service scenario is retained; no new arbitrary timing knob was added.
Fixed instruction time is not physical CPU calibration or deterministic MTTCG.
The four-CPU guest is not, by itself, a concurrent FSW stress test. Phase H's
reported SMP stress remains historical unless explicitly rerun and labeled.
