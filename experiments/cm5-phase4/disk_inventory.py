#!/usr/bin/env python3
"""Read-only, content-free MBR/EBR inventory. Local research only."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import struct

EXPECTED = 15634268160

def regular(path):
    path = Path(path).resolve(strict=True)
    if not stat.S_ISREG(path.stat().st_mode):
        raise ValueError('regular image files required; host block devices forbidden')
    return path

def inventory(path):
    path = regular(path)
    size = path.stat().st_size
    rows = []
    with path.open('rb') as f:
        def sector(lba):
            if lba < 0 or (lba + 1) * 512 > size:
                raise ValueError('partition table outside image')
            f.seek(lba * 512)
            b = f.read(512)
            if b[510:] != b'\x55\xaa':
                raise ValueError('missing DOS signature')
            return [struct.unpack_from('<B3sB3sII', b, 446 + 16*i) for i in range(4)]
        def record(n, entry, base=0):
            _, _, kind, _, start, count = entry
            start += base
            if not count or (start + count)*512 > size:
                raise ValueError('invalid partition extent')
            row = dict(number=n, type=kind, offset=start*512, size=count*512)
            # blkid probes filesystem metadata only, never files.
            import subprocess
            r = subprocess.run(['blkid', '-p', '-O', str(row['offset']), '-S', str(row['size']),
                                '-o', 'export', str(path)], capture_output=True, text=True)
            row['filesystem'] = dict(line.split('=', 1) for line in r.stdout.splitlines()
                                     if '=' in line and line.split('=',1)[0] in
                                     ('TYPE','UUID','LABEL','VERSION','BLOCK_SIZE'))
            rows.append(row)
        for n, entry in enumerate(sector(0), 1):
            if not entry[2]:
                continue
            record(n, entry)
            if entry[2] in (5, 15, 133):
                base = entry[4]
                lba, seen, logical = base, set(), 5
                while lba:
                    if lba in seen or len(seen) > 128:
                        raise ValueError('cyclic or excessive EBR chain')
                    seen.add(lba)
                    entries = sector(lba)
                    record(logical, entries[0], lba)
                    logical += 1
                    lba = base + entries[1][4] if entries[1][2] else 0
    return dict(image=str(path), size=size, expected_size=EXPECTED,
                size_status='PASS' if size == EXPECTED else 'FAIL', partitions=rows)

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('image', type=Path)
    p.add_argument('--sha256', action='store_true')
    a = p.parse_args()
    result = inventory(a.image)
    if a.sha256:
        with regular(a.image).open('rb') as f:
            result['sha256'] = hashlib.file_digest(f, 'sha256').hexdigest()
    print(json.dumps(result, indent=2))
