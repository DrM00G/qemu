#!/usr/bin/env python3
"""Execute a distinct USB-selected synthetic payload. NOT Linux or USB hardware."""
import argparse
import gzip
import json
from pathlib import Path
import subprocess
import sys

import boot_policy as p
from block_reader import BIN, run
from test_handoff import fixture
h = p.h


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    a=parser.parse_args();work=h.private_dir(a.work)
    source=(p.HERE.parent/'cm5-phase10f/synthetic-kernel.S').read_text()
    sources={}; manifests={}; markers={}
    for name in ('emmc','usb'):
        stem=work/name;stem.mkdir()
        marker=f'PHASE10F2_{name.upper()}_SYNTHETIC_EXECUTED'
        markers[name]=marker.encode()
        (stem/'kernel.S').write_text(source.replace('PHASE10F_SELECTED_SYNTHETIC_KERNEL_EXECUTED',marker))
        run(['aarch64-linux-gnu-as','-o',stem/'kernel.o',stem/'kernel.S'])
        run(['aarch64-linux-gnu-objcopy','-O','binary',stem/'kernel.o',stem/'kernel.bin'])
        raw=stem/'base.raw'
        _,expected,_=fixture(raw,payloads={'kernel.img':gzip.compress((stem/'kernel.bin').read_bytes(),mtime=0)})
        with raw.open('r+b') as stream:stream.truncate(4*1024*1024)
        disk=stem/'disk.qcow2';run([BIN/'qemu-img','create','-f','qcow2','-F','raw','-b',raw,disk])
        sources[name]=disk;manifests[name]=expected
    selection=work/'selection';selection.mkdir()
    report,buffers=p.select(sources['emmc'],selection,manifests['emmc'],usb=sources['usb'],usb_expected=manifests['usb'])
    h.require(report['status']=='SELECTED' and report['boot_source_trace']['selected_source']=='usb-msd', 'INVALID_INPUT','USB priority failed')
    h.require(h.sha(buffers['kernel'])==manifests['usb']['kernel.img'] and
              h.sha(buffers['kernel'])!=manifests['emmc']['kernel.img'],'INVALID_IMAGE','source bytes conflated')
    h.export(report,buffers,work/'exports'); exports=h.verify_launch(report,sources['usb'])
    command=[str(BIN/'qemu-system-aarch64'),'-M','cm5io-dev,native-emmc=on,native-mip=on,native-pcie=on,emmc-dma=on',
             '-accel','tcg','-cpu','cortex-a76','-smp','4','-m','512','-display','none','-monitor','none',
             '-serial','stdio','-nic','none','-no-reboot','-kernel',exports['kernel']['path'],
             '-initrd',exports['initramfs']['path'],'-append',buffers['cmdline'].decode().strip(),
             '-drive',f"file={sources['emmc']},format=qcow2,if=none,id=native",'-device',
             'emmc,drive=native,boot-partition-size=0,rpmb-partition-size=0,x-cmd23-read-batch=on']
    h.write_report(work/'command.json',command)
    proc=subprocess.run(command,capture_output=True,timeout=20)
    (work/'serial.log').write_bytes(proc.stdout+proc.stderr)
    h.require(proc.returncode==0 and markers['usb'] in proc.stdout and markers['emmc'] not in proc.stdout,
              'INVALID_IMAGE','selected synthetic USB payload did not execute')
    h.write_report(work/'selection.json',report)
    result=dict(status='PASS',usb_selected_synthetic_payload_executed=True,linux_boot=False,
                physical_usb_enumerated=False,initramfs_executed=False,private_evidence=str(work),
                selected_usb_kernel_sha256=manifests['usb']['kernel.img'],unselected_emmc_kernel_sha256=manifests['emmc']['kernel.img'])
    h.write_report(a.output,result);print(json.dumps(result))


if __name__=='__main__':main()
