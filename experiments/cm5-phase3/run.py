#!/usr/bin/env python3
"""Boot one verified-storage pilot and record observed, separate outcome metrics."""
import argparse
import csv
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
import uuid

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(HERE.parent / 'cm5-phase1'))
import launch as baseline
from inject import inject
from importlib.util import spec_from_file_location, module_from_spec
spec = spec_from_file_location('accept_a', HERE / 'accept-a.py')
diagnostics = module_from_spec(spec)
spec.loader.exec_module(diagnostics)


def provision(directory, run_id, port, config):
    args = argparse.Namespace(root_mode='overlay', expected_page_size=16384)
    baseline.provision(directory, run_id, port, args)
    path = directory / 'user-data'
    data = diagnostics.diagnostics(json.loads(path.read_text().split('\n', 1)[1]))
    for entry in data['write_files']:
        if entry['path'] == '/etc/systemd/system/phase1-test.service':
            entry['content'] = entry['content'].replace('[Service]',
                'Wants=phase3-check.service\nAfter=phase3-check.service\n[Service]')
        if entry['path'] == '/usr/local/lib/phase1-test.py':
            anchor = '    payload = json.dumps(result, sort_keys=True).encode()'
            extra = '''    try:
        result['phase3'] = json.loads(Path('/var/log/flight/phase3-result.json').read_text())
        result['pass'] = result['pass'] and result['phase3'].get('pass') is True
    except Exception as exc:
        result['pass'] = False
        result['phase3_report_error'] = str(exc)
'''
            entry['content'] = entry['content'].replace(anchor, extra + anchor)
    files = [('/usr/local/lib/phase3-storage.py', (HERE / 'guest-storage.py').read_text()),
             ('/etc/phase3-run.json', json.dumps(config))]
    for unit, where, what, options in [('opt-fsw.mount', '/opt/fsw', '/dev/mapper/v8-fsw', 'ro,noload'),
                                     ('var-log-flight.mount', '/var/log/flight', '/dev/vdc', 'rw'),
                                     ('boot.mount', '/boot', '/dev/vde', 'ro,noload')]:
        files.append(('/etc/systemd/system/' + unit,
                      f'[Unit]\nDescription=Phase 3 {where}\n[Mount]\nWhat={what}\nWhere={where}\nType=ext4\nOptions={options}\n'))
    app_dependencies = ''
    if config['prototype']:
        app_dependencies = 'Wants=prototype-fsw.service\nAfter=prototype-fsw.service\n'
        files.append(('/etc/systemd/system/prototype-fsw.service', f'''[Unit]
Description=Synthetic ARM64 prototype FSW
Requires=opt-fsw.mount var-log-flight.mount
After=opt-fsw.mount var-log-flight.mount network-online.target
[Service]
Type=simple
Environment=PHASE3_ENDPOINT=http://10.0.2.2:{port}/probe/{run_id}
ExecStart=/opt/fsw/prototype-fsw
StandardOutput=journal+console
StandardError=journal+console
'''))
    files.append(('/etc/systemd/system/phase3-check.service', f'''[Unit]
Description=Verified storage and correction pilot
Requires=opt-fsw.mount var-log-flight.mount boot.mount
After=opt-fsw.mount var-log-flight.mount boot.mount cloud-final.service network-online.target
{app_dependencies}[Service]
Type=oneshot
ExecStart=/usr/bin/python3 /usr/local/lib/phase3-storage.py
RemainAfterExit=yes
TimeoutStartSec=2100
StandardOutput=journal+console
StandardError=journal+console
'''))
    # Keep the simulator's persistent mount description tied to the verified
    # mapper rather than the public lower image's original raw-device label.
    patch_fstab = """from pathlib import Path
p=Path('/etc/fstab')
lines=[]
for line in p.read_text().splitlines():
    fields=line.split()
    if fields and not fields[0].startswith('#') and len(fields)>1 and fields[1]=='/media/root-ro':
        fields[0]='/dev/mapper/v8-os'
        line='\\t'.join(fields)
    lines.append(line)
p.write_text('\\n'.join(lines)+'\\n')
"""
    data['runcmd'].insert(0, ['python3', '-c', patch_fstab])
    data['write_files'] += [{'path': name, 'permissions': '0644', 'content': text} for name, text in files]
    path.write_text('#cloud-config\n' + json.dumps(data, indent=2) + '\n')
    (directory / 'seed.img').unlink()
    baseline.run('cloud-localds', '--network-config=' + str(directory / 'network-config'),
                 directory / 'seed.img', path, directory / 'meta-data')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--storage', type=Path, default=HERE / 'artifacts/storage-v1/manifest.json')
    p.add_argument('--case', choices=('clean', 'os-fec', 'fsw-fec', 'fsw-no-fec'), default='clean')
    p.add_argument('--kernel-root', type=Path, default=Path(os.environ.get('PHASE3_KERNEL_ROOT', str(Path.home() / 'cm5-phase3-kernel'))))
    p.add_argument('--memory', default='8192')
    p.add_argument('--cpus', default='4')
    p.add_argument('--timeout', type=float, default=2400)
    p.add_argument('--full-os-scan', action='store_true')
    p.add_argument('--artifacts', type=Path, default=HERE / 'artifacts/runs')
    args = p.parse_args()
    run_id = str(uuid.uuid4())
    directory = args.artifacts.resolve() / (time.strftime('%Y%m%d-%H%M%S') + '-' + args.case + '-' + run_id[:8])
    directory.mkdir(parents=True, exist_ok=False)
    summary = {'schema': 1, 'run_id': run_id, 'case': args.case, 'status': 'FAIL_INFRASTRUCTURE', 'boot_success': None,
               'kernel_boot': None, 'verified_root_mounted': None, 'systemd_target': None,
               'prototype_started': None, 'prototype_functions': None, 'prototype_sustained': None,
               'complete_os_recovery': None, 'complete_fsw_recovery': None,
               'fec_correction_activity': None, 'infrastructure_failure': False, 'timeout': False}
    process, server = None, None
    received, original_hashes = [], {}
    event = threading.Event()
    try:
        manifest = json.loads(args.storage.read_text())
        for name, volume in manifest['volumes'].items():
            path = Path(volume['path'])
            actual = baseline.sha256(path)
            if actual != volume['sha256']:
                raise RuntimeError('Golden storage hash mismatch: ' + name)
            original_hashes[name] = actual
        config = {key: manifest[key] for key in ('volumes', 'probe_sha256', 'prototype')}
        config.update(case=args.case, fec=args.case != 'fsw-no-fec', full_os_scan=args.full_os_scan, faults={})
        images = {}
        faulted = 'os' if args.case == 'os-fec' else ('fsw' if args.case in ('fsw-fec', 'fsw-no-fec') else None)
        for name in ('os', 'fsw', 'logs'):
            volume = manifest['volumes'][name]
            if name == faulted:
                injection = inject(Path(volume['path']), directory / ('fault-' + name),
                                   fec_blocks=volume['fec_blocks'])
                images[name] = injection['overlay']
                config['faults'][name] = injection['faults']
                summary['injection'] = injection
            else:
                image = directory / (name + '.qcow2')
                baseline.run(REPO / 'build-arm64-phase1/qemu-img', 'create', '-f', 'qcow2',
                             '-F', 'raw', '-b', volume['path'], image)
                images[name] = str(image)
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path != '/probe/' + run_id:
                    self.send_error(404)
                    return
                self.send_response(200)
                self.end_headers()
                self.wfile.write(baseline.PROBE)

            def do_POST(self):
                if self.path != '/result/' + run_id:
                    self.send_error(404)
                    return
                size = int(self.headers.get('Content-Length', 0))
                if not 0 < size < 2 * 1024**2:
                    self.send_error(400)
                    return
                result = json.loads(self.rfile.read(size))
                if result.get('run_id') != run_id or type(result.get('pass')) is not bool:
                    self.send_error(400)
                    return
                received.append(result)
                (directory / 'guest-result.json').write_text(json.dumps(result, indent=2) + '\n')
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'OK\n')
                event.set()

            def log_message(self, fmt, *values):
                with (directory / 'http.log').open('a') as stream:
                    stream.write(fmt % values + '\n')
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        server.daemon_threads = True
        threading.Thread(target=server.serve_forever, daemon=True).start()
        provision(directory, run_id, server.server_port, config)
        (directory / 'run-config.json').write_text(json.dumps(config, indent=2) + '\n')
        kernel = args.kernel_root / 'build/arch/arm64/boot/Image'
        header = baseline.kernel_diagnostics(kernel, args.kernel_root / 'build/.config')
        if header['header_page_size'] != 16384:
            raise RuntimeError('Refusing a kernel without a 16 KiB Image header')
        if header['sha256'] != manifest['kernel']['image_sha256'] or header['config_sha256'] != manifest['kernel']['config_sha256']:
            raise RuntimeError('Kernel/config differs from the storage preparation manifest')
        shutil.copyfile(args.kernel_root / 'build/.config', directory / 'kernel.config')
        initrd = args.storage.parent / ('initramfs-fec' if config['fec'] else 'initramfs-no-fec') / 'initrd.gz'
        if baseline.sha256(initrd) != manifest['initramfs'][initrd.parent.name]:
            raise RuntimeError('Pinned initramfs hash mismatch')
        command = [str(REPO / 'build-arm64-phase1/qemu-system-aarch64'), '-machine', 'virt',
                   '-cpu', 'cortex-a76', '-accel', 'tcg,thread=multi', '-smp', args.cpus,
                   '-m', args.memory, '-display', 'none', '-monitor', 'none', '-serial', 'stdio',
                   '-no-reboot', '-kernel', str(kernel), '-initrd', str(initrd), '-append',
                   'console=ttyAMA0 root=/dev/mapper/v8-os rootfstype=ext4 rootflags=noload ro rootwait '
                   'fsck.mode=skip overlayroot=tmpfs:recurse=1 overlayroot_cfgdisk=disabled']
        for name in ('os', 'fsw', 'logs', 'recovery', 'boot'):
            image = images.get(name, manifest['volumes'][name]['path'])
            fmt = 'qcow2' if name in images else 'raw'
            readonly = '' if name == 'logs' else ',readonly=on'
            command += ['-drive', f'if=none,id={name},file={image},format={fmt}{readonly}',
                        '-device', f'virtio-blk-pci,drive={name}']
        command += ['-drive', f'if=none,id=seed,file={directory / "seed.img"},format=raw,readonly=on',
                    '-device', 'virtio-blk-pci,drive=seed', '-device', 'virtio-rng-pci',
                    '-netdev', 'user,id=net0', '-device', 'virtio-net-pci,netdev=net0,mac=52:54:00:12:34:56']
        summary.update(command=command, kernel=header, initrd_sha256=baseline.sha256(initrd),
                       memory=args.memory, cpus=args.cpus)
        (directory / 'command.json').write_text(json.dumps(command, indent=2) + '\n')
        print('Artifacts: ' + str(directory), flush=True)
        started = time.monotonic()
        deadline = started + args.timeout
        report_seen = False
        with (directory / 'serial.log').open('xb') as serial:
            process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=serial, stderr=subprocess.STDOUT)
            while process.poll() is None and time.monotonic() < deadline:
                if event.wait(0.5) and not report_seen:
                    deadline = time.monotonic() + 180
                    report_seen = True
                if report_seen:
                    time.sleep(0.1)
        summary['elapsed_seconds'] = round(time.monotonic() - started, 3)
        text = (directory / 'serial.log').read_text(errors='replace')
        summary['kernel_boot'] = 'Linux version ' in text
        summary['qemu_returncode'] = process.poll()
        summary['poweroff_seen'] = 'reboot: Power down' in text
        if process.poll() is None:
            summary.update(status='FAIL_TIMEOUT', timeout=True, reason='shutdown timeout' if received else 'no guest report before deadline')
        elif process.returncode != 0:
            summary.update(status='FAIL_INFRASTRUCTURE', infrastructure_failure=True, reason='QEMU exited nonzero')
        elif not received:
            summary.update(status='FAIL_BOOT', reason='no complete systemd/service report')
        else:
            guest = received[-1]
            storage = guest.get('phase3', {})
            summary.update(verified_root_mounted=storage.get('verified_root_mounted'),
                           systemd_target=guest.get('target') == 'active',
                           prototype_started=storage.get('prototype_started'),
                           prototype_functions=storage.get('prototype_functions'),
                           prototype_sustained=storage.get('prototype_sustained'),
                           fec_correction_activity=storage.get('fec_correction_activity'),
                           complete_os_recovery=storage.get('logical_recovery', {}).get('os', {}).get('complete_recovery'),
                           complete_fsw_recovery=storage.get('logical_recovery', {}).get('fsw', {}).get('complete_recovery'),
                           corruption_detected_without_fec=storage.get('corruption_detected_without_fec'))
            checks = guest.get('checks', {})
            baseline_pass = (guest.get('pid1') == 'systemd' and guest.get('page_size') == 16384 and
                             guest.get('target') == 'active' and guest.get('failed_units') == '' and
                             set(checks) == {'filesystem', 'shared_libraries', 'cpu', 'memory', 'network', 'root_contract'} and
                             all(row.get('pass') is True for row in checks.values()))
            summary['boot_success'] = baseline_pass and storage.get('verified_root_mounted') is True
            passed = guest['pass'] is True and baseline_pass and storage.get('pass') is True and summary['poweroff_seen']
            summary.update(status='PASS' if passed else 'FAIL_GUEST', reason='actual guest service/report contract evaluated')
        if not received and 'PHASE1_RESULT ' in text:
            summary.update(status='FAIL_INFRASTRUCTURE', infrastructure_failure=True, reason='serial report exists but HTTP delivery failed')
    except KeyboardInterrupt:
        summary.update(status='FAIL_INFRASTRUCTURE', infrastructure_failure=True, reason='operator interrupted')
    except Exception as exc:
        summary.update(status='FAIL_INFRASTRUCTURE', infrastructure_failure=True, reason=str(exc))
        if isinstance(exc, subprocess.CalledProcessError):
            summary['tool_output'] = exc.output
    finally:
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        if server:
            server.shutdown()
            server.server_close()
        summary['golden_hashes_before'] = original_hashes
        if original_hashes:
            summary['golden_hashes_after'] = {name: baseline.sha256(Path(manifest['volumes'][name]['path'])) for name in original_hashes}
            if summary['golden_hashes_after'] != original_hashes:
                summary.update(status='FAIL_INFRASTRUCTURE', infrastructure_failure=True, reason='golden image changed')
        (directory / 'result.json').write_text(json.dumps(summary, indent=2) + '\n')
        fields = ['case', 'status', 'kernel_boot', 'verified_root_mounted', 'systemd_target',
                  'prototype_started', 'prototype_functions', 'prototype_sustained',
                  'complete_os_recovery', 'complete_fsw_recovery', 'fec_correction_activity',
                  'infrastructure_failure', 'timeout']
        with (directory / 'result.csv').open('w') as stream:
            writer = csv.DictWriter(stream, fieldnames=fields, extrasaction='ignore')
            writer.writeheader()
            writer.writerow(summary)
        print(json.dumps(summary, indent=2), flush=True)
    return 0 if summary['status'] == 'PASS' else (2 if summary['infrastructure_failure'] else 1)


if __name__ == '__main__':
    raise SystemExit(main())
