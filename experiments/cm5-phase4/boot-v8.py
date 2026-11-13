#!/usr/bin/env python3
"""Boot restricted full CM5 image; writable state exists only in RAM and QCOW2."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import selectors
import shutil
import subprocess
import time
from disk_inventory import regular, EXPECTED
from endpoints import Endpoints
HERE=Path(__file__).resolve().parent
REPO=HERE.parent.parent
os.umask(0o077)
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--diagnostic',type=Path,help='replaceable ARM64 mock executable with the diagnostic CLI contract')
p.add_argument('--image',type=Path,default=Path.home()/'cm5-v8-lab/golden/cm5-emmc-userarea.img')
p.add_argument('--output',type=Path,required=True)
p.add_argument('--inspect',action='store_true')
p.add_argument('--verified-fsw',type=Path)
p.add_argument('--fault',action='store_true',help='one deterministic FSW fault; requires --verified-fsw')
p.add_argument('--timeout',type=int,default=360)
a=p.parse_args()
if a.fault and not a.verified_fsw:p.error('--fault requires original verified FSW metadata')
image=regular(a.image)
if image.stat().st_size!=EXPECTED: p.error('unexpected full disk size')
out=a.output.resolve()
if out.is_relative_to(REPO): p.error('output must be outside repository')
out.mkdir(parents=True,exist_ok=False)
endpoints=Endpoints(out/'network.jsonl')
stage=out/'stage'
shutil.copytree(REPO/'experiments/cm5-phase3/artifacts/initramfs-16k/unpacked',stage,symlinks=True)
if a.diagnostic:
    source=regular(a.diagnostic)
    with source.open('rb') as f:header=f.read(20)
    if header[:5]!=b'\x7fELF\x02' or header[18:20]!=b'\xb7\x00':p.error('ARM64 ELF64 diagnostic required')
    shutil.copy2(source,stage/'cm5-diagnostic');(stage/'cm5-diagnostic').chmod(0o755)
else:
    subprocess.run(['aarch64-linux-gnu-gcc','-O2','-Wall','-Wextra','-Werror','-Wl,-z,max-page-size=65536',
                    str(HERE/'diagnostic.c'),'-ldl','-o',str(stage/'cm5-diagnostic')],check=True)
shutil.copy2(HERE/'v8-init.sh',stage/'init'); (stage/'init').chmod(0o755)
shutil.copy2(HERE/'v8-observe.sh',stage/'cm5-observe')
extra_drives=[];injection=None
if a.verified_fsw:
    derived=a.verified_fsw.resolve(strict=True)
    verification=json.loads((derived/'verification.json').read_text())
    if verification['verification']!={'no_fec':'PASS','fec':'PASS'}:raise ValueError('captured FSW metadata must verify first')
    data=regular(derived/'fsw.ext4');fmt='raw'
    if a.fault:
        spec_i=importlib.util.spec_from_file_location('injector',HERE.parent/'cm5-phase3/inject.py')
        injector=importlib.util.module_from_spec(spec_i);spec_i.loader.exec_module(injector)
        injection=injector.inject(data,out/'fsw-fault',seed=7303,count=1,fec_blocks=132105)
        data=Path(injection['overlay']);fmt='qcow2'
    extra_drives=['-drive',f'file={data},format={fmt},if=virtio,readonly=on']
    for name in ('hash','fec'):
        extra_drives+=['-drive',f'file={regular(derived/('fsw.'+name))},format=raw,if=virtio,readonly=on']
    fields=dict(line.split(':',1) for line in (derived/'verity-dump.txt').read_text().splitlines() if ':' in line)
    salt=fields['Salt'].strip();root=verification['fsw_root']
    table=f'0 1048576 verity 1 /dev/vdc /dev/vdd 4096 4096 131072 1 sha256 {root} {salt} 8 use_fec_from_device /dev/vde fec_roots 2 fec_blocks 132105 fec_start 0'
    (stage/'cm5-fsw-map').write_text("#!/bin/sh\ndmsetup create --readonly --noudevsync cm5-fsw --table '"+table+"'\ndmsetup mknodes\n")
    (out/'fsw-verification-input.json').write_text(json.dumps(verification,indent=2)+'\n')
(stage/'cm5-network').write_text('export CM5_TCP_PORT=%d CM5_UDP_PORT=%d CM5_ROOT_TEST=1\n' % (endpoints.ports['tcp'],endpoints.ports['udp']))
spec=importlib.util.spec_from_file_location('builder',REPO/'experiments/cm5-phase3/prepare-initramfs.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);m.pack(stage,out/'initrd.gz')
qemu=REPO/'build-arm64-phase1/qemu-system-aarch64'
subprocess.run([str(REPO/'build-arm64-phase1/qemu-img'),'create','-f','qcow2','-F','raw',
                '-b',str(image),str(out/'logs.qcow2')],check=True,stdout=subprocess.DEVNULL)
kernel=Path.home()/'cm5-phase3-kernel/build/arch/arm64/boot/Image'
cmd=[str(qemu),'-machine','virt','-cpu','cortex-a76','-accel','tcg','-smp','2','-m','512' if a.inspect else '2048',
     '-display','none','-monitor','none','-serial','stdio','-no-reboot',
     '-kernel',str(kernel),'-initrd',str(out/'initrd.gz'),
     '-append','console=ttyAMA0 rdinit=/init panic=-1 systemd.unit=multi-user.target'+(' v8.inspect=1' if a.inspect else ''),
     '-drive',f'file={image},format=raw,if=virtio,readonly=on',
     '-drive',f'file={out}/logs.qcow2,format=qcow2,if=virtio',
     '-nic','user,model=virtio-net-pci']+extra_drives
(out/'command.json').write_text(json.dumps(cmd,indent=2)+'\n')
proc=subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
sel=selectors.DefaultSelector();sel.register(proc.stdout,selectors.EVENT_READ)
start=time.monotonic(); raw=bytearray();timeout=False;echoed=False
try:
    with (out/'serial.log').open('wb') as f:
        while True:
            if time.monotonic()-start>a.timeout: timeout=True;break
            events=sel.select(.5)
            if not events and proc.poll() is not None:break
            for key,_ in events:
                b=os.read(key.fileobj.fileno(),65536)
                if not b:sel.unregister(key.fileobj);continue
                f.write(b);f.flush();raw.extend(b)
                if not echoed and b'\x10\x20\x30\x40' in raw:
                    proc.stdin.write(b'\x10\x20\x30\x40');proc.stdin.flush();echoed=True
                    (out/'uart.json').write_text(json.dumps(dict(interface='PL011 ttyAMA0',tx='10203040',rx='10203040'))+'\n')
finally:
    if proc.poll() is None:proc.kill()
    proc.wait()
text=raw.decode(errors='replace')
markers=[]
for line in text.splitlines():
    for prefix in ('V8_', '{"test":'):
        if prefix in line:
            markers.append(line[line.index(prefix):])
            break
result=dict(actual_v8=True,experiment_id=out.name,timeout=timeout,returncode=proc.returncode,
            kernel=str(kernel),qemu_source_head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
            qemu_binary_sha256=m.sha256(qemu),diagnostic_sha256=m.sha256(stage/'cm5-diagnostic'),initramfs_sha256=m.sha256(out/'initrd.gz'),kernel_sha256=m.sha256(kernel),
            markers=markers,status='PASS' if 'V8_TARGET=active' in markers and 'V8_DIAGNOSTIC_EXIT=0' in markers else 'INCONCLUSIVE',
            injection=injection,verification='NOT_TESTED',fec='NOT_TESTED',serial_log=str(out/'serial.log'))
(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))

raise SystemExit(0 if result['status']=='PASS' or (a.inspect and 'V8_INSPECTION_END' in markers and not timeout) else 1)
