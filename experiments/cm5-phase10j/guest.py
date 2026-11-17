"""Local-only guest workload. Host prepends PAYLOAD, EXPECTED, DURATION.
Run only inside the disposable QEMU guest; all staging uses /run tmpfs.
"""
import base64
import errno
import hashlib
import json
import os
from pathlib import Path
import pty
import select
import subprocess
import tempfile
import time

r = dict(status='ERROR', duration_requested=DURATION, qemu_virtual_seconds=None)
try:
    if os.geteuid() != 0:
        raise RuntimeError('root required')
    mount = subprocess.check_output(['findmnt', '-n', '-o', 'FSTYPE,OPTIONS', '-T', '/run'], text=True).strip()
    r['parent_mount'] = mount
    if not mount.startswith('tmpfs '):
        raise RuntimeError('/run must be tmpfs')
    work = Path(tempfile.mkdtemp(prefix='cm5-fsw-', dir='/run'))
    # A dedicated disposable submount supports V8's noexec /run without
    # changing parent mount options or writing any protected filesystem.
    subprocess.run(['mount', '-t', 'tmpfs', '-o', 'rw,nosuid,nodev,exec,size=64m',
                    'cm5-fsw-staging', str(work)], check=True, capture_output=True)
    staging = subprocess.check_output(['findmnt', '-n', '-o', 'FSTYPE,OPTIONS', '-T', str(work)], text=True).strip()
    r['staging_mount'] = staging
    if not staging.startswith('tmpfs ') or 'noexec' in staging.split(','):
        raise RuntimeError('dedicated staging tmpfs is not executable')
    r['kernel'] = subprocess.check_output(['uname', '-a'], text=True).strip()
    r['page_size'] = os.sysconf('SC_PAGE_SIZE')
    r['mounts'] = subprocess.check_output(['findmnt', '-rn', '-o', 'TARGET,SOURCE,FSTYPE,OPTIONS'], text=True)
    r['partitions'] = subprocess.check_output(['lsblk', '-J', '-o', 'NAME,TYPE,SIZE,FSTYPE,LABEL,UUID,PARTUUID'], text=True)
    elf = work/'RpiDeployment.elf'
    data = base64.b64decode(PAYLOAD, validate=True)
    r['sha256'] = hashlib.sha256(data).hexdigest()
    if r['sha256'] != EXPECTED:
        raise RuntimeError('guest executable digest mismatch')
    elf.write_bytes(data)
    elf.chmod(0o700)
    r['working_directory'] = str(work)
    r['guest_monotonic_start'] = time.monotonic()
    print('\nP10K_FSW_START='+str(r['guest_monotonic_start']), flush=True)
    master, slave = pty.openpty()
    command = ['timeout', '-s', 'INT', '-k', '10s', str(DURATION)+'s', './RpiDeployment.elf']
    r['command'] = command
    proc = subprocess.Popen(command, cwd=work, stdin=slave, stdout=slave, stderr=slave, start_new_session=True)
    os.close(slave)
    output = bytearray()
    while True:
        ready, _, _ = select.select([master], [], [], 1)
        if ready:
            try:
                chunk = os.read(master, 65536)
            except OSError as exc:
                if exc.errno != errno.EIO:
                    raise
                break
            if not chunk:
                break
            output.extend(chunk)
            os.write(1, chunk)
        if time.monotonic() - r['guest_monotonic_start'] > DURATION + 30:
            import signal
            os.killpg(proc.pid, signal.SIGKILL)
            r['watchdog_killed'] = True
            break
    r['exit_status'] = proc.wait(timeout=5)
    os.close(master)
    r['guest_monotonic_end'] = time.monotonic()
    r['guest_elapsed_seconds'] = r['guest_monotonic_end'] - r['guest_monotonic_start']
    r['output_base64'] = base64.b64encode(output).decode()
    r['status'] = 'COMPLETE'
except Exception as exc:
    r['error'] = repr(exc)
print('\nP10J_RESULT=' + json.dumps(r, separators=(',', ':')), flush=True)
