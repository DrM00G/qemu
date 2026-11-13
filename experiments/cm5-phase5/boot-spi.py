#!/usr/bin/env python3
"""Provisional virt PCI host, real RP1/DW Linux drivers, disposable initramfs."""
import argparse
import json
from pathlib import Path
import subprocess

here = Path(__file__).resolve().parent
repo = here.parent.parent
p = argparse.ArgumentParser()
p.add_argument('--dtb', type=Path)
p.add_argument('--label', default='no-dt')
p.add_argument('--initrd', type=Path)
p.add_argument('--timeout', type=int, default=120)
a = p.parse_args()
out = here / 'artifacts'
qemu = repo / 'build-arm64-phase1/qemu-system-aarch64'
cmd = [str(qemu), '-machine', 'virt,highmem=off,gic-version=3', '-cpu',
       'cortex-a76', '-smp', '2', '-m', '1024', '-accel', 'tcg',
       '-display', 'none', '-monitor', 'none', '-serial', 'stdio',
       '-no-reboot', '-nic', 'none', '-device', 'rp1-pci,id=rp1,addr=1',
       '-device', 'ssi-test-slave,bus=spi,cs=0',
       '-kernel', str(Path.home() / 'cm5-phase3-kernel/build/arch/arm64/boot/Image'),
       '-initrd', str(a.initrd or out / 'guest/spi-initrd.gz'),
       '-append', 'console=ttyAMA0 rdinit=/init panic=-1 loglevel=7',
       '-trace', f'enable=dw_apb_ssi_*,file={out / (a.label + ".trace")}',
       '-trace', 'enable=rp1_msix', '-d', 'unimp,guest_errors',
       '-D', str(out / (a.label + '.unimplemented.log'))]
if a.dtb:
    cmd += ['-dtb', str(a.dtb.resolve())]
(out / (a.label + '.command.json')).write_text(json.dumps(cmd, indent=2) + '\n')
with (out / (a.label + '.serial.log')).open('xb') as serial:
    try:
        result = subprocess.run(cmd, stdin=subprocess.DEVNULL, stdout=serial,
                                stderr=subprocess.STDOUT, timeout=a.timeout)
        print('returncode:', result.returncode)
        if result.returncode:
            raise SystemExit(result.returncode)
    except subprocess.TimeoutExpired:
        print('guest timeout; evidence preserved')
        raise SystemExit(1)
