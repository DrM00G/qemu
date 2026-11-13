#!/usr/bin/env python3
"""Validate retained Phase 8 evidence, without running guest workloads."""
import hashlib
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
OUT = HERE / 'artifacts'
LAB = Path.home() / 'cm5-v8-lab/phase8'
results = {}


def record(name, path, expected=None):
    result = json.loads(path.read_text())
    if result['status'] != 'PASS' or not all(result['checks'].values()):
        raise RuntimeError('failed evidence: ' + str(path))
    if expected:
        for key, value in expected.items():
            if result.get(key) != value:
                raise RuntimeError('wrong profile: ' + str(path))
    results[name] = dict(status='PASS', evidence=str(path), checks=result['checks'])


for name, count in [('rp1', 5), ('cm5io', 2), ('bcm2712-mip', 3), ('bcm2712-sdhci', 3)]:
    path = OUT / f'qtest-{name}-final.log'
    text = path.read_text()
    if len(re.findall(r'^ok [0-9]+ ', text, re.M)) != count or 'not ok' in text:
        raise RuntimeError('qtest failure: ' + str(path))
    results[name + '-qtest'] = dict(status='PASS', tests=count, evidence=str(path))

for platform in ('virt', 'cm5io-dev'):
    for mode in ('spi', 'v8'):
        record(platform + '-' + mode, LAB / f'preserved-regressions/fallbacks/{platform}-{mode}/result.json')
for mode in ('spi', 'v8'):
    record('preserved-native-mip-' + mode, LAB / f'preserved-regressions/native-{mode}/result.json',
           dict(native_mip=True, native_emmc=False))
    record('native-emmc-' + mode, OUT / f'native-{mode}-final/result.json',
           dict(native_mip=True, native_emmc=True))
record('eight-gib', OUT / 'native-8g/result.json')
record('os-verity-clean', OUT / 'os-verity-clean-validated/result-rechecked.json',
       dict(os_verity=True, os_corrupt_block_zero=False))
pilot_path = OUT / 'os-fec-pilot/result-rechecked.json'
pilot = json.loads(pilot_path.read_text())
recovery_checks = ('block_digests', 'os_verity_read', 'os_verity_valid',
                   'kernel_fec_correction', 'native_os_lower', 'original_diagnostic',
                   'spi_diagnostic', 'native_mip_delivery')
if not all(pilot['checks'].get(k) for k in recovery_checks):
    raise RuntimeError('FEC correction not established')
results['os-fec-pilot'] = dict(status='PARTIALLY_IMPLEMENTED',
    recovery='IMPLEMENTED_AND_GUEST_VALIDATED', evidence=str(pilot_path),
    complete_boot='TIMEOUT_WITH_RCU_STALL', checks=pilot['checks'])

before = (OUT / 'golden-before.sha256').read_text().split()[0]
after = (OUT / 'golden-final.sha256').read_text().split()[0]
if before != after:
    raise RuntimeError('golden hash changed')
protection = json.loads((OUT / 'os-verity-clean-validated/block-backend-protection.json').read_text())
if not protection['read_only'] or protection['access_mode'] != 0:
    raise RuntimeError('golden descriptor was writable')
preserved = {}
for line in (OUT / 'baseline-sha256.txt').read_text().splitlines():
    digest, name = line.split(maxsplit=1)
    if name in ('hw/misc/rp1-pci.c', 'hw/ssi/dw-apb-ssi.c',
                'hw/ssi/ssi-test-slave.c', 'hw/intc/bcm2712-mip.c'):
        actual = hashlib.sha256((REPO / name).read_bytes()).hexdigest()
        if actual != digest:
            raise RuntimeError('preserved source changed: ' + name)
        preserved[name] = actual
inventory = dict(status='PASS_WITH_LIMITATIONS', results=results, golden_sha256=after,
                 golden_descriptor=protection, preserved_sources=preserved,
                 physical_observations='NOT_RUN_PHYSICAL',
                 note='Each run inputs.json records its binary/kernel/initramfs hashes; '
                      'result-rechecked.json retains parser corrections without repeating workloads.')
(OUT / 'validation.json').write_text(json.dumps(inventory, indent=2) + '\n')
print('PASS: 13 hardware qtests, six preserved guest regressions, native eMMC SPI/V8, '
      '8 GiB guest and clean OS verity; golden unchanged. '
      'FEC correction and diagnostics passed; corrupted full boot timed out with an RCU stall.')
