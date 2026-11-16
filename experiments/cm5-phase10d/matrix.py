#!/usr/bin/env python3
"""Fresh sequential campaign; CLEAN/OS0 gate remaining original-kernel cases."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

REPO=Path(__file__).resolve().parents[2]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    records=[]
    for case in ('clean','os0','os-far','fsw0','no-fec'):
        out=a.output/(a.output.name+'-'+case)
        cmd=[sys.executable,str(REPO/'experiments/cm5-phase10c/run.py'),
             '--recovery-case',case,'--dma','--batch','--profile','native',
             '--debug-shell','--poweroff-after-validation','--timeout',
             '90' if case=='no-fec' else '420','--output',str(out)]
        with (a.output/(case+'.log')).open('x') as log:
            rc=subprocess.run(cmd,cwd=REPO,stdout=log,stderr=subprocess.STDOUT).returncode
        result=json.loads((out/'recovery-result.json').read_text()) if (out/'recovery-result.json').exists() else {'status':'INCONCLUSIVE'}
        records.append(dict(case=case,status=result['status'],runner_returncode=rc,command=cmd,result=str(out/'recovery-result.json')))
        (a.output/'result.json').write_text(json.dumps(dict(cases=records),indent=2)+'\n')
        print(case,result['status'],flush=True)
        expected='PASS_CLEAN' if case=='clean' else 'EXPECTED_VERITY_REJECTION' if case=='no-fec' else 'PASS_RECOVERED'
        if rc or result['status']!=expected:
            print('Stopped: prerequisites/evidence gate did not pass; unrun cases are not counted.',flush=True)
            return 1
    return 0


if __name__=='__main__':raise SystemExit(main())
