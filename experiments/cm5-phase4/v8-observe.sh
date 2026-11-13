#!/bin/sh
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
. /run-cm5-network
OUT=/var/log/flight/cm5-evidence
mkdir -p "$OUT"
# Production journals are retained locally, never echoed wholesale.
uname -a > "$OUT/kernel.txt"
cat /proc/mounts > "$OUT/mounts.txt"
cat /proc/1/comm > "$OUT/pid1.txt"
getconf PAGESIZE > "$OUT/page-size.txt"
cat /etc/os-release > "$OUT/os-release.txt"
cp /etc/fstab.physical-cm5 "$OUT/fstab.physical-cm5"
find /mnt/recovery -maxdepth 3 -type f > "$OUT/recovery-files.txt"
mkdir -p "$OUT/recovery-metadata"
find /mnt/recovery -maxdepth 3 -name '*.json' -type f -exec cp '{}' "$OUT/recovery-metadata/" ';'
# Stop only the console reader for this explicitly configured UART test.
true # UART is exercised before production console readers start.
# Explicit QEMU user-network policy; never used on physical hardware.
for net in /sys/class/net/*; do
    [ "$(basename "$(readlink -f "$net/device/driver")")" = virtio_net ] || continue
    iface=$(basename "$net")
    nmcli device set "$iface" managed no 2>/dev/null || true
    ip link set "$iface" up
    ip address add 10.0.2.15/24 dev "$iface"
    ip route replace 10.0.2.2/32 dev "$iface"
done
ip address > "$OUT/ip-address.txt"
ip route > "$OUT/ip-route.txt"
if [ -b /dev/mapper/cm5-fsw ]; then
    /run-cm5-dmsetup table > "$OUT/dm-table.txt"
    sha256sum /dev/mapper/cm5-fsw > "$OUT/fsw-logical-sha256.txt"
    echo $? > "$OUT/fsw-scan-exit.txt"
    /run-cm5-dmsetup status > "$OUT/dm-status.txt"
fi
echo V8_HEALTH_BEGIN
echo V8_PID1=$(cat /proc/1/comm)
echo V8_PAGESIZE=$(getconf PAGESIZE)
echo V8_KERNEL=$(uname -r)
# Do not use the active serial console for data transfers while systemd owns it.
/run-cm5-diagnostic /var/log/flight/cm5-diagnostic-new.dat - - 10 > "$OUT/diagnostic.jsonl" 2> "$OUT/diagnostic.stderr"
echo V8_DIAGNOSTIC_EXIT=$?
sha256sum /var/log/flight/cm5-diagnostic-new.dat > "$OUT/logs-file-sha256.txt"
printf cm5-overlay-write-readback-v1 > /cm5-overlay-evidence
cmp /cm5-overlay-evidence /media/root-rw/upper/cm5-overlay-evidence
printf '%s\n' "$?" > "$OUT/overlay-write-exit.txt"
sha256sum /usr/lib/os-release /media/root-ro/usr/lib/os-release > "$OUT/os-file-sha256.txt"
cat "$OUT/diagnostic.jsonl"
# A oneshot observer must finish before multi-user.target can become active.
systemd-run --unit=cm5-final-observe --on-active=15 /bin/sh -c '
OUT=/var/log/flight/cm5-evidence
for i in $(seq 1 120); do
    systemctl is-active --quiet multi-user.target && break
    sleep 1
done
systemctl is-active multi-user.target > "$OUT/target.txt"
systemctl --failed --no-pager --plain > "$OUT/failed-units.txt"
journalctl -b --no-pager > "$OUT/journal.txt"
dmesg > "$OUT/dmesg.txt"
echo V8_TARGET=$(cat "$OUT/target.txt") >/dev/console
echo V8_FAILED_UNIT_NAMES >/dev/console
systemctl --failed --no-legend --plain | awk "{print \$1}" >/dev/console
echo V8_HEALTH_END >/dev/console
sync
systemctl poweroff
'
