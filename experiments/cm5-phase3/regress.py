#!/usr/bin/env python3
"""Run a bounded scenario matrix, stop on failure, and preserve JSON/CSV evidence."""
import argparse
import csv
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

HERE = Path(__file__).resolve().parent
FIELDS = ['case', 'status', 'boot_success', 'kernel_boot', 'verified_root_mounted',
          'systemd_target', 'prototype_started', 'prototype_functions', 'prototype_sustained',
          'complete_os_recovery', 'complete_fsw_recovery', 'fec_correction_activity',
          'corruption_detected_without_fec', 'infrastructure_failure', 'timeout', 'evidence']


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--storage', type=Path, default=HERE / 'artifacts/storage-v1/manifest.json')
    p.add_argument('--cases', default='baseline,clean,os-fec,fsw-fec,fsw-no-fec',
                   help='Comma-separated unique cases; kernel-a is also available')
    p.add_argument('--kernel-root', type=Path, default=Path(os.environ.get('PHASE3_KERNEL_ROOT', str(Path.home() / 'cm5-phase3-kernel'))))
    p.add_argument('--memory', default='8192')
    p.add_argument('--cpus', default='4')
    p.add_argument('--timeout', default='2400')
    p.add_argument('--require-prototype', action='store_true')
    p.add_argument('--skip-full-os-scan', action='store_true')
    args = p.parse_args()
    cases = args.cases.split(',')
    allowed = {'baseline', 'kernel-a', 'clean', 'os-fec', 'fsw-fec', 'fsw-no-fec'}
    if not cases or len(cases) != len(set(cases)) or any(case not in allowed for case in cases):
        p.error('--cases must contain unique supported cases; statistical series are not implemented')
    manifest = json.loads(args.storage.read_text())
    if args.require_prototype and not manifest.get('prototype'):
        p.error('The selected storage has no prototype; prepare a new generation with --fsw-binary')
    directory = HERE / 'artifacts' / ('regression-' + time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:8])
    directory.mkdir(parents=True, exist_ok=False)
    rows = []
    print('Regression artifacts: ' + str(directory), flush=True)
    for case in cases:
        artifacts = directory / case
        if case == 'baseline':
            command = [sys.executable, str(HERE / 'accept-a.py'), '--accept', '--expected-page-size', '4096',
                       '--artifacts', str(artifacts), '--timeout', args.timeout, '--shutdown-timeout', '180']
        elif case == 'kernel-a':
            command = [str(HERE / 'boot-a.sh'), '--kernel', str(args.kernel_root / 'build/arch/arm64/boot/Image'),
                       '--kernel-config', str(args.kernel_root / 'build/.config'), '--artifacts', str(artifacts)]
        else:
            command = [sys.executable, str(HERE / 'run.py'), '--storage', str(args.storage), '--case', case,
                       '--kernel-root', str(args.kernel_root), '--memory', args.memory, '--cpus', args.cpus,
                       '--timeout', args.timeout, '--artifacts', str(artifacts)]
            if case == 'os-fec' and not args.skip_full_os_scan:
                command += ['--full-os-scan']
        print('Running ' + case, flush=True)
        with (directory / (case + '.log')).open('w') as output:
            rc = subprocess.run(command, stdout=output, stderr=subprocess.STDOUT).returncode
        filename = 'acceptance.json' if case in ('baseline', 'kernel-a') else 'result.json'
        files = list(artifacts.glob('*/' + filename))
        row = {name: None for name in FIELDS}
        row.update(case=case, status='FAIL_INFRASTRUCTURE', infrastructure_failure=True,
                   reason='No unique result file was produced', exit_code=rc)
        if len(files) == 1:
            observed = json.loads(files[0].read_text())
            if case in ('baseline', 'kernel-a'):
                guest_path = files[0].with_name('guest-result.json')
                guest = json.loads(guest_path.read_text()) if guest_path.exists() else {}
                row.update(status=observed['status'], kernel_boot=bool(guest.get('kernel')),
                           reason=observed.get('reason'),
                           systemd_target=guest.get('target') == 'active' if guest else None,
                           boot_success=observed['status'] == 'PASS',
                           infrastructure_failure=observed['status'] == 'FAIL_INFRASTRUCTURE',
                           timeout='timeout' in observed.get('reason', '').lower())
            else:
                row.update(observed)
            row['evidence'] = str(files[0])
        if rc != 0 and row['status'] == 'PASS':
            row.update(status='FAIL_INFRASTRUCTURE', infrastructure_failure=True, reason='Result and process exit disagree')
        rows.append(row)
        print(case + ': ' + row['status'], flush=True)
        if row['status'] != 'PASS' or rc != 0:
            # Do not run further faults after an inconclusive or failed scenario.
            break
    passed = len(rows) == len(cases) and all(row['status'] == 'PASS' for row in rows)
    summary = {'schema': 1, 'pass': passed, 'storage': str(args.storage.resolve()),
               'prototype_required': args.require_prototype, 'requested_cases': cases,
               'unexecuted_cases': cases[len(rows):], 'results': rows}
    (directory / 'regression.json').write_text(json.dumps(summary, indent=2) + '\n')
    with (directory / 'regression.csv').open('w') as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps({'pass': passed, 'results': str(directory / 'regression.json')}, indent=2))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
