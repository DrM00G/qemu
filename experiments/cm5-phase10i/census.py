#!/usr/bin/env python3
"""Three-way, sanitized hardware/driver census; never exports raw captured DT."""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import re
import struct
import dt_contract as d

CATEGORIES = ['physically-declared-modeled-exercised','compatible-lab-substitution',
              'intentionally-disabled','guest-advertised-unvalidated',
              'synthetic-fixture','physical-only-unsupported']
BINDINGS = ['reg','ranges','dma-ranges','interrupts','interrupt-parent',
            '#address-cells','#size-cells','#gpio-cells','#interrupt-cells',
            '#clock-cells','#reset-cells','clocks','resets','pinctrl-0','pinctrl-1',
            'gpio-ranges','gpio-reserved-ranges']


def strings(b):return b.rstrip(b'\0').decode(errors='replace').split('\0')


def u32(b):return list(struct.unpack('>'+str(len(b)//4)+'I',b)) if len(b)%4==0 else []


def canonical(path):
    path=path.removeprefix('/axi') if path.startswith('/axi/') else path
    return {'/soc@107c000000/mmc@fff000':'/mmc@1000fff000',
            '/soc@107c000000/serial@7d001000':'/serial@107d001000'}.get(path,path)


def semantic(tree):
    handles={u32(p['phandle'])[0]:name for name,p in tree.items() if 'phandle' in p}
    result={}
    for path,props in tree.items():
        if 'compatible' not in props:continue
        dependencies={}
        for key,count_key in [('clocks','#clock-cells'),('resets','#reset-cells')]:
            data=u32(props.get(key,b''));refs=[];i=0
            while i<len(data):
                provider=handles.get(data[i]);argc=u32(tree.get(provider,{}).get(count_key,b''))
                count=argc[0] if argc else 0
                refs.append(dict(provider=provider,phandle=data[i],args=data[i+1:i+1+count]))
                i+=1+count
            if refs:dependencies[key]=refs
        for key,value in props.items():
            if re.fullmatch(r'pinctrl-\d+',key):
                dependencies[key]=[dict(phandle=h,provider=handles.get(h)) for h in u32(value)]
        result[path]=dict(compatible=strings(props['compatible']),
            status=strings(props.get('status',b'okay\0'))[0],
            bindings={k:u32(props[k]) for k in BINDINGS if k in props},dependencies=dependencies)
    return result


# Only explicit feature matches; counts of unmatched nodes are not feature targets.
FEATURES = [
 ('rp1-gpio-cdev',d.GPIO,'/machine/native-rp1/rp1/gpio','pinctrl-rp1',
  'compatible-lab-substitution','GPIO20/21 direction, values, both edges and exclusive ownership; all other lines reserved',
  ['compiled driver has54 descriptors but only2 usable lines','bulk54-pin pinctrl debug reads and alternate-function selection are unsupported','no debounce or electrical model']),
 ('rp1-spi0','/pcie@1000120000/rp1/spi@50000','/machine/native-rp1/rp1/spi0','dw_spi_mmio',
  'compatible-lab-substitution','unchanged original-driver strict SPI workload',
  ['logical synthetic slave is independent of GPIO pinmux','SPI DMA absent','1MHz is not a reliable baseline']),
 ('rp1-sys-clock','/pcie@1000120000/rp1/clocks@18000','/machine/native-rp1/rp1','rp1-clk',
  'compatible-lab-substitution','Linux native SYS clock200MHz and SPI divider operation',
  ['limited modeled clock register paths','firmware reset presets are lab conventions']),
 ('rp1-other-clocks','/pcie@1000120000/rp1/clocks@18000','/machine/native-rp1/rp1','rp1-clk',
  'guest-advertised-unvalidated','NOT_TESTED',
  ['the real provider driver publishes clock IDs beyond the tested SYS/SLOW subset','do not infer functionality from registration']),
 ('rp1-pcie','/pcie@1000120000','/machine/native-rp1','brcm-pcie',
  'physically-declared-modeled-exercised','logical link, config, BARs, inbound/outbound and bus-master constraints',
  ['logical Gen2x4, no electrical PHY/ASPM timing calibration']),
 ('rp1-mfd','/pcie@1000120000/rp1','/machine/native-rp1/rp1','rp1',
  'physically-declared-modeled-exercised','PCI endpoint,61 MSI-X vectors; functional sources0 and19',
  ['61 vectors do not mean61 implemented peripherals','firmware mailbox/shared-memory protocol absent']),
 ('mip-host-edge','/msi-controller@1000130000','/machine/mip0','mip_msi',
  'physically-declared-modeled-exercised','native MSI-X delivery to parent GIC via supported host edge mode',
  ['level/VPU modes unimplemented','platform mip_msi binding and domain delivery are independently observed']),
 ('native-emmc','/mmc@1000fff000','/machine/emmc-host','sdhci-brcmstb',
  'compatible-lab-substitution','original verified OS/FSW roots2, normal shutdown and LOGS persistence',
  ['modeled SDHCI/clock subset, empty pinctrl lab states','no OTP/RPMB/boot-firmware emulation']),
 ('console-uart','/serial@107d001000',None,'uart-pl011',
  'compatible-lab-substitution','original kernel console and userspace boot',
  ['generic PL011 implementation at BCM2712 address','no physical pad/electrical timing']),
 ('header-uart-debug','/serial@1203000000',None,'uart-pl011',
  'compatible-lab-substitution','disposable guest debug console transport',
  ['generic PL011 at a lab address, not RP1 UART0 registers or GPIO14/15 mux']),
 ('rtc-substitute','/rtc@1203010000',None,'rtc-pl031',
  'compatible-lab-substitution','PROBE_ONLY',
  ['PL031 substitute, not physical PMIC RTC or battery model']),
 ('synthetic-spi-slave','/pcie@1000120000/rp1/spi@50000/test-slave@0',None,'spidev',
  'synthetic-fixture','known MOSI XOR0xa5 response with strict CS oracle',
  ['physical fixture and wiring are unconfirmed']),
 ('synthetic-gpio-loopback',d.GPIO,'/machine/native-rp1/rp1/gpio','pinctrl-rp1',
  'synthetic-fixture','GPIO20->21 logical input stimulus and native edge interrupts',
  ['not physically measured wiring','no analog contention, propagation or synchronizer latency']),
 ('header-i2c-policy','/cm5io-connectors/header-i2c1',None,None,
  'intentionally-disabled','NOT_IMPLEMENTED',
  ['metadata explicitly disabled; no Linux I2C controller is created']),
 ('physical-rp1-i2c1','/pcie@1000120000/rp1/i2c@74000',None,None,
  'physical-only-unsupported','NOT_IMPLEMENTED',['needs DesignWare I2C, clocks and full pinmux']),
 ('physical-rp1-ethernet','/pcie@1000120000/rp1/ethernet@100000',None,None,
  'physical-only-unsupported','NOT_IMPLEMENTED',['MAC/PHY, DMA, clocks and reset GPIO dependencies absent']),
 ('physical-rp1-gpiomem','/pcie@1000120000/rp1/gpiomem@d0000',None,None,
  'physical-only-unsupported','NOT_IMPLEMENTED',['bounded cdev is implemented; broad raw /dev/gpiomem ABI is not exposed']),
 ('physical-rp1-mailbox','/pcie@1000120000/rp1/mailbox@8000',None,None,
  'physical-only-unsupported','NOT_IMPLEMENTED',['no RP1 firmware mailbox/shared-memory protocol']),
 ('physical-usb2','/usb@480000',None,None,
  'physical-only-unsupported','NOT_IMPLEMENTED',['captured live DT versus BOOT base overlay state differs','no wholesale USB node import']),
]


def make(contract_dir, run=None):
    contract_dir=Path(contract_dir);physical=d.inventory(d.PHYSICAL.read_bytes())
    livepath=Path('/home/aweso/cm5-phase10-private/reference/live-v8.dtb')
    live=d.inventory(livepath.read_bytes());base=d.inventory((contract_dir/'base.dtb').read_bytes())
    virtual=d.inventory((contract_dir/'gpio.dtb').read_bytes());sem=semantic(physical)
    canonical_phys={canonical(p):p for p in physical}
    canonical_live={canonical(p):p for p in live}
    users=[];qom={};native={};original={};qtree=''
    if run:
        run=Path(run);users=json.loads((run/'userspace.json').read_text())
        qom=json.loads((run/'phase10i-qom.json').read_text());qtree=qom.get('qtree',{}).get('return','')
        native=json.loads((run.parent/'native-report/result.json').read_text())
        original=json.loads((run/'result.json').read_text())
    drivers=[v for u in users for v in u.get('phase10i_linux',{}).get('drivers',[])]
    gpio_results=[u.get('phase10i_gpio',{}) for u in users]
    caps=[]
    for ident,path,qpath,expected_driver,category,test,limits in FEATURES:
        phys_path=canonical_phys.get(path);live_path=canonical_live.get(path)
        phys=sem.get(phys_path);p=virtual.get(path)
        match=[x for x in drivers if x.get('dt_path')==path and x.get('driver')]
        if ident=='rp1-mfd':match=[x for x in drivers if x['bus']=='pci' and x['name']=='0002:01:00.0' and x.get('driver')]
        if ident=='synthetic-spi-slave':match=[x for x in drivers if x['bus']=='spi' and x.get('driver')=='spidev']
        realized=qom.get(str(qpath)+'/realized',{}).get('return') if qpath else None
        if qpath in ['/machine/mip0','/machine/emmc-host']:
            model='bcm2712-mip' if qpath.endswith('mip0') else 'bcm2712-sdhci'
            realized=('dev: '+model) in qtree if users else None
        if users and ident in ['console-uart','header-uart-debug','rtc-substitute']:
            address={'console-uart':'000000107d001000','header-uart-debug':'0000001203000000',
                     'rtc-substitute':'0000001203010000'}[ident]
            realized=bool(re.search(r'dev: '+('pl031' if ident=='rtc-substitute' else 'pl011')+r',(?:(?!\n  dev:).)*mmio '+address,qtree,re.S))
        status='NOT_RUN'
        if test=='NOT_IMPLEMENTED':status='NOT_IMPLEMENTED'
        elif test=='NOT_TESTED':status='NOT_TESTED'
        elif users:
            if ident in ['rp1-gpio-cdev','synthetic-gpio-loopback']:
                status='PASS' if len(gpio_results)>=2 and all(g.get('status')=='PASS' and g.get('driver')=='pinctrl-rp1' for g in gpio_results) else 'FAIL'
            elif ident in ['rp1-spi0','synthetic-spi-slave']:
                status='PASS' if native.get('checks',{}).get('cs_framing_and_mosi_miso') else 'FAIL'
            elif ident=='mip-host-edge':status='PASS' if native.get('checks',{}).get('native_mip_event') else 'FAIL'
            elif ident=='rp1-sys-clock':status='PASS' if native.get('checks',{}).get('sys_clock_200mhz') else 'FAIL'
            elif ident in ['rp1-pcie','rp1-mfd']:status='PASS' if native.get('checks',{}).get('userspace_bars') else 'FAIL'
            elif ident in ['native-emmc','console-uart','header-uart-debug']:status='PASS' if original.get('status')=='PASS' else 'FAIL'
            else:status='PROBE_ONLY' if match else 'NOT_RUN'
        cap=dict(id=ident,classification=category,
            physical_reference=dict(selected_path=phys_path,declared=bool(phys_path),
                selected_status=phys['status'] if phys else None,captured_live_path=live_path,
                captured_live_status=strings(live[live_path].get('status',b'okay'))[0] if live_path else None,
                evidence='captured DT declaration; not a new physical functional measurement'),
            qemu_realized=realized,qom_path=qpath,runtime_dt_node_present=p is not None,
            runtime_dt_advertised=bool(p is not None and 'compatible' in p and strings(p.get('status',b'okay'))[0] in ['okay','ok']),
            runtime_dt_path=path if p is not None else None,linux_expected_driver=expected_driver,
            linux_driver_bound=(bool(match) if ident not in ['console-uart','header-uart-debug','rtc-substitute'] else None) if users else None,
            linux_driver_evidence=match[:1],
            linux_driver_evidence_scope='platform/pci/spi/i2c symlinks; AMBA bus not enumerated in these runs',
            functional_test=dict(status=status,operation=test,evidence=str(run) if run else None),
            synthetic_fixture=ident if category=='synthetic-fixture' else None,
            known_limitations=limits,required_for_fsw='UNKNOWN',
            physical_measurement_needed=['supervisor-confirmed interface/API and approved matching fixture','approved physical driver/bus baseline','clock and waveform measurements only when relevant and approved'])
        if ident=='mip-host-edge':cap['linux_irq_domain_inferred_active']=status=='PASS'
        caps.append(cap)
    physical_rows=[]
    feature_by_path=collections.defaultdict(list)
    for c in caps:
        if c['physical_reference']['selected_path']:feature_by_path[c['physical_reference']['selected_path']].append(c['id'])
    for path,props in sem.items():
        vpath=canonical(path);related=feature_by_path[path]
        classification=next((c['classification'] for c in caps if c['id'] in related),'physical-only-unsupported')
        if not related and vpath in virtual:classification='guest-advertised-unvalidated'
        physical_rows.append(dict(path=path,classification=classification,virtual_match=vpath if vpath in virtual else None,
                                  related_capabilities=related,**props))
    unresolved=[]
    for path,props in virtual.items():
        if 'compatible' in props and canonical(path) not in canonical_phys:
            related=[c['id'] for c in caps if c['runtime_dt_path']==path]
            unresolved.append(dict(path=path,compatible=strings(props['compatible']),related_capabilities=related,
                classification=next((c['classification'] for c in caps if c['id'] in related),'guest-advertised-unvalidated')))
    raw_counts=lambda a,b:dict(physical_only=len(a.keys()-b.keys()),runtime_only=len(b.keys()-a.keys()),common=len(a.keys()&b.keys()),common_changed=sum(a[k]!=b[k] for k in a.keys()&b.keys()))
    symbols=physical.get('/__symbols__',{})
    return dict(schema=1,environment='qemu',physical_measurements_collected=False,
        pinned_linux_reference=dict(revision='cff533aec2fa601846766b32ff57204e0a61bed7',
                                    source_hash_inventory='reference-sources.json'),
        identities=dict(selected_reference_sha256=d.sha(d.PHYSICAL.read_bytes()),captured_live_sha256=d.sha(livepath.read_bytes()),
                        generated_base_sha256=d.sha((contract_dir/'base.dtb').read_bytes()),generated_target_sha256=d.sha((contract_dir/'gpio.dtb').read_bytes()),
                        runtime_fdt_sha256=sorted({u['boot_handoff_runtime']['fdt_sha256'] for u in users})),
        comparison_scope='node counts are raw path comparisons; explicit /axi flattening and console/eMMC matches used only for feature correspondence',
        raw_counts=dict(base=raw_counts(physical,base),gpio_profile=raw_counts(physical,virtual)),
        symbols=dict(count=len(symbols),sha256=d.sha(json.dumps({k:v.hex() for k,v in symbols.items()},sort_keys=True).encode()),
                     relevant={k:strings(v)[0] for k,v in symbols.items() if k in ['rp1','rp1_gpio','rp1_clocks','rp1_spi0','pcie2','mip0','sdhci0']}),
        capabilities=caps,physical_declared_nodes=physical_rows,virtual_without_exact_physical_path=unresolved,
        ranked_gaps=[dict(rank=1,id='rp1-other-clocks',reason='existing real driver exposes provider outputs beyond tested register subset; audit actual unsupported accesses'),
                     dict(rank=2,id='physical-rp1-gpiomem',reason='confirm cdev versus direct-MMIO/pinmux needs before expanding bounded GPIO'),
                     dict(rank=3,id='physical-rp1-i2c1',reason='possible sensor interface, dependencies unmodeled; FSW requirement UNKNOWN'),
                     dict(rank=4,id='physical-rp1-ethernet',reason='physical board declares MAC/PHY; substantial DMA/reset/provider dependencies'),
                     dict(rank=5,id='physical-usb2',reason='physical runtime overlay differs; do not advertise unsupported controller')],
        linux_observations=len(users),linux_buses=users[-1].get('phase10i_linux',{}).get('buses') if users else None,
        qom_evidence='private phase10i-qom.json: explicit realized queries plus HMP qtree/mtree; null means not established, not absent',
        required_for_fsw='UNKNOWN for every capability; no proprietary FSW was obtained or explicitly launched; captured boot services unchanged')


def render(report):
    lines=['# Hardware capability matrix','',
        'Static captured declarations, QOM realization, Linux binding and functional testing are separate evidence. No new physical measurements. FSW requirements remain UNKNOWN.','',
        '| Capability | Classification | QOM realized | Linux bound | Functional evidence |',
        '| --- | --- | --- | --- | --- |']
    for c in report['capabilities']:
        lines.append('| '+ ' | '.join([c['id'],c['classification'],str(c['qemu_realized']),str(c['linux_driver_bound']),c['functional_test']['status']])+' |')
    lines += ['', 'The manifest contains per-node register/dependency declarations, source identities and ranked gaps. GPIO has54 compiled driver descriptors but52 lines are reserved; only20/21 are usable. Its complete pinctrl/filtered/raw-gpiomem ABI is not implemented. SPI remains logically wired independently of GPIO. Provider registration alone is not a functional test.', '',
        'Raw captured/live DT and QOM/Linux logs remain private. The selected BOOT DT is not installed; the opt-in generator profile is an explicit bounded compatible substitution. Physical-only node counts are not an implementation target.']
    return '\n'.join(lines)+'\n'


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--contract-dir',type=Path,required=True);p.add_argument('--run',type=Path)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--markdown',type=Path,required=True);a=p.parse_args()
    report=make(a.contract_dir,a.run);a.output.write_text(json.dumps(report,indent=2)+'\n');a.markdown.write_text(render(report))
    print('capabilities',len(report['capabilities']),'physical compatible nodes',len(report['physical_declared_nodes']))

if __name__=='__main__':main()
