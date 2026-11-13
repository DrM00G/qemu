#!/usr/bin/env python3
"""Reuse Phase 4 V8 boot, adding the endpoint; no edits to Phase 4 inputs.

Runs Phase 4's init/observer unchanged except for a separate pre-switch-root
SPI hook in the disposable initramfs. Existing diagnostic uses echo response,
so this run configures the SSI fixture xor-mask=0.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import selectors
import shutil
import subprocess
import sys
import time

here = Path(__file__).resolve().parent
repo = here.parent.parent
sys.path.insert(0, str(repo / 'experiments/cm5-phase4'))
from endpoints import Endpoints

p = argparse.ArgumentParser()
p.add_argument('--output', type=Path, required=True)
p.add_argument('--timeout', type=int, default=240)
a = p.parse_args()
out = a.output.resolve()
out.mkdir(parents=True, exist_ok=False)
os.chmod(out, 0o700)
source = Path.home() / 'cm5-v8-lab/runs/v8-verified-clean-1'
stage = out / 'stage'
shutil.copytree(source / 'stage', stage, symlinks=True)
endpoints = Endpoints(out / 'network.jsonl')
(stage / 'cm5-network').write_text('export CM5_TCP_PORT=%d CM5_UDP_PORT=%d CM5_ROOT_TEST=1\n' %
                                  (endpoints.ports['tcp'], endpoints.ports['udp']))
modules = Path.home() / 'cm5-phase3-kernel/modules/lib/modules'
for name in ('spi-dw.ko', 'spi-dw-mmio.ko', 'spidev.ko'):
    mod, = modules.rglob(name)
    shutil.copy2(mod, stage / name)
    subprocess.run(['aarch64-linux-gnu-strip', '--strip-debug', str(stage / name)], check=True)
# Uses V8's real dynamic loader via chroot and the existing Phase 4 diagnostic.
hook = '''
insmod /spi-dw.ko
insmod /spi-dw-mmio.ko
insmod /spidev.ko
echo spidev > /newroot/sys/bus/spi/devices/spi0.0/driver_override
echo spi0.0 > /newroot/sys/bus/spi/drivers/spidev/bind
chroot /newroot /run-cm5-diagnostic /var/log/flight/cm5-spi-rp1-new.dat - /dev/spidev0.0 1 > /newroot/var/log/flight/cm5-evidence/spi-rp1.jsonl 2>&1
echo V8_RP1_SPI_DIAGNOSTIC_EXIT=$?
cat /newroot/var/log/flight/cm5-evidence/spi-rp1.jsonl
'''
init = (stage / 'init').read_text()
init = init.replace('echo V8_SWITCH_ROOT', hook + '\necho V8_SWITCH_ROOT')
(stage / 'init').write_text(init)
spec = importlib.util.spec_from_file_location('builder', repo / 'experiments/cm5-phase3/prepare-initramfs.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
builder.pack(stage, out / 'initrd.gz')
cmd = json.loads((source / 'command.json').read_text())
# Fresh writable LOGS overlay. Every original image remains read-only.
golden = Path.home() / 'cm5-v8-lab/golden/cm5-emmc-userarea.img'
subprocess.run([str(repo / 'build-arm64-phase1/qemu-img'), 'create', '-f', 'qcow2',
                '-F', 'raw', '-b', str(golden), str(out / 'logs.qcow2')], check=True)
cmd[cmd.index('-initrd') + 1] = str(out / 'initrd.gz')
cmd[cmd.index('-machine') + 1] = 'virt,highmem=off,gic-version=3'
# Explicit PCI slots keep the experimental fixed BAR1 DT translation stable.
nic_index = cmd.index('-nic')
cmd[nic_index:nic_index + 2] = ['-netdev', 'user,id=v8net',
                                '-device', 'virtio-net-pci,netdev=v8net,addr=7']
for i, arg in enumerate(cmd):
    if str(source / 'logs.qcow2') in arg:
        cmd[i] = arg.replace(str(source / 'logs.qcow2'), str(out / 'logs.qcow2'))
slot = 2
for i, arg in enumerate(cmd):
    if arg == '-drive':
        drive_id = f'v8disk{slot}'
        cmd[i + 1] = cmd[i + 1].replace('if=virtio', f'if=none,id={drive_id}')
        cmd += ['-device', f'virtio-blk-pci,drive={drive_id},addr={slot}']
        slot += 1
cmd += ['-device', 'rp1-pci,id=rp1,addr=1', '-device',
        'ssi-test-slave,bus=spi,cs=0,xor-mask=0',
        '-dtb', str(here / 'artifacts/v8.dtb'),
        '-trace', 'enable=dw_apb_ssi_*', '-trace', 'enable=rp1_msix',
        '-d', 'unimp,guest_errors', '-D', str(out / 'peripheral.log')]
(out / 'command.json').write_text(json.dumps(cmd, indent=2) + '\n')
inputs = [Path(cmd[0]), Path(cmd[cmd.index('-kernel') + 1]),
          out / 'initrd.gz', here / 'artifacts/v8.dtb',
          stage / 'cm5-diagnostic']
hashes = {}
for path in inputs:
    with path.open('rb') as stream:
        hashes[str(path)] = hashlib.file_digest(stream, 'sha256').hexdigest()
(out / 'inputs.json').write_text(json.dumps(hashes, indent=2) + '\n')
proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
sel = selectors.DefaultSelector()
sel.register(proc.stdout, selectors.EVENT_READ)
raw = bytearray()
start = time.monotonic()
echoed = False
timed_out = False
try:
    with (out / 'serial.log').open('wb') as stream:
        while sel.get_map():
            if time.monotonic() - start > a.timeout:
                timed_out = True
                break
            for key, _ in sel.select(.5):
                data = os.read(key.fileobj.fileno(), 65536)
                if not data:
                    sel.unregister(key.fileobj)
                    continue
                raw.extend(data)
                stream.write(data)
                stream.flush()
                if not echoed and b'\x10\x20\x30\x40' in raw:
                    proc.stdin.write(b'\x10\x20\x30\x40')
                    proc.stdin.flush()
                    echoed = True
finally:
    if proc.poll() is None:
        proc.kill()
    proc.wait()
text = raw.decode(errors='replace')
result = dict(timeout=timed_out, returncode=proc.returncode,
              target_active='V8_TARGET=active' in text,
              diagnostic_pass='V8_DIAGNOSTIC_EXIT=0' in text,
              spi_diagnostic_pass='V8_RP1_SPI_DIAGNOSTIC_EXIT=0' in text)
(out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))
raise SystemExit(0 if all(result[k] for k in
                         ('target_active', 'diagnostic_pass', 'spi_diagnostic_pass'))
                 and not timed_out and proc.returncode == 0 else 1)
