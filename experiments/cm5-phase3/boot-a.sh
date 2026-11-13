#!/usr/bin/env bash
set -euo pipefail
repo=$(cd -- "$(dirname -- "$0")/../.." && pwd)
kernel_root=${PHASE3_KERNEL_ROOT:-$HOME/cm5-phase3-kernel}
exec python3 "$repo/experiments/cm5-phase3/accept-a.py" --accept \
    --disk "$repo/experiments/cm5-phase2/artifacts/public-inputs/rootfs-10g.ext4" \
    --kernel "$kernel_root/build/arch/arm64/boot/Image" \
    --kernel-config "$kernel_root/build/.config" \
    --initramfs "$repo/experiments/cm5-phase3/artifacts/initramfs-16k/initrd.gz" \
    --root-device /dev/vda --root-fstype ext4 --root-flags noload \
    --root-mode overlay --disk-size keep --expected-page-size 16384 \
    --memory 2048 --cpus 2 --timeout 1200 --shutdown-timeout 180 \
    --artifacts "$repo/experiments/cm5-phase3/artifacts/milestone-a" "$@"
