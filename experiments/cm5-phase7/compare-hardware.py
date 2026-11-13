#!/usr/bin/env python3
"""Compare allowlisted capabilities, never raw logs or user-supplied labels."""
import argparse
import json
from pathlib import Path
import re
import sys
sys.path.insert(0, str(Path(__file__).parent / 'physical-probes'))
from hardware_facts import KNOWN

# key, group, QEMU implementation source, experiment impact, implementation action
FEATURES = [
 ('cpu.models', 1, 'hw/arm/cm5io-dev.c', 'Instruction-set/ABI coverage', 'Check CPU model and implemented architectural features'),
 ('cpu.count', 1, 'hw/arm/cm5io-dev.c', 'SMP races and scheduling', 'Match intended CPU topology'),
 ('cpu.affinities', 1, 'hw/arm/cm5io-dev.c', 'CPU affinity and interrupt targeting topology', 'Match observed MPIDR affinity layout'),
 ('cpu.memory_ranges', 1, 'hw/arm/cm5io-dev.c', 'DMA/address-layout coverage', 'Add measured RAM holes/high-memory layout'),
 ('cpu.page_size', 1, 'experiments/cm5-phase6/regress.py', 'Userspace ELF/kernel compatibility', 'Use matching page-size kernel; not a silicon property'),
 ('cpu.kernel_version', 1, 'experiments/cm5-phase6/regress.py', 'Driver-contract differences', 'Retain versions and compare driver revisions, not names alone'),
 ('boot.psci_method', 2, 'hw/arm/cm5io-dev.c', 'Secondary CPU boot path', 'Compare PSCI call conduit and firmware dependency'),
 ('boot.firmware_services', 2, 'hw/arm/cm5io-dev.c', 'Firmware mailbox/clock calls absent under direct boot', 'Implement needed firmware interfaces from observed contracts'),
 ('boot.eeprom_boot_order', 2, 'hw/arm/cm5io-dev.c', 'Direct boot cannot predict EEPROM/BOOT corruption', 'Keep firmware-boot results separate; implement ROM/EEPROM path later'),
 ('storage.native_mmc_controllers', 3, 'hw/sd/bcm2712-sdhci.c', 'Native option versus VirtIO fallback', 'Compare BCM2712 DT and real driver evidence'),
 ('storage.mmc_host_drivers', 3, 'hw/sd/bcm2712-sdhci.c', 'Actual storage driver error behavior differs', 'Confirm unchanged sdhci-brcmstb binding'),
 ('storage.mmc_resources', 3, 'hw/arm/cm5io-dev.c', 'Physical address/IRQ contract', 'Compare translated host/cfg ranges'),
 ('storage.mmc_capabilities', 3, 'hw/sd/bcm2712-sdhci.c', 'PIO/legacy subset versus declared physical speeds', 'Keep DT declarations separate from negotiated mode and timing validation'),
 ('storage.logical_sector_sizes', 3, 'hw/sd/sd.c', 'Sector offset interpretation', 'Compare logical sector size without reading filesystem contents'),
 ('storage.partition_roles', 3, 'experiments/cm5-phase6/STORAGE.md', 'Corruption offsets and region identity', 'Match image geometry; do not relabel a VirtIO controller as eMMC'),
 ('interrupt.controllers', 4, 'hw/intc/bcm2712-mip.c', 'IRQ topology and delivery path', 'Replace remaining generic blocks only with documented behavior'),
 ('interrupt.gic_resources', 4, 'hw/arm/cm5io-dev.c', 'GIC virtualization/register coverage', 'Implement missing interfaces if used; do not merely add DT reg entries'),
 ('interrupt.mip0', 4, 'hw/intc/bcm2712-mip.c', 'RP1 MSI data/address and IRQ range', 'Confirm MIP0 reg/MSI range/offset against live DT'),
 ('interrupt.mip1', 4, 'hw/intc/bcm2712-mip.c', 'Expansion MSI range and offset', 'Resolve offset-to-GIC routing with allocated IRQ evidence'),
 ('interrupt.mip_bindings', 4, 'hw/intc/bcm2712-mip.c', 'DT presence does not establish driver use', 'Confirm actual mip_msi bindings and intended IRQ domain'),
 ('pci.host_drivers_described', 4, 'hw/arm/cm5io-dev.c', 'GPEX bypasses physical host programming', 'Implement brcm,bcm2712-pcie register/reset/window contract'),
 ('pci.rp1_bars', 4, 'hw/misc/rp1-pci.c', 'BAR sizes/decode and missing shared SRAM', 'Compare safe config/sysfs evidence; implement missing BAR2 as required'),
 ('pci.rp1_driver', 4, 'hw/misc/rp1-pci.c', 'PCI identity alone is insufficient', 'Retain real RP1 probe checks and MMIO evidence'),
 ('rp1.spi0', 5, 'hw/ssi/dw-apb-ssi.c', 'Controller route/IRQ/CS configuration', 'Compare active DT and read-only pinmux separately from transfer validation'),
 ('rp1.spi_nodes', 5, 'hw/ssi/dw-apb-ssi.c', 'Device exposure only, not electrical operation', 'Confirm intended mapping before any separately authorized transfer'),
 ('rp1.uart_nodes', 5, 'hw/arm/cm5io-dev.c', 'Debug/header UART routes differ', 'Implement RP1 UART rather than infer equivalence from tty count'),
 ('rp1.i2c_nodes', 5, 'hw/arm/cm5io-dev.c', 'I2C unavailable in current model', 'Implement required DW I2C and board pinmux route'),
 ('rp1.gpio_nodes', 5, 'hw/arm/cm5io-dev.c', 'GPIO/pinmux unavailable in current model', 'Implement RP1 GPIO/pads/mux with input-only initial validation'),
 ('rp1.gpio_controller', 5, 'hw/arm/cm5io-dev.c', 'DT GPIO declaration versus missing model', 'Add register model before claiming GPIO compatibility'),
 ('rp1.clock_controller', 5, 'hw/arm/cm5io-dev.c', 'Fixed clock hides clock-controller behavior', 'Implement clock/reset blocks used by real drivers'),
 ('fault.active_verity_targets', 6, 'experiments/cm5-phase6/STORAGE.md', 'OS/FSW policy depends on actual active mappings', 'Identify mapping roles manually without publishing private names'),
 ('fault.root_filesystem', 6, 'experiments/cm5-phase6/STORAGE.md', 'RAM OverlayFS versus physical root policy changes fault observations', 'Match explicitly recorded root policy; do not equate boot success with verity enforcement'),
 ('fault.recovery_partition_mounted', 6, 'experiments/cm5-phase6/STORAGE.md', 'Mount existence does not prove metadata validity or recovery execution', 'Review approved metadata separately; defer destructive recovery trials'),
]
GROUPS = {1: 'CPU/software execution', 2: 'Boot firmware', 3: 'eMMC/storage',
          4: 'Interrupt/PCIe', 5: 'RP1/IO Board', 6: 'Fault model/recovery'}
SAFE_STRINGS = KNOWN | {'smc', 'hvc', 'OTHER', 'NOT_IMPLEMENTED', 'rp1', 'rp1-pci',
 'GICv2', 'GICv3', 'GICv2m', 'BCM2712-MIP',
 'rp1_pci', 'mip_msi', 'sdhci-brcmstb', 'sdhci-iproc', 'sdhci', 'bcm2835-mmc',
 'mmc_spi', 'sdhci-pci', 'dw_mmc', 'BOOT', 'OS', 'FSW', 'LOGS', 'RECOVERY',
 'ext4', 'vfat', 'overlay', 'squashfs', 'xfs', 'btrfs'}

def safe(value):
    if value is None or isinstance(value, (int, bool)):
        return value
    if isinstance(value, str):
        if value in SAFE_STRINGS or re.fullmatch(r'arm,cortex-a\d+|\d+\.\d+(?:\.\d+)?', value):
            return value
        raise ValueError('non-allowlisted string')
    if isinstance(value, list):
        return [safe(v) for v in value]
    if isinstance(value, dict):
        allowed_keys = {'register_base', 'register_size', 'msi_address', 'msi_size',
            'range', 'offset', 'bar', 'size', 'memory', 'compatible', 'irq',
            'chip_selects', 'role', 'number', 'filesystem', 'readonly', 'active',
            'start_sector_512', 'base', 'bus_width', 'max_frequency',
            'non_removable', 'hs200', 'hs400'}
        if set(value) - allowed_keys:
            raise ValueError('non-allowlisted object')
        return {k: safe(v) for k, v in value.items()}
    raise ValueError('unsupported value')

def compare(physical, qemu):
    rows = []
    for key, group, source, impact, action in FEATURES:
        values, kinds = [], []
        for facts in (physical, qemu):
            entry = facts.get(key, {})
            try:
                val = safe(entry['value'])
                if val is None:
                    raise ValueError('missing observation')
                values.append(val)
            except (KeyError, ValueError):
                values.append('UNAVAILABLE')
            kind = entry.get('evidence_kind')
            kinds.append(kind if kind in ('DT_DESCRIPTION', 'RUNTIME_READ_ONLY',
                'QEMU_SOURCE', 'GUEST_VALIDATED') else 'UNAVAILABLE')
        status = 'UNAVAILABLE' if 'UNAVAILABLE' in values else 'MATCH' if values[0] == values[1] else 'MISMATCH'
        rows.append(dict(feature=key, group=GROUPS[group], physical_value=values[0],
            qemu_value=values[1], status=status,
            physical_evidence='facts.json#/facts/' + key,
            physical_evidence_kind=kinds[0], qemu_evidence_kind=kinds[1],
            qemu_source=source, experiment_impact=impact, recommended_action=action))
    return dict(schema=1, physical_measurements_available=bool(physical),
                note='MATCH compares an observed descriptor only; it does not certify hardware function, timing, or recovery.',
                capabilities=rows)

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--physical', type=Path, help='reviewed facts.json; never raw directory')
    p.add_argument('--qemu', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    physical = json.loads(a.physical.read_text())['facts'] if a.physical else {}
    qemu = json.loads(a.qemu.read_text())['facts']
    report = compare(physical, qemu)
    a.output.mkdir(parents=True, mode=0o700, exist_ok=False)
    (a.output / 'capabilities.json').write_text(json.dumps(report, indent=2) + '\n')
    lines = ['# Hardware capability comparison', '', report['note'], '',
             '| Feature | Physical | QEMU | Status |', '| --- | --- | --- | --- |']
    for row in report['capabilities']:
        def cell(v):
            return json.dumps(v, sort_keys=True).replace('|', '\\|')
        lines.append(f"| {row['feature']} | {cell(row['physical_value'])} | {cell(row['qemu_value'])} | {row['status']} |")
    (a.output / 'CAPABILITIES.md').write_text('\n'.join(lines) + '\n')
    print('Structured, allowlisted report written. Raw data was not read.')
