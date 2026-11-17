#!/usr/bin/env python3
"""Assess a clean persistent-FSW baseline without rereading guest ELF contents."""
import argparse
import ast
import json
import os
from pathlib import Path
import subprocess
import sys

import generation as g
sys.path.insert(0,str(g.ROOT/'experiments/cm5-phase10j'))
from events import summarize


def read_json(path, fallback=None):
    return json.loads(path.read_text()) if path.exists() else fallback


def timings(run):
    path=run/'v8/host-timeline.jsonl'
    rows=[json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
    t={x['event']:x['host_seconds'] for x in rows}
    pairs=dict(launch_to_root=('qemu_launch','verified_root_mount'),
               launch_to_readiness=('qemu_launch','userspace_validated'),
               control_upload=('upload_start','upload_verified'),
               qemu_lifetime=('qemu_launch','qemu_exit'))
    return dict(host_seconds={k:t[b]-t[a] for k,(a,b) in pairs.items() if a in t and b in t},
                transfer=next((x for x in rows if x['event']=='upload_start'),{}))


def execution_proven(fsw, generation_id):
    proof=fsw.get('execution_evidence',{})
    return (fsw.get('execution_mode')==g.MODE and fsw.get('generation_id')==generation_id and
            fsw.get('executable')==g.ELF_PATH and proof.get('exe')==g.ELF_PATH and
            proof.get('command_line')==g.ELF_PATH and proof.get('executable_map_present') is True and
            fsw.get('uid')==0 and fsw.get('executable_prehash') is False and
            fsw.get('elf_uploaded') is False and fsw.get('ram_fallback') is False)


def function_outcomes(boot, users, fsw, counts):
    ready=[u for u in users if u.get('target')=='active' and u.get('pid1')=='systemd']
    launched=bool(fsw.get('execution_evidence'))
    status=lambda reached, passed: ('PASS' if passed else 'FAIL') if reached else 'NOT_REACHED'
    return dict(kernel=status('kernel_entry' in boot,bool(boot.get('kernel_entry'))),
        verified_root=status(bool(boot.get('kernel_entry')),bool(boot.get('os_mount'))),
        userspace=status(bool(boot.get('os_mount')),len(ready)>=2),
        fsw_filesystem=('UNKNOWN' if boot.get('os_mount') and not users else
            status(bool(boot.get('os_mount')),any(u.get('fsw','').startswith('/dev/mapper/cm5_fsw_verified ext4 ro,') for u in users))),
        executable_launch=status(bool(ready),launched),
        dynamic_loading=('FAIL' if fsw.get('failure_stage')=='dynamic-loading' else 'PASS' if launched else 'NOT_REACHED'),
        initialization=status(launched,counts.get('initializations')==20 and counts.get('tasks_created')==11 and counts.get('tasks_started')==10),
        housekeeping=status(launched,counts.get('housekeeping',0)>0),
        internal_packet_path=status(launched,all(counts.get(k,0)>0 for k in ['packet_receipts','packet_routes','queue_items','tx_dumps'])),
        sampled_libc=status(bool(users),all(u.get('libc_call') for u in ready) and bool(ready)),
        external_peripheral_delivery='NOT_EXERCISED_WITH_WORKING_FIXTURE',
        full_filesystem_integrity='NOT_EXERCISED_OPERATIONAL_ON_DEMAND',
        fec_correction='NOT_EXERCISED_CLEAN_BASELINE',
        application_exit=status(launched,fsw.get('exit_status')==124 and not fsw.get('watchdog_killed')),
        shutdown=status(bool(boot),bool(boot.get('normal_poweroff'))))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True)
    parser.add_argument('--generation',type=Path,required=True)
    parser.add_argument('--generation-sha256',required=True)
    parser.add_argument('--phase10l-reference',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.resolve().is_relative_to(g.ROOT):parser.error('private evidence only')
    os.umask(0o077);args.output.mkdir(parents=True,exist_ok=False,mode=0o700)
    manifest=g.load(args.generation,args.generation_sha256,verify_image=False)
    outer=read_json(args.run/'comparison.json',{})
    boot=read_json(args.run/'v8/result.json',{})
    fsw=read_json(args.run/'v8/fsw-result.json',{})
    users=read_json(args.run/'v8/userspace.json',[])
    raw=(args.run/'fsw-output.log').read_bytes() if (args.run/'fsw-output.log').exists() else b''
    events=summarize(raw.decode(errors='replace'));counts=events['counts']
    ready=[u for u in users if u.get('target')=='active' and u.get('pid1')=='systemd']
    image=g.artifact(manifest,'image').resolve()
    inputs=read_json(args.run/'v8/inputs-before.json',{})
    overlay=args.run/'emmc.qcow2'
    own=[]
    if overlay.exists():
        extents=json.loads(subprocess.check_output([str(g.ROOT/'build-arm64-phase1/qemu-img'),'map','--output=json',str(overlay)]))
        own=[x for x in extents if x['depth']==0 and x.get('present')]
    logs=next(p for p in manifest['partitions'] if p['partition']==6)
    lo,hi=logs['start']*512,(logs['start']+logs['sectors'])*512
    program=(args.run/'guest-workload.py').read_text() if (args.run/'guest-workload.py').exists() else ''
    tree=ast.parse(program)
    assignments=[x.targets[0].id for x in tree.body if isinstance(x,ast.Assign) and isinstance(x.targets[0],ast.Name)]
    checks=dict(
        pinned_generation=(boot.get('generation_id')==manifest['generation_id'] and
            inputs.get(str(image),{}).get('sha256')==manifest['artifacts']['image']['sha256']),
        original_and_sealed_unchanged=outer.get('software',{}).get('golden_unchanged') is True and boot.get('inputs_unchanged') is True,
        actual_verified_execution=execution_proven(fsw,manifest['generation_id']),
        no_elf_upload_or_prehash=('PAYLOAD' not in assignments and len(program)<20000 and
            'elf.read_bytes(' not in program and fsw.get('executable_prehash') is False),
        original_os_and_new_fsw_maps=bool(users) and all(g.maps_match(u,manifest) for u in users),
        readonly_mounts=bool(ready) and all(u['lower'].startswith('/dev/mapper/cm5_os_verified ext4 ro,') and
            (not u['fsw'] or u['fsw'].startswith('/dev/mapper/cm5_fsw_verified ext4 ro,')) for u in users) and
            all(u['fsw'].startswith('/dev/mapper/cm5_fsw_verified ext4 ro,') for u in ready),
        readiness_spacing=len(ready)>=2 and ready[-1]['uptime']-ready[0]['uptime']>=20,
        operational_scan_skipped=bool(users) and all(u.get('phase10l_boot',{}).get('profile_marker')=='operational' and
            'PHASE10L_OPERATIONAL' in (u['phase10l_boot'].get('os_log') or '') and not u['phase10l_boot'].get('scan_dd_log_exists') for u in users),
        initialization=counts['initializations']==20 and counts['tasks_created']==11 and counts['tasks_started']==10,
        housekeeping=counts['housekeeping']>=1,
        packet_path=all(counts[k]>=1 for k in ('packet_receipts','packet_routes','queue_items','tx_dumps')),
        timeout_contract=fsw.get('status')=='COMPLETE' and fsw.get('exit_status')==124 and not fsw.get('watchdog_killed'),
        no_application_crash=counts['crashes']==0,
        normal_shutdown=boot.get('normal_poweroff') is True and boot.get('returncode')==0 and not boot.get('timeout'),
        child_writes_only_logs=overlay.exists() and all(lo<=x['start'] and x['start']+x['length']<=hi for x in own))
    reference=read_json(args.phase10l_reference/'comparison.json',{})
    result=dict(status='PASS_CLEAN_VERIFIED_FSW' if all(checks.values()) else 'FAIL_CLEAN_VERIFIED_FSW',
        generation_id=manifest['generation_id'],generation_manifest_sha256=args.generation_sha256,
        checks=checks,outcomes=function_outcomes(boot,users,fsw,counts),events=counts,
        timing=dict(current=timings(args.run),phase10l=timings(args.phase10l_reference),
            current_outer_host_seconds=outer.get('timing',{}).get('host_elapsed_seconds'),
            phase10l_outer_host_seconds=reference.get('timing',{}).get('host_elapsed_seconds'),
            guest_monotonic_fsw_seconds=fsw.get('guest_elapsed_seconds'),qemu_virtual_seconds=None),
        execution_proof=fsw.get('execution_evidence'),failure_stage=fsw.get('failure_stage'),
        child_own_extents=own,elf_bytes_uploaded=0 if checks['no_elf_upload_or_prehash'] else None,
        corruption_injected=False,physical_equivalence=False)
    (args.output/'assessment.json').write_text(json.dumps(result,indent=2)+'\n')
    (args.output/'normalized-events.json').write_text(json.dumps(events,indent=2)+'\n')
    # This receipt binds observed baseline results to the already immutable
    # generation. Never rewrite the sealed manifest after a guest run.
    receipt=dict(schema='cm5-phase10m-baseline-receipt-v1',generation_id=manifest['generation_id'],
        generation_manifest_sha256=args.generation_sha256,assessment_sha256=g.file_sha(args.output/'assessment.json'),
        run=str(args.run.resolve()),status=result['status'])
    (args.output/'baseline-acceptance.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(result,indent=2))
    return 0 if all(checks.values()) else 1


if __name__=='__main__':sys.exit(main())
