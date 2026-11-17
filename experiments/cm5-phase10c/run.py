#!/usr/bin/env python3
"""Bounded observed physical-kernel run; diagnostic copies are explicit."""
import argparse
import base64
import hashlib
import zlib
import json
import os
from pathlib import Path
import re
import selectors
import shlex
import select
import socket
import subprocess
import sys
import time


class HostTimeline:
    """Private diagnostic host offsets; never interpreted as guest time."""
    def __init__(self, path, clock=None):
        self.path = path
        self.clock = clock or time.monotonic
        self.start = self.clock()
        self.seen = set()

    def mark(self, name, **fields):
        if name in self.seen:
            return
        self.seen.add(name)
        with self.path.open('a') as stream:
            stream.write(json.dumps(dict(event=name, host_seconds=self.clock()-self.start,
                                         clock='host-monotonic', **fields))+'\n')

    def console(self, text):
        for name, marker in (
                ('kernel_entry', 'Linux version 6.18.50'),
                ('initramfs_entry', 'Run /init as init process'),
                ('verified_root_mount', 'mounted filesystem a3680812-'),
                ('systemd_entry', 'systemd 257.'),
                ('upload_verified', 'P10J_UPLOAD_VERIFIED'),
                ('fsw_start', 'P10K_FSW_START='),
                ('power_down', 'reboot: Power down')):
            if marker in text:
                self.mark(name)

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO/'experiments/cm5-phase10a'))
from preboot import identity
from diagnostic import build


class PipeEndpoint:
    """Local FIFO chardev endpoint; no socket syscalls or listener."""
    def __init__(self, path):
        self.path = path
        for suffix in ('.in','.out'):
            os.mkfifo(str(path)+suffix, 0o600)
        self.writer = os.open(str(path)+'.in', os.O_RDWR | os.O_NONBLOCK)
        self.reader = os.open(str(path)+'.out', os.O_RDWR | os.O_NONBLOCK)
        self.timeout = 0
    def settimeout(self, seconds): self.timeout = seconds
    def setblocking(self, blocking): self.timeout = None if blocking else 0
    def recv(self, size):
        ready,_,_ = select.select([self.reader],[],[],self.timeout)
        if not ready:
            if self.timeout == 0: raise BlockingIOError()
            raise OSError('control pipe timeout')
        return os.read(self.reader,size)
    def sendall(self, data):
        while data:
            _,ready,_ = select.select([],[self.writer],[],2)
            if not ready: raise OSError('control pipe write timeout')
            n = os.write(self.writer,data)
            data = data[n:]
    def close(self):
        os.close(self.reader);os.close(self.writer)


class QMP:
    def __init__(self, path=None, sock=None):
        self.sock = sock or socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(2)
        if sock is None:
            self.sock.connect(str(path))
        self.pending = b''
        self.receive()
        self.command('qmp_capabilities')

    def receive(self):
        while True:
            while b'\n' not in self.pending:
                part = self.sock.recv(65536)
                if not part: raise OSError('QMP closed')
                self.pending += part
            line,self.pending = self.pending.split(b'\n',1)
            message = json.loads(line)
            if 'event' not in message:
                return message

    def command(self, name, arguments=None):
        self.sock.sendall(json.dumps(dict(execute=name, arguments=arguments or {})).encode()+b'\n')
        return self.receive()


def observer_upload(code, remote='/run/cm5-observer.py'):
    """Public observer only; remote destination is disposable guest tmpfs."""
    if 'P10C' in code.splitlines():
        raise ValueError('observer collides with here-document delimiter')
    path = shlex.quote(remote)
    return ('set +o emacs; set +o vi; stty -echo\n'
            "cat > "+path+" <<'P10C'\n"+code+'\nP10C\n').encode()


def observer_invoke(remote='/run/cm5-observer.py'):
    # With echo disabled, PS1 and program output otherwise share a line.
    return ("printf '\\n'; python3 "+shlex.quote(remote)+'\n').encode()



def workload_upload(code, remote='/run/cm5-fsw-launch.py'):
    """One canonical-TTY line in flight; guest ACK prevents input queue overrun."""
    data = code.encode()
    packed = zlib.compress(data)
    encoded = base64.b64encode(packed).decode()
    frames = [(encoded[i:i+2048]+'\n').encode() for i in range(0, len(encoded), 2048)]
    receiver = f"""import base64,hashlib,json,os,sys,zlib
try:
 data=bytearray()
 print(flush=True)
 print('P10J_UPLOAD_ACK=0',flush=True)
 for index in range({len(frames)}):
  line=sys.stdin.buffer.readline(4096)
  if not line.endswith(b'\\n'): raise RuntimeError('incomplete upload frame')
  data.extend(base64.b64decode(line.strip(),validate=True))
  print('P10J_UPLOAD_ACK='+str(index+1),flush=True)
 if len(data)!={len(packed)} or hashlib.sha256(data).hexdigest()!={hashlib.sha256(packed).hexdigest()!r}: raise RuntimeError('compressed upload digest mismatch')
 code=zlib.decompress(data)
 if hashlib.sha256(code).hexdigest()!={hashlib.sha256(data).hexdigest()!r}: raise RuntimeError('launcher digest mismatch')
 with open({remote!r},'wb') as stream: stream.write(code)
 print('P10J_UPLOAD_VERIFIED',flush=True)
 os.execv(sys.executable,[sys.executable,{remote!r}])
except Exception as exc:
 print('P10J_RESULT='+json.dumps(dict(status='ERROR',error='upload: '+repr(exc))),flush=True)
"""
    # repr keeps the bootstrap on one short shell input line.
    bootstrap = 'python3 -u -c '+shlex.quote('exec('+repr(receiver)+')')+'\n'
    if len(bootstrap.encode()) >= 3000:
        raise ValueError('upload bootstrap exceeds conservative canonical line bound')
    return bootstrap.encode(), frames



def workload_result(console):
    # Nested braces may arrive before the end of a long JSON string. Only a
    # newline proves the complete record has arrived over the serial stream.
    records = re.findall(r'(?:^|[\r\n])P10J_RESULT=(\{[^\r\n]+\})[\r\n]', console)
    return json.loads(records[-1]) if records else None


def upload_acknowledged(console, frame_index):
    # Do not consume the final delimiter: adjacent LF-only records share it.
    records = re.findall(r'(?:^|[\r\n])P10J_UPLOAD_ACK=(\d+)(?=[\r\n])', console)
    return bool(records and int(records[-1]) == frame_index)


def wait_console(selector, debug, timeout):
    """Wake for debug ACKs without changing the main-stream EOF lifecycle.

    The debug endpoint is temporary in the selector: FIFO endpoints remain
    open locally even after QEMU exits. Only the main stream owns run lifetime.
    The caller drains debug at the top of its loop, including fragmented ACKs.
    """
    if debug is None:
        return selector.select(timeout)
    reader = debug.reader if isinstance(debug, PipeEndpoint) else debug
    selector.register(reader, selectors.EVENT_READ, data='debug-wakeup')
    try:
        return [(key, flags) for key, flags in selector.select(timeout)
                if key.data != 'debug-wakeup']
    finally:
        selector.unregister(reader)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--phase10i-gpio-lab', action='store_true',
                   help='opt-in bounded native RP1 GPIO20/21 model, DT and driver test')
    p.add_argument('--phase10h-smp-stress', action='store_true',
                   help='opt-in bounded guest CPU1/2/3 and read-only BAR load during native SPI')
    p.add_argument('--observer-upload-once', action='store_true',
                   help='cache observer in guest /run; disable terminal line editing/echo and await each result')
    p.add_argument('--execution-clock', choices=('host','icount-1ns','icount-adaptive'), default='host',
                   help='explicit experimental CPU timebase; icount is not physical cycle calibration')
    p.add_argument('--control-pipes', action='store_true', help='local FIFO chardevs; no socket syscalls required')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--diagnostic', action='store_true')
    p.add_argument('--dma', action='store_true')
    p.add_argument('--batch', action='store_true')
    p.add_argument('--debug-shell', action='store_true')
    p.add_argument('--poweroff-after-validation', action='store_true')
    p.add_argument('--profile', choices=('gpex', 'native'), default='gpex')
    p.add_argument('--timeout', type=int, default=180)
    p.add_argument('--native-rp1-test', action='store_true',
                   help='Phase10E synthetic SPI slave and guest native-path observer')
    p.add_argument('--native-spi-hz', type=int, choices=(10000, 100000, 1000000),
                   default=10000, help='explicit synthetic SPI workload rate')
    p.add_argument('--native-spi-diagnostics', action='store_true',
                   help='bounded first-event FIFO/shifter/timer diagnostics')
    p.add_argument('--recovery-case', choices=('clean', 'os0', 'os-far', 'fsw0', 'no-fec'),
                   help='opt-in Phase10D overlay campaign; default Phase10C is unchanged')
    p.add_argument('--boot-selection-policy', choices=('emmc-only', 'eeprom-fixture-0xf14'),
                   help='Phase10F: select exclusively from this run overlay; fail before guest launch')
    p.add_argument('--boot-expected', type=Path,
                   help='Phase10F: pre-existing private filename-to-SHA256 lab baseline')
    p.add_argument('--boot-config-profile', choices=('cm5-headless-lab',))
    p.add_argument('--boot-overlay', type=Path,
                   help='Phase10F: use this exact disposable private QCOW2, exclusively owned by this run')
    p.add_argument('--lab-root', type=Path, default=Path('/home/aweso/cm5-v8-lab/phase10c'))
    p.add_argument('--golden', type=Path, default=Path('/home/aweso/cm5-v8-lab/golden/cm5-emmc-userarea.img'))
    p.add_argument('--phase10j-workload', type=Path, help='private generated guest workload; local experiments only')
    p.add_argument('--boot-profile', choices=('strict', 'operational'), default='strict')
    p.add_argument('--operational-initramfs', type=Path)
    p.add_argument('--execution-mode', choices=('ram-staged','verified-fsw-partition'), default='ram-staged')
    p.add_argument('--sealed-generation', type=Path)
    p.add_argument('--generation-sha256')
    a = p.parse_args()
    direct = a.execution_mode == 'verified-fsw-partition'
    if direct and (not a.sealed_generation or not a.generation_sha256 or a.boot_profile != 'operational'):
        p.error('Direct execution requires a pinned sealed operational generation')
    if not direct and (a.sealed_generation or a.generation_sha256):
        p.error('Sealed-generation arguments require verified-fsw-partition mode')
    if (a.boot_profile == 'operational') != (a.operational_initramfs is not None):
        p.error('operational requires an explicit derivative; strict forbids substitutions')
    if a.boot_profile == 'operational' and not a.phase10j_workload:
        p.error('Phase10L operational profile requires the guarded Phase10J experiment')
    if a.phase10j_workload and not (a.boot_overlay and a.boot_expected and a.debug_shell
            and a.observer_upload_once and a.poweroff_after_validation
            and not a.recovery_case and not a.native_rp1_test and not a.phase10i_gpio_lab):
        p.error('Phase10J requires selected overlay, manifest, debug shell, upload-once, poweroff; no recovery or synthetic stimulus')
    if a.phase10i_gpio_lab and (not a.native_rp1_test or a.profile != 'native' or a.phase10h_smp_stress):
        p.error('Phase10I GPIO lab requires native RP1 profile without SMP stress')
    if a.phase10h_smp_stress and not a.native_rp1_test:
        p.error('Phase10H SMP stress requires --native-rp1-test')
    if a.boot_overlay and (not a.boot_selection_policy or a.recovery_case not in (None, 'clean')):
        p.error('--boot-overlay requires BOOT selection and allows only clean recovery-case setup')
    if a.boot_config_profile and not a.boot_selection_policy:
        p.error('--boot-config-profile requires BOOT selection')
    if a.boot_expected and not a.boot_selection_policy:
        p.error('--boot-expected requires --boot-selection-policy')
    if a.boot_selection_policy and (a.diagnostic or a.recovery_case not in (None, 'clean')):
        p.error('BOOT-selected launch forbids diagnostic/no-FEC initramfs replacement and recovery faults')
    native_test = None
    if a.native_rp1_test:
        if a.profile != 'native' or a.recovery_case != 'clean':
            p.error('native RP1 test requires native profile and clean recovery case')
        sys.path.insert(0, str(REPO/'experiments/cm5-phase10e'))
        import native_profile as native_test
    recovery = None
    if a.recovery_case:
        if a.diagnostic or not (a.dma and a.batch and a.debug_shell and a.poweroff_after_validation):
            p.error('recovery cases require DMA, batch, debug-shell and poweroff; no --diagnostic')
        sys.path.insert(0, str(REPO/'experiments/cm5-phase10d'))
        import campaign as recovery
    os.umask(0o077)
    out = a.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    timeline = HostTimeline(out/'host-timeline.jsonl')
    timeline.mark('runner_setup_start')
    lab = a.lab_root.resolve()/out.name
    lab.mkdir(parents=True, exist_ok=False)
    assets = Path('/home/aweso/cm5-phase10-private/physical-boot/boot-assets')
    golden = a.golden.resolve()
    if a.boot_overlay:
        sys.path.insert(0, str(REPO/'experiments/cm5-phase10f'))
        import handoff
        input_files = [Path(node['identity']['path']) for node in handoff.chain(a.boot_overlay)[1:]]
    elif a.boot_selection_policy:
        input_files = [golden]
    else:
        input_files = [*assets.iterdir(), golden]
    timeline.mark('input_identity_start')
    inputs = {str(f): identity(f) for f in input_files if f.is_file()}
    sealed = None
    if direct:
        sys.path.insert(0, str(REPO/'experiments/cm5-phase10m'))
        import generation as sealed_policy
        sealed = sealed_policy.load(a.sealed_generation, a.generation_sha256, verify_image=False)
        base = sealed_policy.artifact(sealed,'image').resolve()
        if set(inputs) != {str(base)} or inputs[str(base)]['sha256'] != sealed['artifacts']['image']['sha256']:
            raise RuntimeError('Overlay backing image is not the pinned sealed generation')
        if identity(a.boot_expected)['sha256'] != sealed['artifacts']['boot_manifest']['sha256']:
            raise RuntimeError('BOOT manifest belongs to a different generation')
    timeline.mark('input_identity_end')
    (out/'inputs-before.json').write_text(json.dumps(inputs, indent=2)+'\n')
    initrd = assets/'initramfs_2712-osverified-v8'
    if a.diagnostic:
        initrd = lab/'diagnostic/initrd'
        (out/'diagnostic-provenance.json').write_text(json.dumps(build(initrd), indent=2)+'\n')
    overlay = a.boot_overlay.resolve() if a.boot_overlay else lab/'emmc.qcow2'
    if a.boot_overlay:
        if overlay.is_relative_to(REPO):
            p.error('BOOT overlay must remain outside the repository')
    else:
        subprocess.run([str(REPO/'build-arm64-phase1/qemu-img'), 'create', '-f', 'qcow2',
                        '-F', 'raw', '-b', str(golden), str(overlay)], check=True, capture_output=True)
    if recovery:
        fault = recovery.prepare(a.recovery_case, out, lab, golden, overlay)
        if a.recovery_case == 'no-fec':
            initrd = recovery.no_fec_initramfs(out, lab, initrd)
    boot_selection = None
    kernel = assets/'kernel_2712.img'
    if a.boot_selection_policy:
        timeline.mark('boot_selection_start')
        sys.path.insert(0, str(REPO/'experiments/cm5-phase10f'))
        import handoff
        selection_work = lab/'boot-selection'
        selection_work.mkdir(mode=0o700)
        source_snapshot = lab/'boot-harness-sources'
        source_snapshot.mkdir(mode=0o700)
        for phase in ('10a','10c','10d','10e','10f','10f1','10f2','10l','10m'):
            for source in (REPO/('experiments/cm5-phase'+phase)).glob('*.py'):
                (source_snapshot/(phase+'-'+source.name)).write_bytes(source.read_bytes())
        expected = json.loads(a.boot_expected.read_text()) if a.boot_expected else None
        if a.boot_selection_policy == 'eeprom-fixture-0xf14':
            sys.path.insert(0, str(REPO/'experiments/cm5-phase10f2'))
            import boot_policy
            boot_selection, selected_buffers = boot_policy.select(
                overlay, selection_work, expected, config_profile=a.boot_config_profile)
        else:
            boot_selection, selected_buffers = handoff.select(
                overlay, selection_work, expected, a.boot_selection_policy, config_profile=a.boot_config_profile)
        handoff.write_report(selection_work/'selection.json', boot_selection)
        timeline.mark('boot_acceptance_end')
        # Public evidence records metadata only. Selected content stays private.
        (out/'boot-selection-location.json').write_text(json.dumps(dict(
            report=str(selection_work/'selection.json')), indent=2)+'\n')
        if boot_selection['status'] != 'SELECTED':
            (out/'result.json').write_text(json.dumps(dict(
                status='BOOT_SELECTION_STOPPED', selection_status=boot_selection['status'],
                reason=boot_selection.get('reason'), process=dict(launched=False),
                private_report=str(selection_work/'selection.json')), indent=2)+'\n')
            return 1
        handoff.export(boot_selection, selected_buffers, selection_work/'exports')
        timeline.mark('boot_export_end')
        handoff.write_report(selection_work/'selection.json', boot_selection)
        kernel = Path(boot_selection['exports']['kernel']['path'])
        initrd = Path(boot_selection['exports']['initramfs']['path'])
    machine = 'cm5io-dev,native-emmc=on,native-mip=on'
    if a.dma:
        machine += ',emmc-dma=on'
    if a.profile == 'native':
        machine += ',native-pcie=on'
    if a.phase10i_gpio_lab:
        machine += ',rp1-gpio-lab=on'
    cmdline_input = (Path(boot_selection['exports']['cmdline']['path']) if boot_selection
                     else assets/'cmdline_2712-osverified-v8.txt')
    cmdline = cmdline_input.read_text().strip()
    selected_cmdline = cmdline
    operational_policy = None
    if a.boot_profile == 'operational':
        sys.path.insert(0, str(REPO/'experiments/cm5-phase10l'))
        import lab_profile
        if direct:
            if a.operational_initramfs.resolve() != sealed_policy.artifact(sealed,'initramfs').resolve():
                raise RuntimeError('Mixed sealed initramfs path')
            operational_policy = sealed_policy.approve(initrd.read_bytes(),
                lab_profile.regular_bytes(a.operational_initramfs),sealed,
                boot_selection['exports']['kernel']['sha256'])
        else:
            operational_policy = lab_profile.approve(
                initrd.read_bytes(), lab_profile.regular_bytes(a.operational_initramfs),
                boot_selection['exports']['kernel']['sha256'])
        initrd = a.operational_initramfs.resolve()
        operational_policy['effective_identity'] = identity(initrd)
        cmdline += ' '+lab_profile.PARAMETER
        (out/'operational-policy.json').write_text(json.dumps(operational_policy, indent=2)+'\n')
    cmdline += ' console=ttyAMA0,115200 earlycon=pl011,mmio32,0x107d001000 ignore_loglevel'
    if a.debug_shell:
        cmdline += ' systemd.debug_shell=ttyAMA1'
    cmd = [str(REPO/'build-arm64-phase1/qemu-system-aarch64'), '-M', machine,
        '-cpu', 'cortex-a76', '-accel', 'tcg', '-smp', '4', '-m', '2048',
        '-display', 'none', '-monitor', 'none', '-serial', 'stdio', '-nic', 'none',
        '-qmp', f'unix:{lab}/qmp.sock,server=on,wait=off', '-no-reboot',
        '-kernel', str(kernel), '-initrd', str(initrd), '-append', cmdline,
        '-drive', f'file={overlay},format=qcow2,if=none,id=native',
        '-device', 'emmc,drive=native,boot-partition-size=0,rpmb-partition-size=0' +
                   (',x-cmd23-read-batch=on' if a.batch else ''),
        '-d', 'unimp,guest_errors', '-D', str(out/'hardware.log')]
    if a.execution_clock != 'host':
        cmd[cmd.index('-accel')+1] = 'tcg,thread=single'
        clock_options = ('shift=0,align=off,sleep=off' if a.execution_clock == 'icount-1ns'
                         else 'shift=auto,align=off,sleep=on')
        cmd += ['-icount', clock_options]
    command_record = lab/'command.json' if boot_selection else out/'command.json'
    command_record.write_text(json.dumps(cmd, indent=2)+'\n')
    if a.debug_shell:
        cmd += ['-serial', f'unix:{lab}/debug.sock,server=on,wait=off']
        command_record.write_text(json.dumps(cmd, indent=2)+'\n')
    if native_test:
        cmd += native_test.qemu_arguments(a.native_spi_diagnostics)
        command_record.write_text(json.dumps(cmd, indent=2)+'\n')
    if a.phase10i_gpio_lab:
        cmd += ['-trace', 'enable=rp1_gpio_irq', '-trace', 'enable=rp1_gpio_access']
        command_record.write_text(json.dumps(cmd, indent=2)+'\n')
    executable = identity(REPO/'build-arm64-phase1/qemu-system-aarch64')
    if recovery:
        (out/'harness-sources.json').write_text(json.dumps({str(f): identity(f) for f in
            [Path(__file__), Path(recovery.__file__), REPO/'experiments/cm5-phase10d/observe.py',
             REPO/'experiments/cm5-phase10c/observe.py']}, indent=2)+'\n')
    if boot_selection:
        # Last gate before opening the same overlay for the actual guest.
        handoff.verify_launch(boot_selection, overlay)
        if operational_policy and identity(initrd) != operational_policy['effective_identity']:
            raise RuntimeError('Operational derivative changed before launch')
        boot_selection['launch'] = dict(command_record=str(command_record), kernel=str(kernel), initramfs=str(initrd),
            overlay=str(overlay), cmdline_input_sha256=boot_selection['exports']['cmdline']['sha256'],
            lab_cmdline_append=cmdline[len(selected_cmdline):],
            lab_cmdline_normalization='strip surrounding ASCII whitespace before appending lab arguments',
            effective_cmdline_sha256=handoff.sha(cmdline.encode()),
            dt_substitution=boot_selection['dt_handoff'])
        boot_selection['launch'].update(boot_profile=a.boot_profile, operational_policy=operational_policy)
        handoff.write_report(selection_work/'selection.json', boot_selection)
    qmp_parent = debug_parent = None
    if a.control_pipes:
        qmp_parent = PipeEndpoint(lab/'qmp-pipe')
        i = cmd.index('-qmp')
        cmd[i:i+2] = ['-chardev', f'pipe,id=qmp,path={lab}/qmp-pipe', '-qmp', 'chardev:qmp']
        if a.debug_shell:
            debug_parent = PipeEndpoint(lab/'debug-pipe')
            i = cmd.index(f'unix:{lab}/debug.sock,server=on,wait=off')
            cmd[i] = 'chardev:debug'
            cmd += ['-chardev', f'pipe,id=debug,path={lab}/debug-pipe']
        command_record.write_text(json.dumps(cmd, indent=2)+'\n')
    timeline.mark('qemu_launch')
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if boot_selection:
        boot_selection['process'] = dict(launched=True, pid=proc.pid)
        handoff.write_report(selection_work/'selection.json', boot_selection)
    (out/'process.json').write_text(json.dumps(dict(pid=proc.pid, executable=executable), indent=2)+'\n')
    start, last = time.monotonic(), -10
    sel = selectors.DefaultSelector()
    sel.register(proc.stdout, selectors.EVENT_READ)
    observer_uploaded = observer_running = False
    observer_results = 0
    qmp = None
    trace_on = False
    timed_out = False
    debug = None
    debug_data = ''
    serial_tail = ''
    last_debug = -30
    shutdown_requested = False
    user_validated = False
    qmp_failed = False
    workload_pending = b''
    workload_frames = []
    workload_frame_index = 0
    workload_started = workload_complete = False
    code = (REPO/'experiments/cm5-phase10c/observe.py').read_text()
    if a.phase10j_workload:
        # No disk writes: staging is tmpfs; do not assume a LOGS partition number.
        code = code[:code.index('payload = bytes(')] + "print('P10C_USER_JSON=' + json.dumps(r, separators=(',', ':')))\n"
        extra = (REPO/'experiments/cm5-phase10l/observe_profile.py').read_text()
        code = code.replace("print('P10C_USER_JSON='", extra+"\nprint('P10C_USER_JSON='")

    if boot_selection:
        extra = (REPO/'experiments/cm5-phase10f1/runtime_observe.py').read_text()
        code = code.replace("print('P10C_USER_JSON='", extra+"\nprint('P10C_USER_JSON='")
        (out/'guest-observer.py').write_text(code)
    if recovery:
        code = recovery.observer(code, fault)
    if native_test:
        code = native_test.observer(code, a.native_spi_hz)
        # Public observer source only, never captured disk/firmware bytes.
        (out/'guest-observer.py').write_text(code)
    if a.phase10h_smp_stress:
        sys.path.insert(0, str(REPO/'experiments/cm5-phase10h'))
        from smp_observer import wrap
        code = wrap(code)
        (out/'guest-observer.py').write_text(code)
    if a.phase10i_gpio_lab:
        sys.path.insert(0, str(REPO/'experiments/cm5-phase10i'))
        import observer as phase10i_observer
        code = phase10i_observer.wrap(code)
        (out/'guest-observer.py').write_text(code)
    try:
        with (out/'serial.log').open('wb') as log:
            while sel.get_map():
                elapsed = time.monotonic()-start
                if elapsed > a.timeout:
                    timed_out = True
                    break
                if qmp is None and not qmp_failed and (qmp_parent is not None or (lab/'qmp.sock').exists()):
                    try:
                        qmp = QMP(lab/'qmp.sock', sock=qmp_parent)
                        qmp_parent = None
                        if a.phase10i_gpio_lab:
                            phase10i_observer.capture_machine(qmp, out)
                    except OSError as error:
                        # A bounded synthetic kernel can power off during negotiation.
                        qmp_failed = True
                        with (out/'observations.jsonl').open('a') as stream:
                            stream.write(json.dumps(dict(qmp_initial_error=str(error)))+'\n')
                if a.debug_shell and debug is None and (debug_parent is not None or (lab/'debug.sock').exists()):
                    debug = debug_parent or socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    if debug_parent is None:
                        debug.connect(str(lab/'debug.sock'))
                    debug_parent = None
                    debug.setblocking(False)
                if debug:
                    try:
                        data = debug.recv(65536)
                    except BlockingIOError:
                        data = b''
                    if data:
                        with (out/'debug-serial.log').open('ab') as stream:
                            stream.write(data)
                            debug_end = stream.tell()
                        with (out/'debug-chunks.jsonl').open('a') as chunks:
                            chunks.write(json.dumps(dict(end_offset=debug_end,
                                host_seconds=time.monotonic()-timeline.start))+'\n')
                        debug_data += data.decode(errors='replace')
                        timeline.console(debug_data)
                    if workload_pending:
                        # Drain output between small writes: canonical tty and FIFO buffers are bounded.
                        _, writable, _ = select.select([], [debug.writer] if isinstance(debug, PipeEndpoint) else [debug], [], 0)
                        if writable:
                            debug.sendall(workload_pending[:512])
                            workload_pending = workload_pending[512:]
                    if workload_frames and not workload_pending:
                        if (upload_acknowledged(debug_data, workload_frame_index)
                                and workload_frame_index < len(workload_frames)):
                            debug.sendall(workload_frames[workload_frame_index])
                            workload_frame_index += 1
                    if a.phase10j_workload and workload_started and not workload_complete:
                        record = workload_result(debug_data)
                        if record is not None:
                            (out/'fsw-result.json').write_text(json.dumps(record, indent=2)+'\n')
                            workload_complete = True
                            timeline.mark('fsw_result_received')
                            debug.sendall(b'systemctl poweroff\n')
                            shutdown_requested = True
                    if ('#' in debug_data and not shutdown_requested and not workload_started and elapsed-last_debug >= 30
                            and not (a.observer_upload_once and observer_running)):
                        last_debug = elapsed
                        # Here-document avoids a canonical tty's single-line limit.
                        if a.observer_upload_once:
                            if not observer_uploaded:
                                # /run is guest tmpfs; original media are untouched.
                                debug.sendall(observer_upload(code))
                                observer_uploaded = True
                            debug.sendall(observer_invoke())
                            observer_running = True
                        else:
                            debug.sendall(('python3 - <<\'P10C\'\n'+code+'\nP10C\n').encode())
                    matches = re.findall(r'(?:^|[\r\n])P10C_USER_JSON=(\{[^\r\n]+\})', debug_data)
                    if matches:
                        records = []
                        for match in matches:
                            try:
                                records.append(json.loads(match))
                            except ValueError:
                                pass
                        if len(records) > observer_results:
                            observer_results = len(records)
                            observer_running = False
                        (out/'userspace.json').write_text(json.dumps(records, indent=2)+'\n')
                        valid = [r for r in records if r.get('pid1') == 'systemd' and
                                 r.get('target') == 'active' and r.get('os_status', '').endswith('verity V') and
                                 r.get('fsw_status', '').endswith('verity V') and
                                 'cm5_os_verified' in r.get('lower', '') and
                                 'cm5_fsw_verified' in r.get('fsw', '') and
                                 'fec_roots 2' in r.get('os_table', '') and
                                 'fec_roots 2' in r.get('fsw_table', '') and
                                 r.get('libc_call') and (r.get('logs_fsync_readback') or a.phase10j_workload)]
                        if a.boot_profile == 'operational':
                            valid = [r for r in valid if
                                r.get('phase10l_boot', {}).get('profile_marker') == 'operational' and
                                'PHASE10L_OPERATIONAL' in (r['phase10l_boot'].get('os_log') or '') and
                                not r['phase10l_boot'].get('scan_dd_log_exists') and
                                'Verified OS full read PASS' not in r['phase10l_boot']['os_log'] and
                                r['lower'].startswith('/dev/mapper/cm5_os_verified ext4 ro,') and
                                r['fsw'].startswith('/dev/mapper/cm5_fsw_verified ext4 ro,')]
                        if direct:
                            valid = [r for r in valid if sealed_policy.maps_match(r,sealed)]
                        user_validated = len(valid) >= 2 and valid[-1].get('uptime', 0) - valid[0].get('uptime', 0) >= 20
                        if user_validated and a.poweroff_after_validation and not shutdown_requested:
                            timeline.mark('userspace_validated')
                            if a.phase10j_workload:
                                if not workload_started:
                                    workload_pending, workload_frames = workload_upload(a.phase10j_workload.read_text())
                                    timeline.mark('upload_start', frames=len(workload_frames),
                                                  bytes=sum(map(len, workload_frames)))
                                    workload_started = True
                            else:
                                debug.sendall(b'systemctl poweroff\n')
                                shutdown_requested = True
                if qmp and elapsed-last >= 10:
                    last = elapsed
                    try:
                        sample = dict(wall_seconds=elapsed, blocks=qmp.command('query-blockstats'),
                                      status=qmp.command('query-status'), host_io=Path(f'/proc/{proc.pid}/io').read_text(),
                                      host_stat=Path(f'/proc/{proc.pid}/stat').read_text(),
                                      host_clk_tck=os.sysconf('SC_CLK_TCK'))
                    except OSError as error:
                        sample = dict(wall_seconds=elapsed, qmp_error=str(error))
                        qmp_failed = True
                        qmp.sock.close()
                        qmp = None
                    with (out/'observations.jsonl').open('a') as f:
                        f.write(json.dumps(sample)+'\n')
                if qmp and 20 <= elapsed < 22 and not trace_on:
                    qmp.command('trace-event-set-state', dict(name='sdcard_read_block', enable=True))
                    qmp.command('trace-event-set-state', dict(name='sdcard_read_batch', enable=True))
                    trace_on = True
                if qmp and elapsed >= 22 and trace_on:
                    qmp.command('trace-event-set-state', dict(name='sdcard_read_block', enable=False))
                    qmp.command('trace-event-set-state', dict(name='sdcard_read_batch', enable=False))
                    trace_on = False
                for key, _ in wait_console(sel, debug, .01 if workload_pending else .1):
                    data = os.read(key.fileobj.fileno(), 65536)
                    if data:
                        log.write(data)
                        log.flush()
                        # Retain chunk offsets so later analyses can map console
                        # observations to host time without modifying raw logs.
                        with (out/'serial-chunks.jsonl').open('a') as chunks:
                            chunks.write(json.dumps(dict(end_offset=log.tell(),
                                host_seconds=time.monotonic()-timeline.start))+'\n')
                        serial_tail = (serial_tail + data.decode(errors='replace'))
                        timeline.console(serial_tail)
                        serial_tail = serial_tail[-256:]
                    else:
                        sel.unregister(key.fileobj)
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.wait()
        timeline.mark('qemu_exit', returncode=proc.returncode)
        if qmp:
            qmp.sock.close()
        if debug:
            debug.close()
        if qmp_parent:
            qmp_parent.close()
        if debug_parent:
            debug_parent.close()
        sel.close()
    serial = (out/'serial.log').read_text(errors='replace')
    timeline.mark('postrun_identity_start')
    result = dict(status='OBSERVED_RUN', diagnostic_copy=a.diagnostic or a.recovery_case == 'no-fec', dma=a.dma, batch=a.batch, profile=a.profile,
        timeout=timed_out, returncode=proc.returncode, wall_seconds=time.monotonic()-start,
        kernel_entry='Linux version 6.18.50' in serial,
        emmc_partitions='mmcblk0: p1 p2 p3' in serial,
        initramfs='Run /init as init process' in serial,
        full_scan_complete='Verified OS full read PASS' in serial,
        os_mount=bool(re.search(r'EXT4-fs \(dm-[0-9]+\): mounted filesystem a3680812-', serial)),
        systemd_pid1='systemd[1]' in serial,
        multi_user='Reached target multi-user.target' in serial,
        inputs_unchanged=all(identity(Path(name)) == meta for name, meta in inputs.items()),
        overlay=identity(overlay))
    timeline.mark('postrun_identity_end')
    if a.phase10j_workload:
        result['fsw_workload_complete'] = workload_complete
        result['normal_poweroff'] = (shutdown_requested and proc.returncode == 0 and not timed_out
                                     and 'reboot: Power down' in serial)
    result['execution_clock'] = a.execution_clock
    result['boot_profile'] = a.boot_profile
    result['execution_mode'] = a.execution_mode
    result['generation_id'] = sealed['generation_id'] if sealed else None
    result['operational_policy'] = operational_policy
    result['observer_upload_once'] = a.observer_upload_once
    result.update(userspace_validated=user_validated, shutdown_requested=shutdown_requested,
                  debug_shell=a.debug_shell)
    if user_validated and (not a.phase10j_workload or workload_complete):
        result['status'] = 'PASS' if proc.returncode == 0 and not timed_out else 'MILESTONES_VALIDATED_CLEANUP_INCOMPLETE'
    if boot_selection:
        boot_selection['process'].update(returncode=proc.returncode, timeout=timed_out)
        handoff.write_report(selection_work/'selection.json', boot_selection)
        result['boot_selection_report'] = str(selection_work/'selection.json')
        result['boot_source'] = 'selected active-overlay private exports, generated lab DT substitution'
        if direct:
            result['boot_source'] = 'sealed lab image; original BOOT selection plus explicit sealed-root initramfs; generated lab DT'
    (out/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    if recovery:
        recovery.finish(out, lab, golden, overlay, fault, result)
    if native_test:
        native_test.finish(out)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    sys.exit(main())
