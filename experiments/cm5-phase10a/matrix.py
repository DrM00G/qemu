#!/usr/bin/env python3
"""Persistent synthetic BOOT fault evidence. NOT full V8 guest tests."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil

from preboot import DEFAULTS, identity, probe, summary
from test_preboot import fixture


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    os.umask(0o077)
    a.output.mkdir(parents=True, exist_ok=False)
    golden = a.output/'synthetic-golden.raw'
    locations = fixture(golden)
    golden.chmod(0o400)
    before = identity(golden)
    cases = [('clean', None, None, 'UNSUPPORTED', 'HEADERS_VALIDATED'),
             ('corrupt-mbr', 510, b'\0\0', 'INVALID_LAYOUT', 'PARTITION_TABLE')]
    for role in ('kernel', 'initramfs', 'dtb'):
        entry = locations[DEFAULTS[role]]
        cases.append(('missing-'+role, entry['entry'], b'\xe5', 'SELECTED_FILE_UNAVAILABLE', 'SELECTED_FILES'))
        cases.append(('corrupt-'+role, entry['offset'], bytes(64), 'INVALID_IMAGE', 'SELECTED_FILES'))
    cases += [('outside-read-set', (2048+4999)*512, b'\xff'*512, 'UNSUPPORTED', 'HEADERS_VALIDATED'),
              ('kernel-body-unvalidated', locations[DEFAULTS['kernel']]['offset']+100,
               b'\xff', 'UNSUPPORTED', 'HEADERS_VALIDATED')]
    results = []
    clean_reads = None
    for name, offset, replacement, expected, stage in cases:
        out = a.output/name
        out.mkdir()
        overlay = out/'emmc.raw'
        shutil.copyfile(golden, overlay)
        corruptions = []
        if offset is not None:
            with overlay.open('r+b') as f:
                f.seek(offset)
                previous = f.read(len(replacement))
                f.seek(offset)
                f.write(replacement)
            corruptions.append(dict(offset=offset, length=len(replacement), operation='replace-bytes',
                physical_guest_sectors=list(range(offset//512, (offset+len(replacement)+511)//512)),
                before_sha256=hashlib.sha256(previous).hexdigest(),
                after_sha256=hashlib.sha256(replacement).hexdigest()))
        r = probe(overlay)
        r.update(golden=before, overlay=identity(overlay), corruptions=corruptions,
                 fixture='synthetic FAT16 small unit fixture, NOT full-size captured V8 disk',
                 expected_status=expected, expected_stage=stage,
                 golden_unchanged=identity(golden) == before)
        r['test_passed'] = r['status'] == expected and r['stage'] == stage and r['golden_unchanged']
        if name == 'clean':
            clean_reads = r['reads']
        if name == 'outside-read-set':
            r['fault_intersects_clean_proxy_reads'] = any(
                x['offset'] < offset+len(replacement) and offset < x['offset']+x['returned'] for x in clean_reads)
            r['test_passed'] &= not r['fault_intersects_clean_proxy_reads']
        (out/'result.json').write_text(json.dumps(r, indent=2)+'\n')
        (out/'summary.txt').write_text(summary(r))
        results.append(dict(case=name, test_passed=r['test_passed'], status=r['status'], stage=r['stage']))
    result = dict(status='PASS' if all(r['test_passed'] for r in results) else 'FAIL',
                  evidence='HOST_PROXY_SYNTHETIC_ONLY', cases=results)
    (a.output/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    (a.output/'summary.txt').write_text('\n'.join(f"{r['case']}: {r['status']} at {r['stage']} (test={r['test_passed']})" for r in results)+'\n')
    print(json.dumps(result, indent=2))
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
