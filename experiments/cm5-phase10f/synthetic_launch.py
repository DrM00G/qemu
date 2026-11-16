#!/usr/bin/env python3
"""Actual QEMU loader smoke test; synthetic code, no Linux/systemd claim."""
import argparse
import gzip
import json
import subprocess
from pathlib import Path

from block_reader import BIN, run
import handoff as h
from test_handoff import fixture


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--work',type=Path,required=True)
    a = p.parse_args()
    work = h.private_dir(a.work)
    src = Path(__file__).with_name('synthetic-kernel.S')
    run(['aarch64-linux-gnu-as','-o',work/'kernel.o',src])
    run(['aarch64-linux-gnu-objcopy','-O','binary',work/'kernel.o',work/'kernel.bin'])
    raw = work/'base.raw'
    locations, expected, files = fixture(raw,payloads={'kernel.img':gzip.compress((work/'kernel.bin').read_bytes(),mtime=0)})
    # QEMU's eMMC model requires a power-of-two capacity for this tiny fixture.
    with raw.open('r+b') as stream:
        stream.truncate(4*1024*1024)
    h.write_report(work/'lab-baseline.json',expected)
    overlay = work/'emmc.qcow2'
    run([BIN/'qemu-img','create','-f','qcow2','-F','raw','-b',raw,overlay])
    selection_work = work/'selection'; selection_work.mkdir()
    report,buffers = h.select(overlay,selection_work,expected)
    h.write_report(work/'selection.json',report)
    if report['status'] != 'SELECTED':
        raise RuntimeError(report)
    h.export(report,buffers,work/'exports')
    exports = h.verify_launch(report,overlay)
    cmd = [str(BIN/'qemu-system-aarch64'),'-M','cm5io-dev,native-emmc=on,native-mip=on,native-pcie=on,emmc-dma=on',
           '-accel','tcg','-cpu','cortex-a76','-smp','4','-m','2048','-display','none','-monitor','none',
           '-serial','stdio','-nic','none','-no-reboot','-kernel',exports['kernel']['path'],
           '-initrd',exports['initramfs']['path'],'-append',buffers['cmdline'].decode().strip(),
           '-drive',f'file={overlay},format=qcow2,if=none,id=native',
           '-device','emmc,drive=native,boot-partition-size=0,rpmb-partition-size=0,x-cmd23-read-batch=on']
    h.write_report(work/'command.json',cmd)
    result = subprocess.run(cmd,capture_output=True,timeout=15)
    (work/'serial.log').write_bytes(result.stdout+result.stderr)
    report['process'] = dict(launched=True,returncode=result.returncode)
    report['synthetic_execution'] = b'PHASE10F_SELECTED_SYNTHETIC_KERNEL_EXECUTED' in result.stdout
    report['linux_boot'] = False
    report['kernel_and_initramfs_supplied_to_QEMU'] = True
    report['initramfs_executed'] = False
    h.write_report(work/'selection.json',report)
    # Actual gate negative control: mutate same disk AFTER previous QEMU has exited.
    run([BIN/'qemu-io','-f','qcow2','-c','write -P 0 510 2',overlay])
    negative_work = work/'negative'; negative_work.mkdir()
    failed,empty = h.select(overlay,negative_work,expected)
    h.write_report(negative_work/'selection.json',failed)
    assert failed['status']=='INVALID_LAYOUT' and not empty and not failed['process']['launched']
    assert report['synthetic_execution'] and result.returncode==0
    print(json.dumps(dict(status='PASS',synthetic_executed=True,linux_boot=False,
                         observed_BOOT_fault_prevents_launch=True,private_work=str(work)),indent=2))


if __name__=='__main__':
    main()
