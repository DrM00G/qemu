#!/usr/bin/env python3
"""Create a new aggregate, without editing any per-run evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import jsonschema

from campaign import save


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--runs',type=Path,nargs='+',required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    schema=json.loads(Path(__file__).with_name('result.schema.json').read_text())
    records=[]
    for run in a.runs:
        path=run/'recovery-result.json'
        if not path.exists():
            records.append(dict(case=run.name,status='INCONCLUSIVE',reason='No completed recovery result',path=str(path)))
            continue
        r=json.loads(path.read_text())
        # Early CLEAN evidence predates adding these explanatory schema fields.
        # Normalize only in this new report; leave original evidence untouched.
        r.setdefault('profile','DIAGNOSTIC_NO_FEC' if r['case']=='no-fec' else 'ORIGINAL_CAPTURED_INITRAMFS')
        r.setdefault('distribution',dict(kind='single-4096-byte-replacement' if r['fault']['inject'] else 'none',tested=True,count=1 if r['fault']['inject'] else 0))
        jsonschema.validate(r,schema)
        save(a.output/(r['case']+'.json'),r)
        records.append(dict(case=r['case'],status=r['status'],profile=r['profile'],
            checks=r['checks'],fec_events=r['fec_events'],
            golden_block_sha256=r['fault']['golden_sha256'],raw_fault_sha256=r['fault']['raw_after_injection_sha256'],
            original_result=str(path),original_result_sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    expected={'clean':'PASS_CLEAN','os0':'PASS_RECOVERED','os-far':'PASS_RECOVERED','fsw0':'PASS_RECOVERED','no-fec':'EXPECTED_VERITY_REJECTION'}
    complete={r['case']:r['status'] for r in records}==expected
    save(a.output/'result.json',dict(status='PASS' if complete else 'INCONCLUSIVE',cases=records,
        schema_validation='PASS for completed cases',scope='Captured roots2 logical corruption; diagnostic OS roots0 negative control; no other configurations tested'))
    (a.output/'summary.txt').write_text('\n'.join(r['case']+': '+r['status'] for r in records)+'\n')
    print((a.output/'summary.txt').read_text(),end='')
    return 0 if complete else 1


if __name__=='__main__':sys.exit(main())
