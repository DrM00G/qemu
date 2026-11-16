#!/usr/bin/env python3
"""Publish reviewed field selections only; never copy raw guest/QOM/DT logs."""
import argparse
import hashlib
import json
from pathlib import Path
import evaluate


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def collect(directory, contract):
    directory = Path(directory)
    load = lambda name: json.loads((directory / name).read_text())
    gate = load('result.json')
    run = Path(gate['run'])
    users = json.loads((run / 'userspace.json').read_text())
    native = load('native-report/result.json')
    provenance = load('provenance/provenance.json')
    recovery = json.loads((run / 'recovery-result.json').read_text())
    correlation = load('correlation.json')
    vertical = evaluate.evaluate(directory, contract)
    source = load('source-manifest.json')
    return dict(run_id=directory.name, status=vertical['status'],
        speed_hz=gate['speed_hz'], execution_clock=gate['execution_clock'],
        physical_measurement=False, required_for_fsw='UNKNOWN',
        original_kernel_release='6.18.50+rpt-rpi-2712',
        executable_sha256=provenance['qemu_executable']['sha256'],
        command_sha256=provenance['actual_qemu_arguments_sha256'],
        execution_sources=source['sources'],
        selected_files=provenance['selected_files'],
        boot_order_confirmation='UNCONFIRMED_FIXTURE',
        physical_firmware_equivalence=False,
        original_provenance_checks=provenance['checks'],
        original_recovery_checks=recovery['checks'],
        native_checks=native['checks'], vertical_checks=vertical['checks'],
        spi=dict(submitted_messages=correlation['submitted_messages'],
                 cs_segments=correlation['cs_segments'],
                 completed_bytes=correlation['completed_bytes'],
                 failed_messages=correlation['failed_messages'],
                 strict_oracle=correlation['strict_oracle']),
        interrupts=vertical['interrupts'],
        gpio_observations=[dict(status=g['status'], driver=g.get('driver'),
             ngpio=g.get('ngpio'), records=g.get('records'),
             reserved_rejections=g.get('reserved_rejections'),
             ownership_rejected=g.get('ownership_rejected'),
             irq_delta=g.get('irq_delta'), no_extra_event=g.get('no_extra_event'),
             discovered_chips=g.get('discovered_chips'))
             for g in vertical['gpio_observations']],
        independently_active_multi_user=[dict(guest_uptime_s=u['uptime'],
                    gpio_status=u['phase10i_gpio']['status'])
                    for u in users if u.get('target') == 'active'],
        live_fdt_sha256=sorted({u['boot_handoff_runtime']['fdt_sha256'] for u in users}),
        live_gpio_contract=vertical['runtime_dt_contract'],
        generated_dt_contract=vertical['transformation'],
        synthetic_fixtures=['logical SPI0 CS0 XOR0xa5 slave',
                            'unidirectional zero-delay GPIO20->21'],
        private_evidence=str(directory),
        evidence_hashes={name:digest(directory/name) for name in
            ['result.json','source-manifest.json','correlation.json',
             'native-report/result.json','provenance/provenance.json']},
        limits=['No physical measurements or approved FSW workload',
                'No calibrated BCM2712 CPU/electrical/bus timing',
                'Do not compare guest-monotonic ns with QEMU virtual ns directly',
                'G aggregate notification counters include GPIO; use per-vector counts',
                'Early inactive/time-out systemd observations retained privately; independent later active observations decide gate'])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',type=Path,action='append',required=True)
    parser.add_argument('--contract-dir',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    report=dict(schema=1,environment='qemu',physical_measurements=False,
                runs=[collect(d,args.contract_dir) for d in args.directory])
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print([(r['run_id'],r['status'],r['spi']) for r in report['runs']])


if __name__=='__main__':main()
