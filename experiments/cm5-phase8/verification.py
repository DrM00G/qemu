#!/usr/bin/env python3
"""Recheck retained OS evidence without repeating the guest workload.

Keep the original result.json. Kernel correction messages may appear between a
digest marker and its digest; dmsetup's current status is simply 'verity V'.
"""
import argparse
import json
from pathlib import Path
import re


def os_checks(serial, corrupt):
    expected = re.search(r'OS_VERITY_EXPECTED=([0-9a-f]{128})', serial)
    region = serial.split('OS_VERITY_DIGEST', 1)[-1].split('OS_VERITY_EXPECTED', 1)[0]
    checks = dict(
        native_os_lower='/dev/mapper/cm5-os /newroot/media/root-ro ext4 ro,' in serial,
        os_verity_read=bool(expected and re.search(
            r'^' + expected[1] + r'\s+-\s*$', region, re.M)),
        os_verity_valid=bool(re.search(r'0 20971520 verity V\b', serial)))
    if corrupt:
        checks['kernel_fec_correction'] = bool(re.search(
            r'verity(?:-fec)?:.*FEC 0: corrected [1-9][0-9]* errors', serial))
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    args = parser.parse_args()
    result = json.loads((args.run / 'result.json').read_text())
    if not result.get('os_verity'):
        parser.error('requires an actual OS verity run')
    serial = (args.run / 'serial.log').read_text()
    result['checks'].update(os_checks(serial, result.get('os_corrupt_block_zero')))
    result['status'] = 'PASS' if all(result['checks'].values()) else 'FAIL'
    result['rechecked_from_retained_evidence'] = True
    with (args.run / 'result-rechecked.json').open('x') as stream:
        stream.write(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result['status'] == 'PASS' else 1)


if __name__ == '__main__':
    main()
