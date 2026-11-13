#!/usr/bin/env python3
"""Run the preserved Phase 2 contract with extra guest failure diagnostics."""
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'cm5-phase1'))
import launch


def diagnostics(data):
    for entry in data['write_files']:
        if entry['path'] == '/usr/local/lib/phase1-test.py':
            anchor = '    payload = json.dumps(result, sort_keys=True).encode()'
            if entry['content'].count(anchor) != 1:
                raise RuntimeError('Phase 1 reporter contract changed; diagnostic insertion refused')
            extra = '''    result['service_journal'] = subprocess.run(
        ['journalctl', '-b', '--no-pager', '-n', '160', '-u', 'snapd.service',
         '-u', 'snapd.seeded.service', '-u', 'multipathd.service'],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT).stdout
    result['kernel_journal'] = subprocess.run(
        ['journalctl', '-b', '-k', '--no-pager', '-n', '100'],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT).stdout
'''
            entry['content'] = entry['content'].replace(anchor, extra + anchor)
    return data


original_provision = launch.provision


def provision(directory, run_id, port, args):
    original_provision(directory, run_id, port, args)
    path = directory / 'user-data'
    data = diagnostics(json.loads(path.read_text().split('\n', 1)[1]))
    path.write_text('#cloud-config\n' + json.dumps(data, indent=2) + '\n')
    (directory / 'seed.img').unlink()
    launch.run('cloud-localds', '--network-config=' + str(directory / 'network-config'),
               directory / 'seed.img', path, directory / 'meta-data')


if __name__ == '__main__':
    launch.provision = provision
    sys.exit(launch.main())
