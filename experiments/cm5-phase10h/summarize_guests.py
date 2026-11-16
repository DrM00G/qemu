#!/usr/bin/env python3
"""Export selected nonproprietary acceptance fields; keep raw guest logs private."""
import argparse
import hashlib
import json
from pathlib import Path


def summarize(root, name):
    directory = root/name
    if not (directory/'result.json').exists():
        return dict(name=name, status='NOT_RUN_OR_INCOMPLETE')
    result = json.loads((directory/'result.json').read_text())
    run = Path(result['run'])
    native = json.loads((directory/'native-report/result.json').read_text())
    provenance = json.loads((directory/'provenance/provenance.json').read_text())
    metrics = json.loads((directory/'metrics.json').read_text())
    original = json.loads((run/'result.json').read_text())
    recovery = json.loads((run/'recovery-result.json').read_text())
    users = json.loads((run/'userspace.json').read_text())
    row = dict(name=name,status=result['status'],speed_hz=result['speed_hz'],
               execution_clock=result['execution_clock'],
               native_checks=native['checks'],provenance_checks=provenance['checks'],
               recovery_checks=recovery['checks'],
               strict_spi=dict(status=native['framing']['status'],
                   messages=native['framing']['expected_messages'],
                   cs_segments=len(native['framing']['segments']),
                   error_count=len(native['framing']['errors'])),
               kernel_sha256=metrics['provenance']['selected_files']['kernel']['sha256'],
               initramfs_sha256=metrics['provenance']['selected_files']['initramfs']['sha256'],
               executable_sha256=provenance['qemu_executable']['sha256'],
               command_sha256=provenance['actual_qemu_arguments_sha256'],
               runtime_dt_sha256=sorted(set(metrics['provenance']['runtime_dt'])),
               boot_order_confirmation=metrics['provenance']['boot_order_confirmation'],
               shutdown_returncode=original['returncode'],wall_seconds=original['wall_seconds'],
               inputs_unchanged=original['inputs_unchanged'],
               active_observations=[dict(uptime_seconds=u['uptime'],pid1=u['pid1'],
                   os_verity_valid=u['os_status'].endswith(' V'),
                   fsw_verity_valid=u['fsw_status'].endswith(' V'),
                   os_fec_roots2='fec_roots 2' in u['os_table'],
                   fsw_fec_roots2='fec_roots 2' in u['fsw_table'],
                   logs_fsync_readback=u['logs_fsync_readback'])
                   for u in users if u['target']=='active'],
               notifications=metrics['interrupts']['notifications'],
               mip_deliveries=metrics['interrupts']['mip_deliveries'],
               synthetic_fixture=metrics['fixture']['identity'],
               workload_definition_sha256=metrics['workload']['definition_sha256'],
               physical_measurements=False)
    if name=='smp-stress':
        observations = [u.get('phase10h_smp') for u in users]
        counts = {w['result']['loops'] for o in observations if o for w in o['workers']
                  if w.get('result')}
        expected = {}
        payload = bytes(range(256))*16
        for i in range(max(counts, default=0)+1):
            digest = hashlib.sha256(payload).digest()
            if i in counts:
                expected[i] = digest.hex()
            payload = digest*128
        validation = []
        for o in observations:
            workers = []
            if o:
                for w in o['workers']:
                    r = w.get('result')
                    if not r:
                        workers.append(dict(status='FAIL', reason='no worker result'))
                        continue
                    before, after = o.get('before_spi_monotonic_ns'), o['after_spi_monotonic_ns']
                    overlap = max(0, min(r['end_monotonic_ns'],after)-
                                  max(r['start_monotonic_ns'],before)) if before else 0
                    checks = dict(exit_zero=w['returncode']==0, progress=r['loops']>0,
                                  affinity=r['affinity']==[r['cpu']],
                                  checksum=r['digest']==expected[r['loops']], overlap=overlap>0)
                    workers.append(dict(cpu=r['cpu'],checks=checks,
                        overlap_guest_monotonic_ns=overlap,
                        covers_observer_interval=bool(before and r['start_monotonic_ns']<=before
                                                     and r['end_monotonic_ns']>=after),
                        status='PASS' if all(checks.values()) else 'FAIL'))
            validation.append(dict(workers=workers,status='PASS' if len(workers)==3 and
                                   all(w['status']=='PASS' for w in workers) else 'FAIL'))
        row['stress_observations'] = observations
        row['stress_validation'] = validation
        threads = root/'smp-stress-threads.json'
        if threads.exists():row['host_tcg_threads'] = json.loads(threads.read_text())['threads']
    return row


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--private-root', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    rows = [summarize(args.private_root, n) for n in
            ('baseline-a','baseline-b','baseline-c','smp-stress')]
    args.output.write_text(json.dumps(dict(schema=1,runs=rows),indent=2)+'\n')
    print([(r['name'],r['status']) for r in rows])


if __name__=='__main__':
    main()
