#!/usr/bin/env python3
"""Strict independent report: boot, BARs, IRQs, bytes AND CS framing."""
import argparse
import hashlib
import json
from pathlib import Path
import re

from trace_check import check


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    base=json.loads((a.run/'recovery-result.json').read_text())
    users=json.loads((a.run/'userspace.json').read_text())
    serial=(a.run/'serial.log').read_text(errors='replace')
    trace=(a.run/'hardware.log').read_text(errors='replace')
    observations=[u['native_rp1'] for u in users if 'native_rp1' in u]
    def bars(n):
        try:return [int(x.split()[1],16)-int(x.split()[0],16)+1 for x in n['resources']]
        except (KeyError,ValueError,IndexError):return []
    native=[n for n in observations if n.get('vendor')=='0x1de4' and n.get('device')=='0x0001' and
            n.get('chip_id')==0x20001927 and n.get('bar2_scratch') and
            n.get('driver','').endswith('/rp1') and bars(n)==[16384,4194304,65536]]
    spi=[n for n in native if n.get('spi',{}).get('status')=='PASS' and n.get('target_after_spi')=='active']
    all_messages=[m for n in observations for m in n.get('spi',{}).get('messages',[])]
    successful = [n['spi'] for n in observations if n.get('spi',{}).get('status')=='PASS']
    def irq_total(record, key):
        return sum(v['count'] for v in record.get(key,{}).values())
    idle_stable = len(successful)>=2 and all(
        irq_total(b,'irq_before') == irq_total(a,'irq_after')
        for a,b in zip(successful,successful[1:]))
    framing=check(trace.splitlines(),all_messages)
    checks=dict(clean_original_verified_boot=base['status']=='PASS_CLEAN',
       native_gen2_x4='1000120000.pcie: link up, 5.0 GT/s PCIe x4' in serial,
       expansion_link_down='1000110000.pcie: link down' in serial,
       endpoint_enumerated='pci 0002:01:00.0: [1de4:0001]' in serial,
       kernel_chip_id='rp1 0002:01:00.0: chip_id 0x20001927' in serial,
       userspace_bars=bool(native), msix_vectors61=any(len(n.get('msi_irqs',[]))==61 for n in native),
       repeated_spi_after_multi_user=len(spi)>=2,
       native_mip_event='bcm2712_mip_raise first=0 vector=19 delivered=1' in trace,
       rp1_msix_event='rp1_msix vector=19' in trace,
       cs_framing_and_mosi_miso=framing['status']=='PASS',
       no_observed_idle_spi_irqs=idle_stable,
       real_dw_driver=any(n.get('spi',{}).get('controller_driver','').endswith('/dw_spi_mmio') for n in native),
       sys_clock_200mhz=any(any('200000000' in line and '1f00050000.spi' in line for line in n.get('sys_clock_summary',[])) for n in native))
    result=dict(status='PASS' if all(checks.values()) else 'PARTIAL',checks=checks,
        primary_target='PASS' if all(checks[k] for k in ('clean_original_verified_boot','endpoint_enumerated','kernel_chip_id','userspace_bars')) else 'INCONCLUSIVE',
        spi_stretch='PASS' if all(checks.values()) else 'NOT_FULLY_VALIDATED',
        original_run=str(a.run.resolve()),baseline_status=base['status'],framing=framing,
        submitted_observer_sha256=hashlib.sha256((a.run/'guest-observer.py').read_bytes()).hexdigest() if (a.run/'guest-observer.py').exists() else None,
        native_observations=observations, kernel='original captured 6.18.50',initramfs='original captured, unmodified',
        run_source_inventory_note='Early native-result source hashes are post-run file inventories, not captured execution snapshots. QEMU and private input identities are recorded at launch; use per-run command/process/inputs records.',
        limitations=['Logical link/clock/PIO model; no electrical link/timing claim','No native hotplug, peer DMA or full RP1 register coverage validation','SPI node deliberately enabled with synthetic slave; captured physical SPI0 node was disabled','No GPIO/pinmux or firmware execution, fixed logical wiring','No SPI DMA; real driver uses PIO','Full FEC campaign not rerun'])
    (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    (a.output/'summary.txt').write_text('\n'.join(f'{k}: {v}' for k,v in checks.items())+'\n')
    print(result['status'],checks)
    return 0 if result['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
