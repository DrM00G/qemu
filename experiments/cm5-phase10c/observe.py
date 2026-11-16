"""Sent to the guest debug UART; writes only a new disposable LOGS artifact."""
import ctypes
import hashlib
import json
import os
from pathlib import Path
import subprocess


def cmd(*args):
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=3).stdout.strip()
    except Exception as error:
        return 'ERROR:' + str(error)


r = dict(uptime=float(Path('/proc/uptime').read_text().split()[0]),
         pid1=Path('/proc/1/comm').read_text().strip(), pid1_exe=os.readlink('/proc/1/exe'),
         target=cmd('systemctl', 'is-active', 'multi-user.target'),
         os_status=cmd('dmsetup', 'status', 'cm5_os_verified'),
         fsw_status=cmd('dmsetup', 'status', 'cm5_fsw_verified'),
         os_table=cmd('dmsetup', 'table', 'cm5_os_verified'),
         fsw_table=cmd('dmsetup', 'table', 'cm5_fsw_verified'),
         lower=cmd('findmnt', '-rn', '-o', 'SOURCE,FSTYPE,OPTIONS', '/media/root-ro'),
         fsw=cmd('findmnt', '-rn', '-o', 'SOURCE,FSTYPE,OPTIONS', '/opt/fsw'),
         logs=cmd('findmnt', '-rn', '-o', 'SOURCE,FSTYPE,OPTIONS', '/var/log/flight'),
         uart_output_tty=os.isatty(1), libc_call=ctypes.CDLL('libc.so.6').getpid() == os.getpid(),
         root_elf_sha256=hashlib.sha256(Path('/usr/bin/python3').read_bytes()).hexdigest(),
         spi_nodes=list(map(str, Path('/dev').glob('spidev*'))))
with open('/dev/mapper/cm5_fsw_verified', 'rb', buffering=0) as f:
    r['fsw_block0_sha256'] = hashlib.sha256(f.read(4096)).hexdigest()
r['fsw_files'] = sorted(p.name for p in Path('/opt/fsw').iterdir())
payload = bytes((i*31+7) % 251 for i in range(4096))
if r['logs'].startswith('/dev/mmcblk0p6 '):
    p = Path('/var/log/flight/phase10c-public-diagnostic-01.dat')
    if not p.exists():
        fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.write(fd, payload)
        os.fsync(fd)
        os.close(fd)
    r['logs_fsync_readback'] = p.read_bytes() == payload
else:
    r['logs_fsync_readback'] = False
print('P10C_USER_JSON=' + json.dumps(r, separators=(',', ':')))
