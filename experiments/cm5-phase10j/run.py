#!/usr/bin/env python3
"""Private, local-only approved CM5 FSW experiment. Never for upstream submission."""
import argparse
import base64
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'experiments/cm5-phase10a'))
from preboot import identity, USER_BYTES
sys.path.insert(0, str(ROOT/'experiments/cm5-phase10f'))
import handoff

FSW_SHA = 'b0b4dd5af15b4cbfd8005da10551cf4dc9f9ce45166299c4996d238a5362fbc3'
GOLDEN_SHA = 'e2fb1a85c2652838793e58f8b13ef908e2e4a4c4295e27297ce742287f69cb87'


def payload_code(data, duration):
    encoded = base64.b64encode(data).decode()
    return ('PAYLOAD = (\n' + ''.join(repr(encoded[i:i+120])+'\n' for i in range(0, len(encoded), 120))
            + ')\nEXPECTED = '+repr(FSW_SHA)+'\nDURATION = '+str(duration)+'\n'
            + Path(__file__).with_name('guest.py').read_text())


def classify(boot, fsw, text):
    # Positive evidence remains reviewable: broad keywords alone never yield PASS.
    patterns = dict(version=r'3\.0\.0-alpha', topology=r'topology.*initial',
        components=r'component.*initial', tasks_created=r'task.*creat',
        tasks_started=r'task.*start', housekeeping=r'housekeeping|\bHK\b',
        packets=r'packet.*(?:rout|forward)|(?:rout|forward).*packet')
    events = {k: re.findall(r'^.*'+v+r'.*$', text, re.I | re.M) for k, v in patterns.items()}
    crash = re.findall(r'^.*(?:segmentation fault|core dumped|illegal instruction|error while loading shared libraries|cannot execute binary).*$\n?', text, re.I | re.M)
    if not fsw:
        return 'INCONCLUSIVE', 'No complete guest workload result', events
    if fsw.get('status') != 'COMPLETE':
        return 'BLOCKED', 'Guest execution prerequisite failed: '+str(fsw.get('error')), events
    if crash or fsw.get('watchdog_killed') or fsw.get('exit_status') != 124:
        return 'FAIL', 'Crash, forced kill, or unexpected FSW timeout exit status; inspect raw output', events
    if boot.get('status') != 'PASS' or not boot.get('fsw_workload_complete') or not boot.get('normal_poweroff'):
        return 'INCONCLUSIVE', 'Boot validation or normal shutdown incomplete', events
    return 'PARTIAL', 'Timeout completed; compare recorded event lines against physical output before declaring functional PASS', events


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--fsw', type=Path, required=True)
    p.add_argument('--golden', type=Path, default=Path('/home/aweso/cm5-v8-lab/golden/cm5-emmc-userarea.img'))
    p.add_argument('--boot-expected', type=Path, default=Path('/home/aweso/cm5-v8-lab/phase10f2/accepted-01/accepted-hashes.json'))
    p.add_argument('--work', type=Path, required=True, help='fresh private directory outside checkout')
    p.add_argument('--duration', type=int, choices=(30, 300), default=30)
    p.add_argument('--host-timeout', type=int, default=1800, help='whole guest host seconds, including boot and serial transfer')
    a = p.parse_args()
    os.umask(0o077)
    work = a.work.resolve()
    if work.is_relative_to(ROOT):
        p.error('work must be outside checkout')
    work.mkdir(parents=True, exist_ok=False, mode=0o700)
    report = dict(environment='qemu', run_id=work.name,
        clock=dict(name='CLOCK_MONOTONIC', domain='guest-monotonic', units='s', timestamp=None),
        software=dict(required_fsw_sha256=FSW_SHA),
        fixture=dict(identity='QEMU CM5; no SatNOGS/serial fixture', synthetic=False, physical_equivalence_measured=False),
        operation=dict(duration_guest_seconds=a.duration, cwd='fresh executable /run tmpfs directory'),
        required_for_fsw='YES', result=dict(status='INCONCLUSIVE'),
        timing=dict(host_elapsed_seconds=None, guest_elapsed_seconds=None, qemu_virtual_seconds=None),
        physical_baseline=dict(source='user observations; raw physical log not provided', duration_seconds=300,
            version='3.0.0-alpha', exit_status=124, stack_clamp_bytes=131072, page_bytes=16384,
            topology=True, components=True, tasks=True, housekeeping=True, packets=True, crash_observed=False))
    report['utc_started'] = datetime.now(timezone.utc).isoformat()
    start = time.monotonic()
    def save():
        report['utc_last_updated'] = datetime.now(timezone.utc).isoformat()
        report['timing']['host_elapsed_seconds'] = time.monotonic()-start
        (work/'comparison.json').write_text(json.dumps(report, indent=2)+'\n')
    save()
    # Shared lock serializes Phase10J. Also reject already-running full guests.
    lock = open('/tmp/cm5-phase10j-'+str(os.getuid())+'.lock', 'a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for entry in Path('/proc').iterdir():
            if entry.name.isdigit():
                try:
                    name = (entry/'comm').read_text().strip()
                except OSError:
                    continue
                if name.startswith('qemu-system'):
                    raise RuntimeError('another full QEMU guest is running')
        bins = ROOT/'build-arm64-phase1'
        report['software']['git_revision'] = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
        (work/'git-status.txt').write_bytes(subprocess.check_output(['git', 'status', '--short'], cwd=ROOT))
        report['software']['tools'] = {name: identity(bins/name) for name in ('qemu-system-aarch64', 'qemu-img', 'qemu-io')}
        report['software']['boot_manifest'] = identity(a.boot_expected)
        golden = identity(a.golden)
        report['software']['golden'] = golden
        if golden['bytes'] != USER_BYTES or golden['sha256'] != GOLDEN_SHA:
            raise RuntimeError('golden does not match independently accepted full-eMMC identity')
        disk = work/'emmc.qcow2'
        subprocess.run([str(bins/'qemu-img'), 'create', '-f', 'qcow2', '-F', 'raw', '-b', golden['path'], str(disk)], check=True, capture_output=True)
        report['software']['overlay_before'] = identity(disk)
        selection_dir = work/'preflight-boot'; selection_dir.mkdir()
        os.environ['CM5_BOOT_READER'] = 'qemu-io'
        os.environ['CM5_BOOT_PREFETCH'] = '65536'
        selection, buffers = handoff.select(disk, selection_dir, json.loads(a.boot_expected.read_text()), config_profile='cm5-headless-lab')
        handoff.write_report(selection_dir/'selection.json', selection)
        report['software']['boot_selection_report'] = str(selection_dir/'selection.json')
        if selection['status'] != 'SELECTED':
            raise RuntimeError('BOOT acceptance failed: '+str(selection.get('reason')))
        report['software']['selected_files'] = {name: {key: meta.get(key) for key in ('size', 'sha256', 'validation')}
                                                  for name, meta in selection['files'].items()}
        report['software']['preflight_chain_unchanged'] = selection['overlay_chain_before'] == selection['overlay_chain_after']
        source_dir = work/'harness-sources'; source_dir.mkdir()
        sources = [Path(__file__), Path(__file__).with_name('guest.py'), ROOT/'experiments/cm5-phase10c/run.py']
        report['software']['harness'] = {str(f.relative_to(ROOT)): identity(f) for f in sources}
        for source in sources:
            target = source_dir/source.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())
        if not a.fsw.exists():
            raise FileNotFoundError('Approved executable absent at explicit path: '+str(a.fsw))
        fsw = identity(a.fsw)
        report['software']['fsw'] = fsw
        if fsw['sha256'] != FSW_SHA:
            raise RuntimeError('FSW SHA256 mismatch')
        data = a.fsw.read_bytes()
        if hashlib.sha256(data).hexdigest() != FSW_SHA or data[:4] != b'\x7fELF' or data[4:6] != b'\x02\x01' or int.from_bytes(data[18:20], 'little') != 183:
            raise RuntimeError('ELF identity/architecture changed or invalid')
        payload = work/'guest-workload.py'; payload.write_text(payload_code(data, a.duration))
        command = [sys.executable, str(ROOT/'experiments/cm5-phase10c/run.py'), '--control-pipes',
            '--dma', '--batch', '--profile', 'native', '--boot-selection-policy', 'eeprom-fixture-0xf14',
            '--boot-config-profile', 'cm5-headless-lab', '--boot-overlay', str(disk),
            '--boot-expected', str(a.boot_expected.resolve()), '--golden', golden['path'],
            '--lab-root', str(work/'control'), '--debug-shell', '--observer-upload-once',
            '--poweroff-after-validation', '--phase10j-workload', str(payload),
            '--timeout', str(a.host_timeout), '--output', str(work/'v8')]
        (work/'launch.json').write_text(json.dumps(command, indent=2))
        save()
        with (work/'runner.log').open('xb') as log:
            rc = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT).returncode
        report['result']['runner_returncode'] = rc
        boot = json.loads((work/'v8/result.json').read_text()) if (work/'v8/result.json').exists() else {}
        fswpath = work/'v8/fsw-result.json'
        result = json.loads(fswpath.read_text()) if fswpath.exists() else {}
        output = base64.b64decode(result.get('output_base64', ''))
        (work/'fsw-output.log').write_bytes(output)
        status, reason, events = classify(boot, result, output.decode(errors='replace'))
        report['result'].update(status=status, justification=reason, events=events, boot=boot,
            fsw={k:v for k,v in result.items() if k != 'output_base64'})
        report['timing']['guest_elapsed_seconds'] = result.get('guest_elapsed_seconds')
        report['software']['golden_unchanged'] = identity(a.golden) == golden
        if not report['software']['golden_unchanged']:
            report['result'].update(status='FAIL', justification='Golden identity changed')
    except Exception as exc:
        report['result'].update(status='BLOCKED', justification=str(exc))
    finally:
        save()
        lock.close()
    print(json.dumps(dict(status=report['result']['status'], reason=report['result'].get('justification'), evidence=str(work/'comparison.json')), indent=2))
    return 0 if report['result']['status'] == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
