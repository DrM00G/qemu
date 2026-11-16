#!/usr/bin/env python3
"""Bounded physical-reference transformations using established libfdt/dtc.

Never installs a runtime tree. Pi firmware fragment activation, arbitrary
__overrides__ encodings, and automatic peripheral discovery are unsupported.
"""
import argparse
import ctypes as C
import difflib
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent/'cm5-phase10f'))
import handoff as h
from validate import dtb

TOOLS = Path('/home/aweso/cm5-phase3-kernel/build/scripts/dtc')


class Tree:
    def __init__(self, data):
        h.require(len(data) <= 2*1024*1024, 'UNSUPPORTED', 'DT exceeds 2MiB')
        dtb(data)
        self.lib = C.CDLL(os.environ.get('CM5_LIBFDT', '/tmp/cm5-phase10f2-tools/libfdt.so'))
        self.lib.fdt_getprop.restype = C.c_void_p
        self.lib.fdt_get_name.restype = C.c_char_p
        self.lib.fdt_getprop_by_offset.restype = C.c_void_p
        self.buf = C.create_string_buffer(len(data)+262144)
        source = C.create_string_buffer(data)
        self.check(self.lib.fdt_open_into(source, self.buf, len(self.buf)))

    @staticmethod
    def check(code):
        h.require(code >= 0, 'UNSUPPORTED', 'libfdt error '+str(code))
        return code

    def node(self, path):
        return self.check(self.lib.fdt_path_offset(self.buf, path.encode()))

    def get(self, path, key):
        size = C.c_int()
        ptr = self.lib.fdt_getprop(self.buf, self.node(path), key.encode(), C.byref(size))
        self.check(size.value)
        return C.string_at(ptr, size.value)

    def props(self, path):
        off = self.lib.fdt_first_property_offset(self.buf, self.node(path)); result = {}
        while off >= 0:
            name = C.c_char_p(); size = C.c_int()
            ptr = self.lib.fdt_getprop_by_offset(self.buf, off, C.byref(name), C.byref(size))
            self.check(size.value)
            result[name.value.decode('ascii')] = C.string_at(ptr, size.value)
            h.require(len(result) <= 4096, 'UNSUPPORTED', 'property bound')
            off = self.lib.fdt_next_property_offset(self.buf, off)
        h.require(off == -1, 'UNSUPPORTED', 'invalid property list')
        return result

    def children(self, path):
        off = self.lib.fdt_first_subnode(self.buf, self.node(path)); result = []
        while off >= 0:
            result.append(self.lib.fdt_get_name(self.buf, off, None).decode('ascii'))
            h.require(len(result) <= 4096, 'UNSUPPORTED', 'node bound')
            off = self.lib.fdt_next_subnode(self.buf, off)
        h.require(off == -1, 'UNSUPPORTED', 'invalid child list')
        return result

    def set(self, path, key, value):
        self.check(self.lib.fdt_setprop_namelen(self.buf, self.node(path), key.encode(), len(key), value, len(value)))

    def bytes(self):
        self.check(self.lib.fdt_pack(self.buf))
        size = struct.unpack('>I', self.buf.raw[4:8])[0]
        result = self.buf.raw[:size]; dtb(result)
        return result


def string(data):
    h.require(data.endswith(b'\0') and data.count(b'\0') == 1, 'UNSUPPORTED', 'single DT string required')
    return data[:-1].decode('ascii')


def resolve(mapping, name, soc='bcm2712'):
    h.require(re.fullmatch(r'[A-Za-z0-9_-]+', name), 'UNSUPPORTED', 'invalid overlay name')
    tree = Tree(mapping)
    if name not in tree.children('/'):
        return name  # Official map: missing entry retains original overlay name.
    props = tree.props('/'+name)
    h.require(soc in props, 'UNSUPPORTED', 'overlay map excludes this SoC')
    resolved = string(props[soc]) if props[soc] else name
    h.require(re.fullmatch(r'[A-Za-z0-9_-]+', resolved), 'UNSUPPORTED', 'invalid mapped name')
    return resolved


def transform(base, mapping, overlays, name, params, work, target='physical-reference'):
    h.require(target == 'physical-reference', 'UNSUPPORTED', 'physical peripherals incompatible with lab runtime')
    resolved = resolve(mapping, name)
    h.require(resolved in ('nospi10', 'dwc2', 'vc4-kms-v3d-pi5'), 'UNSUPPORTED', 'overlay hardware semantics outside supported captured subset')
    overlay = overlays[resolved]
    bt, ot = Tree(base), Tree(overlay)
    h.require(b'brcm,bcm2712' in bt.get('/', 'compatible').split(b'\0'), 'UNSUPPORTED', 'physical reference requires BCM2712')
    top = ot.children('/')
    h.require(all(n.startswith('fragment@') or n in ('__fixups__','__symbols__','__local_fixups__','__overrides__')
                  for n in top), 'UNSUPPORTED', 'unsupported overlay root node')
    fragments = [n for n in top if n.startswith('fragment@')]
    h.require(0 < len(fragments) <= 64, 'UNSUPPORTED', 'fragment count')
    for frag in fragments:
        h.require(ot.children('/'+frag) == ['__overlay__'], 'UNSUPPORTED', 'dormant/unknown fragment semantics')
        props = ot.props('/'+frag)
        h.require(('target' in props) != ('target-path' in props), 'UNSUPPORTED', 'one fragment target required')
        if 'target' in props:
            h.require(len(props['target']) == 4, 'UNSUPPORTED', 'invalid target phandle')
        else:
            bt.node(string(props['target-path']))
    symbols = bt.props('/__symbols__') if '__symbols__' in bt.children('/') else {}
    fixups = ot.props('/__fixups__') if '__fixups__' in top else {}
    references = {}
    for symbol, encoded in fixups.items():
        h.require(symbol in symbols, 'UNSUPPORTED', 'missing base symbol '+symbol)
        path = string(symbols[symbol]); bt.node(path); references[symbol] = path
        h.require(encoded.endswith(b'\0'), 'UNSUPPORTED', 'unterminated fixups')
        for ref in encoded[:-1].split(b'\0'):
            fields = ref.decode('ascii').split(':')
            h.require(len(fields) == 3 and fields[2].isdigit(), 'UNSUPPORTED', 'invalid fixup reference')
            prop = ot.get(fields[0], fields[1]); offset = int(fields[2])
            h.require(offset % 4 == 0 and offset+4 <= len(prop), 'UNSUPPORTED', 'fixup outside property')
    # Supported captured parameter: a single phandle + string property name.
    for key, value in params.items():
        h.require(resolved == 'dwc2' and key == 'dr_mode' and value in ('host','peripheral','otg'),
                  'UNSUPPORTED', 'unsupported parameter/value')
        encoded = ot.get('/__overrides__', key)
        h.require(len(encoded) > 4 and string(encoded[4:]) == 'dr_mode', 'UNSUPPORTED', 'override encoding')
        target_path = '/fragment@0/__overlay__'
        h.require(ot.get(target_path, 'phandle') == encoded[:4], 'UNSUPPORTED', 'override phandle mismatch')
        ot.get(target_path, key)
        ot.set(target_path, key, value.encode()+b'\0')
    work = h.private_dir(work)
    (work/'before.dtb').write_bytes(base)
    processed = ot.bytes(); (work/'overlay.dtbo').write_bytes(processed)
    command = [str(TOOLS/'fdtoverlay'), '-i',str(work/'before.dtb'),'-o',str(work/'after.dtb'),str(work/'overlay.dtbo')]
    applied = subprocess.run(command,capture_output=True,timeout=20)
    (work/'apply.log').write_bytes(applied.stderr)
    h.require(applied.returncode == 0, 'UNSUPPORTED', 'libfdt rejected overlay; see apply.log')
    after = (work/'after.dtb').read_bytes(); Tree(after)
    for stem in ('before','after'):
        result = subprocess.run([str(TOOLS/'dtc'),'-s','-I','dtb','-O','dts',str(work/(stem+'.dtb'))],
                                capture_output=True,timeout=20,check=True)
        (work/(stem+'.dts')).write_bytes(result.stdout)
        (work/(stem+'.warnings')).write_bytes(result.stderr)
    diff = ''.join(difflib.unified_diff((work/'before.dts').read_text().splitlines(True),
                 (work/'after.dts').read_text().splitlines(True),fromfile='before',tofile='after'))
    (work/'tree.diff').write_text(diff)
    report = dict(status='APPLIED_PHYSICAL_REFERENCE', runtime_installed=False, requested=name, resolved=resolved,
        parameters=params, required_symbols=references, input_sha256=h.sha(base), overlay_map_sha256=h.sha(mapping),
        overlay_sha256=h.sha(overlay), parameter_sha256=h.sha(json.dumps(params,sort_keys=True).encode()),
        parameterized_overlay_sha256=h.sha(processed), output_sha256=h.sha(after), diff_sha256=h.sha(diff.encode()),
        tools={str(p):h.identity(p) for p in (TOOLS/'fdtoverlay',TOOLS/'dtc',Path(ot.lib._name))})
    h.write_report(work/'transformation.json', report)
    return report, after


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base',type=Path,required=True); p.add_argument('--map',type=Path,required=True)
    p.add_argument('--overlays',type=Path,required=True); p.add_argument('--name',required=True)
    p.add_argument('--param',action='append',default=[]); p.add_argument('--work',type=Path,required=True)
    a=p.parse_args()
    try:
        name=resolve(a.map.read_bytes(),a.name)
        report,_=transform(a.base.read_bytes(),a.map.read_bytes(),{name:(a.overlays/(name+'.dtbo')).read_bytes()},
                           a.name,dict(x.split('=',1) for x in a.param),a.work)
        print(json.dumps(report)); return 0
    except (h.Outcome,OSError,ValueError,KeyError,subprocess.SubprocessError) as exc:
        print(json.dumps(dict(status='UNSUPPORTED',reason=str(exc),runtime_installed=False)));return 1


if __name__ == '__main__': sys.exit(main())
