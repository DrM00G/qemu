#!/usr/bin/env python3
"""Final evidence gate. Physical measurements must remain unavailable tonight."""
import hashlib
import json
from pathlib import Path
import re

here = Path(__file__).resolve().parent
repo = here.parent.parent
art = here / 'artifacts'
qemu = repo / 'build-arm64-phase1/qemu-system-aarch64'
def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()
binary = sha(qemu)
runs = {}
for name in ('native-spi-final', 'native-v8-final', 'fallback-spi-final',
             'fallback-v8-final', 'virt-spi-final', 'virt-v8-final'):
    result = json.loads((art / name / 'result.json').read_text())
    assert result['status'] == 'PASS' and all(result['checks'].values()), name
    assert json.loads((art / name / 'inputs.json').read_text())[str(qemu)] == binary, name
    runs[name] = result
qtests = {}
for name, count in (('rp1', 5), ('cm5io', 2), ('mip', 3)):
    text = (art / f'qtest-{name}-final.log').read_text()
    assert len(re.findall(r'^ok \d ', text, re.M)) == count and 'not ok' not in text
    qtests[name] = count
src = Path.home() / 'cm5-phase3-kernel/linux-62a56e350fcfd1c5e204c62dac4ea4ee205eb24e/drivers/irqchip/irq-bcm2712-mip.c'
module = art / 'mip-module/irq-bcm2712-mip.ko'
assert sha(src) == sha(module.with_suffix('.c'))
old = json.loads((repo / 'experiments/cm5-phase5/artifacts/validation.json').read_text())
kernel = Path.home() / 'cm5-phase3-kernel/build/arch/arm64/boot/Image'
assert sha(kernel) == old['sha256'][str(kernel)]
for path in ('hw/misc/rp1-pci.c', 'hw/ssi/dw-apb-ssi.c', 'hw/ssi/ssi-test-slave.c',
             'include/hw/ssi/dw-apb-ssi.h', 'tests/qtest/rp1-test.c'):
    assert sha(repo / path) == old['sha256'][str(repo / path)]
trace = (art / 'native-spi-final/peripheral.log').read_text()
assert trace.count('bcm2712_mip_raise first=0 vector=19 delivered=1') > 0
matrix = json.loads((art / 'friday-planning-matrix/capabilities.json').read_text())
assert not matrix['physical_measurements_available']
assert all(r['physical_value'] == 'UNAVAILABLE' for r in matrix['capabilities'])
tool_tests = (art / 'tool-tests.log').read_text()
assert 'Ran 7 tests' in tool_tests and '\nOK\n' in tool_tests
v8_trace = (art / 'native-v8-final/peripheral.log').read_text()
assert re.search(r'bcm2712_mip_raise first=8 vector=\d+ delivered=1', v8_trace)
result = dict(status='PASS', native_driver='unmodified public mip_msi external module',
    native_edge_path='IMPLEMENTED_AND_GUEST_VALIDATED',
    full_mip_register_fidelity='PARTIALLY_IMPLEMENTED',
    physical_validation='NOT_RUN_PHYSICAL', qemu_sha256=binary,
    kernel_sha256=sha(kernel), module_sha256=sha(module), linux_driver_sha256=sha(src),
    qtests=qtests, guest_runs=runs, phase5_sources_unchanged=True,
    original_kernel_unchanged=True, physical_matrix_rows=len(matrix['capabilities']),
    parser_privacy_tests=7, native_mip1_guest_delivery=True,
    model_limitations=['unverified reset image', 'INT_CLEAR/level/VPU semantics absent',
                       'masked-event retention unverified', 'fixed MSI inbound aperture only; GPEX still supplies config space'])
print(json.dumps(result, indent=2))
