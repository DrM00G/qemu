#!/bin/sh
set -eu
out=experiments/cm5-phase9/artifacts
export QTEST_QEMU_BINARY=./build-arm64-phase1/qemu-system-aarch64
export CM5_PHASE8_IMAGE_DIR=/home/aweso/cm5-v8-lab/phase9/qtest
for name in rp1 cm5io bcm2712-mip bcm2712-sdhci; do
 ./build-arm64-phase1/tests/qtest/"$name"-test > "$out/qtest-$name-final.log" 2>&1
done
