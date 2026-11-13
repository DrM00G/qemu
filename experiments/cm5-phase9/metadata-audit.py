#!/usr/bin/env python3
"""Read-only audit of captured partitions and original verification metadata."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

os.umask(0o077)
lab = Path.home() / 'cm5-v8-lab'
out = lab / 'phase9/metadata'
out.mkdir(parents=True, exist_ok=False)
golden = lab / 'golden/cm5-emmc-userarea.img'
derived = lab / 'derived-fsw'
assert golden.is_file() and golden.stat().st_size == 15634268160
assert __import__('shutil').disk_usage(out).free > 1024**3

def digest_range(path, offset, size):
    h = hashlib.sha256()
    with path.open('rb') as f:
        f.seek(offset)
        while size:
            data = f.read(min(size, 8 * 1024**2))
            if not data:
                raise ValueError('truncated input')
            h.update(data)
            size -= len(data)
    return h.hexdigest()

recovery_digest = digest_range(golden, 12896436224, 2736782848)
assert recovery_digest == digest_range(derived / 'recovery.ext4', 0, 2736782848)
report = dict(metadata_regenerated=False, recovery_matches_exact_capture=True,
              recovery_sha256=recovery_digest, partitions={})
for role, offset, blocks in [('os', 545259520, 2621440), ('fsw', 11283726336, 131072)]:
    for suffix in ('hash', 'fec', 'roothash'):
        target = out / f'{role}.{suffix}'
        subprocess.run(['debugfs', '-R',
            f'dump /cm5-verity-v2/{role}/{role}.{suffix} {target}',
            str(derived / 'recovery.ext4')], check=True, capture_output=True)
        assert target.is_file()
    info = subprocess.check_output(['veritysetup', 'dump', str(out / f'{role}.hash')], text=True)
    fields = dict(line.split(':', 1) for line in info.splitlines() if ':' in line)
    salt = bytes.fromhex(fields['Salt'].strip())
    root = bytes.fromhex((out / f'{role}.roothash').read_text().strip())
    assert int(fields['Data blocks']) == blocks
    assert int(fields['Data block size'].split()[0]) == 4096
    levels = []
    n = blocks
    while n > 1:
        n = (n + 127) // 128
        levels.append(n)
    expected = root
    pos = 4096
    with (out / f'{role}.hash').open('rb') as f:
        for count in reversed(levels):
            f.seek(pos)
            pages = f.read(count * 4096)
            assert len(pages) == count * 4096
            for i in range(count):
                assert hashlib.sha256(salt + pages[i*4096:(i+1)*4096]).digest() == expected[i*32:(i+1)*32]
            expected = pages
            pos += count * 4096
    checked = 0
    with golden.open('rb') as f:
        f.seek(offset)
        while checked < blocks:
            batch = f.read(min(2048, blocks - checked) * 4096)
            assert batch
            for i in range(0, len(batch), 4096):
                assert hashlib.sha256(salt + batch[i:i+4096]).digest() == expected[checked*32:(checked+1)*32]
                checked += 1
    report['partitions'][role] = dict(status='PASS', data_blocks_checked=checked,
        offset=offset, root=root.hex(), salt=salt.hex(), hash_blocks=sum(levels),
        fec_blocks=blocks+sum(levels), metadata_sha256={suffix:
            digest_range(out / f'{role}.{suffix}', 0, (out / f'{role}.{suffix}').stat().st_size)
            for suffix in ('hash', 'fec', 'roothash')})
(out / 'audit.json').write_text(json.dumps(report, indent=2) + '\n')
print('PASS: complete original OS/FSW Merkle trees and exact captured data; original metadata only.')
