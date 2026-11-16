#!/usr/bin/env python3
"""Read-only captured p5 inspection; private partition bytes stay outside repo."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO/'experiments/cm5-phase10a'))
from preboot import identity


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=False, mode=0o700)
    lab = Path('/home/aweso/cm5-v8-lab/phase10c')/a.output.name
    lab.mkdir(parents=True, exist_ok=False)
    golden = Path('/home/aweso/cm5-v8-lab/golden/cm5-emmc-userarea.img')
    image = lab/'fsw.ext4'
    subprocess.run([str(REPO/'build-arm64-phase1/qemu-img'), 'convert', '--image-opts', '-O', 'raw',
        f'driver=raw,offset=11283726336,size=536870912,file.driver=file,file.filename={golden}', str(image)], check=True)
    image.chmod(0o400)
    entries = []
    for directory in ('/', '/lost+found'):
        command = ['debugfs', '-R', 'ls -p '+directory, str(image)]
        r = subprocess.run(command, capture_output=True, text=True, check=True)
        for line in r.stdout.splitlines():
            if not line.startswith('/'):
                continue
            fields = line.split('/')
            if int(fields[1]) and fields[5] not in ('.', '..'):
                entries.append(dict(path=directory.rstrip('/')+'/'+fields[5],
                    inode=int(fields[1]), mode=fields[2],
                    type='directory' if int(fields[2], 8) & 0o170000 == 0o040000 else 'other',
                    file_content_sha256=None))
    with golden.open('rb') as f:
        f.seek(11283726336)
        expected_block = hashlib.sha256(f.read(4096)).hexdigest()
    result = dict(status='NO_CAPTURED_EXECUTABLE' if [e['path'] for e in entries] == ['/lost+found']
                  else 'NEEDS_FURTHER_INSPECTION',
                  partition='p5', guest_offset=11283726336, bytes=536870912,
                  export=identity(image), entries=entries,
                  expected_verified_block0_sha256=expected_block,
                  note='No regular files found; no executable bytes copied into public repo; no filesystem mounted or modified.')
    (a.output/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    print(result['status'])


if __name__ == '__main__':
    main()
