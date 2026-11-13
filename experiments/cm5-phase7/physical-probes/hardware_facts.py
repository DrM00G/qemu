#!/usr/bin/env python3
"""Allowlisted hardware facts. Never copy DT serial/MAC/chosen or log strings."""
import re
import os
import struct
from pathlib import Path

KNOWN = {
 'brcm,bcm2712-mip', 'arm,gic-400', 'arm,cortex-a15-gic', 'arm,gic-v3',
 'arm,gic-v2m-frame', 'brcm,bcm2712-pcie', 'pci-host-ecam-generic',
 'snps,dw-apb-ssi', 'brcm,bcm2712-sdhci', 'brcm,sdhci-brcmstb',
 'raspberrypi,rp1-gpio', 'raspberrypi,rp1-clocks', 'raspberrypi,rp1-reset',
 'arm,pl011', 'arm,pl011-axi', 'arm,pl031', 'qemu,cm5io-dev',
 'raspberrypi,5-compute-module', 'brcm,bcm2712', 'linux,dummy-virt',
 'raspberrypi,bcm2835-firmware', 'raspberrypi,firmware', 'raspberrypi,rpi-rtc',
}

def strings(value):
    return value.rstrip(b'\0').decode('ascii', errors='replace').split('\0')

def cells(value):
    return list(struct.unpack('>' + 'I' * (len(value) // 4), value)) if len(value) % 4 == 0 else []

def number(values):
    n = 0
    for v in values:
        n = (n << 32) | v
    return n

def dt_from_dir(root):
    root = Path(root)
    nodes = {}
    if not root.is_dir():
        return nodes
    for entry in root.rglob('*'):
        if entry.is_file() and not entry.is_symlink():
            node = '/' + entry.parent.relative_to(root).as_posix().strip('.')
            nodes.setdefault(node, {})[entry.name] = entry.read_bytes()
    return nodes

def dt_from_blob(path):
    data = Path(path).read_bytes()
    if len(data) < 40 or struct.unpack_from('>I', data)[0] != 0xd00dfeed:
        raise ValueError('not a flattened Device Tree')
    total, off_struct, off_strings = struct.unpack_from('>III', data, 4)
    if total > len(data):
        raise ValueError('truncated DT')
    pos, stack, nodes = off_struct, [], {}
    while pos + 4 <= total:
        token = struct.unpack_from('>I', data, pos)[0]
        pos += 4
        if token == 1:
            end = data.index(0, pos, total)
            stack.append(data[pos:end].decode('ascii', errors='replace'))
            pos = (end + 4) & ~3
            nodes.setdefault('/' + '/'.join(stack[1:]), {})
        elif token == 2:
            stack.pop()
        elif token == 3:
            length, nameoff = struct.unpack_from('>II', data, pos)
            pos += 8
            if pos + length > total:
                raise ValueError('truncated property')
            start = off_strings + nameoff
            end = data.index(0, start, total)
            name = data[start:end].decode('ascii', errors='replace')
            nodes['/' + '/'.join(stack[1:])][name] = data[pos:pos + length]
            pos = (pos + length + 3) & ~3
        elif token == 9:
            return nodes
        elif token != 4:
            raise ValueError('invalid FDT token')
    raise ValueError('missing FDT end')

def compatibles(props):
    values = strings(props.get('compatible', b''))
    return sorted(v for v in values if v in KNOWN or re.fullmatch(r'arm,cortex-a[0-9]+', v))

def cpu_resources(nodes, path):
    """Normalize simple-bus cells/ranges to CPU addresses; never guess PCI BARs."""
    def parent(p):
        return p.rsplit('/', 1)[0] or '/'
    def width(p, prop, default):
        return number(cells(nodes.get(p, {}).get(prop, struct.pack('>I', default))))
    bus = parent(path)
    ac, sc = width(bus, '#address-cells', 2), width(bus, '#size-cells', 1)
    reg = cells(nodes[path].get('reg', b''))
    if ac not in (1, 2) or sc not in (1, 2) or len(reg) % (ac + sc):
        return None
    resources = []
    for i in range(0, len(reg), ac + sc):
        addr, size = number(reg[i:i + ac]), number(reg[i + ac:i + ac + sc])
        current = bus
        while current != '/':
            up = parent(current)
            props = nodes.get(current, {})
            if 'ranges' not in props:
                return None
            ranges = cells(props['ranges'])
            ca, pa = width(current, '#address-cells', 2), width(up, '#address-cells', 2)
            ss = width(current, '#size-cells', 1)
            stride = ca + pa + ss
            if ca not in (1, 2) or pa not in (1, 2) or ss not in (1, 2):
                return None
            if ranges:
                if len(ranges) % stride:
                    return None
                mapped = False
                for j in range(0, len(ranges), stride):
                    child = number(ranges[j:j + ca])
                    host = number(ranges[j + ca:j + ca + pa])
                    length = number(ranges[j + ca + pa:j + stride])
                    if child <= addr and addr + size <= child + length:
                        addr = host + addr - child
                        mapped = True
                        break
                if not mapped:
                    return None
            current = up
        resources.append(dict(base=addr, size=size))
    return resources

def describe_dt(nodes):
    facts = {}
    def put(key, value, source, kind='DT_DESCRIPTION'):
        facts[key] = dict(value=value, source=source, evidence_kind=kind)
    if not nodes:
        return facts
    put('rp1.board_compatible', compatibles(nodes.get('/', {})), 'live-dt:/compatible')
    cpu = [p for p in nodes.values() if p.get('device_type') == b'cpu\0']
    put('cpu.models', sorted({v for p in cpu for v in compatibles(p)}), 'live-dt:CPU compatible')
    put('cpu.count', len(cpu), 'live-dt:CPU nodes')
    if cpu and all('reg' in p for p in cpu):
        put('cpu.affinities', sorted(number(cells(p['reg'])) for p in cpu),
            'live-dt:CPU reg/MPIDR affinity values')
    root = nodes.get('/', {})
    ac = number(cells(root.get('#address-cells', b'\0\0\0\2')))
    sc = number(cells(root.get('#size-cells', b'\0\0\0\2')))
    memory = []
    for path, props in nodes.items():
        if props.get('device_type') == b'memory\0':
            reg = cells(props.get('reg', b''))
            for i in range(0, len(reg), ac + sc):
                if len(reg[i:i + ac + sc]) == ac + sc:
                    memory.append([number(reg[i:i + ac]), number(reg[i + ac:i + ac + sc])])
    put('cpu.memory_ranges', sorted(memory), 'live-dt:memory reg')
    method = next((strings(p['method'])[0] for p in nodes.values()
        if 'method' in p and any(v.startswith('arm,psci') for v in strings(p.get('compatible', b'')))), None)
    if method in ('smc', 'hvc'):
        put('boot.psci_method', method, 'live-dt:PSCI method')
    all_compat = {v for p in nodes.values() for v in compatibles(p)}
    put('boot.firmware_services', sorted(v for v in all_compat if 'firmware' in v), 'live-dt:firmware compatible')
    put('storage.native_mmc_controllers', sorted(v for v in all_compat if 'sdhci' in v), 'live-dt:MMC controller compatible')
    mmc_resources = []
    mmc_capabilities = []
    for path, props in nodes.items():
        if 'brcm,bcm2712-sdhci' in compatibles(props):
            resources = cpu_resources(nodes, path)
            if resources is not None:
                mmc_resources.extend(resources)
            mmc_capabilities.append(dict(
                bus_width=number(cells(props.get('bus-width', b'\0\0\0\1'))),
                max_frequency=number(cells(props.get('max-frequency', b'\0\0\0\0'))),
                non_removable='non-removable' in props,
                hs200='mmc-hs200-1_8v' in props,
                hs400='mmc-hs400-1_8v' in props))
    put('storage.mmc_resources', mmc_resources, 'live-dt:translated BCM2712 host/cfg reg')
    put('storage.mmc_capabilities', mmc_capabilities, 'live-dt:declared capabilities, not negotiated mode')
    kinds = {'arm,gic-400': 'GICv2', 'arm,cortex-a15-gic': 'GICv2',
             'arm,gic-v3': 'GICv3', 'arm,gic-v2m-frame': 'GICv2m',
             'brcm,bcm2712-mip': 'BCM2712-MIP'}
    put('interrupt.controllers', sorted({kinds[v] for v in all_compat if v in kinds}),
        'live-dt:normalized interrupt architecture, compatible aliases folded')
    put('pci.host_drivers_described', sorted(v for v in all_compat if v in ('brcm,bcm2712-pcie', 'pci-host-ecam-generic')), 'live-dt:PCI host compatible')
    put('rp1.gpio_controller', 'raspberrypi,rp1-gpio' in all_compat, 'live-dt:RP1 GPIO compatible')
    put('rp1.clock_controller', 'raspberrypi,rp1-clocks' in all_compat, 'live-dt:RP1 clock compatible')
    for path, props in nodes.items():
        compat = compatibles(props)
        if 'brcm,bcm2712-mip' in compat:
            reg = cells(props.get('reg', b''))
            if len(reg) == 8:
                base = number(reg[:2])
                which = 'mip0' if base == 0x1000130000 else 'mip1' if base == 0x1000131000 else None
                if which:
                    raw = cells(props.get('msi-ranges', b''))
                    offset = cells(props.get('brcm,msi-offset', b'\0\0\0\0'))
                    put('interrupt.' + which, dict(register_base=base,
                        register_size=number(reg[2:4]), msi_address=number(reg[4:6]),
                        msi_size=number(reg[6:]), range=raw[1:], offset=offset[0]),
                        'live-dt:MIP reg, msi-ranges, brcm,msi-offset')
        if any(v in compat for v in ('arm,gic-400', 'arm,cortex-a15-gic', 'arm,gic-v3')):
            resources = cpu_resources(nodes, path)
            if resources is not None:
                put('interrupt.gic_resources', resources,
                    'live-dt:GIC reg translated through simple-bus ranges')
        if 'snps,dw-apb-ssi' in compat:
            reg = cells(props.get('reg', b''))
            if len(reg) >= 4 and number(reg[:2]) & 0x3fffff == 0x50000:
                put('rp1.spi0', dict(compatible=compat, offset=0x50000,
                    irq=cells(props.get('interrupts', b'')),
                    chip_selects=number(cells(props.get('num-cs', b'')))),
                    'live-dt:RP1 SPI0 reg/interrupts/num-cs')
    return facts

def runtime_facts(root, dm_text=None):
    root = Path(root)
    facts = {}
    def put(key, value, source):
        facts[key] = dict(value=value, source=source, evidence_kind='RUNTIME_READ_ONLY')
    pci = root / 'sys/bus/pci/devices'
    bars, drivers = [], []
    for p in pci.glob('*'):
        try:
            if int((p / 'vendor').read_text(), 0) != 0x1de4 or int((p / 'device').read_text(), 0) != 1:
                continue
            for i, line in enumerate((p / 'resource').read_text().splitlines()[:6]):
                start, end, flags = [int(x, 16) for x in line.split()]
                if flags:
                    bars.append(dict(bar=i, size=end - start + 1, memory=bool(flags & 0x200)))
            if (p / 'driver').is_symlink():
                name = (p / 'driver').resolve().name
                drivers.append('rp1' if name in ('rp1', 'rp1-pci', 'rp1_pci') else 'OTHER')
        except (OSError, ValueError):
            continue
    if bars:
        put('pci.rp1_bars', bars, '/sys/bus/pci/devices/<1de4:0001>/resource')
        put('pci.rp1_driver', sorted(drivers), '/sys/bus/pci/devices/<1de4:0001>/driver')
    mip = []
    for p in (root / 'sys/bus/platform/devices').glob('*'):
        driver = p / 'driver'
        if driver.is_symlink() and driver.resolve().name == 'mip_msi':
            mip.append('mip_msi')
    if (root / 'sys/bus/platform/devices').is_dir():
        put('interrupt.mip_bindings', len(mip), '/sys/bus/platform/devices/*/driver')
    for key, pattern in (('spi', 'spidev*'), ('uart', 'ttyAMA*'), ('i2c', 'i2c-*'), ('gpio', 'gpiochip*')):
        devdir = root / 'dev'
        if devdir.is_dir() and os.access(devdir, os.R_OK | os.X_OK):
            count = len(list(devdir.glob(pattern)))
            put('rp1.' + key + '_nodes', count, '/dev/' + pattern + ' (exposure, not transfer validation)')
    mmc_drivers = []
    for p in (root / 'sys/class/mmc_host').glob('*'):
        driver = p / 'device/driver'
        if driver.is_symlink():
            name = driver.resolve().name
            mmc_drivers.append(name if name in ('sdhci-brcmstb', 'sdhci-iproc',
                'sdhci', 'bcm2835-mmc', 'mmc_spi', 'sdhci-pci', 'dw_mmc') else 'OTHER')
    if (root / 'sys/class/mmc_host').is_dir():
        put('storage.mmc_host_drivers', sorted(mmc_drivers), '/sys/class/mmc_host/*/device/driver')
    logical_sizes = []
    for p in (root / 'sys/class/block').glob('mmcblk*'):
        if re.fullmatch(r'mmcblk[0-9]+', p.name):
            try:
                logical_sizes.append(int((p / 'queue/logical_block_size').read_text()))
            except (OSError, ValueError):
                pass
    if logical_sizes:
        put('storage.logical_sector_sizes', sorted(logical_sizes),
            '/sys/class/block/mmcblk*/queue/logical_block_size')
    if dm_text is not None:
        count = sum(bool(re.search(r'\bverity\b', line)) for line in dm_text.splitlines())
        put('fault.active_verity_targets', count, 'dmsetup status (does not identify OS/FSW policy)')
    return facts

def partition_facts(text):
    import json
    roles = {'bootfs': 'BOOT', 'rootfs': 'OS', 'FSW': 'FSW',
             'LOGS': 'LOGS', 'RECOVERY': 'RECOVERY'}
    result = []
    def visit(nodes):
        for node in nodes:
            label = node.get('label')
            if label in roles and node.get('type') == 'part':
                match = re.search(r'(\d+)$', node.get('name', ''))
                fs = node.get('fstype')
                result.append(dict(role=roles[label],
                    number=int(match[1]) if match else None,
                    size=int(node['size']),
                    start_sector_512=int(node['start']) if node.get('start') is not None else None,
                    filesystem=fs if fs in ('ext4', 'vfat') else 'OTHER'))
            visit(node.get('children', []))
    visit(json.loads(text).get('blockdevices', []))
    # Multiple attached clones may have identical labels/geometry; omit names.
    unique = {tuple(sorted(p.items())): p for p in result}
    return sorted(unique.values(), key=lambda p: (p['role'], p['number'] or 0))
