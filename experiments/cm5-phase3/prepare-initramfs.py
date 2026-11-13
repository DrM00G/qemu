#!/usr/bin/env python3
"""Repack public Ubuntu initramfs with modules matching the new 16 KiB kernel."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'cm5-phase1'))
from launch import sha256


def pack(stage, archive):
    with archive.open('xb') as stream:
        find = subprocess.Popen(['find', '.', '-print0'], cwd=stage, stdout=subprocess.PIPE)
        cpio = subprocess.Popen(['cpio', '--null', '-o', '-H', 'newc', '--owner=0:0'],
                                cwd=stage, stdin=find.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        find.stdout.close()
        gz = subprocess.Popen(['gzip', '-n', '-1'], stdin=cpio.stdout, stdout=stream)
        cpio.stdout.close()
        errors = cpio.stderr.read()
        if gz.wait() or cpio.wait() or find.wait():
            raise RuntimeError('initramfs packing failed: ' + errors.decode())


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--kernel-root', type=Path, default=Path(os.environ.get('PHASE3_KERNEL_ROOT', str(Path.home() / 'cm5-phase3-kernel'))))
    p.add_argument('--input', type=Path, default=HERE.parent / 'cm5-phase2/artifacts/public-inputs/initrd')
    p.add_argument('--output', type=Path, default=HERE / 'artifacts/initramfs-16k')
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    release = (args.kernel_root / 'build/kernelrelease.txt').read_text().strip()
    unpacked = args.output / 'unpacked'
    subprocess.run(['unmkinitramfs', str(args.input), str(unpacked)], check=True)
    stage = unpacked / 'main' if (unpacked / 'main/init').exists() else unpacked
    modules = stage / 'usr/lib/modules'
    if modules.exists():
        shutil.rmtree(modules)
    shutil.copytree(args.kernel_root / 'modules/lib/modules', modules, symlinks=True,
                    ignore=shutil.ignore_patterns('build', 'source'))
    # Strip debug sections from this disposable copy, keeping matching symbols
    # and vermagic while avoiding a large resident initramfs under TCG.
    for module in modules.rglob('*.ko'):
        subprocess.run(['aarch64-linux-gnu-strip', '--strip-debug', str(module)], check=True)
    # Do not attempt to load unrelated Ubuntu distro modules during pre-root boot.
    (stage / 'conf/modules').write_text('')
    archive = args.output / 'initrd.gz'
    pack(stage, archive)
    manifest = {'release': release, 'original_initrd': str(args.input),
                'original_sha256': sha256(args.input), 'initrd': str(archive.resolve()),
                'sha256': sha256(archive), 'modules': str(args.kernel_root / 'modules/lib/modules')}
    (args.output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    main()
