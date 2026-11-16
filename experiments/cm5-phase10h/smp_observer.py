"""Wrap the existing native observer in optional bounded guest CPU/BAR load."""
import json
from pathlib import Path


def wrap(code):
    begin = code.index("import mmap\nr['native_rp1'] = {}")
    end = code.index("print('P10C_USER_JSON='", begin)
    worker = (Path(__file__).with_name('smp_worker.py')).read_text()
    prefix = '''import tempfile
import time
stress_dir = Path(tempfile.mkdtemp(prefix='cm5-h-smp-', dir='/run'))
stress_workers = []
r['phase10h_smp'] = dict(online=Path('/sys/devices/system/cpu/online').read_text().strip(),
                         clock='guest-monotonic-ns', workers=[])
try:
    for stress_cpu in (1, 2, 3):
        stress_workers.append(subprocess.Popen(['python3', '-c', WORKER_CODE,
            str(stress_cpu), str(stress_dir)], stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True))
    stress_deadline = time.monotonic() + 5
    while not all((stress_dir/f'ready-{c}').exists() for c in (1, 2, 3)):
        if time.monotonic() >= stress_deadline:
            raise RuntimeError('SMP worker startup timeout')
        time.sleep(0.01)
    r['phase10h_smp']['before_spi_monotonic_ns'] = time.monotonic_ns()
'''.replace('WORKER_CODE', json.dumps(worker))
    suffix = '''except Exception as stress_error:
    r['phase10h_smp']['error'] = str(stress_error)
finally:
    r['phase10h_smp']['after_spi_monotonic_ns'] = time.monotonic_ns()
    (stress_dir/'stop').touch()
    for stress_process in stress_workers:
        try:
            stress_out, stress_err = stress_process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            stress_process.kill()
            stress_out, stress_err = stress_process.communicate()
        r['phase10h_smp']['workers'].append(dict(returncode=stress_process.returncode,
            result=json.loads(stress_out) if stress_out else None, error=stress_err))
'''
    return code[:begin] + prefix + ''.join('    '+line+'\n' for line in code[begin:end].splitlines()) + suffix + code[end:]
