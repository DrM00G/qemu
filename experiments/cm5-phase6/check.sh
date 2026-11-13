#!/bin/sh
# Local research regression gate: real kernels and userspace, no fault sweeps.
set -eu
if [ "$#" -ne 1 ]; then
    echo "usage: $0 FRESH_OUTPUT_DIRECTORY" >&2
    exit 2
fi
out=$1
mkdir "$out"
QTEST_QEMU_BINARY=./build-arm64-phase1/qemu-system-aarch64 \
    ./build-arm64-phase1/tests/qtest/rp1-test > "$out/qtest-rp1.log" 2>&1
QTEST_QEMU_BINARY=./build-arm64-phase1/qemu-system-aarch64 \
    ./build-arm64-phase1/tests/qtest/cm5io-test > "$out/qtest-cm5io.log" 2>&1
for platform in virt cm5io-dev; do
    for mode in spi v8; do
        python3 experiments/cm5-phase6/regress.py --platform "$platform" \
            --mode "$mode" --output "$out/$platform-$mode"
    done
done
