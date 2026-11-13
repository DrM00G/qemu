#!/usr/bin/env python3
"""Verify restricted input and decompress once; no filesystem contents exported."""
import os
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from disk_inventory import inventory, regular, EXPECTED
os.umask(0o077)
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--package',type=Path,default=Path.home()/'cm5-v8-lab/import/cm5-v8-reference')
p.add_argument('--output',type=Path,default=Path.home()/'cm5-v8-lab/golden')
a=p.parse_args()
if a.output.resolve().is_relative_to(Path(__file__).resolve().parents[2]):p.error('output must be outside repository')
source=regular(a.package/'images/cm5-emmc-userarea.img.zst')
expected=(source.with_suffix(source.suffix+'.sha256')).read_text().split()[0]
with source.open('rb') as f: actual=hashlib.file_digest(f,'sha256').hexdigest()
if actual!=expected: raise ValueError('compressed checksum mismatch')
a.output.mkdir(parents=True,exist_ok=True)
image=a.output/'cm5-emmc-userarea.img'
record=a.output/'import.json'
if image.exists():
    prior=json.loads(record.read_text())
    if prior['compressed_sha256']!=actual or image.stat().st_size!=EXPECTED:
        raise ValueError('existing golden mismatch')
else:
    if shutil.disk_usage(a.output).free<EXPECTED+1024**3: raise ValueError('insufficient disk space')
    partial=a.output/'cm5-emmc-userarea.img.partial'
    digest=hashlib.sha256(); total=0
    with partial.open('xb') as out:
        proc=subprocess.Popen(['zstd','-dc',str(source)],stdout=subprocess.PIPE)
        while chunk:=proc.stdout.read(8*1024*1024):
            total+=len(chunk)
            if total>EXPECTED: proc.kill(); raise ValueError('oversized image')
            digest.update(chunk); out.write(chunk)
        if proc.wait() or total!=EXPECTED: raise ValueError('decompression failure or wrong size')
    partial.chmod(0o444); partial.rename(image)
    record.write_text(json.dumps(dict(compressed_sha256=actual,image_sha256=digest.hexdigest(),
                                     size=total),indent=2)+'\n')
result=inventory(image)
(a.output/'inventory.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(dict(import_record=json.loads(record.read_text()),inventory=result),indent=2))
