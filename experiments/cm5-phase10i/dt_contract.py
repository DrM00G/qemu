#!/usr/bin/env python3
"""Audit the opt-in generator transformation; never load arbitrary physical DT."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'experiments/cm5-phase10f2'))
import dt_pipeline as d

GPIO = '/pcie@1000120000/rp1/gpio@d0000'
PHYSICAL = Path('/home/aweso/cm5-phase10-private/physical-boot/boot-assets/bcm2712-rpi-cm5-cm5io.dtb')
PHYSICAL_SHA = 'b297f9516345eb4eb22d22f4c364fcb3705970f28b6d87875583dadf37fbb3ac'
META = {('/cm5io-connectors/header-gpio','status'),
        ('/cm5io-connectors/header-gpio','qemu,implementation'),
        ('/cm5io-connectors','qemu,pinmux')}
KEYS = {'compatible','reg','phandle','interrupt-parent','interrupts',
        'gpio-controller','#gpio-cells','interrupt-controller','#interrupt-cells',
        'gpio-ranges','gpio-reserved-ranges','gpio-line-names'}


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def sha(data): return hashlib.sha256(data).hexdigest()


def cells(*values): return struct.pack('>'+str(len(values))+'I',*values)


def inventory(data):
    tree=d.Tree(data);result={}
    def walk(path):
        result[path]=tree.props(path)
        for child in tree.children(path):walk(path.rstrip('/')+'/'+child)
    walk('/')
    return result


def validate(base, target, reference, enabled=True):
    before, after, physical = inventory(base), inventory(target), inventory(reference)
    require(sha(reference)==PHYSICAL_SHA, 'unaccepted selected physical DT reference')
    require(before['/']['compatible']==b'qemu,cm5io-dev\0', 'wrong generated base')
    require(GPIO not in before, 'fallback base already has GPIO')
    if not enabled:
        require(base==target, 'disabled transformation must be a no-op')
        return dict(effect='NO_CHANGE_GENERATED_FALLBACK',changed=False)
    require(set(after)-set(before)=={GPIO}, 'unsupported node addition')
    require(not set(before)-set(after), 'node deletion')
    changes=[]
    for path in before:
        for key in before[path].keys() | after[path].keys():
            if before[path].get(key)!=after[path].get(key):changes.append((path,key))
    require(set(changes)==META, 'non-allowlisted base property mutation')
    p=after[GPIO]; require(p.keys()==KEYS, 'GPIO property allowlist')
    phys=physical['/axi/pcie@1000120000/rp1/gpio@d0000']
    for key in ['compatible','reg','#gpio-cells','#interrupt-cells','gpio-controller','interrupt-controller']:
        require(p[key]==phys[key], 'binding mismatch '+key)
    require(p['reg']==cells(0xc0,0x400d0000,0,0xc000,0xc0,0x400e0000,0,0xc000,0xc0,0x400f0000,0,0xc000), 'DT contract postcondition')
    require(p['interrupts']==cells(0,4), 'bank0 level-high IRQ only')
    require(p['interrupt-parent']==after['/pcie@1000120000/rp1']['phandle'], 'DT contract postcondition')
    require(p['gpio-ranges']==p['phandle']+cells(0,0,54), 'DT contract postcondition')
    require(p['gpio-reserved-ranges']==cells(0,20,22,32), 'only GPIO20/21 usable')
    require(p['gpio-line-names'].split(b'\0')[20:22]==[b'GPIO20',b'GPIO21'], 'DT contract postcondition')
    require(len(p['phandle'])==4 and p['phandle']!=cells(0), 'DT contract postcondition')
    require(after['/cm5io-connectors/header-gpio']['status']==b'okay\0', 'DT contract postcondition')
    return dict(effect='ADDED_BOUNDED_GPIO_PROVIDER',changed=True,
        added_nodes=[GPIO],modified_properties=sorted(changes),
        physical_properties_preserved=['compatible','reg','#gpio-cells','#interrupt-cells'],
        differences=['only bank0 interrupt advertised','GPIO0..19/22..53 reserved',
                     'no physical hogs/alt functions imported','synthetic GPIO20->21 loopback'],
        external_physical_dt_installed=False)


def generate(work):
    work=Path(work);work.mkdir(parents=True,exist_ok=False)
    commands=[]
    for enabled,name in [(False,'base'),(True,'gpio')]:
        command=[str(ROOT/'build-arm64-phase1/qemu-system-aarch64'),'-M',
            'cm5io-dev,native-pcie=on,native-mip=on,native-emmc=on,emmc-dma=on'+
            (',rp1-gpio-lab=on' if enabled else '')+',dumpdtb='+str(work/(name+'.dtb')),
            '-m','2048','-smp','4','-accel','tcg,thread=single','-S','-display','none',
            '-monitor','none','-serial','none','-nodefaults']
        process=subprocess.run(command,capture_output=True,timeout=30)
        (work/(name+'.log')).write_bytes(process.stdout+process.stderr)
        require(process.returncode==0, 'DT generator failed')
        commands.append(command)
    base=(work/'base.dtb').read_bytes();target=(work/'gpio.dtb').read_bytes();reference=PHYSICAL.read_bytes()
    report=dict(schema=1,status='PASS',commands=commands,
        selected_reference_sha256=sha(reference),generated_base_sha256=sha(base),
        generated_target_sha256=sha(target),transformation=validate(base,target,reference),
        fallback=validate(base,base,reference,False),
        specification_sha256=sha(Path(__file__).read_bytes()),
        qemu_executable_sha256=sha((ROOT/'build-arm64-phase1/qemu-system-aarch64').read_bytes()),
        gpio_property_hashes={k:sha(v) for k,v in inventory(target)[GPIO].items()})
    (work/'contract.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


def runtime_check(contract, run):
    users=json.loads((Path(run)/'userspace.json').read_text());rows=[]
    for user in users:
        observed=user['boot_handoff_runtime'];p=observed['nodes'][GPIO]
        checks={k:p['properties'].get(k)==v for k,v in contract['gpio_property_hashes'].items()}
        rows.append(dict(runtime_fdt_sha256=observed['fdt_sha256'],checks=checks,
                         extra_live_properties=sorted(p['properties'].keys()-checks.keys())))
    require(len(rows)>=2 and all(all(r['checks'].values()) for r in rows), 'runtime GPIO contract failed')
    require(len({r['runtime_fdt_sha256'] for r in rows})==1, 'runtime FDT changed between observations')
    return dict(status='PASS',observations=rows,stage_note='generated base/target precede ARM boot fixups; actual runtime FDT identity observed independently')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--work',type=Path,required=True)
    a=p.parse_args();print(json.dumps(generate(a.work),indent=2))

if __name__=='__main__':main()
