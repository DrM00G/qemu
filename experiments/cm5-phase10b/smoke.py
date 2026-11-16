#!/usr/bin/env python3
"""Unmodified physical V8 kernel/initramfs smoke. Local experiment, no firmware."""
import argparse
import json
import os
from pathlib import Path
import re
import selectors
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO/'experiments/cm5-phase10a'))
from preboot import identity, USER_BYTES


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--profile', choices=('gpex', 'native'), default='gpex')
    p.add_argument('--timeout', type=int, default=120)
    a = p.parse_args()
    os.umask(0o077)
    out = a.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    assets = Path('/home/aweso/cm5-phase10-private/physical-boot/boot-assets')
    golden = Path('/home/aweso/cm5-v8-lab/golden/cm5-emmc-userarea.img')
    result = dict(status='SKIPPED_WITH_REASON', reason='missing private inputs', profile=a.profile)
    required = list(assets.glob('*')) + [golden, REPO/'build-arm64-phase1/qemu-system-aarch64']
    if not golden.is_file() or not (assets/'kernel_2712.img').is_file() or not (assets/'initramfs_2712-osverified-v8').is_file():
        (out/'result.json').write_text(json.dumps(result, indent=2))
        return
    inputs = {str(f): identity(f) for f in required if f.is_file()}
    assert inputs[str(golden)]['bytes'] == USER_BYTES
    (out/'inputs-before.json').write_text(json.dumps(inputs, indent=2)+'\n')
    lab = Path('/home/aweso/cm5-v8-lab/phase10b')/out.name
    lab.mkdir(parents=True, exist_ok=False)
    overlay = lab/'emmc.qcow2'
    subprocess.run([str(REPO/'build-arm64-phase1/qemu-img'), 'create', '-f', 'qcow2',
                    '-F', 'raw', '-b', str(golden), str(overlay)], check=True)
    machine = 'cm5io-dev,native-emmc=on,native-mip=on'
    if a.profile == 'native':
        machine += ',native-pcie=on'
    original = (assets/'cmdline_2712-osverified-v8.txt').read_text().strip()
    # Console routing/diagnostics only; root/verity command line is retained.
    append = original + ' console=ttyAMA0,115200 earlycon=pl011,mmio32,0x107d001000 ignore_loglevel'
    cmd = [str(REPO/'build-arm64-phase1/qemu-system-aarch64'), '-M', machine,
           '-cpu', 'cortex-a76', '-accel', 'tcg', '-smp', '4', '-m', '2048',
           '-display', 'none', '-monitor', 'none', '-serial', 'stdio', '-nic', 'none',
           '-no-reboot', '-kernel', str(assets/'kernel_2712.img'),
           '-initrd', str(assets/'initramfs_2712-osverified-v8'), '-append', append,
           '-drive', f'file={overlay},format=qcow2,if=none,id=native',
           '-device', 'emmc,drive=native,boot-partition-size=0,rpmb-partition-size=0',
           '-trace', 'enable=bcm2712_sdhci_*', '-trace', 'enable=bcm2712_mip_*',
           '-d', 'unimp,guest_errors', '-D', str(out/'hardware.log')]
    if a.profile == 'native':
        cmd += ['-trace', 'enable=bcm2712_pcie_*']
    (out/'command.json').write_text(json.dumps(cmd, indent=2)+'\n')
    started = time.monotonic()
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            stdin=subprocess.DEVNULL)
    (out/'process.json').write_text(json.dumps(dict(pid=proc.pid, started_utc=time.time()), indent=2)+'\n')
    selector = selectors.DefaultSelector()
    selector.register(proc.stdout, selectors.EVENT_READ)
    timed_out = False
    try:
        with (out/'serial.log').open('wb') as log:
            while selector.get_map():
                if time.monotonic()-started > a.timeout:
                    timed_out = True
                    break
                for key, _ in selector.select(.2):
                    data = os.read(key.fileobj.fileno(), 65536)
                    if data:
                        log.write(data)
                        log.flush()
                    else:
                        selector.unregister(key.fileobj)
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.wait()
        selector.close()
    serial = (out/'serial.log').read_text(errors='replace')
    patterns = dict(kernel_entry=r'Booting Linux|Linux version 6\.18\.50',
        driver_probe=r'1000fff000\.mmc|brcm-pcie',
        emmc_card=r'mmc0: new .*MMC card|mmcblk0:',
        partitions=r'mmcblk0: p1 p2 p3', initramfs_init=r'Run /init as init process',
        os_on_dm=r'EXT4-fs \(dm-[0-9]+\): mounted filesystem a3680812-',
        verified_root=r'CM5 V8 LATE.*PASS: OS and FSW verified',
        userspace=r'systemd\[1\]|Welcome to Debian')
    milestones = {name: bool(re.search(pattern, serial)) for name, pattern in patterns.items()}
    after = {str(f): identity(f) for f in required if f.is_file()}
    result = dict(status='BOOT_MILESTONES_OBSERVED' if milestones['userspace'] and milestones['verified_root'] else 'BLOCKED',
        profile=a.profile, firmware='NOT_EXECUTED_DIRECT_KERNEL',
        dtb='generated virtual DT; captured DTB NOT passed to guest',
        command_line_departure='append ttyAMA0/earlycon/ignore_loglevel only',
        milestones=milestones, last_observed_milestone=next((k for k in reversed(milestones) if milestones[k]), 'NONE'),
        qemu_returncode=proc.returncode, timeout=timed_out,
        timeout_interpretation='inconclusive beyond observed milestones' if timed_out else None,
        kernel_panic='Kernel panic' in serial, wall_seconds=time.monotonic()-started,
        inputs=inputs, inputs_unchanged=inputs == after, overlay=identity(overlay))
    (out/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    (out/'summary.txt').write_text(json.dumps({k:v for k,v in result.items() if k not in ('inputs','overlay')}, indent=2)+'\n')
    print((out/'summary.txt').read_text())


if __name__ == '__main__':
    main()
