#!/usr/bin/env python3
"""One fresh BOOT-selected captured V8/native SPI experiment; no physical I/O."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--work', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--hz', type=int, choices=(10000, 100000, 1000000), required=True)
    p.add_argument('--execution-clock', choices=('host','icount-1ns','icount-adaptive'), default='host')
    p.add_argument('--timeout', type=int, default=600, help='explicit full guest wall-time bound')
    p.add_argument('--phase10i-gpio-lab', action='store_true')
    p.add_argument('--phase10h-smp-stress', action='store_true')
    p.add_argument('--diagnostics', action='store_true')
    a = p.parse_args()
    work, out = a.work.resolve(), a.output.resolve()
    if work.is_relative_to(ROOT):
        p.error('private work must be outside repository')
    work.mkdir(mode=0o700, parents=True, exist_ok=False)
    out.mkdir(parents=True, exist_ok=False)
    env = dict(os.environ, CM5_BOOT_READER='qemu-io', CM5_BOOT_PREFETCH='65536')
    disk = work/'emmc.qcow2'
    commands = []
    def execute(command, name):
        commands.append([str(x) for x in command])
        (out/'commands.json').write_text(json.dumps(commands, indent=2))
        with (out/(name+'.log')).open('xb') as log:
            return subprocess.run(commands[-1], cwd=ROOT, env=env, stdout=log,
                                  stderr=subprocess.STDOUT).returncode
    execute([ROOT/'build-arm64-phase1/qemu-img','create','-f','qcow2','-F','raw',
             '-b','/home/aweso/cm5-v8-lab/golden/cm5-emmc-userarea.img',disk], 'image')
    sources = [ROOT/x for x in ('hw/ssi/dw-apb-ssi.c','include/hw/ssi/dw-apb-ssi.h',
        'hw/misc/rp1-pci.c','hw/intc/bcm2712-mip.c','hw/arm/bcm2712-pcie.c',
        'experiments/cm5-phase10e/native_profile.py','experiments/cm5-phase10c/run.py',
        'hw/ssi/trace-events','hw/misc/trace-events','hw/intc/trace-events',
        'experiments/cm5-phase10g/run.py','experiments/cm5-phase10g/correlate.py',
        'experiments/cm5-phase10g/metrics.py')]
    if a.phase10h_smp_stress:
        sources += [ROOT/'experiments/cm5-phase10h'/name for name in
                    ('smp_observer.py', 'smp_worker.py')]
    if a.phase10i_gpio_lab:
        sources += [ROOT/x for x in ('hw/arm/cm5io-dev.c', 'hw/gpio/rp1-gpio.c',
            'include/hw/gpio/rp1-gpio.h', 'hw/gpio/trace-events',
            'include/hw/arm/bcm2712-pcie.h', 'hw/gpio/meson.build',
            'experiments/cm5-phase10i/guest_gpio.py', 'experiments/cm5-phase10i/linux_census.py',
            'experiments/cm5-phase10i/observer.py')]
    snapshot = work/'execution-sources'; snapshot.mkdir()
    for source in sources:
        destination=snapshot/source.relative_to(ROOT)
        destination.parent.mkdir(parents=True,exist_ok=True)
        destination.write_bytes(source.read_bytes())
    (out/'source-manifest.json').write_text(json.dumps(dict(schema=1,
        sources={str(x):hashlib.sha256(x.read_bytes()).hexdigest() for x in sources},
        private_snapshot=str(snapshot),hz=a.hz,diagnostics=a.diagnostics,execution_clock=a.execution_clock,
        phase10h_smp_stress=a.phase10h_smp_stress,phase10i_gpio_lab=a.phase10i_gpio_lab),indent=2))
    run = out/(out.name+'-v8')
    command = [sys.executable,ROOT/'experiments/cm5-phase10c/run.py',
        '--execution-clock',a.execution_clock,'--control-pipes','--dma','--batch','--profile','native',
        '--boot-selection-policy','eeprom-fixture-0xf14','--boot-config-profile','cm5-headless-lab',
        '--boot-overlay',disk,'--boot-expected',
        '/home/aweso/cm5-v8-lab/phase10f2/accepted-01/accepted-hashes.json',
        '--debug-shell','--poweroff-after-validation','--recovery-case','clean',
        '--native-rp1-test','--native-spi-hz',str(a.hz),'--timeout',str(a.timeout),'--output',run]
    if a.phase10i_gpio_lab:
        command += ['--phase10i-gpio-lab', '--observer-upload-once']
    if a.phase10h_smp_stress:
        command += ['--phase10h-smp-stress', '--observer-upload-once']
    if a.execution_clock != 'host':command.append('--observer-upload-once')
    if a.diagnostics:
        command.append('--native-spi-diagnostics')
    rc = execute(command,'runner')
    if not (run/'recovery-result.json').exists():
        raise SystemExit('runner stopped; inspect runner.log (rc '+str(rc)+')')
    native_rc = execute([sys.executable,ROOT/'experiments/cm5-phase10e/report.py',
        '--run',run,'--output',out/'native-report'],'native-report')
    provenance_rc = execute([sys.executable,ROOT/'experiments/cm5-phase10f1/evaluate.py',
        '--run',run,'--native-report',out/'native-report/result.json',
        '--output',out/'provenance'],'provenance')
    correlation_rc = 0
    if a.diagnostics:
        correlation_rc = execute([sys.executable,ROOT/'experiments/cm5-phase10g/correlate.py',
                 '--run',run,'--output',out/'correlation.json'],'correlation')
    metrics_command=[sys.executable,ROOT/'experiments/cm5-phase10g/metrics.py',
        '--run',run,'--native-report',out/'native-report/result.json','--output',out/'metrics.json']
    if a.diagnostics:metrics_command += ['--correlation',out/'correlation.json']
    metrics_rc = execute(metrics_command,'metrics')
    original = json.loads((run/'result.json').read_text())
    complete = original['status']=='PASS' and rc == native_rc == provenance_rc == correlation_rc == metrics_rc == 0
    status = 'PASS' if complete else 'PARTIAL'
    if original['status'] != 'PASS':status='INCONCLUSIVE'
    result = dict(schema=1,status=status,
        report_returncodes=dict(runner=rc,native=native_rc,provenance=provenance_rc,
                                correlation=correlation_rc,metrics=metrics_rc),
        speed_hz=a.hz,execution_clock=a.execution_clock,native_report=str(out/'native-report/result.json'),run=str(run),
        physical_measurement=False)
    (out/'result.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result),flush=True)


if __name__ == '__main__':
    main()
