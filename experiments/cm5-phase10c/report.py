#!/usr/bin/env python3
"""Normalize independently observed milestones and check post-exit persistence."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--fsw-audit', type=Path, required=True)
    p.add_argument('--controls', type=Path, required=True)
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=False, mode=0o700)
    run = json.loads((a.run/'result.json').read_text())
    users = json.loads((a.run/'userspace.json').read_text())
    fsw = json.loads((a.fsw_audit/'result.json').read_text())
    controls = json.loads((a.controls/'result.json').read_text())
    serial = (a.run/'serial.log').read_text(errors='replace')
    eligible = [u for u in users if u['target'] == 'active' and u['pid1'] == 'systemd']
    latest = eligible[-1]
    overlay = Path(run['overlay']['path'])
    lab = Path('/home/aweso/cm5-v8-lab/phase10c')/a.output.name
    lab.mkdir(parents=True, exist_ok=False)
    extents = json.loads(subprocess.check_output(['build-arm64-phase1/qemu-img', 'map',
                                                  '--output=json', str(overlay)]))
    own = [e for e in extents if e['depth'] == 0 and e.get('present')]
    logs_only = all(e['start'] >= 11821645824 and
                    e['start']+e['length'] <= 11821645824+1073741824 for e in own)
    subprocess.run(['build-arm64-phase1/qemu-img', 'convert', '--image-opts', '-O', 'raw',
        f'driver=raw,offset=11821645824,size=1073741824,file.driver=qcow2,file.file.driver=file,file.file.filename={overlay}',
        str(lab/'logs.ext4')], check=True, capture_output=True)
    (lab/'logs.ext4').chmod(0o400)
    dump = subprocess.run(['debugfs', '-R', f'dump /phase10c-public-diagnostic-01.dat {lab}/diagnostic.dat',
                           str(lab/'logs.ext4')], check=True, capture_output=True, text=True)
    (a.output/'persistence-tool.log').write_text(dump.stdout+dump.stderr)
    data = (lab/'diagnostic.dat').read_bytes()
    expected = bytes((i*31+7) % 251 for i in range(4096))
    milestones = dict(kernel_entry=run['kernel_entry'], native_emmc_partitions=run['emmc_partitions'],
        captured_initramfs_unmodified=not run['diagnostic_copy'],
        os_table_roots2='fec_roots 2' in latest['os_table'],
        fsw_table_roots2='fec_roots 2' in latest['fsw_table'],
        both_mappings_valid=latest['os_status'].endswith('verity V') and latest['fsw_status'].endswith('verity V'),
        verified_os_mount=latest['lower'].startswith('/dev/mapper/cm5_os_verified ext4 ro,'),
        switch_root_and_systemd=latest['pid1_exe'] == '/usr/lib/systemd/systemd',
        multi_user=len(eligible) >= 2 and eligible[-1]['uptime']-eligible[0]['uptime'] >= 20,
        verified_fsw_mount=latest['fsw'].startswith('/dev/mapper/cm5_fsw_verified ext4 ro,'),
        verified_fsw_block=latest['fsw_block0_sha256'] == fsw['expected_verified_block0_sha256'],
        library_call=latest['libc_call'], logs_guest_readback=latest['logs_fsync_readback'],
        logs_host_persistence=data == expected, writes_only_logs=logs_only,
        normal_qemu_exit=run['returncode'] == 0 and not run['timeout'], inputs_unchanged=run['inputs_unchanged'])
    root = re.search(r'\[\s*([0-9.]+)\] EXT4-fs \(dm-1\): mounted filesystem a3680812-', serial)
    comparison = dict(
        physical_v8=dict(kernel='6.18.50+rpt-rpi-2712', root_mount_seconds=41.377123,
            verification='OS/FSW V in reference status files; roots2 from earlier physical tables',
            storage='HS400/ADMA64/CQE16', pcie='native, RP1 x4 linked; expansion link down',
            logging_gap_cause='not empirically established; unchanged hook contains full verified scan'),
        phase9=dict(kernel='6.18.62 development surrogate', controls=controls,
            storage='legacy PIO', pcie='GPEX with RP1 and MIP',
            diagnostic='RAM-injected ELF reads FSW; no captured FSW executable claim'),
        phase10c=dict(kernel='captured 6.18.50+rpt-rpi-2712', root_mount_seconds=float(root[1]) if root else None,
            storage='opt-in existing ADMA64 plus bounded CMD23 backend batching',
            pcie='native MDIO and two enumerated root ports; no downstream RP1/link/translation/MSI',
            diagnostic='captured OS Python ELF and libc; captured FSW block and filesystem reads'))
    report = dict(status='PASS' if all(milestones.values()) else 'FAIL', milestones=milestones,
        original_result=str(a.run/'result.json'), userspace_evidence=str(a.run/'userspace.json'),
        original_parser_limits='serial-only multi_user/full_scan_complete false fields mean missing markers; independent userspace records establish target',
        scan_completion=dict(serial_marker_observed='Verified OS full read PASS' in serial,
            gated_handoff_inference=True,
            explanation='Unmodified captured hook gates root handoff on forty successful verified dd chunks and valid status; not a per-byte trace of all 10GiB.'),
        native_root_ports=sorted(set(re.findall(r'pci (000[12]:00:00\.0): \[14e4:2712\]', serial))),
        captured_fsw=fsw, user_record=latest,
        logs_file_sha256=hashlib.sha256(data).hexdigest(), overlay_extents=own,
        comparison=comparison,
        limitations=['No new physical FEC correction claim for this clean boot',
                     'No native RP1 endpoint, windows, training or native MSI validation',
                     'Header UART substitute only; SPI remains unavailable to captured kernel',
                     'Debug shell/console arguments added; firmware BOOT selection not executed'])
    (a.output/'result.json').write_text(json.dumps(report, indent=2)+'\n')
    (a.output/'comparison.json').write_text(json.dumps(comparison, indent=2)+'\n')
    (a.output/'summary.txt').write_text('\n'.join(f'{k}: {v}' for k, v in milestones.items())+'\n')
    print(report['status'], milestones)
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
