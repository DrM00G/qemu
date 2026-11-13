#!/usr/bin/env python3
"""Check all four real-guest regression results and retained source provenance."""
import hashlib
import json
from pathlib import Path
import re

here = Path(__file__).resolve().parent
repo = here.parent.parent
art = here / 'artifacts'

def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

qemu = repo / 'build-arm64-phase1/qemu-system-aarch64'
current_sha = sha(qemu)
runs = {}
for name in ('cm5-spi-verified', 'virt-spi-final', 'cm5-v8-final', 'virt-v8-final'):
    result = json.loads((art / name / 'result.json').read_text())
    assert result['status'] == 'PASS' and all(result['checks'].values()), name
    inputs = json.loads((art / name / 'inputs.json').read_text())
    assert inputs[str(qemu)] == current_sha, f'{name}: different QEMU binary'
    runs[name] = result
qtests = {}
for name, count in (('qtest-rp1-final.log', 5), ('qtest-cm5io-final.log', 2)):
    text = (art / name).read_text()
    assert len(re.findall(r'^ok \d ', text, re.M)) == count
    assert 'not ok' not in text
    qtests[name] = count
baseline = json.loads((art / 'phase5-validation.json').read_text())
unchanged = []
for filename, expected in baseline['sha256'].items():
    path = Path(filename)
    if any(path.is_relative_to(repo / p) for p in ('hw', 'include/hw', 'tests/qtest')):
        assert sha(path) == expected, f'Phase 5 source changed: {path}'
        unchanged.append(str(path.relative_to(repo)))
assert sha(art / 'qemu-phase5-known-good') == baseline['sha256'][str(qemu)]
default_dt = (art / 'cm5io.dts').read_text()
minimal_dt = (art / 'cm5io-minimal.dts').read_text()
assert 'qemu,cm5io-dev' in default_dt
assert 'brcm,bcm2712-pcie' not in default_dt
assert 'spi@50000' in default_dt and 'spi@50000' not in minimal_dt
assert 'pcie@1201000000' in default_dt and 'pcie@1201000000' not in minimal_dt
assert 'qemu,gpio-vref-millivolt = <0xce4>' in default_dt
assert 'qemu,gpio-vref-millivolt = <0x708>' in minimal_dt
sources = ('hw/arm/cm5io-dev.c', 'include/hw/arm/cm5io-dev.h',
           'hw/arm/Kconfig', 'hw/arm/meson.build', 'hw/pci-host/gpex.c',
           'include/hw/pci-host/gpex.h', 'tests/qtest/cm5io-test.c',
           'tests/qtest/meson.build')
result = dict(status='PASS', machine='cm5io-dev', full_bcm2712_compatibility=False,
              qemu_sha256=current_sha, qtests=qtests, guest_regressions=runs,
              phase5_sources_unchanged=unchanged,
              preserved_phase5_binary=True, generated_dt_profiles_checked=True,
              source_sha256={name: sha(repo / name) for name in sources})
print(json.dumps(result, indent=2))
