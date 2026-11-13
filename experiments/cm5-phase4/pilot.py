#!/usr/bin/env python3
"""Bounded host injection pilot using Phase 3, not a guest correction claim."""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess

HERE=Path(__file__).resolve().parent
REPO=HERE.parent.parent
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--source',type=Path,required=True,help='regular raw partition image, not full disk')
p.add_argument('--output',type=Path,required=True)
p.add_argument('--case',choices=['clean','os-small','fsw-small','no-fec'],required=True)
p.add_argument('--seed',type=int,default=7303)
a=p.parse_args()
if a.output.resolve().is_relative_to(REPO): p.error('output must be outside repository')
spec=importlib.util.spec_from_file_location('inject',HERE.parent/'cm5-phase3/inject.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
# Prevent accidental use of a complete disk as a partition pilot.
from disk_inventory import regular
source=regular(a.source)
with source.open('rb') as f:
    f.seek(510)
    if f.read(2)==b'\x55\xaa': p.error('DOS disk signature: provide an explicitly derived partition image')
if a.case=='clean':
    a.output.mkdir(parents=True,exist_ok=False)
    before=m.sha256(source)
    overlay=a.output.resolve()/'clean.qcow2'
    subprocess.run([str(REPO/'build-arm64-phase1/qemu-img'),'create','-f','qcow2','-F','raw',
                    '-b',str(source),str(overlay)],check=True)
    injection={'source_sha256_before':before,'source_sha256_after':m.sha256(source),
               'faults':[],'overlay':str(overlay)}
else:
    injection=m.inject(source,a.output,a.seed,3)
result={'case':a.case,'status':'NOT_TESTED','host_injection_status':'PASS',
        'guest_boot':'NOT_TESTED','corruption_detection':'NOT_TESTED',
        'logical_recovery':'NOT_TESTED','fec_correction':'NOT_TESTED',
        'fec_requested':a.case!='no-fec','fec_configured_in_guest':False,
        'mechanism':'XOR ff on all bytes in each selected 4096-byte block',
        'fraction_denominator':'all 4096-byte blocks of supplied raw partition',
        'fraction':len(injection['faults'])*4096/source.stat().st_size,
        'seed':a.seed,'injection':injection}
(a.output/'pilot.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
