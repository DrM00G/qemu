#!/usr/bin/env python3
"""Rerun unchanged Phase 9 controls and capture provenance. Local experiment."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import time

from preboot import USER_BYTES, identity, probe


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--cases', nargs='+', choices=('clean', 'os0', 'os1', 'no-fec', 'fsw0'),
                   default=['clean', 'os0', 'os1', 'no-fec', 'fsw0'])
    a = p.parse_args()
    repo = Path(__file__).resolve().parents[2]
    out = a.output.resolve()
    os.umask(0o077)
    out.mkdir(parents=True, exist_ok=False, mode=0o700)
    golden = Path.home() / 'cm5-v8-lab/golden/cm5-emmc-userarea.img'
    if not golden.is_file():
        (out/'result.json').write_text(json.dumps(dict(status='SKIPPED_WITH_REASON', reason='private golden missing')))
        (out/'summary.txt').write_text('SKIPPED_WITH_REASON: private golden missing; no guest launched\n')
        return
    before = identity(golden)
    (out/'golden-before.json').write_text(json.dumps(before, indent=2)+'\n')
    if before['bytes'] != USER_BYTES:
        raise RuntimeError('wrong user area size')
    geometry = probe(golden).get('partitions')
    records = []
    for case in a.cases:
        run = out / (out.name + '-' + case)
        command = ['sh', 'experiments/cm5-phase9/run.sh', case, run.name,
                   '--output', str(run)]
        started = time.monotonic()
        with (out/(case+'.log')).open('w') as log:
            rc = subprocess.run(command, cwd=repo, stdout=log, stderr=subprocess.STDOUT).returncode
        existing = json.loads((run/'result.json').read_text()) if (run/'result.json').exists() else {}
        lab = Path.home()/'cm5-v8-lab/phase9'/run.name
        # regress.py uses the last --output option's basename for its lab path.
        serial = (run/'serial.log').read_text(errors='replace') if (run/'serial.log').exists() else ''
        reads, attempted = [], 0
        trace = run/'peripheral.log'
        if trace.exists():
            with trace.open(errors='replace') as stream:
                for line in stream:
                    m = re.search(r'sdcard_read_block addr 0x([0-9a-f]+) size 0x([0-9a-f]+)', line)
                    if m:
                        offset, length = (int(v, 16) for v in m.groups())
                        attempted += length
                        reads.append((offset, offset+length))
        merged = []
        for lo, hi in sorted(set(reads)):
            if merged and lo <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], hi)
            else:
                merged.append([lo, hi])
        fault = run/'corruption.json'
        corruption = json.loads(fault.read_text()) if fault.exists() else None
        if corruption:
            corruption['physical_guest_sectors'] = list(range(corruption['offset']//512,
                (corruption['offset']+corruption['length']+511)//512))
        record = dict(case=case, command=command, runner_returncode=rc,
            wall_seconds=time.monotonic()-started, golden=before,
            total_user_area_bytes=before['bytes'], partitions=geometry,
            overlay=identity(lab/'emmc.qcow2') if (lab/'emmc.qcow2').exists() else None,
            overlay_identity_stage='after guest exit',
            overlay_format='qcow2 with raw golden backing',
            selected_boot_files=None, boot_source='Phase9 direct host kernel/initrd; generated DTB',
            process=dict(launched=bool(serial) or existing.get('returncode') is not None,
                         returncode=existing.get('returncode'),
                         timeout=(not existing['checks']['no_timeout']) if 'no_timeout' in existing.get('checks', {}) else None),
            stage='COLLECTED' if 'PHASE9_COLLECTION_DONE=' in serial else
                  'ROOT_REJECTED' if 'PHASE9_EXPECTED_ROOT_REJECTION' in serial else 'INCONCLUSIVE',
            corruption=corruption, phase9=existing,
            os_verity_fec={k: v for k, v in existing.get('checks', {}).items() if k.startswith(('os_', 'os1_', 'target_fec'))},
            fsw_verity_fec={k: v for k, v in existing.get('checks', {}).items() if k.startswith(('fsw_', 'target_fec'))},
            functional_diagnostics=existing.get('phase9', {}).get('diagnostic', []),
            inputs=json.loads((run/'inputs.json').read_text()) if (run/'inputs.json').exists() else None,
            guest_read_trace=dict(observer='QEMU sdcard_read_block BEFORE blk_pread',
                attempted_bytes=attempted, successful_bytes=None, attempted_ranges=merged,
                note='Trace proves attempted card reads; no per-read backend success event exists.'),
            backend_read_error_seen='sd_blk_read: read error on host side' in serial)
        (run/'provenance.json').write_text(json.dumps(record, indent=2)+'\n')
        (run/'summary.txt').write_text(f"{case}: {existing.get('status', 'INCONCLUSIVE')}; stage={record['stage']}; "
                                      f"qemu={record['process']['returncode']}; timeout={record['process']['timeout']}\n")
        records.append(dict(case=case, status=existing.get('status', 'INCONCLUSIVE'),
                            expected_status='EXPECTED_FAILURE' if case == 'no-fec' else 'PASS',
                            runner_returncode=rc, provenance=str(run/'provenance.json')))
        print(records[-1], flush=True)
    unchanged = identity(golden) == before
    result = dict(status='PASS' if unchanged and all(r['runner_returncode'] == 0 and
                  r['status'] == r['expected_status'] for r in records) else 'FAIL',
                  golden_unchanged=unchanged, cases=records)
    (out/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    (out/'summary.txt').write_text('\n'.join(f"{r['case']}: {r['status']}" for r in records) +
                                  f"\ngolden unchanged: {unchanged}\n")
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
