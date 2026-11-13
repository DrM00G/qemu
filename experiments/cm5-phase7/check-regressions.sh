#!/bin/sh
# Existing fallback gates plus native MIP; fresh outputs, no corruption sweeps.
set -eu
if [ "$#" -ne 1 ]; then echo "usage: $0 FRESH_OUTPUT_DIRECTORY" >&2; exit 2; fi
out=$1
mkdir "$out"
QTEST_QEMU_BINARY=./build-arm64-phase1/qemu-system-aarch64 \
 ./build-arm64-phase1/tests/qtest/bcm2712-mip-test > "$out/qtest-mip.log" 2>&1
sh experiments/cm5-phase6/check.sh "$out/fallbacks"
module=experiments/cm5-phase7/artifacts/mip-module/irq-bcm2712-mip.ko
for mode in spi v8; do
 python3 experiments/cm5-phase6/regress.py --platform cm5io-dev --mode "$mode" \
  --native-mip --mip-module "$module" --output "$out/native-$mode"
done
