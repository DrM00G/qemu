#!/usr/bin/env python3
"""Extract only simulator-created evidence from disposable LOGS, locally."""
import os
import argparse
from pathlib import Path
import subprocess
HERE=Path(__file__).resolve().parent
REPO=HERE.parent.parent
os.umask(0o077)
p=argparse.ArgumentParser(description=__doc__);p.add_argument('run',type=Path);a=p.parse_args()
r=a.run.resolve(strict=True)
if r.is_relative_to(REPO):p.error('lab run directory required')
# Do not run while the guest is active.
image=r/'logs-export.ext4'
if not image.exists():
    subprocess.run([str(REPO/'build-arm64-phase1/qemu-img'),'convert','--image-opts','-O','raw',
        'driver=raw,offset=11821645824,size=1073741824,file.driver=qcow2,file.file.filename='+str(r/'logs.qcow2'),
        str(image)],check=True)
out=r/'guest-evidence';out.mkdir(exist_ok=False)
with (r/'export.log').open('w') as log:
    subprocess.run(['debugfs','-R',f'rdump /cm5-evidence {out}',str(image)],stdout=log,stderr=log,check=True)
print('Exported only /cm5-evidence into',out)
