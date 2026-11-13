#!/usr/bin/python3
"""Local research guest checks. No packages or credentials are provisioned."""
import ctypes
import errno
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request

CONFIG = json.loads(Path('/etc/phase1-config.json').read_text())
RESULT = Path('/var/lib/phase1/checks.json')
PROBE = b'cm5-phase1-virtual-network-probe-v1\n'


def command(*args):
    return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT).strip()


def perform():
    checks = {}
    def check(name, fn):
        try:
            checks[name] = {'pass': True, 'detail': fn()}
        except Exception as exc:
            checks[name] = {'pass': False, 'detail': str(exc)}

    def filesystem():
        data = bytes(range(256)) * 4096
        path = RESULT.parent / 'rw-test.bin'
        with path.open('wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        assert path.read_bytes() == data, 'filesystem readback differs'
        path.unlink()
        return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}

    def libraries():
        # These are the baseline Ubuntu runtime libraries, not future FSW dependencies.
        loaded = [ctypes.CDLL(name) for name in ('libc.so.6', 'libm.so.6', 'libpthread.so.0', 'libdl.so.2')]
        loaded[0].getpid.restype = ctypes.c_int
        assert loaded[0].getpid() == os.getpid()
        loaded[1].sqrt.argtypes = [ctypes.c_double]
        loaded[1].sqrt.restype = ctypes.c_double
        assert loaded[1].sqrt(81.0) == 9.0
        return [lib._name for lib in loaded]

    def computation():
        value = sum(i * i for i in range(100000))
        assert value == 333328333350000
        return {'sum_squares': value}

    def memory():
        data = bytearray(32 * 1024 * 1024)
        for offset in range(0, len(data), 4096):
            data[offset] = (offset // 4096) % 251
        assert all(data[n] == (n // 4096) % 251 for n in range(0, len(data), 4096))
        return {'allocated_bytes': len(data), 'pages_touched': len(data) // 4096}

    def network():
        # Probe the host over VirtIO + user networking; no public Internet needed.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(CONFIG['endpoint'] + '/probe/' + CONFIG['run_id'], timeout=30) as response:
            data = response.read()
        assert data == PROBE, 'unexpected network probe response'
        return {'sha256': hashlib.sha256(data).hexdigest(), 'routes': command('ip', '-json', 'route')}

    def root_contract():
        root = json.loads(command('findmnt', '-J', '-M', '/'))['filesystems'][0]
        detail = {'mode': CONFIG.get('root_mode', 'rw'), 'root': root,
                  'block_readonly': Path('/sys/block/vda/ro').read_text().strip()}
        assert 'rw' in root['options'].split(','), 'merged root must be writable for this test service'
        if detail['mode'] == 'overlay':
            assert root['fstype'] == 'overlay', 'OverlayFS did not become root'
            lower = json.loads(command('findmnt', '-J', '-M', '/media/root-ro'))['filesystems'][0]
            detail['lower'] = lower
            assert 'ro' in lower['options'].split(','), 'lower mount is not read-only'
            assert detail['block_readonly'] == '1', 'lower block device is writable'
            probe = Path('/media/root-ro/phase2-readonly-probe')
            try:
                probe.write_text('must not be written')
            except OSError as exc:
                assert exc.errno == errno.EROFS, f'unexpected lower write error: {exc}'
            else:
                probe.unlink()
                raise AssertionError('lower accepted a write')
            upper = next(v.split('=', 1)[1] for v in root['options'].split(',') if v.startswith('upperdir='))
            merged = Path('/phase2-copyup-probe')
            merged.write_text('phase2 upper only\n')
            assert (Path(upper) / merged.name).read_text() == merged.read_text()
            assert not (Path('/media/root-ro') / merged.name).exists()
            merged.unlink()
            detail['lower_write_rejected'] = True
            detail['upper_write_verified'] = True
        else:
            assert detail['block_readonly'] == '0', 'unexpected read-only root block device'
        return detail

    RESULT.parent.mkdir(parents=True, exist_ok=True)
    for name, fn in [('filesystem', filesystem), ('shared_libraries', libraries),
                     ('cpu', computation), ('memory', memory), ('network', network),
                     ('root_contract', root_contract)]:
        check(name, fn)
    RESULT.write_text(json.dumps(checks, sort_keys=True) + '\n')
    return 0 if all(item['pass'] for item in checks.values()) else 1


def report():
    result = {'schema': 1, 'run_id': CONFIG['run_id'], 'checks': {}}
    try:
        result['checks'] = json.loads(RESULT.read_text())
        result['pid1'] = Path('/proc/1/comm').read_text().strip()
        result['pid1_executable'] = os.readlink('/proc/1/exe')
        result['target'] = command('systemctl', 'is-active', 'multi-user.target')
        result['service'] = command('systemctl', 'show', 'phase1-test.service',
                                    '-p', 'Result', '-p', 'ExecMainStatus')
        result['failed_units'] = command('systemctl', '--failed', '--no-legend', '--plain', '--no-pager')
        result['kernel'] = command('uname', '-a')
        result['page_size'] = os.sysconf('SC_PAGE_SIZE')
        result['cmdline'] = Path('/proc/cmdline').read_text().strip()
        result['mountinfo'] = Path('/proc/self/mountinfo').read_text()
        result['block_devices'] = json.loads(command('lsblk', '-J', '-o', 'NAME,SIZE,RO,FSTYPE,MOUNTPOINTS'))
        result['os_release'] = Path('/etc/os-release').read_text()
        result['cloud_init_schema'] = command('cloud-init', 'schema', '--system')
        result['cloud_init_schema_valid'] = True
        result['cloud_init_status'] = json.loads(command('cloud-init', 'status', '--format', 'json'))
        expected = {'filesystem', 'shared_libraries', 'cpu', 'memory', 'network', 'root_contract'}
        result['pass'] = (set(result['checks']) == expected and
                          all(v['pass'] for v in result['checks'].values()) and
                          result['pid1'] == 'systemd' and result['pid1_executable'].endswith('/systemd') and
                          result['target'] == 'active' and
                          'Result=success' in result['service'].splitlines() and
                          'ExecMainStatus=0' in result['service'].splitlines() and
                          result['cloud_init_status'].get('status') == 'done' and
                          (not CONFIG.get('expected_page_size') or
                           result['page_size'] == CONFIG['expected_page_size']) and
                          not result['failed_units'])
    except Exception as exc:
        result.update({'pass': False, 'error': str(exc)})
    payload = json.dumps(result, sort_keys=True).encode()
    Path('/var/lib/phase1/result.json').write_bytes(payload + b'\n')
    print('PHASE1_RESULT ' + payload.decode(), flush=True)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for attempt in range(3):
        try:
            request = urllib.request.Request(CONFIG['endpoint'] + '/result/' + CONFIG['run_id'],
                                             data=payload, headers={'Content-Type': 'application/json'})
            with opener.open(request, timeout=15) as response:
                assert response.status == 200
            break
        except Exception as exc:
            print('PHASE1_REPORT_ERROR ' + str(exc), flush=True)
            time.sleep(2)
    subprocess.run(['systemctl', 'poweroff', '--no-block'], check=True)
    return 0 if result['pass'] else 1


if __name__ == '__main__':
    sys.exit(report() if '--report' in sys.argv else perform())
