#!/usr/bin/env python3
"""Reproduce synthetic execution + real Phase10C runner gates, with fresh run IDs."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

import handoff as h
from block_reader import BIN, REPO, run


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--control-pipes',action='store_true')
    p.add_argument('--work',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    work=h.private_dir(a.work)
    out=a.output.resolve(); out.mkdir(parents=True,exist_ok=False)
    source=Path(__file__).parent
    # Freeze public harness sources privately before execution.
    snapshot=work/'sources'; snapshot.mkdir()
    for path in [*source.glob('*.py'),source/'synthetic-kernel.S', REPO/'experiments/cm5-phase10c/run.py']:
        target=snapshot/(path.parent.name+'-'+path.name)
        target.write_bytes(path.read_bytes())
    with (out/'loader-smoke.log').open('xb') as log:
        subprocess.run([sys.executable,str(source/'synthetic_launch.py'),'--work',str(work/'fixture')],
                       stdout=log,stderr=subprocess.STDOUT,check=True)
    results=[]
    for case in ('clean','mbr'):
        private=work/case; private.mkdir()
        overlay=private/'emmc.qcow2'
        run([BIN/'qemu-img','create','-f','qcow2','-F','raw','-b',work/'fixture/base.raw',overlay])
        if case=='mbr':
            run([BIN/'qemu-io','-f','qcow2','-c','write -P 0 510 2',overlay])
        output=out/(out.name+'-'+case)
        cmd=[sys.executable,str(REPO/'experiments/cm5-phase10c/run.py'),'--dma','--batch','--profile','native',
             '--boot-selection-policy','emmc-only','--boot-overlay',str(overlay),
             '--boot-expected',str(work/'fixture/lab-baseline.json'),'--timeout','15','--output',str(output)]
        if a.control_pipes:
            cmd += ['--control-pipes']
        h.write_report(private/'runner-command.json',cmd)
        with (out/(case+'.log')).open('xb') as log:
            proc=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT)
        result=json.loads((output/'result.json').read_text())
        if case=='clean':
            assert proc.returncode==0 and result['returncode']==0 and not result['timeout']
            assert b'PHASE10F_SELECTED_SYNTHETIC_KERNEL_EXECUTED' in (output/'serial.log').read_bytes()
            selection=json.loads(Path(result['boot_selection_report']).read_text())
            command=json.loads(Path(selection['launch']['command_record']).read_text())
            assert command[command.index('-kernel')+1]==selection['exports']['kernel']['path']
            assert command[command.index('-initrd')+1]==selection['exports']['initramfs']['path']
            assert str(overlay) in command[command.index('-drive')+1]
            assert selection['process']['launched'] and selection['process']['returncode']==0
        else:
            assert proc.returncode==1 and result['status']=='BOOT_SELECTION_STOPPED'
            assert result['selection_status']=='INVALID_LAYOUT' and not result['process']['launched']
            assert not (output/'process.json').exists()
        results.append(dict(case=case,status='PASS',runner_returncode=proc.returncode,result=str(output/'result.json')))
    result=dict(status='PASS',cases=results,linux_boot=False,private_work=str(work))
    h.write_report(out/'result.json',result)
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
