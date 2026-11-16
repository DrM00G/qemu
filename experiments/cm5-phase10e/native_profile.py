"""Opt-in native endpoint/SPI guest observations; no production input changes."""
import hashlib
import json
from pathlib import Path
import re
from trace_check import check

HERE=Path(__file__).resolve().parent


def qemu_arguments(diagnostics=False):
    args = ['-device','ssi-test-slave,bus=spi,cs=0',
            '-trace','enable=rp1_msix', '-trace','enable=bcm2712_mip_raise',
            '-trace','enable=dw_apb_ssi_cs', '-trace','enable=dw_apb_ssi_transfer']
    if diagnostics:
        args += ['-trace', 'enable=dw_apb_ssi_state',
                 '-trace', 'enable=dw_apb_ssi_boundary',
                 '-trace', 'enable=dw_apb_ssi_timer',
                 '-trace', 'enable=rp1_spi_notify',
                 '-trace', 'enable=rp1_spi_state',
                 '-trace', 'enable=bcm2712_mip_timed']
    return args


def observer(code, speed=10000):
    spi = (HERE/'spi_guest.py').read_text().replace('SPI_HZ = 10000',
                                                  'SPI_HZ = '+str(speed))
    extra="SPI_CODE = r'''\n"+spi+"\n'''\n"+(HERE/'native_observe.py').read_text()
    return code.replace("print('P10C_USER_JSON='", extra+"\nprint('P10C_USER_JSON='")


def finish(out):
    baseline=json.loads((out/'recovery-result.json').read_text())
    serial=(out/'serial.log').read_text(errors='replace')
    users=json.loads((out/'userspace.json').read_text()) if (out/'userspace.json').exists() else []
    native=[r['native_rp1'] for r in users if 'native_rp1' in r]
    actual=[r for r in native if r.get('chip_id')==0x20001927 and r.get('bar2_scratch')]
    spi=[r['spi'] for r in actual if r.get('spi',{}).get('status')=='PASS' and r.get('target_after_spi')=='active']
    messages=[m for r in native for m in r.get('spi',{}).get('messages',[])]
    framing=check((out/'hardware.log').read_text().splitlines(),messages)
    checks=dict(clean_original_boot=baseline['status']=='PASS_CLEAN',
        native_endpoint_enumerated='pci 0002:01:00.0: [1de4:0001]' in serial,
        native_chip_id='rp1 0002:01:00.0: chip_id 0x20001927' in serial,
        userspace_bar_access=bool(actual), spi_messages_and_irq=len(spi)>=2,
        cs_framing=framing['status']=='PASS')
    r=dict(status='PASS' if all(checks.values()) else 'PARTIAL',checks=checks,
           baseline=str(out/'recovery-result.json'),observations=native,framing=framing,
           source_inventory_stage='post-run files; see guest-observer.py for actual submitted code',
           source_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in HERE.glob('*.py')})
    (out/'native-result.json').write_text(json.dumps(r,indent=2)+'\n')
    print('PHASE10E_NATIVE='+r['status'],flush=True)
