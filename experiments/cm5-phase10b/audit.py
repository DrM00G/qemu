#!/usr/bin/env python3
"""Read-only physical assets/DT/initramfs audit, never executes or mounts inputs."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import sys

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO/'experiments/cm5-phase10a'))
from preboot import identity


def cpio_entries(data):
    pos = 0
    while pos < len(data):
        while pos < len(data) and data[pos] == 0:
            pos += 1
        if pos == len(data):
            return
        if data[pos:pos+4] == b'\x28\xb5\x2f\xfd':
            data = subprocess.run(['zstd', '-d', '-c'], input=data[pos:],
                                  capture_output=True, check=True).stdout
            pos = 0
        header = data[pos:pos+110]
        if header[:6] not in (b'070701', b'070702'):
            raise ValueError('Unsupported initramfs segment')
        size, namesize = int(header[54:62], 16), int(header[94:102], 16)
        name = data[pos+110:pos+110+namesize-1].decode()
        start = (pos+110+namesize+3) & ~3
        if start+size > len(data):
            raise ValueError('Truncated initramfs')
        yield name, data[start:start+size]
        pos = (start+size+3) & ~3


def dt_nodes(path):
    data = path.read_bytes()
    magic, total, tree, strings = struct.unpack_from('>4I', data)
    assert magic == 0xd00dfeed and total <= len(data)
    stack, nodes, pos = [], {}, tree
    while pos+4 <= total:
        token = struct.unpack_from('>I', data, pos)[0]
        pos += 4
        if token == 1:
            end = data.index(0, pos)
            stack.append(data[pos:end].decode())
            pos = (end+4) & ~3
            nodes['/'.join(stack) or '/'] = {}
        elif token == 2:
            stack.pop()
        elif token == 3:
            length, nameoff = struct.unpack_from('>2I', data, pos)
            pos += 8
            end = data.index(0, strings+nameoff)
            name = data[strings+nameoff:end].decode()
            nodes['/'.join(stack) or '/'][name] = data[pos:pos+length]
            pos = (pos+length+3) & ~3
        elif token == 9:
            return nodes
        elif token != 4:
            raise ValueError('Invalid DT token')
    raise ValueError('Truncated DT')


def dt_summary(path):
    result = {}
    for node, props in dt_nodes(path).items():
        compat = props.get('compatible', b'').replace(b'\0', b',').decode(errors='replace')
        if node in ('/', '/axi', '/soc@107c000000') or any(
                x in compat for x in ('pcie', 'pci-host', 'sdhci', 'mip', 'gic',
                                     'pl011', 'fixed-clock', 'firmware-clocks')):
            selected = {}
            for key in ('compatible', 'status', 'reg', 'interrupts', 'interrupt-parent', 'interrupt-names',
                        'clocks', 'clock-names', 'clock-frequency', 'resets', 'reset-names', 'dma-ranges',
                        'ranges', 'bus-width', 'num-lanes', 'linux,pci-domain', 'msi-parent', 'supports-cqe'):
                if key not in props:
                    continue
                value = props[key]
                if key in ('compatible', 'status', 'interrupt-names', 'clock-names', 'reset-names'):
                    selected[key] = value.rstrip(b'\0').decode().split('\0')
                else:
                    selected[key] = [f'0x{v:x}' for v in struct.unpack('>'+'I'*(len(value)//4), value)]
            result[node] = selected
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=False, mode=0o700)
    private = Path('/home/aweso/cm5-phase10-private')
    assets = private/'physical-boot/boot-assets'
    identities = {f.name: identity(f) for f in assets.iterdir() if f.is_file()}
    entries = []
    for name, body in cpio_entries((assets/'initramfs_2712-osverified-v8').read_bytes()):
        if 'verity' not in name:
            continue
        item = dict(name=name, bytes=len(body), sha256=hashlib.sha256(body).hexdigest())
        if name.endswith('dm-verity.ko'):
            vermagic = re.search(rb'vermagic=([^\0]+)', body)
            item['vermagic'] = vermagic[1].decode() if vermagic else None
            item['fec_symbol_strings'] = sorted(set(s.decode() for s in re.findall(rb'verity_fec_[a-zA-Z0-9_]+', body)))
            item['interpretation'] = 'static symbols plus guest module load support FEC availability; no correction claim'
        if name.startswith('scripts/'):
            item['full_verified_os_scan_present'] = b'I" -lt 40' in body and b'count=64' in body and b'bs=4194304' in body
            item['fec_roots2_activation_present'] = b'--fec-roots=2' in body
        entries.append(item)
    lab = Path('/home/aweso/cm5-v8-lab/phase10b')/a.output.name
    lab.mkdir(parents=True, exist_ok=False)
    dtbs = {}
    for profile in ('gpex', 'native'):
        target = lab/(profile+'.dtb')
        machine = 'cm5io-dev,native-emmc=on,native-mip=on'
        if profile == 'native':
            machine += ',native-pcie=on'
        command = [str(REPO/'build-arm64-phase1/qemu-system-aarch64'), '-M', machine+',dumpdtb='+str(target),
                   '-display', 'none', '-nic', 'none', '-kernel', str(assets/'kernel_2712.img')]
        subprocess.run(command, check=True, capture_output=True, timeout=30)
        dtbs[profile] = dict(identity=identity(target), nodes=dt_summary(target),
                             scope='machine generated tree; not ARM loader final runtime fixups')
    dtbs['captured_boot'] = dt_summary(assets/'bcm2712-rpi-cm5-cm5io.dtb')
    dtbs['captured_live'] = dt_summary(private/'reference/live-v8.dtb')
    result = dict(physical_assets=identities, initramfs_verity_entries=entries, device_trees=dtbs,
                  golden_import=json.loads(Path('/home/aweso/cm5-v8-lab/golden/import.json').read_text()),
                  windows_reference_zip_present=Path('/mnt/c/Users/aweso/projects/cm5-v8-reference.zip').is_file(),
                  windows_extracted_reference='/mnt/c/Users/aweso/projects/cm5-v8-reference')
    (a.output/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    print('Asset hashes, module metadata and selected physical/virtual DT properties recorded.')


if __name__ == '__main__':
    main()
