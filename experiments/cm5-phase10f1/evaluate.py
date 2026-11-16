#!/usr/bin/env python3
"""Independent selected-byte/argv/runtime provenance evaluator, local only."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'cm5-phase10f'))
import handoff as h


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',type=Path,required=True)
    p.add_argument('--native-report',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    run=json.loads((a.run/'result.json').read_text())
    baseline=json.loads((a.run/'recovery-result.json').read_text())
    native=json.loads(a.native_report.read_text())
    selection_path=Path(run['boot_selection_report']);s=json.loads(selection_path.read_text())
    command_path=Path(s['launch']['command_record']);cmd=json.loads(command_path.read_text())
    users=json.loads((a.run/'userspace.json').read_text())
    runtime=[u['boot_handoff_runtime'] for u in users if 'boot_handoff_runtime' in u]
    proc=json.loads((a.run/'process.json').read_text())
    selected_hashes={k:s['files'][v]['sha256'] for k,v in s['selected'].items()}
    checks=dict(selected=s['status']=='SELECTED' and s['selection_complete'],
        exact_exports=all(h.identity(Path(m['path']))==m for m in s['exports'].values()),
        selected_kernel_argv=cmd[cmd.index('-kernel')+1]==s['exports']['kernel']['path'],
        selected_initramfs_argv=cmd[cmd.index('-initrd')+1]==s['exports']['initramfs']['path'],
        same_overlay=cmd[cmd.index('-drive')+1].startswith('file='+s['launch']['overlay']+',format=qcow2,'),
        captured_kernel=selected_hashes['kernel']=='154f0ea1e14bb1075077dfd1bdc63c1502bc0b17b0354628d515b4fbd3a4198d',
        captured_initramfs=selected_hashes['initramfs']=='fcaade1e3aab0d79a51a170f556d25d0d1476bc17518099de54f5ebe16feab5b',
        original_kernel_entry=run['kernel_entry'],native_emmc=run['emmc_partitions'],
        original_initramfs_executes=run['initramfs'] and not run['diagnostic_copy'],
        verified_userspace=run['status']=='PASS' and baseline['status']=='PASS_CLEAN',
        strict_native_spi=native['status']=='PASS',
        persisted_logs=baseline['checks']['host_logs_persistence'],
        runtime_dt_observed=len(runtime)>=2 and all(r['fdt_sha256'] for r in runtime),
        runtime_cmdline_matches=bool(runtime) and all(r['chosen_bootargs_sha256']==s['launch']['effective_cmdline_sha256']
            and r['proc_cmdline_sha256']==s['launch']['effective_cmdline_sha256'] for r in runtime),
        normal_shutdown=run['returncode']==0 and not run['timeout'])
    r=dict(schema=1,status='PASS' if all(checks.values()) else 'PARTIAL',checks=checks,
        source_selection=str(selection_path),actual_qemu_arguments=str(command_path),
        actual_qemu_arguments_sha256=h.sha(command_path.read_bytes()),qemu_executable=proc['executable'],
        active_overlay=s['launch']['overlay'],backing_chain_at_selection=s['overlay_chain_before'],
        selected_files={k:dict(name=n,sha256=s['files'][n]['sha256'],size=s['files'][n]['size'],
                              validation=s['files'][n].get('validation')) for k,n in s['selected'].items()},
        exact_private_exports=s['exports'],dt=s['dt_handoff'],cmdline=s['launch'],
        runtime=runtime,physical_firmware_equivalence=False,
        firmware_scope=('documented-order fixture software BOOT proxy' if s.get('boot_source_trace') else 'explicit emmc-only software BOOT proxy')+'; generated compatible DT and documented config substitutions',
        evidence=dict(run=str(a.run.resolve()),native_report=str(a.native_report.resolve())))
    h.write_report(out/'provenance.json',r)
    print(json.dumps(dict(status=r['status'],checks=checks),indent=2))
    return 0 if r['status']=='PASS' else 1


if __name__=='__main__':sys.exit(main())
