#!/bin/sh
# Reuse existing Phase 6/7 gates. All new disk overlays live in the lab.
set -eu
out=experiments/cm5-phase8/artifacts
lab=/home/aweso/cm5-v8-lab/phase8
if [ "${1:-}" = --archive-images ]; then
    python3 - <<'PY'
from pathlib import Path
root = Path('experiments/cm5-phase8/artifacts')
lab = Path.home() / 'cm5-v8-lab/phase8'
for archive in root.glob('*/initrd.gz'):
    if archive.is_symlink():
        continue
    target = lab / archive.parent.name / 'initrd.gz'
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise RuntimeError('refusing to replace ' + str(target))
    archive.rename(target)
    archive.symlink_to(target)
PY
    exit 0
fi
mkdir -p "$lab/qtest"
export QTEST_QEMU_BINARY=./build-arm64-phase1/qemu-system-aarch64
export CM5_PHASE8_IMAGE_DIR="$lab/qtest"
for test in rp1 cm5io bcm2712-mip bcm2712-sdhci; do
    ./build-arm64-phase1/tests/qtest/"$test"-test > "$out/qtest-$test-final.log" 2>&1
done
if [ "${1:-}" = --hardware-only ]; then exit 0; fi
sh experiments/cm5-phase7/check-regressions.sh "$lab/preserved-regressions" > "$out/preserved-regressions.log" 2>&1
for mode in spi v8; do
    python3 experiments/cm5-phase6/regress.py --platform cm5io-dev --mode "$mode" \
        --native-mip --mip-module experiments/cm5-phase7/artifacts/mip-module/irq-bcm2712-mip.ko \
        --native-emmc --mmc-module "$out/mmc-module/sdhci-brcmstb.ko" \
        --output "$out/native-$mode-final" --timeout 300 > "$out/native-$mode-final.log" 2>&1
done
sha256sum /home/aweso/cm5-v8-lab/golden/cm5-emmc-userarea.img > "$out/golden-after.sha256"
cmp "$out/golden-before.sha256" "$out/golden-after.sha256"
