#!/usr/bin/env python3
"""Independent end-to-end GPIO, DT, QOM and preserved V8 gate evaluation."""
import argparse
import json
from pathlib import Path
import re
import dt_contract as d


def evaluate(directory, contract_dir):
    directory=Path(directory);summary=json.loads((directory/'result.json').read_text())
    run=Path(summary['run']);users=json.loads((run/'userspace.json').read_text())
    rows=[u.get('phase10i_gpio',{}) for u in users]
    qom=json.loads((run/'phase10i-qom.json').read_text())
    contract=json.loads((Path(contract_dir)/'contract.json').read_text())
    runtime=d.runtime_check(contract,run)
    checks=dict(original_v8_and_strict_spi=summary['status']=='PASS',
        gpio_all_observations_pass=len(rows)>=2 and all(r.get('status')=='PASS' for r in rows),
        actual_original_pinctrl_driver=all(r.get('driver')=='pinctrl-rp1' for r in rows),
        cdev54_with_only_two_usable_lines=all(r.get('ngpio')==54 and
            [v['line'] for v in r.get('reserved_rejections',[])]==[19,22,28,53,54] for r in rows),
        gpio_values_and_edges=all([r['output'] for r in g.get('records',[])]==[1,0,1,0] and
            [r['input'] for r in g.get('records',[])]==[1,0,1,0] and
            [r['edge'] for r in g.get('records',[])]==[1,2,1,2] for g in rows),
        exclusive_ownership=all(r.get('ownership_rejected')==16 for r in rows),
        irq_accounting_and_quiescence=all(r.get('irq_delta',0)>=4 and r.get('no_extra_event') for r in rows),
        gpio_qom_realized=qom.get('/machine/native-rp1/rp1/gpio/realized',{}).get('return') is True,
        spi_qom_realized=qom.get('/machine/native-rp1/rp1/spi0/realized',{}).get('return') is True,
        dt_runtime_postconditions=runtime['status']=='PASS',
        active_multi_user_gpio_observations=sum(u.get('target')=='active' and
            u.get('phase10i_gpio',{}).get('status')=='PASS' for u in users)>=2)
    trace=(run/'hardware.log').read_text()
    notifications=re.findall(r'rp1_msix vector=(\d+)',trace)
    deliveries=re.findall(r'bcm2712_mip_timed virtual_ns=\d+ first=0 vector=(\d+) delivered=1',trace)
    checks['native_gpio_msix_mip_observed']=notifications.count('0')>=4 and deliveries.count('0')>=4
    checks['no_unsupported_gpio_mmio']=not re.search(r'rp1_gpio_access .*valid=0|rp1-gpio: unsupported',trace)
    report=dict(schema=1,status='PASS' if all(checks.values()) else 'PARTIAL',checks=checks,
        evidence_level='original captured kernel, original bound GPIO driver and cdev; virtual logical fixture only',
        physical_measurements=False,required_for_fsw='UNKNOWN',
        synthetic_fixture='GPIO20->21, logical directional loopback, zero-delay sampling',
        gpio_observations=rows,runtime_dt_contract=runtime,transformation=contract,
        source_inventory=str(directory/'source-manifest.json'),
        interrupts=dict(rp1_notifications_by_vector={v:notifications.count(v) for v in sorted(set(notifications))},
                        native_mip_deliveries_by_vector={v:deliveries.count(v) for v in sorted(set(deliveries))}),
        run=str(run),original_gate=summary)
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--directory',type=Path,required=True)
    p.add_argument('--contract-dir',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();report=evaluate(a.directory,a.contract_dir)
    a.output.write_text(json.dumps(report,indent=2)+'\n');print(report['status'],report['checks'])
    raise SystemExit(report['status']!='PASS')

if __name__=='__main__':main()
