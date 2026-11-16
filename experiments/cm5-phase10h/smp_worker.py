"""Disposable guest worker: CPU/private RAM work and read-only RP1 chip ID.

Invoked only by the optional Phase 10H observer wrapper; no storage writes.
"""
import hashlib
import json
import mmap
import os
from pathlib import Path
import sys
import time

cpu, directory = int(sys.argv[1]), Path(sys.argv[2])
os.sched_setaffinity(0, {cpu})
start = time.monotonic_ns()
loops = 0
payload = bytes(range(256)) * 16
fd = os.open('/sys/bus/pci/devices/0002:01:00.0/resource1', os.O_RDONLY)
with mmap.mmap(fd, 4096, flags=mmap.MAP_SHARED, prot=mmap.PROT_READ) as regs:
    chip_id = int.from_bytes(regs[:4], 'little')
    if chip_id != 0x20001927:
        raise RuntimeError('chip ID mismatch')
    (directory/f'ready-{cpu}').write_text(json.dumps(dict(cpu=cpu, start_monotonic_ns=start)))
    while not (directory/'stop').exists() and time.monotonic_ns()-start < 30_000_000_000:
        for _ in range(32):
            payload = hashlib.sha256(payload).digest() * 128
            if int.from_bytes(regs[:4], 'little') != chip_id:
                raise RuntimeError('concurrent BAR read changed')
            loops += 1
os.close(fd)
print(json.dumps(dict(cpu=cpu, affinity=sorted(os.sched_getaffinity(0)), loops=loops,
                     digest=hashlib.sha256(payload).hexdigest(),
                     start_monotonic_ns=start, end_monotonic_ns=time.monotonic_ns())))
