#!/bin/sh
# Fresh lab overlays only. Reuses the established kernel/initramfs/runner.
set -eu
case_name=$1
run_name=$2
shift 2
case "$case_name" in
 reproduce|os0|no-fec) set -- --os-corrupt-block-zero "$@" ;;
 clean|os1|fsw0|trim) ;;
 *) echo 'unknown case' >&2; exit 2 ;;
esac
python3 experiments/cm5-phase6/regress.py --platform cm5io-dev --mode v8 \
 --native-mip --mip-module experiments/cm5-phase7/artifacts/mip-module/irq-bcm2712-mip.ko \
 --native-emmc --mmc-module experiments/cm5-phase8/artifacts/mmc-module/sdhci-brcmstb.ko \
 --os-verity --phase9-case "$case_name" --timeout 360 \
 --output "experiments/cm5-phase9/artifacts/$run_name" "$@"
