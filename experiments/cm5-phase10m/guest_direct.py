"""Executed only in the guest. Host prepends DURATION, GENERATION, TABLES, ELF_SIZE.

No ELF upload, content read/hash, RAM copy or fallback. Private experiment only.
"""
import base64
import errno
import json
import os
from pathlib import Path
import pty
import select
import stat
import subprocess
import tempfile
import time


def canonical_table(table):
    fields = table.split()
    fields[4:6] = ['DATA_DEVICE', 'HASH_DEVICE']
    fields[fields.index('use_fec_from_device')+1] = 'FEC_DEVICE'
    return fields


def require_mount(text, source):
    fields = text.split()
    if len(fields) != 3 or fields[:2] != [source, 'ext4']:
        raise RuntimeError('Not the required verified ext4 mount: '+text)
    flags = fields[2].split(',')
    if 'ro' not in flags or 'rw' in flags or 'norecovery' not in flags:
        raise RuntimeError('Protected filesystem is not ro,norecovery')


def failure_stage(exit_status, output, executed):
    if 'error while loading shared libraries' in output or 'ld-linux' in output:
        return 'dynamic-loading'
    if not executed or exit_status in (126,127):
        return 'executable-launch'
    if exit_status != 124:
        return 'application-operation'
    return None


r = dict(status='ERROR', stage='verified-mount-validation', duration_requested=DURATION,
         execution_mode='verified-fsw-partition', generation_id=GENERATION,
         executable='/opt/fsw/RpiDeployment.elf', executable_prehash=False,
         elf_uploaded=False, ram_fallback=False, qemu_virtual_seconds=None)
proc = None
try:
    if os.geteuid() != 0:
        raise RuntimeError('root required')
    r['uid'] = os.geteuid()
    r['tables'], r['statuses'], r['protected_mounts'] = {}, {}, {}
    for role, target in [('os','/media/root-ro'),('fsw','/opt/fsw')]:
        mapper = 'cm5_'+role+'_verified'
        table = subprocess.check_output(['dmsetup','table',mapper],text=True).strip()
        state = subprocess.check_output(['dmsetup','status',mapper],text=True).strip()
        if canonical_table(table) != TABLES[role+'_table'] or not state.endswith('verity V'):
            raise RuntimeError('Unexpected verified mapping/root/FEC: '+role)
        r['tables'][role] = table; r['statuses'][role] = state
        mount = subprocess.check_output(['findmnt','-rn','-o','SOURCE,FSTYPE,OPTIONS','-T',target],text=True).strip()
        require_mount(mount, '/dev/mapper/'+mapper)
        r['protected_mounts'][role] = mount
    r['stage'] = 'executable-metadata'
    elf = Path(r['executable'])
    info = elf.lstat()
    if (elf.resolve() != elf or not stat.S_ISREG(info.st_mode) or
            info.st_uid != 0 or not info.st_mode & stat.S_IXUSR or info.st_size != ELF_SIZE):
        raise RuntimeError('Unexpected protected ELF metadata/path')
    r['elf_metadata'] = dict(inode=info.st_ino, bytes=info.st_size, mode=oct(stat.S_IMODE(info.st_mode)), uid=info.st_uid)
    # Only writable working data goes to the existing noexec /run tmpfs.
    # The executable always stays on the read-only verified FSW mount.
    work = Path(tempfile.mkdtemp(prefix='cm5-direct-work-',dir='/run'))
    r['working_directory'] = str(work)
    r['kernel'] = subprocess.check_output(['uname','-a'],text=True).strip()
    r['page_size'] = os.sysconf('SC_PAGE_SIZE')
    r['command'] = ['timeout','-s','INT','-k','10s',str(DURATION)+'s',str(elf)]
    r['stage'] = 'executable-launch'
    master, slave = pty.openpty()
    r['guest_monotonic_start'] = time.monotonic()
    print('\nP10K_FSW_START='+str(r['guest_monotonic_start']),flush=True)
    proc = subprocess.Popen(r['command'],cwd=work,stdin=slave,stdout=slave,stderr=slave,start_new_session=True)
    os.close(slave)
    output = bytearray()
    while True:
        if 'execution_evidence' not in r:
            children = Path('/proc/'+str(proc.pid)+'/task/'+str(proc.pid)+'/children')
            try:
                for pid in children.read_text().split():
                    if os.readlink('/proc/'+pid+'/exe') == str(elf):
                        maps = Path('/proc/'+pid+'/maps').read_text()
                        r['execution_evidence'] = dict(pid=int(pid),exe=str(elf),
                            command_line=Path('/proc/'+pid+'/cmdline').read_bytes().split(b'\0')[0].decode(),
                            executable_map_present=any(str(elf) in line and 'r-x' in line for line in maps.splitlines()),
                            observed_guest_monotonic=time.monotonic())
                        r['stage'] = 'application-operation'
            except (OSError, ProcessLookupError):
                pass
        ready,_,_ = select.select([master],[],[],1)
        if ready:
            try:
                chunk = os.read(master,65536)
            except OSError as exc:
                if exc.errno != errno.EIO:
                    raise
                break
            if not chunk:
                break
            output.extend(chunk); os.write(1,chunk)
        if time.monotonic()-r['guest_monotonic_start'] > DURATION+30:
            import signal
            os.killpg(proc.pid,signal.SIGKILL);r['watchdog_killed']=True
            break
    r['exit_status'] = proc.wait(timeout=5)
    os.close(master)
    r['guest_monotonic_end'] = time.monotonic()
    r['guest_elapsed_seconds'] = r['guest_monotonic_end']-r['guest_monotonic_start']
    r['output_base64'] = base64.b64encode(output).decode()
    r['failure_stage'] = failure_stage(r['exit_status'],output.decode(errors='replace'),bool(r.get('execution_evidence')))
    r['status'] = 'COMPLETE'
except Exception as exc:
    r['error'] = repr(exc)
    r['failure_stage'] = r['stage']
    if proc is not None and proc.poll() is None:
        import signal
        os.killpg(proc.pid,signal.SIGKILL);proc.wait()
print('\nP10J_RESULT='+json.dumps(r,separators=(',',':')),flush=True)
