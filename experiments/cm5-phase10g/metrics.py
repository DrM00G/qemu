#!/usr/bin/env python3
"""Small normalized virtual observation; no physical collection or timing claim."""
import argparse
import hashlib
import json
from pathlib import Path


def export(run, native, correlation=None):
    users=json.loads((run/'userspace.json').read_text())
    observations=[u['native_rp1'] for u in users if 'native_rp1' in u]
    messages=[m for n in observations for m in n.get('spi',{}).get('messages',[])]
    first=next(n for n in observations if n.get('spi',{}).get('messages'))
    selection=json.loads(Path(json.loads((run/'result.json').read_text())['boot_selection_report']).read_text())
    rows=[]
    for i,m in enumerate(messages):
        spans=correlation['messages'][i]['segments'] if correlation else None
        rows.append(dict(index=i,length=m['length'],tx_sha256=m['tx_sha256'],rx_sha256=m['rx_sha256'],
            cs_segments=spans,completion='DATA_RETURNED_FRAMING_SEPARATELY_VALIDATED'))
    rates=correlation.get('ssi_rates',[]) if correlation else []
    return dict(schema=1,environment='virtual',run_id=run.name,status=native['status'],
        fixture=dict(identity='qemu,ssi-test-slave XOR0xa5',wiring='logical native RP1 SPI0 CS0',
                     comparability='physical fixture/wiring UNKNOWN; no electrical comparison'),
        workload=dict(mode=0,bits_per_word=8,requested_speed_hz=first['spi']['speed_hz'],
            divider_speed_hz=rates[0]['divider_speed_hz'] if len(rates)==1 else None,measured_sclk_hz=None,
            definition_sha256=hashlib.sha256(json.dumps(messages,sort_keys=True).encode()).hexdigest()),
        provenance=dict(selected_files={k:dict(name=n,sha256=selection['files'][n]['sha256']) for k,n in selection['selected'].items()},
            runtime_dt=[u.get('boot_handoff_runtime',{}).get('fdt_sha256') for u in users],
            boot_order_confirmation='UNCONFIRMED_FIXTURE',driver=first['spi']['controller_driver']),
        pcie=dict(bdf='0002:01:00.0',
            link_gt_s=5.0 if native['checks'].get('native_gen2_x4') else None,
            link_width=4 if native['checks'].get('native_gen2_x4') else None,resources=first['resources'],chip_id=first['chip_id']),
        ssi=dict(clock_divider_observations=rates,register_events='see correlation.json',dma='UNSUPPORTED_PIO_ONLY'),
        interrupts=dict(msix_vectors=len(first.get('msi_irqs',[])),source_vector=19,
            sample_counts=[dict(before=n.get('spi',{}).get('irq_before'),after=n.get('spi',{}).get('irq_after')) for n in observations],
            notifications=correlation.get('notifications') if correlation else None,
            mip_deliveries=correlation.get('mip_deliveries') if correlation else None),
        clock_domains=dict(execution_profile=json.loads((run/'result.json').read_text()).get('execution_clock','host'),
                           guest_virtual_ns='QEMU_CLOCK_VIRTUAL; execution profile in command.json',
                           guest_uptime='guest kernel clock since boot',host_elapsed='runner monotonic seconds',
                           analyzer=None),messages=rows,
        raw_evidence=[str(run),native['original_run']],
        limitations=['No physical observations','No electrical timebase or SCLK measurement',
                     'Generated lab DT substitutes captured physical DT','No GPIO/pinctrl or SPI DMA'])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',type=Path,required=True);p.add_argument('--native-report',type=Path,required=True)
    p.add_argument('--correlation',type=Path);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();r=export(a.run,json.loads(a.native_report.read_text()),
                            json.loads(a.correlation.read_text()) if a.correlation else None)
    a.output.write_text(json.dumps(r,indent=2)+'\n')


if __name__=='__main__':main()
