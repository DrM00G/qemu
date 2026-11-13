#!/usr/bin/env python3
"""Read-only CM5 observation. Writes only a fresh mode-0700 evidence directory.

No raw MMIO, device transfers, I2C scans, GPIO requests/outputs, remounts,
EEPROM changes, reboot, package installation or proprietary source access.
Raw results are PRIVATE until manually reviewed. stdout contains no raw data.
"""
import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import time
from hardware_facts import describe_dt, dt_from_dir, runtime_facts, partition_facts

p = argparse.ArgumentParser()
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
os.umask(0o077)
out = a.output.resolve()
out.mkdir(parents=True, mode=0o700, exist_ok=False)
raw = out / 'raw'
raw.mkdir(mode=0o700)
manifest = {}

def save(name, data):
    (raw / name).write_bytes(data[:8 * 1024 * 1024])

def command(name, argv):
    if shutil.which(argv[0]) is None:
        manifest[name] = dict(status='UNAVAILABLE', reason='optional utility absent')
        return None
    try:
        r = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, timeout=25)
        save(name + '.stdout', r.stdout)
        save(name + '.stderr', r.stderr)
        manifest[name] = dict(status='COLLECTED' if r.returncode == 0 else 'UNAVAILABLE',
                              returncode=r.returncode, command=argv)
        return r.stdout.decode(errors='replace') if r.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired) as e:
        manifest[name] = dict(status='UNAVAILABLE', reason=type(e).__name__)
        return None

# All commands below are observation-only, fixed argv (no shell execution).
commands = {
 'kernel': ['uname', '-r'], 'page-size': ['getconf', 'PAGESIZE'],
 'cpu': ['lscpu', '--json'], 'memory': ['cat', '/proc/meminfo'],
 'pci-topology': ['lspci', '-Dnnk'], 'pci-resources': ['lspci', '-Dnnvv'],
 'interrupts': ['cat', '/proc/interrupts'], 'interrupts-second': ['cat', '/proc/interrupts'],
 'iomem': ['cat', '/proc/iomem'], 'mounts': ['findmnt', '--json'],
 'blocks': ['lsblk', '--json', '-b', '-o',
            'NAME,PKNAME,TYPE,SIZE,START,LOG-SEC,PHY-SEC,FSTYPE,LABEL,RO,MOUNTPOINTS'],
 'partitions': ['cat', '/proc/partitions'], 'dm-status': ['dmsetup', 'status'],
 'dm-info': ['dmsetup', 'info', '-c'], 'boot-log': ['dmesg', '--color=never'],
 'systemd-time': ['systemd-analyze', 'time'],
 'systemd-critical-chain': ['systemd-analyze', 'critical-chain'],
 'systemd-failures': ['systemctl', '--failed', '--no-pager', '--plain'],
 'pinmux': ['pinctrl', 'get'], 'pinmux-legacy': ['raspi-gpio', 'get'],
 'gpio-info': ['gpioinfo'], 'i2c-adapters': ['i2cdetect', '-l'],
 'firmware-version': ['vcgencmd', 'version'],
 'bootloader-version': ['vcgencmd', 'bootloader_version'],
 'bootloader-config': ['vcgencmd', 'bootloader_config'],
}
results = {}
for name, argv in commands.items():
    if name == 'interrupts-second':
        time.sleep(1)
    results[name] = command(name, argv)

# Copy only kernel-generated DT properties, never arbitrary mounted files.
dtroot = Path('/sys/firmware/devicetree/base')
if dtroot.is_dir():
    target = raw / 'live-dt'
    read_errors = 0
    for source in dtroot.rglob('*'):
        if source.is_file() and not source.is_symlink():
            dest = target / source.relative_to(dtroot)
            try:
                data = source.read_bytes()
                if len(data) > 1024 * 1024:
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                dest.write_bytes(data)
            except OSError:
                read_errors += 1
                continue
    manifest['live-dt'] = dict(status='PARTIAL' if read_errors else
        'COLLECTED' if target.exists() else 'UNAVAILABLE', read_errors=read_errors)
else:
    manifest['live-dt'] = dict(status='UNAVAILABLE', reason='no readable live DT')
try:
    save('live-fdt.dtb', Path('/sys/firmware/fdt').read_bytes())
    manifest['live-fdt'] = dict(status='COLLECTED')
except OSError:
    manifest['live-fdt'] = dict(status='UNAVAILABLE', reason='no readable FDT blob')

# Sysfs driver topology only, not data from flight-software paths or block files.
topology = {}
for group in ('pci/devices', 'platform/devices', 'spi/devices', 'i2c/devices'):
    entries = []
    for dev in Path('/sys/bus', group).glob('*'):
        entry = dict(path=str(dev))
        for name in ('vendor', 'device', 'class', 'revision', 'resource', 'modalias'):
            try:
                entry[name] = (dev / name).read_text()
            except OSError:
                pass
        for name in ('driver', 'of_node'):
            if (dev / name).is_symlink():
                entry[name] = str((dev / name).resolve())
        entries.append(entry)
    topology[group] = entries
save('sysfs-topology.json', json.dumps(topology, indent=2).encode())
# Phase 8 addition: passive MMC descriptors only. Never issue MMC commands,
# read EXT_CSD through a device, or mount debugfs to obtain missing fields.
mmc = []
for host in sorted(Path('/sys/class/mmc_host').glob('mmc*')):
    row = dict(host=host.name, topology=str(host.resolve()), descriptors={})
    for link in ('device/driver', 'device/of_node'):
        if (host / link).is_symlink():
            row[link] = str((host / link).resolve())
    paths = {name: host / name for name in
             ('f_min', 'f_max', 'actual_clock', 'caps', 'caps2')}
    paths['ios'] = Path('/sys/kernel/debug') / host.name / 'ios'
    for name, path in paths.items():
        try:
            row['descriptors'][name] = path.read_text()[:16384]
        except OSError:
            row['descriptors'][name] = 'UNAVAILABLE'
    mmc.append(row)
save('mmc-passive.json', json.dumps(mmc, indent=2).encode())
manifest['mmc-passive'] = dict(status='COLLECTED' if mmc else 'UNAVAILABLE',
    source='existing sysfs links/descriptors and already-mounted debugfs ios')
try:
    facts = describe_dt(dt_from_dir(raw / 'live-dt')) if manifest['live-dt']['status'] == 'COLLECTED' else {}
except (OSError, ValueError):
    facts = {}
facts.update(runtime_facts('/', results['dm-status']))
if results['blocks']:
    try:
        facts['storage.partition_roles'] = dict(value=partition_facts(results['blocks']),
            source='lsblk allowed partition labels/geometry', evidence_kind='RUNTIME_READ_ONLY')
        def recovery_mount(nodes):
            found = []
            for node in nodes:
                if node.get('label') == 'RECOVERY':
                    found.append(any(node.get('mountpoints') or []))
                found.extend(recovery_mount(node.get('children', [])))
            return found
        recovery = recovery_mount(json.loads(results['blocks']).get('blockdevices', []))
        if recovery:
            facts['fault.recovery_partition_mounted'] = dict(value=any(recovery),
                source='lsblk RECOVERY mount state; contents not read', evidence_kind='RUNTIME_READ_ONLY')
    except (ValueError, KeyError, TypeError):
        pass
if results['mounts']:
    try:
        def root_fs(nodes):
            for node in nodes:
                if node.get('target') == '/':
                    return node.get('fstype')
                value = root_fs(node.get('children', []))
                if value:
                    return value
        fs = root_fs(json.loads(results['mounts']).get('filesystems', []))
        if fs in ('ext4', 'overlay', 'squashfs', 'xfs', 'btrfs'):
            facts['fault.root_filesystem'] = dict(value=fs, source='findmnt root FSTYPE only',
                evidence_kind='RUNTIME_READ_ONLY')
    except (ValueError, TypeError):
        pass
if results['bootloader-config']:
    import re
    order = re.search(r'^BOOT_ORDER=(0x[0-9a-fA-F]+|[0-9]+)$', results['bootloader-config'], re.M)
    if order:
        facts['boot.eeprom_boot_order'] = dict(value=int(order[1], 0),
            source='vcgencmd bootloader_config BOOT_ORDER only (configured, not observed boot path)',
            evidence_kind='RUNTIME_READ_ONLY')
facts['cpu.page_size'] = dict(value=os.sysconf('SC_PAGE_SIZE'), source='sysconf(SC_PAGE_SIZE)', evidence_kind='RUNTIME_READ_ONLY')
# Only the numeric release is publishable automatically; full release stays raw.
import re
version = re.match(r'\d+\.\d+(?:\.\d+)?', platform.release())
if version:
    facts['cpu.kernel_version'] = dict(value=version.group(), source='uname -r (numeric prefix)', evidence_kind='RUNTIME_READ_ONLY')
(out / 'facts.json').write_text(json.dumps(dict(schema=1, facts=facts), indent=2) + '\n')
(out / 'manifest.json').write_text(json.dumps(dict(schema=1, raw_private=True,
    observations=manifest), indent=2) + '\n')
print('Read-only collection complete. Raw data is restricted; review before sharing.')
print('Missing commands/permissions are recorded as UNAVAILABLE in manifest.json.')
