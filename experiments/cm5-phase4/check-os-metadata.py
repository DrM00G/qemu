#!/usr/bin/env python3
"""Verify a captured verity Merkle path and compare OS block zero, no full scan."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
from disk_inventory import regular
os.umask(0o077)
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--full',action='store_true',help='read all OS blocks once, stopping at first mismatch')
p.add_argument('--derived',type=Path,default=Path.home()/'cm5-v8-lab/derived-fsw')
p.add_argument('--image',type=Path,default=Path.home()/'cm5-v8-lab/golden/cm5-emmc-userarea.img')
a=p.parse_args();d=a.derived.resolve();image=regular(a.image)
for suffix in ['hash','roothash']:
    dst=d/('os.'+suffix)
    if not dst.exists():
        subprocess.run(['debugfs','-R',f'dump /cm5-verity-v2/os/os.{suffix} {dst}',
                        str(regular(d/'recovery.ext4'))],capture_output=True,check=True)
info=subprocess.check_output(['veritysetup','dump',str(d/'os.hash')],text=True)
(d/'os-verity-dump.txt').write_text(info)
fields=dict(l.split(':',1) for l in info.splitlines() if ':' in l)
blocks=int(fields['Data blocks']);salt=bytes.fromhex(fields['Salt'].strip())
if fields['Hash type'].strip()!='1' or fields['Hash algorithm'].strip()!='sha256':raise ValueError('unsupported format')
if int(fields['Data block size'].split()[0])!=4096 or int(fields['Hash block size'].split()[0])!=4096:raise ValueError('unsupported geometry')
levels=[];n=blocks
while n>1:
    n=(n+127)//128;levels.append(n)
expected=bytes.fromhex((d/'os.roothash').read_text().strip())
offset=4096;path=True
with regular(d/'os.hash').open('rb') as tree:
    for count in reversed(levels):
        tree.seek(offset);page=tree.read(4096)
        if hashlib.sha256(salt+page).digest()!=expected:path=False;break
        expected=page[:32];offset+=count*4096
with image.open('rb') as raw:
    raw.seek(545259520);actual=hashlib.sha256(salt+raw.read(4096)).digest()
match=path and actual==expected
result=dict(scope='OS block 0 only; authenticated path to captured unauthenticated root',
            metadata_regenerated=False,merkle_path='PASS' if path else 'FAIL',
            data_block_match='PASS' if match else 'FAIL',
            os_metadata_matches_capture='FAIL' if path and not match else 'INCONCLUSIVE',
            fec_recovery='NOT_TESTED',whole_os_scan='NOT_TESTED',
            data_partition_offset=545259520,logical_block=0)
if a.full:
    expected_nodes=bytes.fromhex((d/'os.roothash').read_text().strip())
    tree_ok=True;offset=4096
    with regular(d/'os.hash').open('rb') as tree:
        for count in reversed(levels):
            tree.seek(offset);pages=tree.read(count*4096)
            if len(pages)!=count*4096:raise ValueError('truncated tree')
            for i in range(count):
                if hashlib.sha256(salt+pages[i*4096:(i+1)*4096]).digest()!=expected_nodes[i*32:(i+1)*32]:
                    tree_ok=False;break
            if not tree_ok:break
            expected_nodes=pages;offset+=count*4096
    checked=0;bad=None
    if tree_ok:
        with image.open('rb') as raw:
            raw.seek(545259520)
            while checked<blocks:
                batch=raw.read(min(2048,blocks-checked)*4096)
                for i in range(0,len(batch),4096):
                    if hashlib.sha256(salt+batch[i:i+4096]).digest()!=expected_nodes[checked*32:(checked+1)*32]:
                        bad=checked;break
                    checked+=1
                if bad is not None:break
    result.update(scope='complete captured OS and Merkle tree; captured root is not independently authenticated',whole_tree='PASS' if tree_ok else 'FAIL',data_blocks_checked=checked,
                  first_mismatched_block=bad,whole_os_scan='PASS' if checked==blocks else 'FAIL',
                  os_metadata_matches_capture='PASS' if checked==blocks else 'FAIL')
(d/'os-metadata-check.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
