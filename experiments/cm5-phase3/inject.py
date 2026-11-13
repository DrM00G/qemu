#!/usr/bin/env python3
"""Deterministic full-block XOR faults in a new QCOW2 overlay, never its base."""
import argparse
import hashlib
import json
from pathlib import Path
import random
import stat
import subprocess
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(HERE.parent / 'cm5-phase1'))
from launch import sha256


def inject(source, output, seed=7303, count=3, fec_blocks=None):
    source = source.resolve(strict=True)
    if not stat.S_ISREG(source.stat().st_mode) or source.stat().st_size % 4096:
        raise ValueError('Only 4 KiB-aligned regular raw image files may be faulted')
    output.mkdir(parents=True, exist_ok=False)
    original = sha256(source)
    blocks = source.stat().st_size // 4096
    rng = random.Random(seed)
    # One faulty block per interleaving group makes this a bounded roots=2 pilot.
    rounds = ((fec_blocks or blocks) + 252) // 253
    if blocks <= 2048 or not 1 <= count <= min(rounds, blocks - 2048):
        raise ValueError('Invalid fault count or image too small for bounded scattered faults')
    selected, groups = [], set()
    while len(selected) < count:
        block = rng.randrange(1024, blocks - 1024)
        if block not in selected and block % rounds not in groups:
            selected.append(block)
            groups.add(block % rounds)
    overlay = output / 'faults.qcow2'
    subprocess.run([str(REPO / 'build-arm64-phase1/qemu-img'), 'create', '-f', 'qcow2',
                    '-F', 'raw', '-b', str(source), str(overlay)], check=True, stdout=subprocess.DEVNULL)
    rows = []
    with source.open('rb') as stream:
        for index, block in enumerate(selected):
            offset = block * 4096
            stream.seek(offset)
            clean = stream.read(4096)
            corrupted = bytes(value ^ 0xff for value in clean)
            payload = output / f'xor-{index}.bin'
            payload.write_bytes(corrupted)
            subprocess.run([str(REPO / 'build-arm64-phase1/qemu-io'), '-f', 'qcow2', '-c',
                            f'write -s {payload.resolve()} {offset} 4096', str(overlay)],
                           check=True, stdout=subprocess.DEVNULL)
            actual = output / f'observed-{index}.bin'
            subprocess.run([str(REPO / 'build-arm64-phase1/qemu-img'), 'dd', '-f', 'qcow2',
                            # qemu-img dd count caps the input endpoint before skip.
                            '-O', 'raw', 'bs=4096', f'skip={block}', f'count={block + 1}',
                            'if=' + str(overlay), 'of=' + str(actual)],
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            observed = actual.read_bytes()
            if observed != corrupted or sum(a != b for a, b in zip(clean, observed)) != 4096:
                raise RuntimeError('Fault readback did not prove all 4096 bytes changed')
            rows.append({'block': block, 'offset': offset, 'length': 4096, 'xor_mask': 'ff',
                         'changed_bytes': 4096, 'clean_sha256': hashlib.sha256(clean).hexdigest(),
                         'corrupt_sha256': hashlib.sha256(observed).hexdigest()})
    after = sha256(source)
    if after != original:
        raise RuntimeError('Golden source changed during injection')
    manifest = {'seed': seed, 'algorithm': 'Python Random.randrange with distinct FEC interleaving groups',
                'source': str(source), 'source_sha256_before': original, 'source_sha256_after': after,
                'overlay': str(overlay.resolve()), 'fec_rounds': rounds, 'faults': rows}
    (output / 'injection.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--seed', type=int, default=7303)
    p.add_argument('--count', type=int, default=3)
    args = p.parse_args()
    print(json.dumps(inject(args.source, args.output, args.seed, args.count), indent=2))
