#!/usr/bin/env python3
"""Private, read-only Phase10K captured-evidence analysis. Not for upstream."""
import argparse
import base64
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'cm5-phase10j'))
from events import summarize

PHYSICAL = dict(initializations=20, components=13, tasks_created=11,
                tasks_started=10, housekeeping=11, packet_receipts=5,
                packet_routes=5, queue_items=5, tx_dumps=5,
                watchdog_unimplemented=30, spi_failures=273,
                spi_open_failures=1, serial_init_failures=1, crashes=0)


def analyze(source, output):
    os.umask(0o077)
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    raw = (source/'fsw-output.log').read_bytes()
    fsw = json.loads((source/'v8/fsw-result.json').read_text())
    if raw != base64.b64decode(fsw['output_base64'], validate=True):
        raise ValueError('Raw FSW log differs from guest result')
    normalized = summarize(raw.decode(errors='replace'))
    normalized.update(raw_sha256=hashlib.sha256(raw).hexdigest(),
        physical_source='User-supplied complete-transcript counts; raw physical transcript not inspected here',
        comparison={k: dict(qemu=normalized['counts'][k], physical=v,
                            delta=normalized['counts'][k]-v) for k, v in PHYSICAL.items()})
    original = json.loads((source/'comparison.json').read_text())
    normalized['old_classifier_counts'] = {k: len(v) for k, v in original['result']['events'].items()}
    observations = [json.loads(x) for x in (source/'v8/observations.jsonl').read_text().splitlines()]
    io = []
    for sample in observations:
        fields = {k: int(v) for k, v in re.findall(r'(\w+): (\d+)', sample.get('host_io', ''))}
        io.append(dict(host_seconds_since_qemu_start=sample.get('wall_seconds'), **fields))
    hardware = (source/'v8/hardware.log').read_text(errors='replace')
    serial = (source/'v8/serial.log').read_text(errors='replace')
    milestones = {}
    for name, pattern in dict(initramfs=r'Run /init as init process',
                              recovery_mount=r'EXT4-fs \(mmcblk0p7\): mounted',
                              verified_root_mount=r'EXT4-fs \(dm-1\): mounted',
                              systemd=r'systemd\[1\]: systemd 257',
                              power_down=r'reboot: Power down').items():
        match = re.search(r'\[\s*([0-9.]+)\] '+pattern, serial)
        milestones[name] = float(match[1]) if match else None
    packed = base64.b64encode(zlib.compress((source/'guest-workload.py').read_bytes()))
    frame_count = (len(packed)+2047)//2048
    batches = re.findall(r'sdcard_read_batch addr=(0x[0-9a-f]+) bytes=(\d+) result=(-?\d+)', hardware)
    names = ['preflight-boot/selection.json', 'launch.json', 'v8/inputs-before.json',
             'v8/process.json', 'v8/fsw-result.json', 'v8/result.json', 'comparison.json']
    started = datetime.fromisoformat(original['utc_started']).timestamp()
    artifacts = {n: dict(mtime_host_utc_seconds=(source/n).stat().st_mtime,
                         seconds_after_outer_start=(source/n).stat().st_mtime-started)
                 for n in names}
    runtime = dict(outer_host_seconds=original['timing']['host_elapsed_seconds'],
        qemu_loop_host_seconds=original['result']['boot']['wall_seconds'],
        guest_monotonic_fsw_seconds=fsw['guest_elapsed_seconds'],
        guest_monotonic_fsw_start=fsw['guest_monotonic_start'],
        guest_monotonic_fsw_end=fsw['guest_monotonic_end'],
        kernel_log_guest_seconds=milestones,
        upload=dict(encoded_frame_bytes_with_newlines=len(packed)+frame_count,
                    frames=frame_count, framing='2048 base64 characters per acknowledged frame',
                    caveat='Recomputed from captured launcher using unchanged transport; no host per-ACK timestamps in baseline'),
        qemu_virtual_seconds=None,
        artifact_mtimes=artifacts,
        mtime_caveat='Host file mtimes give approximate stage boundaries, not event timestamps or CPU attribution',
        host_io_samples=io,
        bounded_trace=dict(window_host_seconds=[20, 22], batch_calls=len(batches),
            batch_bytes=sum(int(b[1]) for b in batches),
            unsuccessful_batches=sum(int(b[2]) < 0 for b in batches),
            sizes=sorted(set(int(b[1]) for b in batches)),
            logical_block_trace_calls=len(re.findall(r'sdcard_read_block ', hardware)),
            caveat='Logical 512-byte trace calls include cache hits; not backend calls. Window is runner-requested, with no per-event timestamps.'),
        qmp_caveat='Existing blockstats report zero reads despite host reads and SD trace; not a usable storage throughput counter',
        userspace=[{k: x.get(k) for k in ('uptime', 'target', 'os_status', 'fsw_status')}
                   for x in json.loads((source/'v8/userspace.json').read_text())])
    for name, data in [('normalized-events.json', normalized), ('runtime.json', runtime)]:
        (output/name).write_text(json.dumps(data, indent=2)+'\n')
    files = ['fsw-output.log', 'comparison.json', 'v8/fsw-result.json', 'v8/result.json',
             'v8/userspace.json', 'v8/hardware.log', 'runner.log', 'preflight-boot/selection.json']
    (output/'source-identities.json').write_text(json.dumps({n: dict(
        sha256=hashlib.sha256((source/n).read_bytes()).hexdigest(), bytes=(source/n).stat().st_size)
        for n in files}, indent=2)+'\n')
    for key, row in normalized['comparison'].items():
        print(f"{key}: QEMU={row['qemu']} physical={row['physical']} delta={row['delta']:+d}")
    print('PARTIAL: count agreement does not establish physical equivalence')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True, help='fresh private directory outside checkout')
    args = parser.parse_args()
    if args.output.resolve().is_relative_to(Path(__file__).resolve().parents[2]):
        parser.error('output must remain outside checkout')
    analyze(args.source, args.output)
