#!/usr/bin/env python3
"""Create sparse public/synthetic V8-like storage; never operate on block devices."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'cm5-phase1'))
from launch import sha256

MIB = 1024**2
SALT = '000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f'


def run(*args):
    return subprocess.check_output([str(a) for a in args], stderr=subprocess.STDOUT, text=True)


def regular(path):
    if not stat.S_ISREG(path.stat().st_mode):
        raise RuntimeError('Only regular image files are accepted: ' + str(path))


def filesystem(path, size, label, contents):
    with path.open('xb') as stream:
        stream.truncate(size)
    output = run('mkfs.ext4', '-q', '-F', '-b', '4096', '-L', label,
                 '-E', 'lazy_itable_init=0,lazy_journal_init=0', '-d', contents, path)
    path.with_suffix('.mkfs.log').write_text(output)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--os', type=Path, default=HERE.parent / 'cm5-phase2/artifacts/public-inputs/rootfs-10g.ext4')
    p.add_argument('--output', type=Path, default=HERE / 'artifacts/storage-v1')
    p.add_argument('--kernel-root', type=Path, default=Path(os.environ.get('PHASE3_KERNEL_ROOT', str(Path.home() / 'cm5-phase3-kernel'))))
    p.add_argument('--initramfs', type=Path, default=HERE / 'artifacts/initramfs-16k/initrd.gz')
    p.add_argument('--fsw-binary', type=Path, help='Optional later-stage prototype; initial storage tests use synthetic data only')
    p.add_argument('--reuse-os-from', type=Path, help='Reuse proven OS tree/parity from a previous manifest after checking all digests')
    args = p.parse_args()
    regular(args.os)
    if args.os.stat().st_size != 10 * 1024**3:
        p.error('--os must be a 10 GiB raw filesystem image')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    manifest = {'schema': 1, 'block_size': 4096, 'hash': 'sha256', 'fec_roots': 2,
                'source_os': str(args.os.resolve()), 'veritysetup_version': run('veritysetup', '--version').strip(),
                'trust': 'Root hashes pinned in generated initramfs; no secure hardware boot chain is claimed.'}
    manifest['kernel'] = {'image_sha256': sha256(args.kernel_root / 'build/arch/arm64/boot/Image'),
                          'config_sha256': sha256(args.kernel_root / 'build/.config'),
                          'source_commit': (args.kernel_root / 'build/source-commit.txt').read_text().strip(),
                          'release': (args.kernel_root / 'build/kernelrelease.txt').read_text().strip()}
    os_hash = sha256(args.os)
    previous = json.loads(args.reuse_os_from.read_text()) if args.reuse_os_from else None
    if previous:
        if (previous['volumes']['os']['sha256'] != os_hash or previous['block_size'] != 4096 or
                previous['hash'] != 'sha256' or previous['fec_roots'] != 2):
            raise RuntimeError('Previous OS metadata does not match this data/format')
        old_recovery = Path(previous['volumes']['recovery']['path'])
        regular(old_recovery)
        if sha256(old_recovery) != previous['volumes']['recovery']['sha256']:
            raise RuntimeError('Previous recovery container hash differs from its manifest')
    fsw_contents = output / 'fsw-contents'
    fsw_contents.mkdir()
    payload = bytes(range(256)) * 4096
    (fsw_contents / 'probe.bin').write_bytes(payload)
    (fsw_contents / 'config.json').write_text(json.dumps({'schema': 1, 'interval_ms': 100,
        'iterations': 50, 'log_directory': '/var/log/flight',
        'spi_adapter': 'UNSUPPORTED', 'uart_adapter': 'UNSUPPORTED'}) + '\n')
    if args.fsw_binary:
        regular(args.fsw_binary)
        shutil.copyfile(args.fsw_binary, fsw_contents / 'prototype-fsw')
        (fsw_contents / 'prototype-fsw').chmod(0o755)
        library = args.fsw_binary.parent / 'libflightmath.so'
        regular(library)
        shutil.copyfile(library, fsw_contents / 'libflightmath.so')
    fsw = output / 'fsw.ext4'
    filesystem(fsw, 512 * MIB, 'V8-FSW', fsw_contents)
    logs_contents = output / 'logs-contents'
    logs_contents.mkdir()
    logs = output / 'logs.ext4'
    filesystem(logs, 1024 * MIB, 'V8-LOGS', logs_contents)
    boot_contents = output / 'boot-contents'
    boot_contents.mkdir()
    shutil.copyfile(args.kernel_root / 'build/arch/arm64/boot/Image', boot_contents / 'Image')
    shutil.copyfile(args.kernel_root / 'build/.config', boot_contents / 'kernel.config')
    shutil.copyfile(args.initramfs, boot_contents / 'initrd.gz')
    (boot_contents / 'README').write_text('Public surrogate components. QEMU direct boot uses host-side pinned artifacts.\n')
    boot = output / 'boot.ext4'
    recovery = output / 'recovery.raw'
    with recovery.open('xb') as stream:
        stream.truncate(2560 * MIB)
    devices = {'os': (args.os.resolve(), MIB, 128 * MIB),
               'fsw': (fsw, 256 * MIB, 272 * MIB)}
    manifest['volumes'] = {}
    for name, (data, hash_offset, fec_offset) in devices.items():
        hash_file, fec_file = output / (name + '.hash'), output / (name + '.fec')
        print('Generating real verity/FEC for ' + name, flush=True)
        if name == 'os' and previous:
            old = previous['volumes']['os']
            blocks, hash_blocks, root_hash = old['data_blocks'], old['hash_blocks'], old['root_hash']
            if old['salt'] != SALT:
                raise RuntimeError('Previous OS salt differs')
            with old_recovery.open('rb') as stream:
                for destination, offset, size in [(hash_file, old['hash_start'] * 4096, hash_blocks * 4096),
                                                   (fec_file, old['fec_start'] * 4096, old['fec_parity_bytes'])]:
                    stream.seek(offset)
                    with destination.open('xb') as dest:
                        while size:
                            chunk = stream.read(min(size, MIB))
                            if not chunk:
                                raise RuntimeError('Truncated previous recovery region')
                            dest.write(chunk)
                            size -= len(chunk)
            (output / 'os.format.log').write_text('Reused generated OS tree/parity from digest-checked ' + str(args.reuse_os_from) + '\n')
            manifest['reused_os_metadata_manifest'] = {'path': str(args.reuse_os_from.resolve()), 'sha256': sha256(args.reuse_os_from)}
        else:
            formatted = run('veritysetup', 'format', data, hash_file, '--no-superblock',
                            '--hash=sha256', '--data-block-size=4096', '--hash-block-size=4096',
                            '--salt=' + SALT, '--fec-roots=2', '--fec-device=' + str(fec_file))
            (output / (name + '.format.log')).write_text(formatted)
            fields = dict(line.split(':', 1) for line in formatted.splitlines() if ':' in line)
            fields = {key.strip(): value.strip().split()[0] if value.strip() else '' for key, value in fields.items()}
            blocks, hash_blocks = int(fields['Data blocks']), int(fields['Hash blocks'])
            root_hash = fields['Root hash']
        hash_limit, fec_limit = ((128 * MIB, 256 * MIB) if name == 'os' else (272 * MIB, 2560 * MIB))
        if hash_offset + hash_file.stat().st_size > hash_limit or fec_offset + fec_file.stat().st_size > fec_limit:
            raise RuntimeError('Generated metadata exceeds its reserved region')
        with recovery.open('r+b') as dest:
            for source, offset in [(hash_file, hash_offset), (fec_file, fec_offset)]:
                dest.seek(offset)
                with source.open('rb') as stream:
                    shutil.copyfileobj(stream, dest)
        verified = run('veritysetup', 'verify', data, hash_file, root_hash,
                       '--no-superblock', '--hash=sha256', '--data-block-size=4096',
                       '--hash-block-size=4096', '--salt=' + SALT)
        (output / (name + '.host-verify.log')).write_text(verified)
        manifest['volumes'][name] = {'path': str(data), 'bytes': data.stat().st_size,
            'sha256': os_hash if name == 'os' else sha256(data), 'root_hash': root_hash,
            'salt': SALT, 'data_blocks': blocks, 'hash_blocks': hash_blocks,
            'hash_start': hash_offset // 4096, 'fec_start': fec_offset // 4096,
            'fec_blocks': blocks + hash_blocks, 'fec_parity_bytes': fec_file.stat().st_size}
    manifest['probe_sha256'] = hashlib.sha256(payload).hexdigest()
    manifest['prototype'] = bool(args.fsw_binary)
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    manifest['initramfs'] = {}
    for name, extra in [('initramfs-fec', []), ('initramfs-no-fec', ['--no-fec'])]:
        subprocess.run([sys.executable, str(HERE / 'prepare-verity-initramfs.py'),
                        '--storage', str(output / 'manifest.json'), '--input', str(args.initramfs),
                        '--output', str(output / name)] + extra, check=True)
        shutil.copyfile(output / name / 'initrd.gz', boot_contents / (name + '.gz'))
        manifest['initramfs'][name] = sha256(output / name / 'initrd.gz')
    for name in ('os', 'fsw'):
        (boot_contents / (name + '.root-hash')).write_text(manifest['volumes'][name]['root_hash'] + '\n')
    filesystem(boot, 512 * MIB, 'V8-BOOT', boot_contents)
    for name, path in [('logs', logs), ('boot', boot), ('recovery', recovery)]:
        manifest['volumes'][name] = {'path': str(path), 'bytes': path.stat().st_size}
        if name != 'recovery':
            manifest['volumes'][name]['sha256'] = sha256(path)
    encoded = json.dumps(manifest, indent=2).encode()
    if len(encoded) >= MIB:
        raise RuntimeError('Recovery manifest exceeds reserved header region')
    with recovery.open('r+b') as stream:
        stream.write(encoded + b'\n')
    manifest['volumes']['recovery']['sha256'] = sha256(recovery)
    if sha256(args.os) != os_hash:
        raise RuntimeError('Golden OS image changed')
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps(manifest, indent=2), flush=True)


if __name__ == '__main__':
    main()
