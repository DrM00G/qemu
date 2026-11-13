#!/usr/bin/env python3
"""Generate a matching virt DT and append the experimental RP1 subset."""
import argparse
from pathlib import Path
import subprocess

here = Path(__file__).resolve().parent
repo = here.parent.parent
p = argparse.ArgumentParser()
p.add_argument('--ram', type=int, choices=(1024, 2048), default=1024)
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
out = a.output.resolve()
if out.exists():
    raise SystemExit(f'refusing to overwrite {out}')
out.parent.mkdir(parents=True, exist_ok=True)
base = out.with_suffix('.base.dtb')
dts = out.with_suffix('.dts')
subprocess.run([str(repo / 'build-arm64-phase1/qemu-system-aarch64'),
                '-machine', f'virt,highmem=off,gic-version=3,dumpdtb={base}',
                '-cpu', 'cortex-a76', '-smp', '2', '-m', str(a.ram),
                '-display', 'none', '-nic', 'none',
                '-device', 'rp1-pci,id=rp1,addr=1'], check=True)
dtc = Path.home() / 'cm5-phase3-kernel/build/scripts/dtc/dtc'
result = subprocess.run([str(dtc), '-I', 'dtb', '-O', 'dts', str(base)],
                        check=True, capture_output=True, text=True)
dts.write_text(result.stdout + '\n' + (here / 'rp1-virt.dtsi').read_text())
with out.with_suffix('.dtc.log').open('w') as log:
    subprocess.run([str(dtc), '-I', 'dts', '-O', 'dtb', str(dts), '-o', str(out)],
                   check=True, stderr=log)
print(out)
