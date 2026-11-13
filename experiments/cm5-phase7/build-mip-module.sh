#!/bin/sh
# Compile the unchanged public driver against the preserved matching kernel.
set -eu
if [ "$#" -ne 1 ]; then echo "usage: $0 FRESH_MODULE_OUTPUT_DIRECTORY" >&2; exit 2; fi
src=/home/aweso/cm5-phase3-kernel/linux-62a56e350fcfd1c5e204c62dac4ea4ee205eb24e
build=/home/aweso/cm5-phase3-kernel/build
mkdir -p "$1"
out=$(realpath "$1")
if [ -e "$out/irq-bcm2712-mip.c" ]; then echo 'refusing to replace source' >&2; exit 1; fi
cp "$src/drivers/irqchip/irq-bcm2712-mip.c" "$out/"
printf '%s\n' 'obj-m += irq-bcm2712-mip.o' 'ccflags-y += -DDEBUG' > "$out/Makefile"
make -C "$build" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- M="$out" modules
cmp "$src/drivers/irqchip/irq-bcm2712-mip.c" "$out/irq-bcm2712-mip.c"
