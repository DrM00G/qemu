#!/usr/bin/env python3
"""Embed pinned experimental verity tables in a disposable matching initramfs."""
import argparse
import importlib.util
import json
from pathlib import Path
import shlex
import subprocess

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('initrd_builder', HERE / 'prepare-initramfs.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def table(volume, data_device, fec=True):
    for field in ('root_hash', 'salt'):
        if len(volume[field]) != 64 or any(c not in '0123456789abcdef' for c in volume[field]):
            raise ValueError('Invalid pinned verity digest/salt')
    words = ['0', str(volume['data_blocks'] * 8), 'verity', '1', data_device, '/dev/vdd',
             '4096', '4096', str(volume['data_blocks']), str(volume['hash_start']),
             'sha256', volume['root_hash'], volume['salt']]
    if fec:
        words += ['8', 'use_fec_from_device', '/dev/vdd', 'fec_roots', '2',
                  'fec_blocks', str(volume['fec_blocks']), 'fec_start', str(volume['fec_start'])]
    return ' '.join(words)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--storage', type=Path, required=True)
    p.add_argument('--input', type=Path, default=HERE / 'artifacts/initramfs-16k/initrd.gz')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--no-fec', action='store_true')
    args = p.parse_args()
    manifest = json.loads(args.storage.read_text())
    args.output.mkdir(parents=True, exist_ok=False)
    unpacked = args.output / 'unpacked'
    subprocess.run(['unmkinitramfs', str(args.input), str(unpacked)], check=True)
    stage = unpacked / 'main' if (unpacked / 'main/init').exists() else unpacked
    tables = {'v8-os': table(manifest['volumes']['os'], '/dev/vda', not args.no_fec),
              'v8-fsw': table(manifest['volumes']['fsw'], '/dev/vdb', not args.no_fec)}
    hook = '''#!/bin/sh
case "$1" in prereqs) echo ''; exit 0;; esac
. /scripts/functions
[ ! -b /dev/mapper/v8-os ] || exit 0
for device in /dev/vda /dev/vdb /dev/vdd; do
    count=0
    while [ ! -b "$device" ]; do
        sleep 1
        count=$((count + 1))
        if [ "$count" -ge 60 ]; then
            echo "PHASE3_INIT_FAILURE missing $device" >/dev/console
            panic "Phase 3 required block device missing: $device"
            exit 1
        fi
    done
done
'''
    for name, value in tables.items():
        hook += ('dmsetup create --noudevsync --readonly ' + name + ' --table ' + shlex.quote(value) +
                 ' || { echo PHASE3_INIT_FAILURE ' + name + ' >/dev/console; panic "verity mapping failed"; exit 1; }\n')
    hook += '''dmsetup mknodes
mkdir -p /run/initramfs
dmsetup table > /run/initramfs/phase3-dm-table.txt
dmsetup status > /run/initramfs/phase3-dm-status.txt
echo PHASE3_MAPPING_READY >/dev/console
'''
    hook_path = stage / 'scripts/local-top/phase3-verity'
    hook_path.write_text(hook)
    hook_path.chmod(0o755)
    order = stage / 'scripts/local-top/ORDER'
    order.write_text(order.read_text() + '\n/scripts/local-top/phase3-verity "$@"\n')
    (stage / 'etc/phase3-pinned-tables.json').write_text(json.dumps(tables, indent=2) + '\n')
    archive = args.output / 'initrd.gz'
    builder.pack(stage, archive)
    (args.output / 'manifest.json').write_text(json.dumps({'fec': not args.no_fec,
        'tables': tables, 'initrd_sha256': builder.sha256(archive)}, indent=2) + '\n')
    print(archive)


if __name__ == '__main__':
    main()
