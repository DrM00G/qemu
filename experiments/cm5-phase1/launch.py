#!/usr/bin/env python3
"""Disposable ARM64 virt experiment and clean-boot acceptance runner."""
import argparse
import gzip
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import shutil
import shlex
import subprocess
import sys
import threading
import time
import uuid

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
PROBE = b'cm5-phase1-virtual-network-probe-v1\n'


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def run(*args):
    return subprocess.check_output([str(arg) for arg in args], text=True, stderr=subprocess.STDOUT)


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--disk', type=Path, default=Path.home() / 'vm-images/ubuntu-arm64/ubuntu-24.04-server-cloudimg-arm64.img')
    p.add_argument('--qemu', type=Path, default=REPO / 'build-arm64-phase1/qemu-system-aarch64')
    p.add_argument('--qemu-img', type=Path, default=REPO / 'build-arm64-phase1/qemu-img')
    p.add_argument('--firmware-code', type=Path, default=Path('/usr/share/AAVMF/AAVMF_CODE.fd'))
    p.add_argument('--firmware-vars', type=Path, default=Path('/usr/share/AAVMF/AAVMF_VARS.fd'))
    p.add_argument('--kernel', type=Path)
    p.add_argument('--initramfs', type=Path)
    p.add_argument('--append', default='console=ttyAMA0')
    p.add_argument('--root-device', help='Direct boot root selector: /dev/vda, /dev/vda1, UUID=..., PARTUUID=...')
    p.add_argument('--root-fstype', help='Direct boot rootfstype, e.g. ext4 or squashfs')
    p.add_argument('--root-flags', help='Direct boot rootflags; ext4 immutable lower commonly needs noload')
    p.add_argument('--root-mode', choices=('rw', 'ro', 'overlay'), default='rw',
                   help='overlay requires an initramfs implementing Ubuntu overlayroot=tmpfs')
    p.add_argument('--virtio-transport', choices=('pci', 'mmio'), default='pci')
    p.add_argument('--expected-page-size', type=int, choices=(4096, 16384, 65536))
    p.add_argument('--kernel-config', type=Path, help='Save driver/config diagnostics for the supplied kernel')
    p.add_argument('--dump-dtb', action='store_true', help='Save QEMU-generated virt DTB in the run directory')
    p.add_argument('--earlycon', action='store_true', help='Enable DT-described early console and ignore_loglevel')
    p.add_argument('--memory', default='2048')
    p.add_argument('--cpus', type=int, default=2)
    p.add_argument('--cpu', default='cortex-a76')
    p.add_argument('--network', choices=('user', 'none'), default='user')
    p.add_argument('--net-options', default='', help='Additional user-net options, e.g. hostfwd=tcp:127.0.0.1:2222-:22')
    p.add_argument('--serial-log', type=Path)
    p.add_argument('--timeout', type=float, default=900)
    p.add_argument('--shutdown-timeout', type=float, default=90)
    p.add_argument('--disk-size', default='8G', help='Minimum disposable overlay size, or keep; RO modes never resize')
    p.add_argument('--artifacts', type=Path, default=HERE / 'artifacts')
    p.add_argument('--no-provision', action='store_true', help='Boot an OS without injecting Ubuntu cloud-init tests')
    p.add_argument('--accept', action='store_true', help='Require structured guest checks and clean shutdown')
    return p


def kernel_diagnostics(path, config_path=None):
    with path.open('rb') as stream:
        compressed = stream.read(2) == b'\x1f\x8b'
    with (gzip.open(path, 'rb') if compressed else path.open('rb')) as stream:
        header = stream.read(64)
    if len(header) < 64 or header[56:60] != b'ARM\x64':
        raise RuntimeError('Direct boot requires an ARM64 Linux Image (plain or gzip), not a CM5 firmware blob')
    flags = int.from_bytes(header[24:32], 'little')
    result = {'path': str(path), 'sha256': sha256(path), 'gzip': compressed,
              'header_page_size': {0: None, 1: 4096, 2: 16384, 3: 65536}[(flags >> 1) & 3]}
    if config_path:
        text = config_path.read_text()
        names = ['ARM64_16K_PAGES', 'ARM64_4K_PAGES', 'ARM_GIC', 'ARM_GIC_V3',
                 'ARM_ARCH_TIMER', 'SERIAL_AMBA_PL011', 'SERIAL_AMBA_PL011_CONSOLE',
                 'PCI', 'PCI_HOST_GENERIC', 'VIRTIO', 'VIRTIO_PCI', 'VIRTIO_MMIO',
                 'VIRTIO_BLK', 'VIRTIO_NET', 'DEVTMPFS', 'BLK_DEV_INITRD',
                 'EXT4_FS', 'SQUASHFS', 'OVERLAY_FS', 'TMPFS', 'TMPFS_XATTR']
        result['config'] = {name: (re.search(r'^CONFIG_' + name + r'=(.*)$', text, re.M).group(1)
                                   if re.search(r'^CONFIG_' + name + r'=(.*)$', text, re.M) else 'not set')
                            for name in names}
        result['config_sha256'] = sha256(config_path)
    return result


def direct_arguments(args):
    words = shlex.split(args.append)
    original_count = len(words)
    if args.root_device and any(w.startswith('root=') for w in words):
        raise RuntimeError('Specify root once: use --root-device or root= in --append')
    if args.root_device:
        words += ['root=' + args.root_device]
    if sum(w.startswith('root=') for w in words) != 1:
        raise RuntimeError('Direct boot requires exactly one --root-device or root= in --append')
    # Avoid ambiguous last-option-wins behavior for safety-critical root choices.
    if any(w in ('ro', 'rw') or w.startswith('overlayroot=') for w in words):
        raise RuntimeError('Use --root-mode for ro/rw/overlayroot instead of --append')
    words += ['rw' if args.root_mode == 'rw' else 'ro', 'rootwait']
    if args.root_fstype:
        if any(w.startswith('rootfstype=') for w in words):
            raise RuntimeError('Specify rootfstype once')
        words += ['rootfstype=' + args.root_fstype]
    if args.root_flags:
        if any(w.startswith('rootflags=') for w in words):
            raise RuntimeError('Specify rootflags once')
        words += ['rootflags=' + args.root_flags]
    if args.root_mode != 'rw':
        words += ['fsck.mode=skip']
    if args.root_mode == 'overlay':
        words += ['overlayroot=tmpfs:recurse=1', 'overlayroot_cfgdisk=disabled']
    if args.earlycon:
        words += ['earlycon', 'ignore_loglevel']
    return (args.append.strip() + ' ' + ' '.join(words[original_count:])).strip()


def provision(directory, run_id, port, args):
    config = {'run_id': run_id, 'endpoint': f'http://10.0.2.2:{port}',
              'root_mode': args.root_mode, 'expected_page_size': args.expected_page_size}
    test_unit = '''[Unit]
Description=Phase 1 Linux functional checks
After=network-online.target cloud-final.service
Wants=network-online.target
[Service]
Type=oneshot
ExecStart=/usr/bin/python3 /usr/local/lib/phase1-test.py
RemainAfterExit=yes
StandardOutput=journal+console
StandardError=journal+console
TimeoutStartSec=180
'''
    report_unit = '''[Unit]
Description=Phase 1 boot acceptance report
Wants=phase1-test.service
After=phase1-test.service multi-user.target cloud-final.service
[Service]
Type=oneshot
ExecStart=/usr/bin/python3 /usr/local/lib/phase1-test.py --report
StandardOutput=journal+console
StandardError=journal+console
TimeoutStartSec=180
'''
    files = [('/usr/local/lib/phase1-test.py', (HERE / 'guest-test.py').read_text()),
             ('/etc/phase1-config.json', json.dumps(config)),
             ('/etc/systemd/system/phase1-test.service', test_unit),
             ('/etc/systemd/system/phase1-report.service', report_unit)]
    # JSON is a YAML subset; cloud-init accepts this after the cloud-config header.
    data = {'users': [], 'disable_root': True, 'ssh_pwauth': False,
            'ssh_genkeytypes': ['ed25519'], 'package_update': False, 'package_upgrade': False,
            'write_files': [{'path': path, 'permissions': '0644', 'content': content} for path, content in files],
            'runcmd': [['systemctl', 'daemon-reload'],
                       ['systemctl', 'set-default', 'multi-user.target'],
                       ['systemctl', 'start', '--no-block', 'phase1-report.service']]}
    (directory / 'user-data').write_text('#cloud-config\n' + json.dumps(data, indent=2) + '\n')
    (directory / 'meta-data').write_text(json.dumps({'instance-id': run_id, 'local-hostname': 'cm5-phase1'}) + '\n')
    (directory / 'network-config').write_text(json.dumps({'version': 2, 'ethernets': {'virtio': {
        'match': {'macaddress': '52:54:00:12:34:56'}, 'dhcp4': True, 'dhcp6': False}}}) + '\n')
    run('cloud-localds', '--network-config=' + str(directory / 'network-config'),
        directory / 'seed.img', directory / 'user-data', directory / 'meta-data')


def main():
    args = parser().parse_args()
    if args.accept and (args.no_provision or args.network != 'user'):
        parser().error('--accept requires provisioning and --network user')
    if args.initramfs and not args.kernel:
        parser().error('--initramfs requires --kernel')
    if not args.kernel and (args.root_device or args.root_fstype or args.root_flags or
                            args.root_mode != 'rw' or args.earlycon or args.kernel_config or
                            args.append != 'console=ttyAMA0'):
        parser().error('Root controls, earlycon and kernel-config require direct --kernel boot')
    if args.root_mode == 'overlay' and not args.initramfs:
        parser().error('--root-mode overlay requires an initramfs with overlayroot support')
    if args.root_mode == 'ro' and not args.no_provision:
        parser().error('Pure read-only root requires --no-provision; cloud-init needs writes. Use overlay for Ubuntu acceptance')
    if args.cpus < 1 or args.timeout <= 0 or args.shutdown_timeout <= 0:
        parser().error('CPU count and timeouts must be positive')
    size_match = re.fullmatch(r'([1-9][0-9]*)([KMGT]?)', args.disk_size.upper())
    if not size_match and args.disk_size != 'keep':
        parser().error('--disk-size must be a positive integer with optional K, M, G or T suffix')
    minimum_size = (int(size_match[1]) * 1024 ** (' KMGT'.index(size_match[2]) if size_match[2] else 0)) if size_match else 0
    run_id = str(uuid.uuid4())
    directory = args.artifacts.resolve() / (time.strftime('%Y%m%d-%H%M%S') + '-' + run_id[:8])
    directory.mkdir(parents=True, exist_ok=False)
    serial = args.serial_log.resolve() if args.serial_log else directory / 'serial.log'
    serial.parent.mkdir(parents=True, exist_ok=True)
    summary = {'schema': 1, 'run_id': run_id, 'status': 'FAIL_INFRASTRUCTURE', 'artifacts': str(directory)}
    server = None
    process = None
    image = None
    original_hash = None
    received = []
    event = threading.Event()
    try:
        image = args.disk.expanduser().resolve(strict=True)
        original_hash = sha256(image)
        summary.update({'image': str(image), 'image_sha256_before': original_hash})
        summary['boot_mode'] = 'direct' if args.kernel else 'uefi'
        summary['root_mode'] = args.root_mode
        if args.kernel:
            summary['kernel'] = kernel_diagnostics(args.kernel.resolve(strict=True), args.kernel_config)
            if args.expected_page_size and summary['kernel']['header_page_size'] != args.expected_page_size:
                raise RuntimeError('Kernel Image header page size does not match --expected-page-size')
            summary['boot_arguments'] = direct_arguments(args)
            if args.initramfs:
                summary['initramfs'] = {'path': str(args.initramfs.resolve(strict=True)), 'sha256': sha256(args.initramfs)}
                if args.root_mode == 'overlay' and not shutil.which('lsinitramfs'):
                    raise RuntimeError('Overlay preflight requires lsinitramfs; install initramfs-tools-core')
                if shutil.which('lsinitramfs'):
                    listing = run('lsinitramfs', args.initramfs)
                    (directory / 'initramfs-files.txt').write_text(listing)
                    if args.root_mode == 'overlay' and 'scripts/init-bottom/overlayroot' not in listing:
                        raise RuntimeError('Initramfs lacks Ubuntu overlayroot hook; adapt the laboratory initramfs before using this mode')
        for executable in (args.qemu, args.qemu_img):
            if not os.access(executable, os.X_OK):
                raise RuntimeError(f'Missing executable {executable}; run ./build.sh')
        info = json.loads(run(args.qemu_img, 'info', '--output=json', image))
        if info.get('backing-filename'):
            raise RuntimeError('Base image must be standalone so its preservation hash covers all guest data')
        overlay = directory / 'disk.qcow2'
        run(args.qemu_img, 'create', '-f', 'qcow2', '-F', info['format'], '-b', image, overlay)
        summary['source_virtual_size'] = info['virtual-size']
        if info['virtual-size'] < minimum_size and args.root_mode == 'rw':
            run(args.qemu_img, 'resize', overlay, args.disk_size)

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path != '/probe/' + run_id:
                    self.send_error(404)
                    return
                self.send_response(200)
                self.end_headers()
                self.wfile.write(PROBE)

            def do_POST(self):
                if self.path != '/result/' + run_id:
                    self.send_error(404)
                    return
                try:
                    size = int(self.headers.get('Content-Length', '0'))
                    if not 0 < size <= 1024 * 1024:
                        raise ValueError('invalid payload length')
                    result = json.loads(self.rfile.read(size))
                    if result.get('run_id') != run_id or type(result.get('pass')) is not bool:
                        raise ValueError('invalid result envelope')
                    received.append(result)
                    (directory / 'guest-result.json').write_text(json.dumps(result, indent=2) + '\n')
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b'OK\n')
                    event.set()
                except (ValueError, OSError) as exc:
                    self.send_error(400, str(exc))

            def log_message(self, fmt, *values):
                with (directory / 'http.log').open('a') as stream:
                    stream.write(fmt % values + '\n')

        if not args.no_provision:
            server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
            server.daemon_threads = True
            threading.Thread(target=server.serve_forever, daemon=True).start()
            if not shutil.which('cloud-localds'):
                raise RuntimeError('cloud-localds missing; install cloud-image-utils')
            provision(directory, run_id, server.server_port, args)
        block_device = 'virtio-blk-pci' if args.virtio_transport == 'pci' else 'virtio-blk-device'
        net_device = 'virtio-net-pci' if args.virtio_transport == 'pci' else 'virtio-net-device'
        rng_device = 'virtio-rng-pci' if args.virtio_transport == 'pci' else 'virtio-rng-device'
        readonly = ',readonly=on' if args.root_mode != 'rw' else ''
        command = [str(args.qemu.resolve()), '-machine', 'virt', '-cpu', args.cpu,
                   '-accel', 'tcg,thread=multi', '-smp', str(args.cpus), '-m', args.memory,
                   '-display', 'none', '-monitor', 'none', '-serial', 'stdio', '-no-reboot',
                   '-drive', f'if=none,id=osdisk,format=qcow2,file={overlay}{readonly}',
                   '-device', block_device + ',drive=osdisk', '-device', rng_device]
        if args.kernel:
            command += ['-kernel', str(args.kernel.resolve(strict=True)), '-append', summary['boot_arguments']]
            if args.initramfs:
                command += ['-initrd', str(args.initramfs.resolve(strict=True))]
        else:
            code = args.firmware_code.resolve(strict=True)
            var_template = args.firmware_vars.resolve(strict=True)
            var_copy = directory / 'AAVMF_VARS.fd'
            shutil.copyfile(var_template, var_copy)
            command += ['-drive', f'if=pflash,format=raw,unit=0,readonly=on,file={code}',
                        '-drive', f'if=pflash,format=raw,unit=1,file={var_copy}']
            summary['firmware'] = {'code': str(code), 'code_sha256': sha256(code),
                                   'vars_template': str(var_template), 'vars_sha256': sha256(var_template)}
        if not args.no_provision:
            command += ['-drive', f'if=none,id=seed,format=raw,readonly=on,file={directory / "seed.img"}',
                        '-device', block_device + ',drive=seed']
        if args.network == 'user':
            net = 'user,id=net0' + (',' + args.net_options if args.net_options else '')
            command += ['-netdev', net, '-device', net_device + ',netdev=net0,mac=52:54:00:12:34:56']
        else:
            command += ['-nic', 'none']
        summary['qemu_version'] = run(args.qemu, '--version').splitlines()[0]
        summary['source_commit'] = run('git', '-C', REPO, 'rev-parse', 'HEAD').strip()
        summary['command'] = command
        (directory / 'command.json').write_text(json.dumps(command, indent=2) + '\n')
        if args.dump_dtb:
            dump_command = command.copy()
            dump_command[dump_command.index('-machine') + 1] = 'virt,dumpdtb=' + str(directory / 'virt.dtb')
            (directory / 'dtb-dump.log').write_text(run(*dump_command))
        print(f'Artifacts: {directory}\nSerial: {serial}', flush=True)
        started = time.monotonic()
        deadline = started + args.timeout
        report_time = None
        with serial.open('xb') as output:
            process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT)
            while process.poll() is None and time.monotonic() < deadline:
                if event.wait(0.5) and report_time is None:
                    report_time = time.monotonic()
                    deadline = report_time + args.shutdown_timeout
                if event.is_set():
                    time.sleep(0.1)
        summary['elapsed_seconds'] = round(time.monotonic() - started, 2)
        summary['qemu_returncode'] = process.poll()
        serial_text = serial.read_text(errors='replace')
        summary['guest_poweroff_seen'] = 'reboot: Power down' in serial_text
        if process.poll() is None:
            summary.update(status='FAIL_BOOT', reason='shutdown timeout' if received else 'boot timeout; no guest report')
        elif process.returncode != 0:
            summary.update(status='FAIL_INFRASTRUCTURE', reason=f'QEMU exited {process.returncode}; inspect serial.log')
        elif received:
            result = received[-1]
            expected = {'filesystem', 'shared_libraries', 'cpu', 'memory', 'network', 'root_contract'}
            checks = result.get('checks', {})
            passed = (result['pass'] and result.get('pid1') == 'systemd' and
                      result.get('pid1_executable', '').endswith('/systemd') and
                      result.get('target') == 'active' and result.get('failed_units') == '' and
                      result.get('cloud_init_status', {}).get('status') == 'done' and
                      result.get('cloud_init_schema_valid') is True and
                      (not args.expected_page_size or result.get('page_size') == args.expected_page_size) and
                      summary['guest_poweroff_seen'] and
                      set(checks) == expected and all(v.get('pass') is True for v in checks.values()) and
                      set(result.get('service', '').splitlines()) == {'Result=success', 'ExecMainStatus=0'})
            summary.update(status='PASS' if passed else 'FAIL_GUEST', reason='guest report and QEMU shutdown received')
        elif args.no_provision and not args.accept:
            summary.update(status='STOPPED', reason='guest exited; acceptance not requested')
        else:
            summary.update(status='FAIL_BOOT', reason='guest exited without an acceptance report')
        # A serial result without HTTP delivery indicates a reporting/infrastructure problem.
        if not received and 'PHASE1_RESULT ' in serial_text:
            summary.update(status='FAIL_INFRASTRUCTURE', reason='guest emitted serial result but HTTP delivery failed; inspect serial.log')
        signatures = {'kernel_panic': 'Kernel panic', 'missing_root': 'does not exist.  Dropping to a shell',
                      'mount_failure': 'Unable to mount root', 'emergency_mode': 'emergency mode',
                      'overlay_setup': 'overlayroot:', 'systemd_seen': 'systemd['}
        summary['serial_diagnostics'] = {name: token in serial_text for name, token in signatures.items()}
        (directory / 'diagnostics.json').write_text(json.dumps(summary, indent=2) + '\n')
    except (OSError, RuntimeError, subprocess.CalledProcessError, ValueError) as exc:
        summary.update(status='FAIL_INFRASTRUCTURE', reason=str(exc))
        if isinstance(exc, subprocess.CalledProcessError):
            summary['tool_output'] = exc.output
    except KeyboardInterrupt:
        summary.update(status='FAIL_INFRASTRUCTURE', reason='interrupted by operator')
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
        if image and original_hash:
            summary['image_sha256_after'] = sha256(image)
            if summary['image_sha256_after'] != original_hash:
                summary.update(status='FAIL_INFRASTRUCTURE', reason='original image hash changed')
        summary['serial_log'] = str(serial)
        (directory / 'acceptance.json').write_text(json.dumps(summary, indent=2) + '\n')
        print(json.dumps(summary, indent=2), flush=True)
    return 0 if summary['status'] in ('PASS', 'STOPPED') else (1 if summary['status'] in ('FAIL_BOOT', 'FAIL_GUEST') else 2)


if __name__ == '__main__':
    sys.exit(main())
