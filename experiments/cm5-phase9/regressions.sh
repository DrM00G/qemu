#!/bin/sh
# Existing preservation gates, no fault sweeps. All disk outputs stay in lab.
set -eu
out=experiments/cm5-phase9/artifacts
lab=/home/aweso/cm5-v8-lab/phase9
sh experiments/cm5-phase9/hardware.sh
sh experiments/cm5-phase7/check-regressions.sh "$lab/preserved-regressions" > "$out/preserved-regressions.log" 2>&1
for mode in spi v8; do
 python3 experiments/cm5-phase6/regress.py --platform cm5io-dev --mode "$mode" \
  --native-mip --mip-module experiments/cm5-phase7/artifacts/mip-module/irq-bcm2712-mip.ko \
  --native-emmc --mmc-module experiments/cm5-phase8/artifacts/mmc-module/sdhci-brcmstb.ko \
  --output "$lab/preserved-native-emmc-$mode" > "$out/preserved-native-emmc-$mode.log" 2>&1
done
python3 experiments/cm5-phase6/regress.py --platform cm5io-dev --mode v8 \
 --native-mip --mip-module experiments/cm5-phase7/artifacts/mip-module/irq-bcm2712-mip.ko \
 --native-emmc --mmc-module experiments/cm5-phase8/artifacts/mmc-module/sdhci-brcmstb.ko \
 --os-verity --output "$lab/preserved-os-verity" --timeout 300 > "$out/preserved-os-verity.log" 2>&1
