#!/usr/bin/env python3
"""Extract a public Ubuntu cloud image without mounting or changing the source.

Also derive a disposable 10 GiB ext4 root-only fixture; never use on lab media.
Local research only, not intended for upstream submission.
"""
import argparse
import gzip
import json
from pathlib import Path
import re
import subprocess
import sys
import struct

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'cm5-phase1'))
from launch import sha256


def run(*args, allowed=(0,)):
    result = subprocess.run([str(a) for a in args], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if result.returncode not in allowed:
        raise RuntimeError(f'{args[0]} exited {result.returncode}: {result.stdout}')
    return result.stdout


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--disk', type=Path, default=Path.home() / 'vm-images/ubuntu-arm64/ubuntu-24.04-server-cloudimg-arm64.img')
    p.add_argument('--output', type=Path, default=Path(__file__).resolve().parent / 'artifacts/public-inputs')
    p.add_argument('--qemu-img', type=Path, default=Path(__file__).resolve().parents[2] / 'build-arm64-phase1/qemu-img')
    args = p.parse_args()
    source = args.disk.resolve(strict=True)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    before = sha256(source)
    manifest = {'source': str(source), 'source_sha256_before': before, 'status': 'FAIL'}
    try:
        raw = output / 'disk.raw'
        run(args.qemu_img, 'convert', '-O', 'raw', source, raw)
        partitions = {}
        with raw.open('rb') as stream:
            stream.seek(512)
            header = stream.read(92)
            if header[:8] != b'EFI PART':
                raise RuntimeError('This public-image extractor expects a GPT Ubuntu cloud disk')
            table, count, size = struct.unpack_from('<QII', header, 72)
            if count > 1024 or size < 128 or size > 4096:
                raise RuntimeError('Invalid GPT entry bounds')
            for n in range(count):
                stream.seek(table * 512 + n * size)
                entry = stream.read(size)
                if entry[:16] == bytes(16):
                    continue
                start, end = struct.unpack_from('<QQ', entry, 32)
                stream.seek(start * 512 + 1024)
                sb = stream.read(256)
                if sb[56:58] != b'\x53\xef':
                    continue
                label = sb[120:136].rstrip(b'\0').decode()
                partitions[label] = {'number': n + 1, 'offset': start * 512, 'bytes': (end - start + 1) * 512}
        manifest['partitions'] = partitions
        def extract(label, destination):
            part = partitions[label]
            run('dd', f'if={raw}', f'of={destination}', 'bs=4M', 'iflag=skip_bytes,count_bytes',
                f'skip={part["offset"]}', f'count={part["bytes"]}', 'conv=sparse', 'status=none')
        boot = output / 'boot.ext4'
        extract('BOOT', boot)
        listing = run('debugfs', '-R', 'ls -l /', boot)
        versions = re.findall(r'\bvmlinuz-([^\s]+)', listing)
        if len(versions) != 1:
            raise RuntimeError('Select a public image with exactly one installed boot kernel')
        version = versions[0]
        for src, dst in [(f'vmlinuz-{version}', 'vmlinuz'), (f'initrd.img-{version}', 'initrd'),
                         (f'config-{version}', 'kernel.config')]:
            run('debugfs', '-R', f'dump /{src} {output / dst}', boot)
            if not (output / dst).is_file() or (output / dst).stat().st_size == 0:
                raise RuntimeError(f'debugfs did not extract {src}')
        kernel = output / 'Image'
        with (output / 'vmlinuz').open('rb') as stream:
            compressed = stream.read(2) == b'\x1f\x8b'
        if compressed:
            with gzip.open(output / 'vmlinuz', 'rb') as stream, kernel.open('xb') as dest:
                while block := stream.read(1024 * 1024):
                    dest.write(block)
        else:
            kernel.write_bytes((output / 'vmlinuz').read_bytes())
        (output / 'initramfs-files.txt').write_text(run('lsinitramfs', output / 'initrd'))
        root = output / 'rootfs-10g.ext4'
        extract('cloudimg-rootfs', root)
        original_fstab = output / 'fstab.original'
        run('debugfs', '-R', f'dump /etc/fstab {original_fstab}', root)
        fstab = output / 'fstab.root-only'
        # The root-only fixture has no BOOT or UEFI partitions. Adjust this copy only.
        fstab.write_text(''.join(line for line in original_fstab.read_text().splitlines(keepends=True)
                                 if len(line.split()) < 2 or line.split()[1] not in ('/boot', '/boot/efi')))
        run('debugfs', '-w', '-R', 'rm /etc/fstab', root)
        run('debugfs', '-w', '-R', f'write {fstab} /etc/fstab', root)
        with root.open('r+b') as stream:
            stream.truncate(10 * 1024**3)
        (output / 'fsck.log').write_text(run('e2fsck', '-f', '-y', root, allowed=(0, 1)))
        (output / 'resize.log').write_text(run('resize2fs', root))
        manifest.update(status='PASS', kernel_version=version,
                        files={name: {'bytes': (output / name).stat().st_size, 'sha256': sha256(output / name)}
                               for name in ('Image', 'initrd', 'kernel.config', 'rootfs-10g.ext4')})
    except Exception as exc:
        manifest['error'] = str(exc)
    finally:
        manifest['source_sha256_after'] = sha256(source)
        if manifest['source_sha256_after'] != before:
            manifest.update(status='FAIL', error='source image hash changed')
        (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
        print(json.dumps(manifest, indent=2))
    return 0 if manifest['status'] == 'PASS' else 2


if __name__ == '__main__':
    sys.exit(main())
