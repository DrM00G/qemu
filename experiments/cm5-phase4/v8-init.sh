#!/bin/sh
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
mkdir -p /dev /proc /sys /run
mount -t devtmpfs devtmpfs /dev
mount -t proc proc /proc
mount -t sysfs sysfs /sys
mount -t tmpfs tmpfs /run
exec </dev/console >/dev/console 2>&1
fail() { echo V8_INIT_FAILURE="$*"; sleep 5; poweroff -f; }
for i in $(seq 1 60); do [ -b /dev/vda7 ] && break; sleep 1; done
mkdir -p /lower /ram /newroot
mount -t ext4 -o ro,noload /dev/vda2 /lower || fail root_mount
if grep -q 'v8.inspect=1' /proc/cmdline; then
    echo V8_INSPECTION_BEGIN
    for f in etc/os-release etc/fstab etc/crypttab; do
        echo V8_CONFIG_FILE=$f
        [ ! -f /lower/$f ] || cat /lower/$f
    done
    echo V8_DEFAULT_TARGET
    readlink /lower/etc/systemd/system/default.target
    echo V8_PRODUCTION_UNIT_NAMES
    find /lower/etc/systemd/system -maxdepth 2 -type l | sed 's|/lower||'
    mkdir -p /recovery
    mount -t ext4 -o ro,noload /dev/vda7 /recovery && {
        echo V8_RECOVERY_TOPLEVEL
        ls -l /recovery
        find /recovery -maxdepth 3 -type f | sed "s|/recovery||"
        for f in /recovery/os-verity-v1/README.txt /recovery/cm5-verity-v2/README.txt /recovery/cm5-verity-v2/os/os.roothash /recovery/cm5-verity-v2/fsw/fsw.roothash; do
            echo V8_RECOVERY_METADATA=$f
            cat "$f"
        done
    }
    echo V8_INSPECTION_END
    poweroff -f
fi
modprobe overlay || fail overlay_module
mount -t tmpfs -o size=768m tmpfs /ram || fail ram
mkdir -p /ram/upper /ram/work
mount -t overlay overlay -o lowerdir=/lower,upperdir=/ram/upper,workdir=/ram/work /newroot || fail overlay
mkdir -p /newroot/media/root-ro /newroot/media/root-rw /newroot/opt/fsw /newroot/var/log/flight /newroot/boot/firmware
mount --move /lower /newroot/media/root-ro || fail move_lower
mount --move /ram /newroot/media/root-rw || fail move_upper
FSW_DEVICE=/dev/vda5
if [ -f /cm5-fsw-map ]; then
    sh /cm5-fsw-map || fail fsw_verity_map
    FSW_DEVICE=/dev/mapper/cm5-fsw
fi
mount -t ext4 -o ro,noload "$FSW_DEVICE" /newroot/opt/fsw || fail fsw_mount
mkdir -p /newroot/mnt/recovery
mount -t ext4 -o ro,noload /dev/vda7 /newroot/mnt/recovery || fail recovery_mount
modprobe vfat
mount -t vfat -o ro /dev/vda1 /newroot/boot/firmware || fail boot_mount
mount -t ext4 /dev/vdb6 /newroot/var/log/flight || fail logs_mount
# Only this RAM view changes; retain the physical fstab for local review.
cp /newroot/etc/fstab /newroot/etc/fstab.physical-cm5
cat > /newroot/etc/fstab <<EOF
overlay / overlay defaults 0 0
/dev/vda1 /boot/firmware vfat ro 0 0
/dev/vda7 /mnt/recovery ext4 ro,noload 0 0
$FSW_DEVICE /opt/fsw ext4 ro,noload 0 0
/dev/vdb6 /var/log/flight ext4 defaults 0 0
EOF
cp /usr/sbin/dmsetup /newroot/run-cm5-dmsetup
cp /cm5-network /newroot/run-cm5-network
cp /cm5-diagnostic /newroot/run-cm5-diagnostic
cp /cm5-observe /newroot/run-cm5-observe
chmod 755 /newroot/run-cm5-diagnostic /newroot/run-cm5-observe
cat > /newroot/etc/systemd/system/cm5-observe.service <<'EOF'
[Unit]
Description=Local CM5 V8 observation
After=local-fs.target
[Service]
Type=oneshot
ExecStart=/run-cm5-observe
TimeoutStartSec=240
StandardOutput=journal+console
StandardError=journal+console
[Install]
WantedBy=multi-user.target
EOF
mkdir -p /newroot/etc/systemd/system/multi-user.target.wants
ln -s ../cm5-observe.service /newroot/etc/systemd/system/multi-user.target.wants/cm5-observe.service
for path in dev proc sys run; do
    mkdir -p /newroot/$path
    mount --move /$path /newroot/$path || fail move_$path
done
# Execute with V8's own dynamic loader before production console readers start.
mkdir -p /newroot/var/log/flight/cm5-evidence
chroot /newroot /run-cm5-diagnostic /var/log/flight/cm5-uart-preinit-new.dat /dev/ttyAMA0 - 1 > /newroot/var/log/flight/cm5-evidence/uart-preinit.jsonl 2>&1
echo V8_PREINIT_UART_DIAGNOSTIC_EXIT=$?
cat /newroot/var/log/flight/cm5-evidence/uart-preinit.jsonl
echo V8_SWITCH_ROOT
exec switch_root /newroot /sbin/init
