#!/usr/bin/env python3
"""Compare observed generated runtime declarations with private reference DT.

The supported nospi10 slice is an explicit validated no-op: physical SPI10 is
absent. RP1 SPI0 is independent and must remain enabled. No nodes are injected.
"""
import argparse
import json
from pathlib import Path
import dt_pipeline as d

PHYSICAL_SPI = '/soc@107c000000/spi@7d004000'
RP1_SPI = '/pcie@1000120000/rp1/spi@50000'


def nospi10(nodes):
    d.h.require(nodes['/']['compatible'] == ['qemu,cm5io-dev'], 'UNSUPPORTED', 'wrong runtime board')
    d.h.require(PHYSICAL_SPI not in nodes, 'UNSUPPORTED', 'physical SPI10 unexpectedly declared')
    spi = nodes.get(RP1_SPI, {})
    d.h.require(spi.get('status') == 'okay' and 'snps,dw-apb-ssi' in spi.get('compatible', []),
                'UNSUPPORTED', 'native RP1 SPI declaration missing/incompatible')
    return dict(operation='nospi10', effect='VALIDATED_ABSENCE_NO_CHANGE',
                runtime_installed=False, physical_spi10_present=False, rp1_spi0_preserved=True)


def inventory(data):
    tree = d.Tree(data); result = {}
    def walk(path):
        props = tree.props(path)
        result[path] = dict(properties={k:d.h.sha(v) for k,v in props.items()},
            compatible=props.get('compatible',b'').rstrip(b'\0').decode(errors='replace').split('\0'),
            status=props.get('status',b'okay\0').rstrip(b'\0').decode(errors='replace'))
        for child in tree.children(path):
            walk(path.rstrip('/')+'/'+child)
    walk('/')
    return result


def compare(physical, runtime, expected_hash):
    d.h.require(runtime['fdt_sha256'] == expected_hash, 'INVALID_IMAGE', 'runtime output hash mismatch')
    actual = runtime['nodes']; before = inventory(physical)
    common = sorted(before.keys() & actual.keys())
    return dict(schema=1, physical_sha256=d.h.sha(physical), runtime_sha256=expected_hash,
        runtime_installed=False, equivalent=False, minimal_slice=nospi10(actual),
        physical_only=sorted(before.keys()-actual.keys()), runtime_only=sorted(actual.keys()-before.keys()),
        common_changed={k:dict(physical=before[k],runtime=actual[k]) for k in common if before[k]!=actual[k]},
        substitutions={'dwc2':'no USB host workload/model compatibility',
                       'vc4-kms-v3d-pi5':'headless; graphics/CMA unsupported',
                       'dtparam=audio=on':'no modeled audio'},
        runtime_native_spi=actual[RP1_SPI])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--physical',type=Path,required=True);p.add_argument('--run',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--expected-runtime-sha256', required=True,
                   help='independently accepted generated-DT identity')
    a=p.parse_args();users=json.loads((a.run/'userspace.json').read_text())
    observed=[u['boot_handoff_runtime'] for u in users if 'boot_handoff_runtime' in u]
    d.h.require(len(observed)>=2, 'INVALID_IMAGE', 'two runtime observations required')
    expected=a.expected_runtime_sha256
    reports=[compare(a.physical.read_bytes(),r,expected) for r in observed]
    d.h.write_report(a.output,dict(status='PASS_COMPATIBILITY_AUDIT',observations=len(reports),comparison=reports[-1]))


if __name__=='__main__':main()
