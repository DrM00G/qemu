#!/usr/bin/env python3
"""Repeat real qtests; retain commands, replies, and ordered device events.

AI-assisted local experiments only. Raw output is required outside the repo.
No physical devices and no full guest are started by this harness.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess

ROOT = Path(__file__).resolve().parents[2]
CASES = {
    'rp1': ['h-edge-config-no-duplicate', 'h-refill-before-completion',
            'h-function-pending-ack', 'h-delayed-service',
            'h-disable-abort-boundary', 'h-bar-decode-inflight',
            'h-two-pending-vectors', 'h-bme-inflight', 'drain-refill-deadline',
            'reset-active-pending-msix'],
    'cm5io': ['native-ssi-msix-inbound-mip', 'native-rp1-clock-pll-gate-reset'],
    'bcm2712-mip': ['edge-mask-gic-clear-reset', 'vector-ranges-offset'],
}
EVENTS = ['dw_apb_ssi_boundary', 'dw_apb_ssi_timer', 'dw_apb_ssi_cs',
          'dw_apb_ssi_transfer', 'rp1_spi_notify', 'rp1_spi_state',
          'bcm2712_mip_timed', 'bcm2712_pcie_access', 'bcm2712_pcie_dma_write',
          'qmp_enter_system_reset', 'qmp_exit_system_reset']


def digest(data):
    return hashlib.sha256(data).hexdigest()


def normalize(path, protocol=False):
    rows = []
    for line in path.read_text().splitlines():
        if protocol or protocol is None:
            # Remove host elapsed timestamps only, retaining every command/reply.
            match = re.match(r'\[([RS]) [^]]+\] (.*)', line)
            if match:
                rows.append(dict(direction=match[1], payload=match[2]))
                continue
        if not protocol:
            match = re.search(r'^(' + '|'.join(EVENTS) + r') (.*)', line)
            if not match:
                continue
            payload = match[2]
            fields = dict(re.findall(r'(\w+)=([^ ]+)', payload))
            fields = {k: int(v, 0) for k, v in fields.items()}
            if match[1].startswith('qmp_'):
                rows.append(dict(event=match[1], payload=payload, virtual_ns=None))
                continue
            rows.append(dict(event=match[1], transition=payload.split()[0]
                             if '=' not in payload.split()[0] else None,
                             virtual_ns=fields.get('virtual_ns'), fields=fields))
    if not rows:
        raise ValueError('empty capture: ' + str(path))
    return rows



def semantic_checks(name, events):
    expectations = {
        'h-edge-config-no-duplicate': ([0x12, 0x34], 2, 2),
        'h-refill-before-completion': ([0x12, 0x34], 1, 0),
        'h-function-pending-ack': ([0x12, 0x34], 2, 2),
        'h-delayed-service': ([0x12, 0x34, 0x56], 2, 3),
        'h-disable-abort-boundary': ([0x56], 2, 0),
        'h-bar-decode-inflight': ([0x12], 1, 0),
        'h-bme-inflight': ([0x12], 1, 2),
        'reset-active-pending-msix': ([0x12], 2, 1),
        'drain-refill-deadline': ([0x12, 0x34], 2, 0),
    }
    if name not in expectations:
        return {'qtest_state_assertions': True}
    words, segments, notifications = expectations[name]
    transfers = [e['fields'] for e in events if e['event']=='dw_apb_ssi_transfer']
    actual_segments = sum(e['event']=='dw_apb_ssi_cs' and
                          e['fields']['selected']==1 for e in events)
    attempts = sum(e['event']=='rp1_spi_notify' for e in events)
    return dict(tx_sequence=[t['tx'] for t in transfers]==words,
                rx_sequence=[t['rx'] for t in transfers]==[w ^ 0xa5 for w in words],
                cs_segments=actual_segments==segments, notification_attempts=attempts==notifications)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--summary', type=Path, required=True)
    parser.add_argument('--sequences', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    if out.is_relative_to(ROOT):
        parser.error('raw captures must be outside repository')
    out.mkdir(parents=True, exist_ok=False)
    executable = ROOT/'build-arm64-phase1/qemu-system-aarch64'
    inventory = [ROOT/p for p in ['hw/misc/rp1-pci.c', 'hw/ssi/dw-apb-ssi.c',
                 'hw/arm/bcm2712-pcie.c', 'hw/arm/cm5io-dev.c', 'hw/intc/bcm2712-mip.c',
                 'tests/qtest/rp1-test.c', 'tests/qtest/cm5io-test.c',
                 'tests/qtest/bcm2712-mip-test.c', 'experiments/cm5-phase10h/ordering.py']]
    result = dict(schema=1, clock='qtest-controlled-virtual-ns',
                  physical_measurements=False, executable_sha256=digest(executable.read_bytes()),
                  sources={str(p.relative_to(ROOT)): digest(p.read_bytes()) for p in inventory},
                  private_evidence=str(out), cases=[])
    for suite, names in CASES.items():
        prefix = 'cm5io-dev' if suite == 'cm5io' else suite
        for name in names:
            runs = []
            for repetition in range(2):
                stem = out/f'{suite}-{name}-{repetition}'
                # One stderr stream preserves command/device/reply ordering.
                combined = Path(str(stem)+'.log')
                extra = ['-qtest-log', '/dev/stderr']
                for event in EVENTS:
                    extra += ['-trace', 'enable='+event]
                command = [str(ROOT/f'build-arm64-phase1/tests/qtest/{suite}-test'),
                           '-p', f'/aarch64/{prefix}/{name}']
                env = dict(os.environ, QTEST_QEMU_BINARY=str(executable),
                           QTEST_QEMU_ARGS=shlex.join(extra))
                # A pipe avoids independent file offsets from /dev/stderr opens.
                process = subprocess.run(command, env=env, stdout=subprocess.PIPE,
                                         stderr=subprocess.STDOUT, timeout=60)
                combined.write_bytes(process.stdout)
                capture = dict(command=command, extra_args=extra, returncode=process.returncode,
                               events=normalize(combined), protocol=normalize(combined, True),
                               sequence=normalize(combined, None))
                encoded = json.dumps(capture, sort_keys=True).encode()
                Path(str(stem)+'.json').write_bytes(encoded)
                runs.append(capture)
            events_equal = runs[0]['events'] == runs[1]['events']
            protocol_equal = runs[0]['protocol'] == runs[1]['protocol']
            sequence_equal = runs[0]['sequence'] == runs[1]['sequence']
            row = dict(suite=suite, name=name, returncodes=[r['returncode'] for r in runs],
                       events_equal=events_equal, protocol_equal=protocol_equal, sequence_equal=sequence_equal,
                       event_count=len(runs[0]['events']), protocol_count=len(runs[0]['protocol']),
                       events_sha256=digest(json.dumps(runs[0]['events'],sort_keys=True).encode()),
                       protocol_sha256=digest(json.dumps(runs[0]['protocol'],sort_keys=True).encode()))
            row['semantic_checks'] = semantic_checks(name, runs[0]['events'])
            row['status'] = 'PASS' if (row['returncodes']==[0,0] and events_equal and
                protocol_equal and sequence_equal and all(row['semantic_checks'].values())) else 'FAIL'
            result['cases'].append(row)
    result['status'] = 'PASS' if all(c['status']=='PASS' for c in result['cases']) else 'FAIL'
    evidence = args.sequences
    evidence.mkdir(exist_ok=False)
    for capture_file in sorted(out.glob('*-0.json')):
        capture = json.loads(capture_file.read_text())
        (evidence/(capture_file.stem.removesuffix('-0')+'.jsonl')).write_text(
            ''.join(json.dumps(dict(index=i, **row),sort_keys=True)+'\n'
                    for i,row in enumerate(capture['sequence'])))
    (out/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    args.summary.write_text(json.dumps(result,indent=2)+'\n')
    print(result['status'], len(result['cases']), 'cases, two runs each')
    raise SystemExit(result['status'] != 'PASS')


if __name__ == '__main__':
    main()
