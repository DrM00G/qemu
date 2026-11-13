#!/bin/sh
# Build the public driver unchanged against the existing 16KiB kernel.
set -eu
src=/home/aweso/cm5-phase3-kernel/linux-62a56e350fcfd1c5e204c62dac4ea4ee205eb24e
build=/home/aweso/cm5-phase3-kernel/build
test "$#" = 1
mkdir "$1"
out=$(realpath "$1")
for name in sdhci-brcmstb.c sdhci.h sdhci-pltfm.h sdhci-cqhci.h cqhci.h; do
    cp "$src/drivers/mmc/host/$name" "$out/"
done
printf '%s\n' 'obj-m += sdhci-brcmstb.o' > "$out/Makefile"
make -C "$build" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- M="$out" modules
cmp "$src/drivers/mmc/host/sdhci-brcmstb.c" "$out/sdhci-brcmstb.c"
