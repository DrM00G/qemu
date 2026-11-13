#!/usr/bin/python3
"""Observe actual kernel mappings, mounts, faults and verified logical reads."""
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

CONFIG = json.loads(Path('/etc/phase3-run.json').read_text())
RESULT = Path('/var/log/flight/phase3-result.json')


def command(*args):
    return subprocess.check_output(args, stderr=subprocess.STDOUT, text=True).strip()


def scan(device, expected, size):
    started = time.monotonic()
    digest = hashlib.sha256()
    count = 0
    proc = subprocess.Popen(['dd', 'if=' + device, 'bs=1M', 'iflag=direct', 'status=none'],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    while block := proc.stdout.read(1024 * 1024):
        digest.update(block)
        count += len(block)
        if count % (1024**3) == 0:
            print(f'PHASE3_SCAN {device} bytes={count}', flush=True)
    error = proc.stderr.read().decode()
    rc = proc.wait()
    return {'attempted': True, 'bytes_read': count, 'expected_bytes': size,
            'sha256': digest.hexdigest(), 'expected_sha256': expected,
            'exit_code': rc, 'error': error, 'elapsed_seconds': round(time.monotonic() - started, 3),
            'complete_recovery': rc == 0 and count == size and digest.hexdigest() == expected}


def main():
    result = {'schema': 1, 'case': CONFIG['case'], 'pass': False,
              'kernel_boot': True, 'page_size': os.sysconf('SC_PAGE_SIZE'),
              'prototype_started': None, 'prototype_functions': None,
              'prototype_sustained': None, 'logical_recovery': {}}
    try:
        assert result['page_size'] == 16384, 'runtime page size is not 16 KiB'
        result['cmdline'] = Path('/proc/cmdline').read_text().strip()
        result['cpu_count'] = os.cpu_count()
        result['memory_info'] = Path('/proc/meminfo').read_text()
        result['crypto_algorithms'] = Path('/proc/crypto').read_text()
        result['mountinfo'] = Path('/proc/self/mountinfo').read_text()
        result['fstab'] = Path('/etc/fstab').read_text()
        result['sizes'] = command('df', '-B1', '/', '/media/root-ro', '/opt/fsw', '/var/log/flight', '/boot')
        result['block_devices'] = json.loads(command('lsblk', '-b', '-J', '-o', 'NAME,SIZE,RO,FSTYPE,MOUNTPOINTS'))
        result['dm_table'] = command('dmsetup', 'table', '--target', 'verity')
        result['dm_status_before'] = command('dmsetup', 'status', '--target', 'verity')
        mounts = {}
        for point in ('/media/root-ro', '/opt/fsw', '/var/log/flight', '/boot'):
            mounts[point] = json.loads(command('findmnt', '-J', '-M', point))['filesystems'][0]
        result['mounts'] = mounts
        result['verified_root_mounted'] = mounts['/media/root-ro']['source'] in ('/dev/mapper/v8-os', '/dev/dm-0')
        result['verified_fsw_mounted'] = mounts['/opt/fsw']['source'] in ('/dev/mapper/v8-fsw', '/dev/dm-1')
        assert result['verified_root_mounted'] and result['verified_fsw_mounted'], 'unverified mount source'
        for point in ('/media/root-ro', '/opt/fsw', '/boot'):
            assert 'ro' in mounts[point]['options'].split(','), point + ' is not read-only'
        assert 'rw' in mounts['/var/log/flight']['options'].split(',')
        for name in ('os', 'fsw'):
            assert CONFIG['volumes'][name]['root_hash'] in result['dm_table'], 'pinned root differs from active table'
        result['fec_enabled'] = 'use_fec_from_device' in result['dm_table']
        assert result['fec_enabled'] == CONFIG['fec'], 'FEC table does not match the scenario'
        assert hashlib.sha256(Path('/opt/fsw/probe.bin').read_bytes()).hexdigest() == CONFIG['probe_sha256']
        RESULT.parent.mkdir(parents=True, exist_ok=True)
        probe = RESULT.parent / 'storage-write-test'
        probe.write_text('approved writable LOGS storage\n')
        assert probe.read_text() == 'approved writable LOGS storage\n'
        probe.unlink()
        result['storage_service_started'] = bool(os.environ.get('INVOCATION_ID'))
        assert result['storage_service_started'], 'storage check was not launched as a systemd service'
        result['fsw_probe_passed'] = True
        if CONFIG.get('prototype'):
            # Observe the actual systemd-owned process, not only self-reporting.
            app_result = RESULT.parent / 'prototype-result.json'
            samples = []
            observed_start = time.monotonic()
            initial_pid = int(command('systemctl', 'show', 'prototype-fsw.service', '-p', 'MainPID', '--value'))
            assert initial_pid > 0 and Path(f'/proc/{initial_pid}').exists(), 'prototype has no live MainPID'
            assert command('systemctl', 'is-active', 'prototype-fsw.service') == 'active'
            samples.append({'time': observed_start, 'pid': initial_pid, 'alive': True})
            deadline = time.monotonic() + 90
            while not app_result.exists() and time.monotonic() < deadline:
                pid = int(command('systemctl', 'show', 'prototype-fsw.service', '-p', 'MainPID', '--value'))
                samples.append({'time': time.monotonic(), 'pid': pid, 'alive': pid > 0 and Path(f'/proc/{pid}').exists()})
                time.sleep(0.25)
            app = json.loads(app_result.read_text())
            assert app.get('pid') == initial_pid and app.get('systemd_service') is True
            result['prototype'] = app
            result['prototype_observations'] = samples
            result['prototype_started'] = samples[0]['alive']
            result['prototype_functions'] = app.get('functions_passed') is True
            initial_window = (app.get('sustained') is True and
                              app.get('elapsed_seconds', 0) >= 4.5 and app.get('heartbeats', 0) >= 50)
            assert result['prototype_started'] and result['prototype_functions'] and initial_window
        result['fault_readback'] = []
        for name, faults in CONFIG.get('faults', {}).items():
            fd = os.open('/dev/mapper/v8-' + name, os.O_RDONLY)
            try:
                for fault in faults:
                    row = {'volume': name, 'offset': fault['offset'], 'expected_sha256': fault['clean_sha256']}
                    try:
                        block = os.pread(fd, 4096, fault['offset'])
                        row.update(sha256=hashlib.sha256(block).hexdigest(), read_error=None)
                        row['matches_clean'] = row['sha256'] == fault['clean_sha256']
                    except OSError as exc:
                        row.update(read_error=exc.errno, matches_clean=False, error=str(exc))
                    result['fault_readback'].append(row)
            finally:
                os.close(fd)
        for name in ('os', 'fsw'):
            if name == 'fsw' or CONFIG.get('full_os_scan'):
                volume = CONFIG['volumes'][name]
                result['logical_recovery'][name] = scan('/dev/mapper/v8-' + name, volume['sha256'], volume['bytes'])
            else:
                result['logical_recovery'][name] = {'attempted': False, 'complete_recovery': None}
        if CONFIG.get('prototype'):
            while time.monotonic() - observed_start < 5:
                assert Path(f'/proc/{initial_pid}').exists(), 'prototype exited during observation interval'
                time.sleep(0.25)
            final_pid = int(command('systemctl', 'show', 'prototype-fsw.service', '-p', 'MainPID', '--value'))
            assert final_pid == initial_pid and Path(f'/proc/{final_pid}').exists()
            assert command('systemctl', 'is-active', 'prototype-fsw.service') == 'active'
            heartbeats = [json.loads(line) for line in (RESULT.parent / 'heartbeat.jsonl').read_text().splitlines() if line.strip()]
            latest = heartbeats[-1]
            assert latest['pid'] == initial_pid and latest['beat'] > app['heartbeats'], 'periodic heartbeat stopped'
            result['prototype_last_heartbeat'] = latest
            result['prototype_observed_alive_seconds'] = time.monotonic() - observed_start
            result['prototype_observations'].append({'time': time.monotonic(), 'pid': final_pid, 'alive': True})
            result['prototype'] = json.loads(app_result.read_text())
            result['prototype_functions'] = result['prototype'].get('functions_passed') is True
            assert result['prototype_functions'], 'prototype reported a later capability failure'
            result['prototype_sustained'] = True
        result['dm_status_after'] = command('dmsetup', 'status', '--target', 'verity')
        result['kernel_log'] = command('dmesg', '--color=never')
        result['correction_logs'] = re.findall(r'^.*FEC .*corrected [1-9][0-9]* errors.*$', result['kernel_log'], re.M)
        result['fec_correction_activity'] = bool(result['correction_logs'])
        faults = result['fault_readback']
        if CONFIG['fec']:
            assert all(row['matches_clean'] for row in faults), 'a fault did not recover to clean bytes'
            if faults:
                assert result['fec_correction_activity'], 'no actual kernel FEC correction evidence'
            assert all(row.get('complete_recovery') for row in result['logical_recovery'].values() if row['attempted'])
            result['corruption_detected_without_fec'] = None
        else:
            detected = bool(faults) and all(row['read_error'] == errno.EIO for row in faults)
            result['corruption_detected_without_fec'] = detected
            assert detected, 'no-FEC case did not detect actual corrupted blocks'
            assert not result['fec_correction_activity'], 'FEC unexpectedly ran in no-FEC scenario'
            assert result['logical_recovery']['fsw']['complete_recovery'] is False
        result['pass'] = True
    except Exception as exc:
        result['error'] = str(exc)
        result['kernel_log'] = subprocess.run(['dmesg', '--color=never'], text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT).stdout
    RESULT.write_text(json.dumps(result, indent=2) + '\n')
    print('PHASE3_STORAGE_RESULT ' + json.dumps(result, sort_keys=True), flush=True)
    return 0 if result['pass'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
