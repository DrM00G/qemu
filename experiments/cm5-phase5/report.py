#!/usr/bin/env python3
"""Verify guest ioctl bytes against every QEMU-side SSI transfer event."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

here = Path(__file__).resolve().parent
repo = here.parent.parent
p = argparse.ArgumentParser()
p.add_argument('--label', default='spi-verified')
p.add_argument('--v8', type=Path)
a = p.parse_args()
serial_path = here / f'artifacts/{a.label}.serial.log'
trace_path = here / f'artifacts/{a.label}.unimplemented.log'
serial = serial_path.read_text()
trace = trace_path.read_text()
requests = re.findall(r'SPI_IOC_MESSAGE\(1\) mode=(\d+) hz=(\d+) len=(\d+) TX=([0-9a-f]+)', serial)
responses = re.findall(r'SPI_RESULT ret=(-?\d+) errno=(\d+) RX=([0-9a-f]+)', serial)
assert len(requests) == len(responses) == 72
expected = []
for (mode, speed, length, txhex), (ret, err, rxhex) in zip(requests, responses):
    tx = bytes.fromhex(txhex)
    rx = bytes.fromhex(rxhex)
    assert len(tx) == len(rx) == int(length) == int(ret) and int(err) == 0
    assert rx == bytes(b ^ 0xa5 for b in tx)
    expected.extend(zip(tx, rx))
events = re.findall(r'dw_apb_ssi_transfer cs=0x1 bits=8 tx=0x([0-9a-f]+) rx=0x([0-9a-f]+)', trace)
assert [(int(tx, 16), int(rx, 16)) for tx, rx in events] == expected
assert 'SPI_DIAGNOSTIC=PASS failures=0' in serial
assert 'SPI_INVALID_BPW ret=-1 errno=22' in serial
assert '../../../../../bus/pci/drivers/rp1' in serial
assert 'rp1_irq_chip  19 Level' in serial
assert 'PHASE5_GUEST_END' in serial
assert 'Kernel panic' not in serial and 'BUG:' not in serial
qtest = (here / 'artifacts/qtest.log').read_text()
assert len(re.findall(r'^ok \d ', qtest, re.M)) == 5

def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            h.update(block)
    return h.hexdigest()

kernel = Path.home() / 'cm5-phase3-kernel/build/arch/arm64/boot/Image'
qemu = repo / 'build-arm64-phase1/qemu-system-aarch64'
inputs = [kernel, qemu, here / 'artifacts/guest/spi-initrd.gz',
          here / 'artifacts/spi.dtb', serial_path, trace_path]
inputs += [repo / name for name in ('hw/misc/rp1-pci.c', 'hw/ssi/dw-apb-ssi.c',
           'hw/ssi/ssi-test-slave.c', 'include/hw/ssi/dw-apb-ssi.h', 'tests/qtest/rp1-test.c')]
result = dict(status='IMPLEMENTED_AND_GUEST_VALIDATED',
              platform='provisional ARM virt PCI host, not BCM2712',
              qtests=5, ioctls=72, traced_ssi_words=len(events),
              modes=[0, 1, 2, 3], speeds_hz=[100000, 1000000, 5000000],
              lengths=[1, 4, 63, 64, 65, 257],
              tx_example='10203040', rx_example='b58595e5',
              invalid_bpw_errno=22, physical_equivalence_verified=False,
              head=subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
              sha256={str(path): sha(path) for path in inputs})
if a.v8:
    result['v8'] = json.loads((a.v8 / 'result.json').read_text())
    v8 = result['v8']
    assert v8['returncode'] == 0 and not v8['timeout']
    assert all(v8[k] for k in ('target_active', 'diagnostic_pass', 'spi_diagnostic_pass'))
    v8trace = (a.v8 / 'peripheral.log').read_text()
    v8events = re.findall(r'dw_apb_ssi_transfer cs=0x1 bits=8 tx=0x([0-9a-f]+) rx=0x([0-9a-f]+)', v8trace)
    assert [(int(tx, 16), int(rx, 16)) for tx, rx in v8events] == [
        (0x10, 0x10), (0x20, 0x20), (0x30, 0x30), (0x40, 0x40)]
    v8inputs = json.loads((a.v8 / 'inputs.json').read_text())
    assert v8inputs[str(qemu)] == result['sha256'][str(qemu)]
    result['v8']['traced_ssi_words'] = len(v8events)
    result['v8']['same_qemu_binary'] = True
print(json.dumps(result, indent=2))
