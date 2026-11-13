#!/usr/bin/env python3
"""Extract only FSW/RECOVERY derived regular files and verify captured metadata."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
from disk_inventory import regular
os.umask(0o077)
HERE=Path(__file__).resolve().parent;REPO=HERE.parent.parent
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--output',type=Path,default=Path.home()/'cm5-v8-lab/derived-fsw')
p.add_argument('--image',type=Path,default=Path.home()/'cm5-v8-lab/golden/cm5-emmc-userarea.img')
a=p.parse_args()
if a.output.resolve().is_relative_to(REPO):p.error('output must be outside repository')
image=regular(a.image);a.output.mkdir(exist_ok=False)
qimg=REPO/'build-arm64-phase1/qemu-img'
for name,offset,size in [('fsw',11283726336,536870912),('recovery',12896436224,2736782848)]:
    subprocess.run([str(qimg),'convert','--image-opts','-O','raw',
                    f'driver=raw,offset={offset},size={size},file.driver=file,file.filename={image}',
                    str(a.output/(name+'.ext4'))],check=True)
with (a.output/'extraction.log').open('w') as log:
    for suffix in ['hash','fec','roothash']:
        subprocess.run(['debugfs','-R',f'dump /cm5-verity-v2/fsw/fsw.{suffix} {a.output}/fsw.{suffix}',
                        str(a.output/'recovery.ext4')],stdout=log,stderr=log,check=True)
root=(a.output/'fsw.roothash').read_text().strip()
with (a.output/'verity-dump.txt').open('w') as log:
    subprocess.run(['veritysetup','dump',str(a.output/'fsw.hash')],stdout=log,stderr=subprocess.STDOUT,check=True)
checks={}
for fec in [False,True]:
    cmd=['veritysetup','verify',str(a.output/'fsw.ext4'),str(a.output/'fsw.hash'),root]
    if fec:cmd+=['--fec-device',str(a.output/'fsw.fec'),'--fec-roots','2']
    with (a.output/('verify-fec.txt' if fec else 'verify-no-fec.txt')).open('w') as log:
        r=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT)
    checks['fec' if fec else 'no_fec']='PASS' if r.returncode==0 else 'FAIL'
with (a.output/'fsw.ext4').open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
result=dict(captured_metadata=True,fsw_root=root,fsw_sha256=digest,verification=checks,
            os_metadata='NOT_TESTED',metadata_regenerated=False)
(a.output/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
