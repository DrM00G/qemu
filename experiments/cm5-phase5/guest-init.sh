#!/bin/sh
export PATH=/bin:/sbin:/usr/bin:/usr/sbin
mkdir -p /proc /sys /dev /run
mount -t proc proc /proc
mount -t sysfs sysfs /sys
mount -t devtmpfs devtmpfs /dev
mount -t tmpfs tmpfs /run
echo PHASE5_GUEST_START
uname -a
for p in /sys/bus/pci/devices/*; do
    echo PCI_DEVICE=$p
    cat "$p/vendor" "$p/device" "$p/resource"
    readlink "$p/driver"
done
cat /proc/interrupts
insmod /spi-dw.ko
insmod /spi-dw-mmio.ko
insmod /spidev.ko
sleep 2
for p in /sys/bus/spi/devices/*; do
    echo SPI_DEVICE=$p
    echo spidev > "$p/driver_override"
    echo "${p##*/}" > /sys/bus/spi/drivers/spidev/bind
done
ls -l /dev/spidev*
for p in /dev/spidev*; do
    /spi-diagnostic "$p"
done
cat /proc/interrupts
dmesg | tail -100
echo PHASE5_GUEST_END
poweroff -f
