#!/usr/bin/env python3
"""Dump the board-generated DT through QMP, without external DT injection."""
import argparse
import json
from pathlib import Path
import subprocess

here = Path(__file__).resolve().parent
repo = here.parent.parent
p = argparse.ArgumentParser()
p.add_argument('--output', type=Path, required=True)
p.add_argument('--machine', default='cm5io-dev')
a = p.parse_args()
out = a.output.resolve()
if out.exists():
    raise SystemExit(f'refusing to overwrite {out}')
commands = [dict(execute='qmp_capabilities'),
            dict(execute='dumpdtb', arguments=dict(filename=str(out))),
            dict(execute='quit')]
result = subprocess.run([str(repo / 'build-arm64-phase1/qemu-system-aarch64'),
    '-M', a.machine, '-m', '2048', '-display', 'none', '-serial', 'null',
    '-monitor', 'none', '-nic', 'none', '-S', '-qmp', 'stdio'],
    input=''.join(json.dumps(c) + '\n' for c in commands),
    capture_output=True, text=True, timeout=15)
result.check_returncode()
for line in result.stdout.splitlines():
    if line.startswith('{'):
        response = json.loads(line)
        if 'error' in response:
            raise RuntimeError(response['error'])
assert out.is_file()
dtc = Path.home() / 'cm5-phase3-kernel/build/scripts/dtc/dtc'
with out.with_suffix('.dtc.log').open('w') as errors:
    subprocess.run([str(dtc), '-I', 'dtb', '-O', 'dts', str(out), '-o',
                    str(out.with_suffix('.dts'))], check=True, stderr=errors)
print(out)
