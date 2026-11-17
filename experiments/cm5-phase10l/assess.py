#!/usr/bin/env python3
"""Read-only clean operational-run assessment; not a corruption injector."""
import argparse
import json
import os
from pathlib import Path
import re
import statistics
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'experiments/cm5-phase10j'))
from events import summarize


def load(path):
    return json.loads(path.read_text())


def timeline(run):
    return {r['event']: r['host_seconds'] for r in
            map(json.loads, (run/'v8/host-timeline.jsonl').read_text().splitlines())}


def intervals(run):
    t = timeline(run)
    pairs = dict(kernel_to_root=('kernel_entry', 'verified_root_mount'),
                 launch_to_root=('qemu_launch', 'verified_root_mount'),
                 launch_to_userspace_validated=('qemu_launch', 'userspace_validated'),
                 upload=('upload_start', 'upload_verified'),
                 fsw_receipt_interval=('fsw_start', 'fsw_result_received'),
                 qemu_lifetime=('qemu_launch', 'qemu_exit'))
    return {k: t[b]-t[a] for k, (a, b) in pairs.items() if a in t and b in t}


def ack_metrics(run):
    console = (run/'v8/debug-serial.log').read_bytes()
    chunks = list(map(json.loads, (run/'v8/debug-chunks.jsonl').read_text().splitlines()))
    index, observations = 0, []
    for match in re.finditer(rb'(?:^|[\r\n])P10J_UPLOAD_ACK=(\d+)(?=[\r\n])', console):
        while chunks[index]['end_offset'] < match.end()+1:
            index += 1
        observations.append(dict(ack=int(match[1]), host_seconds=chunks[index]['host_seconds']))
    delta = [b['host_seconds']-a['host_seconds'] for a, b in zip(observations, observations[1:])]
    return dict(observations=observations, count=len(observations),
                consecutive=[x['ack'] for x in observations] == list(range(len(observations))),
                delta_median=statistics.median(delta) if delta else None,
                delta_mean=statistics.mean(delta) if delta else None)


def canonical_table(table):
    parts = table.split()
    # Kernel-assigned device numbers are not persistent artifact identities.
    parts[4:6] = ['DATA_DEVICE', 'HASH_DEVICE']
    if 'use_fec_from_device' in parts:
        parts[parts.index('use_fec_from_device')+1] = 'FEC_DEVICE'
    return parts


def verified_mounts(users):
    ready = [u for u in users if u['target'] == 'active' and u['pid1'] == 'systemd']
    # Before systemd mounts FSW, the mapper can already be valid while findmnt
    # returns no mount. Never permit an observed raw/writable substitute, and
    # require both protected mounts at every readiness observation.
    return bool(ready) and all(
        u['lower'].startswith('/dev/mapper/cm5_os_verified ext4 ro,') and
        (not u['fsw'] or u['fsw'].startswith('/dev/mapper/cm5_fsw_verified ext4 ro,'))
        for u in users) and all(
            u['fsw'].startswith('/dev/mapper/cm5_fsw_verified ext4 ro,') for u in ready)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--strict-reference', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.resolve().is_relative_to(ROOT):
        parser.error('output must remain private outside checkout')
    os.umask(0o077)
    args.output.mkdir(parents=True, exist_ok=False, mode=0o700)
    report = load(args.run/'comparison.json')
    boot = load(args.run/'v8/result.json')
    fsw = load(args.run/'v8/fsw-result.json')
    users = load(args.run/'v8/userspace.json')
    reference = load(args.strict_reference/'v8/userspace.json')[-1]
    serial = (args.run/'v8/serial.log').read_text(errors='replace')
    events = summarize((args.run/'fsw-output.log').read_bytes().decode(errors='replace'))
    ready = [u for u in users if u['target'] == 'active' and u['pid1'] == 'systemd']
    overlay = args.run/'emmc.qcow2'
    extents = json.loads(subprocess.check_output([
        str(ROOT/'build-arm64-phase1/qemu-img'), 'map', '--output=json', str(overlay)]))
    own = [x for x in extents if x['depth'] == 0 and x.get('present')]
    # Captured LOGS p6 range; assert against the accepted partition table too.
    selection = load(args.run/'preflight-boot/selection.json')
    logs = next(x for x in selection['partitions'] if x['partition'] == 6)
    lo, hi = logs['start']*512, (logs['start']+logs['sectors'])*512
    counts = events['counts']
    checks = dict(
        profile=boot['boot_profile'] == 'operational' and report['operation']['boot_profile'] == 'operational',
        golden_unchanged=report['software']['golden_unchanged'] and boot['inputs_unchanged'],
        kernel_and_verified_root=boot['kernel_entry'] and boot['os_mount'],
        multi_user=len(ready) >= 2 and ready[-1]['uptime']-ready[0]['uptime'] >= 20,
        maps_and_original_root_settings=all(
            canonical_table(u[k]) == canonical_table(reference[k]) and u[k.replace('table', 'status')].endswith('verity V')
            for u in users for k in ('os_table', 'fsw_table')),
        protected_mounts_readonly=verified_mounts(users),
        exhaustive_scan_skipped=all(u['phase10l_boot']['profile_marker'] == 'operational' and
            'PHASE10L_OPERATIONAL' in (u['phase10l_boot']['os_log'] or '') and
            not u['phase10l_boot']['scan_dd_log_exists'] and
            'Verified OS full read PASS' not in u['phase10l_boot']['os_log'] for u in users),
        approved_ram_elf=fsw['sha256'] == 'b0b4dd5af15b4cbfd8005da10551cf4dc9f9ce45166299c4996d238a5362fbc3',
        fsw_timeout=fsw['status'] == 'COMPLETE' and fsw['exit_status'] == 124 and not fsw.get('watchdog_killed'),
        initialization=counts['initializations'] == 20 and counts['tasks_created'] == 11 and counts['tasks_started'] == 10,
        housekeeping=counts['housekeeping'] >= 1,
        internal_packet_path=all(counts[k] >= 1 for k in ('packet_receipts', 'packet_routes', 'queue_items', 'tx_dumps')),
        sampled_libc=all(u['libc_call'] for u in users),
        no_observed_application_crash=counts['crashes'] == 0,
        normal_shutdown=boot['normal_poweroff'] and boot['returncode'] == 0 and not boot['timeout'],
        no_protected_partition_allocations=all(lo <= x['start'] and x['start']+x['length'] <= hi for x in own))
    ack = ack_metrics(args.run)
    checks['all_frames_acknowledged'] = ack['consecutive'] and ack['count'] == next(
        r['frames']+1 for r in map(json.loads, (args.run/'v8/host-timeline.jsonl').read_text().splitlines())
        if r['event'] == 'upload_start')
    guest_kernel = {}
    for name, pattern in [('verified_root', r'EXT4-fs \(dm-1\): mounted'), ('systemd', r'systemd\[1\]: systemd 257')]:
        match = re.search(r'\[\s*([\d.]+)\] '+pattern, serial)
        guest_kernel[name] = float(match[1]) if match else None
    result = dict(status='PASS_LOCAL_OPERATIONAL' if all(checks.values()) else 'FAIL_LOCAL_OPERATIONAL',
        checks=checks, events=counts, host_intervals_seconds=intervals(args.run),
        strict_host_intervals_seconds=intervals(args.strict_reference),
        outer_host_seconds=report['timing']['host_elapsed_seconds'],
        strict_outer_host_seconds=load(args.strict_reference/'comparison.json')['timing']['host_elapsed_seconds'],
        guest_kernel_log_seconds=guest_kernel,
        guest_monotonic_fsw_seconds=fsw['guest_elapsed_seconds'], qemu_virtual_seconds=None,
        overlay_own_extents=own,
        limitations=dict(protected_fsw_executable_survival='NOT_TESTED_RAM_STAGED',
            unaccessed_os_integrity='NOT_SCANNED_BY_DESIGN', peripheral_external_io='NOT_ESTABLISHED',
            corruption_recovery='NOT_TESTED_CLEAN_OVERLAY', full_physical_equivalence=False))
    (args.output/'assessment.json').write_text(json.dumps(result, indent=2)+'\n')
    (args.output/'acks.json').write_text(json.dumps(ack, indent=2)+'\n')
    (args.output/'normalized-events.json').write_text(json.dumps(events, indent=2)+'\n')
    print(json.dumps(result, indent=2))
    return 0 if all(checks.values()) else 1


if __name__ == '__main__':
    sys.exit(main())
