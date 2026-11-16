# Runs as a bounded child using captured OS Python, never a replacement driver.
import ctypes
import fcntl
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess

SPI_HZ = 10000

for module in ('spi-dw-mmio', 'spidev'):
    r = subprocess.run(['modprobe', module], capture_output=True, text=True, timeout=5)
    if r.returncode:
        raise RuntimeError(module+': '+r.stderr)
p = Path('/sys/bus/spi/devices/spi0.0')
if not p.exists():
    raise RuntimeError('real DesignWare controller/device did not appear')
if not (p/'driver').exists():
    (p/'driver_override').write_text('spidev\n')
    Path('/sys/bus/spi/drivers/spidev/bind').write_text('spi0.0\n')

def irqs():
    rows = {}
    for line in Path('/proc/interrupts').read_text().splitlines():
        if 'spi0' in line or '1f00050000' in line:
            head, tail = line.split(':', 1)
            counts = []
            for word in tail.split():
                if not word.isdigit():
                    break
                counts.append(int(word))
            rows[head.strip()] = {'count':sum(counts), 'line':line}
    return rows

before = irqs()
fd = os.open('/dev/spidev0.0', os.O_RDWR)
records = []
try:
    fcntl.ioctl(fd, 0x40016b01, bytes([0])) # mode0
    fcntl.ioctl(fd, 0x40016b03, bytes([8])) # bits per word
    for repetition in range(3):
        for length in (4, 64, 65, 128, 257, 4096):
            payload = bytes((i*17+repetition*37+length)%256 for i in range(length))
            tx = ctypes.create_string_buffer(payload)
            rx = ctypes.create_string_buffer(length)
            transfer = struct.pack('=QQIIHBBBBBB', ctypes.addressof(tx), ctypes.addressof(rx),
                length, SPI_HZ, 0, 8, 0, 0, 0, 0, 0)
            assert len(transfer) == 32
            fcntl.ioctl(fd, 0x40206b00, transfer)
            actual = rx.raw
            if actual != bytes(b^0xa5 for b in payload):
                raise RuntimeError('MOSI/MISO mismatch at '+str((repetition,length)))
            records.append({'length':length,'repetition':repetition,
                            'tx_sha256':hashlib.sha256(payload).hexdigest(),
                            'rx_sha256':hashlib.sha256(actual).hexdigest()})
finally:
    os.close(fd)
after = irqs()
delta = sum(row['count'] for row in after.values())-sum(row['count'] for row in before.values())
print(json.dumps(dict(status='PASS' if delta>0 else 'NO_OBSERVED_IRQ',
                     speed_hz=SPI_HZ,messages=records,irq_before=before,irq_after=after,irq_delta=delta,
                     controller_driver=os.readlink('/sys/bus/platform/devices/1f00050000.spi/driver') if Path('/sys/bus/platform/devices/1f00050000.spi/driver').exists() else None)))
