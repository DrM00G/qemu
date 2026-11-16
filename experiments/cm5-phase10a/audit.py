#!/usr/bin/env python3
"""Derive BOOT coverage from recorded card-read attempts, not simulated reads."""
import argparse
import hashlib
import json
from pathlib import Path


def coverage(ranges, start, end):
    attempted = []
    for lo, hi in sorted(ranges):
        lo, hi = max(lo, start), min(hi, end)
        if lo < hi:
            if attempted and lo <= attempted[-1][1]:
                attempted[-1][1] = max(attempted[-1][1], hi)
            else:
                attempted.append([lo, hi])
    gaps, cursor = [], start
    for lo, hi in attempted:
        if cursor < lo:
            gaps.append([cursor, lo])
        cursor = hi
    if cursor < end:
        gaps.append([cursor, end])
    return dict(attempted_ranges=attempted, never_attempted_ranges=gaps,
                attempted_unique_bytes=sum(hi-lo for lo, hi in attempted),
                never_attempted_bytes=sum(hi-lo for lo, hi in gaps),
                range_convention='physical guest byte offsets, half-open [start,end)')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--controls', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    controls = json.loads((a.controls/'result.json').read_text())
    a.output.mkdir(parents=True, exist_ok=False, mode=0o700)
    cases = []
    repo = Path(__file__).resolve().parents[2]
    source = repo/'hw/arm/cm5io-dev.c'
    for case in controls['cases']:
        provenance = Path(case['provenance'])
        r = json.loads(provenance.read_text())
        command = json.loads((provenance.parent/'command.json').read_text())
        boot = next(p for p in r['partitions'] if p['partition'] == 1)
        c = coverage(r['guest_read_trace']['attempted_ranges'], boot['start']*512,
                     (boot['start']+boot['sectors'])*512)
        cases.append(dict(case=r['case'], provenance=str(provenance), boot=c,
            kernel=dict(path=command[command.index('-kernel')+1],
                        sha256=r['inputs'][command[command.index('-kernel')+1]]),
            initramfs=dict(path=command[command.index('-initrd')+1],
                           sha256=r['inputs'][command[command.index('-initrd')+1]]),
            dtb=dict(origin='cm5io-dev generated device tree, subsequently fixed up by ARM loader',
                     source=str(source.relative_to(repo)), source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                     exact_runtime_dtb_hash=None),
            selected_boot_files=None,
            interpretation='No firmware file selection occurred. Trace covers card read attempts, not successful bytes returned.'))
    result = dict(evidence='COMPILED_QEMU_GUEST_READ_ATTEMPTS', cases=cases)
    (a.output/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    (a.output/'summary.txt').write_text('\n'.join(
        f"{c['case']}: BOOT attempted={c['boot']['attempted_unique_bytes']} bytes; "
        f"never attempted={c['boot']['never_attempted_bytes']} bytes; firmware file selection absent"
        for c in cases)+'\n')
    print((a.output/'summary.txt').read_text(), end='')


if __name__ == '__main__':
    main()
