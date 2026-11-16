#!/usr/bin/env python3
"""Append a labeled diagnostic layer; never change captured initramfs bytes."""
from pathlib import Path
import argparse
import hashlib
import json
import gzip
import subprocess
import sys

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO/'experiments/cm5-phase10b'))
from audit import cpio_entries

MONITOR = r'''#!/bin/sh
export PATH=/sbin:/bin:/usr/sbin:/usr/bin
while [ ! -r /sys/class/tty/ttyAMA0/dev ] || [ ! -d /run ]; do sleep 1; done
read -r dev < /sys/class/tty/ttyAMA0/dev
mknod /dev/phase10c-serial c ${dev%:*} ${dev#*:}
exec >/dev/phase10c-serial 2>&1
echo PHASE10C_DIAGNOSTIC_COPY_NOT_PRODUCTION=1
for i in $(seq 1 18); do
 echo PHASE10C_SNAPSHOT_BEGIN=$(cut -d' ' -f1 /proc/uptime)
 for role in os fsw; do
  dev=/dev/mapper/cm5_${role}_verified
  if [ -b "$dev" ]; then
   dmsetup status cm5_${role}_verified
   dmsetup table cm5_${role}_verified
   if [ ! -e /run/phase10c-$role-read ]; then
    echo PHASE10C_FIRST_VERIFIED_READ=$role
    dd if="$dev" bs=4096 count=1 2>/run/phase10c-dd-$role.log | sha256sum
    cat /run/phase10c-dd-$role.log
    touch /run/phase10c-$role-read
   fi
  fi
 done
 for f in /run/cm5-os-verified.log /run/cm5-fsw-verity.log /run/cm5-v8-late.log; do
  [ ! -r "$f" ] || tail -8 "$f"
 done
 cat /proc/diskstats
 for f in /proc/[0-9]*/comm; do
  read -r comm < "$f"
  case "$comm" in dd|veritysetup|dmsetup|init|systemd|mount)
   dir=${f%/comm}
   echo PHASE10C_PROCESS=$dir:$comm
   cat "$dir/stat" "$dir/wchan" "$dir/stack" 2>/dev/null
   ;;
  esac
 done
 grep -E 'dm-|mapper|mmcblk| / ' /proc/mounts
 echo PHASE10C_SNAPSHOT_END
 sleep 10
done
'''


def newc(name, body, ino, mode=0o100755, rmajor=0, rminor=0):
    fields = [ino, mode, 0, 0, 1, 0, len(body), 0, 0, rmajor, rminor, len(name)+1, 0]
    data = b'070701' + ''.join(f'{v:08x}' for v in fields).encode() + name.encode() + b'\0'
    data += bytes(-len(data) % 4)
    data += body
    data += bytes(-len(data) % 4)
    return data


def build(dest):
    source = Path('/home/aweso/cm5-phase10-private/physical-boot/boot-assets/initramfs_2712-osverified-v8')
    original = source.read_bytes()
    init = next(body for name, body in cpio_entries(original) if name == 'init')
    wrapper = b'#!/bin/sh\n/cm5-phase10c-monitor </init.physical &\nexec /init.physical "$@"\n'
    extra = newc('init.physical', init, 90001) + newc('init', wrapper, 90002)
    extra += newc('dev/null', b'', 90004, 0o020666, 1, 3)
    extra += newc('cm5-phase10c-monitor', MONITOR.encode(), 90003) + newc('TRAILER!!!', b'', 0)
    pos = 0
    while original[pos:pos+6] in (b'070701', b'070702'):
        header = original[pos:pos+110]
        length, namesize = int(header[54:62], 16), int(header[94:102], 16)
        pos = (((pos+110+namesize+3) & ~3)+length+3) & ~3
        while pos < len(original) and original[pos] == 0:
            pos += 1
    assert original[pos:pos+4] == b'\x28\xb5\x2f\xfd'
    payload = subprocess.run(['zstd', '-d', '-c'], input=original[pos:],
                             capture_output=True, check=True).stdout
    diagnostic = gzip.compress(original[:pos]+payload+bytes(-len(payload) % 4)+extra, mtime=0)
    dest.parent.mkdir(parents=True, exist_ok=False)
    with dest.open('xb') as f:
        f.write(diagnostic)
    return dict(source=str(source), source_sha256=hashlib.sha256(original).hexdigest(),
                diagnostic=str(dest), diagnostic_sha256=hashlib.sha256(dest.read_bytes()).hexdigest(),
                departure='gzip-repacked newc archives with init wrapper and read-only monitor; original hooks/root scan unchanged')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    print(json.dumps(build(a.output), indent=2))
