#!/usr/bin/env python3
"""Execute public full-system regression boots; exit 0 only if every case passes."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
import uuid

HERE = Path(__file__).resolve().parent


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--case', choices=('all', 'uefi', 'direct', 'overlay'), default='all')
    p.add_argument('--public-inputs', type=Path, default=HERE / 'artifacts/public-inputs')
    p.add_argument('--disk', type=Path, default=Path.home() / 'vm-images/ubuntu-arm64/ubuntu-24.04-server-cloudimg-arm64.img')
    p.add_argument('--timeout', default='900')
    args = p.parse_args()
    directory = HERE / 'artifacts' / ('regress-' + time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:8])
    directory.mkdir(parents=True)
    cases = ['uefi', 'direct', 'overlay'] if args.case == 'all' else [args.case]
    results = []
    for case in cases:
        command = [sys.executable, str(HERE.parent / 'cm5-phase1/launch.py'), '--accept',
                   '--timeout', args.timeout, '--shutdown-timeout', '120',
                   '--artifacts', str(directory / case), '--disk', str(args.disk)]
        if case != 'uefi':
            command += ['--kernel', str(args.public_inputs / 'Image'),
                        '--initramfs', str(args.public_inputs / 'initrd'),
                        '--kernel-config', str(args.public_inputs / 'kernel.config'),
                        '--expected-page-size', '4096', '--dump-dtb',
                        '--root-device', '/dev/vda' if case == 'overlay' else '/dev/vda1']
        if case == 'overlay':
            command += ['--disk', str(args.public_inputs / 'rootfs-10g.ext4'),
                        '--root-mode', 'overlay', '--root-fstype', 'ext4', '--root-flags', 'noload',
                        '--disk-size', 'keep']
        print('Running ' + case + '; artifacts: ' + str(directory), flush=True)
        with (directory / (case + '.log')).open('w') as stream:
            result = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT)
        acceptance_files = list((directory / case).glob('*/acceptance.json'))
        acceptance = json.loads(acceptance_files[0].read_text()) if len(acceptance_files) == 1 else {}
        passed = result.returncode == 0 and acceptance.get('status') == 'PASS'
        results.append({'case': case, 'pass': passed, 'exit_code': result.returncode,
                        'acceptance': str(acceptance_files[0]) if acceptance_files else None})
        print(f'{case}: {"PASS" if passed else "FAIL"}', flush=True)
    summary = {'pass': all(row['pass'] for row in results), 'results': results}
    (directory / 'regression.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))
    return 0 if summary['pass'] else 1


if __name__ == '__main__':
    sys.exit(main())
