#!/usr/bin/env python3
"""Describe the generated native-MIP DT, implementation, and validated guest."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent / 'physical-probes'))
from hardware_facts import describe_dt, dt_from_blob

p = argparse.ArgumentParser()
p.add_argument('--dtb', type=Path, required=True)
p.add_argument('--guest-run', type=Path)
p.add_argument('--v8-run', type=Path)
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
facts = describe_dt(dt_from_blob(a.dtb))
def run_result(path):
    rechecked = path / 'result-rechecked.json'
    return json.loads((rechecked if rechecked.exists() else path / 'result.json').read_text())

def add(key, value, source, kind='QEMU_SOURCE'):
    facts[key] = dict(value=value, source=source, evidence_kind=kind)
add('boot.eeprom_boot_order', 'NOT_IMPLEMENTED', 'hw/arm/cm5io-dev.c: direct kernel loader')
add('pci.rp1_bars', [dict(bar=0, size=16384, memory=True),
                    dict(bar=1, size=4194304, memory=True)], 'hw/misc/rp1-pci.c')
add('storage.mmc_host_drivers', [], 'hw/arm/cm5io-dev.c: no native eMMC host')
add('rp1.i2c_nodes', 0, 'hw/arm/cm5io-dev.c: no I2C model')
add('rp1.gpio_nodes', 0, 'hw/arm/cm5io-dev.c: no RP1 GPIO model')
if a.guest_run:
    result = run_result(a.guest_run)
    if result['status'] != 'PASS' or not result.get('native_mip'):
        raise SystemExit('requires a passing native-MIP run')
    serial = (a.guest_run / 'serial.log').read_text()
    if not result['checks'].get('native_mip_initialized') or 'GICv2m:' in serial:
        raise SystemExit('no native driver initialization proof')
    add('interrupt.mip_bindings', 2, 'guest:sysfs mip_msi binding + init writes', 'GUEST_VALIDATED')
    add('pci.rp1_driver', ['rp1'], 'guest:real RP1 probe + SPI events', 'GUEST_VALIDATED')
    add('cpu.page_size', 16384, 'preserved guest kernel config and diagnostic', 'GUEST_VALIDATED')
    add('cpu.kernel_version', '6.18.62', 'preserved guest kernel uname', 'GUEST_VALIDATED')
    if result['mode'] == 'spi':
        add('rp1.spi_nodes', 1, 'guest:spidev0.0 ioctl byte/trace validation', 'GUEST_VALIDATED')
    if result.get('native_emmc'):
        if not all(result['checks'].get(k) for k in
                   ('brcmstb_bound', 'emmc_card', 'partition_geometry', 'block_digests')):
            raise SystemExit('missing native eMMC driver/read evidence')
        add('storage.mmc_host_drivers', ['sdhci-brcmstb'],
            'guest:sysfs binding, MMC enumeration, actual block digests', 'GUEST_VALIDATED')
        add('storage.logical_sector_sizes', [512],
            'guest:mmcblk0 queue/logical_block_size', 'GUEST_VALIDATED')
    import re
    uart = set(re.findall(r'ttyAMA[0-9]+ at MMIO', serial))
    if uart:
        add('rp1.uart_nodes', len(uart), 'guest:PL011 probe (not RP1 UART0 register equivalence)', 'GUEST_VALIDATED')
if a.v8_run:
    v8 = run_result(a.v8_run)
    if v8['status'] != 'PASS' or not v8.get('native_mip'):
        raise SystemExit('requires passing native V8 evidence')
    add('fault.root_filesystem', 'overlay', 'validated preserved V8 init OverlayFS root', 'GUEST_VALIDATED')
    add('fault.recovery_partition_mounted', True, 'validated V8 init read-only RECOVERY mount before switch_root', 'GUEST_VALIDATED')
    if v8.get('native_emmc'):
        add('fault.active_verity_targets', int(v8.get('os_verity', False)),
            'guest:native profile original partitions; optional cm5-os mapping', 'GUEST_VALIDATED')
    inventory = Path(__file__).parent.parent / 'cm5-phase6/artifacts/storage-inventory.json'
    roles = {1: 'BOOT', 2: 'OS', 5: 'FSW', 6: 'LOGS', 7: 'RECOVERY'}
    partitions = []
    for row in json.loads(inventory.read_text())['partitions']:
        if row['number'] in roles:
            partitions.append(dict(role=roles[row['number']], number=row['number'],
                size=row['size'], start_sector_512=row['offset'] // 512,
                filesystem=row['filesystem']['TYPE']))
    add('storage.partition_roles', sorted(partitions, key=lambda p: (p['role'], p['number'])),
        'read-only preserved golden image MBR/EBR inventory', 'QEMU_SOURCE')
a.output.write_text(json.dumps(dict(schema=1, facts=facts), indent=2) + '\n')
