#!/usr/bin/env python3
"""Re-evaluate retained evidence into a new directory; never rerun the guest."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

from campaign import finish, save


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    raw=json.loads((a.run/'recovery-result.json').read_text())
    if raw['case']!='os-far':p.error('This recheck is only for the documented OS-FAR RS-base evaluator correction')
    a.output.mkdir(parents=True,exist_ok=False)
    lab=Path('/home/aweso/cm5-v8-lab/phase10d')/a.output.name;lab.mkdir(parents=True,exist_ok=False)
    for name in ('serial.log','userspace.json','result.json','fault.json','inputs-before.json','command.json','process.json'):
        shutil.copyfile(a.run/name,a.output/name)
    save(a.output/'original-evaluation.json',raw)
    save(a.output/'recheck-provenance.json',dict(original_run=str(a.run.resolve()),
        original_evaluation_sha256=hashlib.sha256((a.run/'recovery-result.json').read_bytes()).hexdigest(),
        reason='FEC log uses interleaved RS byte base, not absolute block byte offset. Correct source-backed formula: (block % ceil(fec_blocks/(255-roots)))*4096.',
        no_guest_rerun=True,no_new_fault=True,original_files_unchanged=True))
    run=raw['run'];overlay=Path(run['overlay']['path'])
    finish(a.output,lab,Path('/home/aweso/cm5-v8-lab/golden/cm5-emmc-userarea.img'),overlay,raw['fault'],run)
    return 0 if json.loads((a.output/'recovery-result.json').read_text())['status']=='PASS_RECOVERED' else 1


if __name__=='__main__':raise SystemExit(main())
