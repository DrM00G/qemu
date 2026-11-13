#!/usr/bin/env python3
"""Summarize simulator-owned evidence without exposing production journals."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
p=argparse.ArgumentParser(description=__doc__);p.add_argument('run',type=Path);a=p.parse_args()
r=a.run.resolve(); e=r/'guest-evidence/cm5-evidence'
base=json.loads((r/'result.json').read_text())
def read(name):return (e/name).read_text().strip()
functions=[json.loads(line) for line in read('diagnostic.jsonl').splitlines()]
failed=[]
for line in read('failed-units.txt').splitlines():
    cols=line.split()
    if len(cols)>2 and cols[0].endswith(('.service','.mount','.socket','.target')):failed.append(cols[0])
mounts=[line.split() for line in read('mounts.txt').splitlines()]
def mounted(where,kind,options):
    return any(m[1]==where and m[2]==kind and set(options)<=set(m[3].split(',')) for m in mounts)
mount_checks={'os_lower':mounted('/media/root-ro','ext4',['ro','norecovery']),
              'ram_upper':mounted('/media/root-rw','tmpfs',['rw']),
              'root_overlay':mounted('/','overlay',['rw']),
              'fsw':mounted('/opt/fsw','ext4',['ro','norecovery']),
              'logs':mounted('/var/log/flight','ext4',['rw']),
              'boot':mounted('/boot/firmware','vfat',['ro']),
              'recovery':mounted('/mnt/recovery','ext4',['ro','norecovery'])}
boot=read('pid1.txt')=='systemd' and read('target.txt')=='active' and read('page-size.txt')=='16384' and all(mount_checks.values())
diag=any(f['test']=='exit' and f['status']=='PASS' for f in functions)
uart=[]
if (e/'uart-preinit.jsonl').exists():
    uart=[json.loads(line) for line in read('uart-preinit.jsonl').splitlines() if line.startswith('{')]
uart_ok=any(f['test']=='uart_loopback' and f['status']=='PASS' for f in uart)
fsw_digest=None;fsw_match=None;corrections=[]
if (e/'fsw-logical-sha256.txt').exists():
    fsw_digest=read('fsw-logical-sha256.txt').split()[0]
    expected=json.loads((r/'fsw-verification-input.json').read_text())['fsw_sha256']
    fsw_match=read('fsw-scan-exit.txt')=='0' and fsw_digest==expected
    corrections=[line for line in read('dmesg.txt').splitlines() if 'verity' in line and 'corrected' in line]
injected=base.get('injection') is not None
corrected=injected and fsw_match and bool(corrections)
record=json.loads((Path.home()/'cm5-v8-lab/golden/import.json').read_text())
result={**base,'schema_version':1,'status':'PASS' if boot and diag and (uart_ok if uart else True) and fsw_match is not False and (not injected or corrected) and not base['timeout'] else 'FAIL',
        'scope':'V8 simulator profile; production unit failures reported independently',
        'kernel_version':read('kernel.txt').split()[2], 'page_size':int(read('page-size.txt')),
        'input_image_sha256':record['image_sha256'],'hardware':'simulated',
        'linux_boot':'PASS' if boot else 'FAIL','systemd_target':read('target.txt'),
        'production_failed_units':failed,'production_services':'FAIL' if failed else 'PASS',
        'mount_checks':mount_checks,'functions':functions,'uart_preinit_functions':uart,
        'uart_status':'PASS' if uart_ok else 'NOT_TESTED','corruption':base.get('injection'),
        'fsw_logical_sha256':fsw_digest,'fsw_complete_read':('PASS' if fsw_match else 'FAIL') if fsw_match is not None else 'NOT_TESTED',
        'kernel_correction_evidence':corrections,
        'verified_root':'NOT_TESTED', 'os_root_runtime_verity':False,
        'dm_verity_scope':'FSW only',
        'dm_verity':('PASS' if fsw_match else 'FAIL') if fsw_match is not None else 'NOT_TESTED',
        'fec_correction':('PASS' if corrected else 'FAIL') if injected else 'NOT_TESTED',
        'logical_recovery':('PASS' if fsw_match else 'FAIL') if injected else 'NOT_TESTED',
        'uart_trace':str(r/'uart.json') if (r/'uart.json').exists() else None,
        'network_trace':str(r/'network.jsonl'),
        'corruption_target':'FSW' if injected else None,
        'corruption_fraction':4096/536870912 if injected else 0,
        'corruption_mechanism':'XOR ff across one 4096-byte block' if injected else None}
(r/'v8-result.json').write_text(json.dumps(result,indent=2)+'\n')
with (r/'v8-result.csv').open('w') as f:
    w=csv.DictWriter(f,fieldnames=['test','status','errno','bytes','monotonic_ns']);w.writeheader();w.writerows(functions)
lines=['# V8 functional results','',f"Boot/profile: {result['status']}; production units: {result['production_services']}",'',
       '| Function | Status | errno | Bytes/value |','|---|---|---|---|']
lines += [f"| {v['test']} | {v['status']} | {v['errno']} | {v['bytes']} |" for v in functions]
lines+=['','Failed units: '+', '.join(failed)]
(r/'v8-result.md').write_text('\n'.join(lines)+'\n')
print(json.dumps({k:result[k] for k in ['status','linux_boot','kernel_version','page_size','production_failed_units','mount_checks']},indent=2))

raise SystemExit(0 if result['status']=='PASS' else 1)
