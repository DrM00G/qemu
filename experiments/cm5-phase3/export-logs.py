#!/usr/bin/env python3
"""Read retained per-run LOGS overlays into reviewable files without mounting."""
import argparse
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('run', type=Path, help='Completed Phase 3 run directory containing result.json and logs.qcow2')
    args = p.parse_args()
    run = args.run.resolve(strict=True)
    if not (run / 'result.json').exists():
        p.error('Only completed runs may be exported; wait for the QEMU process and source-hash checks')
    destination = run / 'log-export'
    destination.mkdir(exist_ok=False)
    filesystem = destination / 'logs.ext4'
    subprocess.run([str(REPO / 'build-arm64-phase1/qemu-img'), 'convert', '-f', 'qcow2', '-O', 'raw',
                    str(run / 'logs.qcow2'), str(filesystem)], check=True)
    files = destination / 'files'
    files.mkdir()
    subprocess.run(['debugfs', '-R', f'rdump / {files}', str(filesystem)], check=True,
                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    heartbeat = files / 'heartbeat.jsonl'
    summary = {'run': str(run), 'files': sorted(path.name for path in files.iterdir()),
               'heartbeat_records': None}
    if heartbeat.exists():
        rows = [json.loads(line) for line in heartbeat.read_text().splitlines() if line.strip()]
        summary.update(heartbeat_records=len(rows), heartbeat_pids=sorted({row['pid'] for row in rows}),
                       first=rows[0] if rows else None, last=rows[-1] if rows else None)
    (destination / 'export.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
