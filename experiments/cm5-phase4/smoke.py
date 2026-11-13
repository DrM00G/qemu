#!/usr/bin/env python3
"""Actual ARM64/16K/PL011 smoke; no OS disk and no systemd claim."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import selectors
import shutil
import subprocess
import time

HERE=Path(__file__).resolve().parent
REPO=HERE.parent.parent
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--output', type=Path, required=True)
a=p.parse_args()
out=a.output.resolve()
if out.is_relative_to(REPO):
    p.error('evidence and generated binaries must be outside repository')
out.mkdir(parents=True,exist_ok=False)
subprocess.run(['aarch64-linux-gnu-gcc','-O2','-Wall','-Wextra','-Werror',
                '-Wl,-z,max-page-size=65536',str(HERE/'diagnostic.c'),'-ldl','-o',str(out/'diagnostic')],check=True)
stage=out/'stage'
shutil.copytree(REPO/'experiments/cm5-phase3/artifacts/initramfs-16k/unpacked',stage,symlinks=True)
shutil.copy2(out/'diagnostic',stage/'diagnostic')
# Use the compiler's matching runtime; keep existing initramfs libraries intact.
(stage/'cm5lib').mkdir()
for name in ('libc.so.6','libm.so.6','ld-linux-aarch64.so.1'):
    shutil.copy2(Path('/usr/aarch64-linux-gnu/lib')/name,stage/'cm5lib'/name)
(stage/'init').write_text('''#!/bin/sh
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
mount -t devtmpfs devtmpfs /dev
mount -t proc proc /proc
mount -t sysfs sysfs /sys
exec </dev/console >/dev/console 2>&1
/cm5lib/ld-linux-aarch64.so.1 --library-path /cm5lib /diagnostic /cm5-test.dat /dev/ttyAMA0 - 3
echo PHASE4_DIAGNOSTIC_EXIT=$?
poweroff -f
''')
(stage/'init').chmod(0o755)
spec=importlib.util.spec_from_file_location('builder',REPO/'experiments/cm5-phase3/prepare-initramfs.py')
builder=importlib.util.module_from_spec(spec); spec.loader.exec_module(builder)
builder.pack(stage,out/'initrd.gz')
cmd=[str(REPO/'build-arm64-phase1/qemu-system-aarch64'),'-machine','virt','-cpu','cortex-a76',
     '-accel','tcg','-smp','2','-m','512','-display','none','-monitor','none','-serial','stdio',
     '-kernel',str(Path.home()/'cm5-phase3-kernel/build/arch/arm64/boot/Image'),
     '-initrd',str(out/'initrd.gz'),'-append','console=ttyAMA0 rdinit=/init panic=-1']
(out/'command.json').write_text(json.dumps(cmd,indent=2))
proc=subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
sel=selectors.DefaultSelector(); sel.register(proc.stdout,selectors.EVENT_READ)
raw=bytearray(); echoed=False; start=time.monotonic(); timed_out=False
try:
    with (out/'serial.log').open('wb') as log, (out/'peripheral.jsonl').open('w') as trace:
        while True:
            if time.monotonic()-start>120:
                timed_out=True; proc.terminate(); break
            events=sel.select(.5)
            if proc.poll() is not None and not events: break
            for key,_ in events:
                data=os.read(key.fileobj.fileno(),65536)
                if not data:
                    sel.unregister(key.fileobj)
                    break
                raw.extend(data); log.write(data); log.flush()
                if not echoed and b'\x10\x20\x30\x40' in raw:
                    proc.stdin.write(b'\x10\x20\x30\x40'); proc.stdin.flush(); echoed=True
                    trace.write(json.dumps(dict(interface='PL011 ttyAMA0',tx='10203040',rx='10203040',
                                                host_monotonic=time.monotonic()))+'\n'); trace.flush()
finally:
    if proc.poll() is None: proc.kill()
    proc.wait()
rows=[]
for line in bytes(raw).decode(errors='replace').splitlines():
    # UART transfer bytes can prefix the next result.
    pos=line.find('{"test":')
    if pos>=0:
        try: rows.append(json.loads(line[pos:]))
        except json.JSONDecodeError: pass
passed=not timed_out and proc.returncode==0 and echoed and any(r['test']=='exit' and r['status']=='PASS' for r in rows)
result=dict(experiment_id=out.name,status='PASS' if passed else 'FAIL',actual_v8=False,
            environment='ARM64 diagnostic initramfs; no systemd',hardware='simulated',
            systemd='NOT_TESTED',verified_root='NOT_TESTED',fec='NOT_TESTED',
            qemu_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
            kernel_version='6.18.62-cm5-surrogate-16k (Phase 3 supplied kernel)',
            page_size=next((r['bytes'] for r in rows if r['test']=='page_16k'),None),
            input_image_sha256=None,corruption=None,dm_verity='NOT_TESTED',
            linux_boot='PASS' if rows else 'INCONCLUSIVE',
            fsw_startup='PASS' if rows else 'INCONCLUSIVE',
            logical_recovery='NOT_TESTED',errors=['host timeout'] if timed_out else [],
            timeout=timed_out,returncode=proc.returncode,functions=rows,
            serial_log=str(out/'serial.log'),peripheral_trace=str(out/'peripheral.jsonl'))
(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
raise SystemExit(0 if passed else 1)
