#!/usr/bin/env python3
"""Build disposable initramfs from Phase 3; leaves validated inputs untouched."""
import importlib.util
import argparse
from pathlib import Path
import shutil
import subprocess

here = Path(__file__).resolve().parent
repo = here.parent.parent
p = argparse.ArgumentParser()
p.add_argument('--output', type=Path, default=here / 'artifacts/guest')
a = p.parse_args()
out = a.output.resolve()
out.mkdir(parents=True, exist_ok=False)
stage = out / 'stage'
if stage.exists():
    raise SystemExit('stage exists; preserve it or choose a fresh artifact directory')
shutil.copytree(repo / 'experiments/cm5-phase3/artifacts/initramfs-16k/unpacked',
                stage, symlinks=True)
shutil.copy2(here / 'guest-init.sh', stage / 'init')
(stage / 'init').chmod(0o755)
subprocess.run(['aarch64-linux-gnu-gcc', '-static', '-O2', '-Wall', '-Wextra',
                '-Werror', '-Wl,-z,max-page-size=65536',
                str(here / 'spi-diagnostic.c'), '-o', str(stage / 'spi-diagnostic')],
               check=True)
modules = Path.home() / 'cm5-phase3-kernel/modules/lib/modules'
for name in ('spi-dw.ko', 'spi-dw-mmio.ko', 'spidev.ko'):
    source, = modules.rglob(name)
    shutil.copy2(source, stage / name)
    subprocess.run(['aarch64-linux-gnu-strip', '--strip-debug', str(stage / name)],
                   check=True)
spec = importlib.util.spec_from_file_location('builder', repo / 'experiments/cm5-phase3/prepare-initramfs.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
builder.pack(stage, out / 'spi-initrd.gz')
