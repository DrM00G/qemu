"""Local-only read-only QCOW2 logical pread via QEMU NBD; no kernel NBD device."""
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import time
import tempfile
import sys
import re
import select as select_io
from collections import OrderedDict

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO/'experiments/cm5-phase10a'))
from preboot import Outcome, require, regular, identity

BIN = REPO/'build-arm64-phase1'


def run(args):
    try:
        return subprocess.check_output([str(x) for x in args], stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as exc:
        raise Outcome('READ_ERROR', 'QEMU block tool failed: '+exc.stderr.decode(errors='replace')[:2048]) from exc


def chain(path):
    # First reject special files; then validate every backing file before NBD open.
    with regular(path):
        pass
    result, seen = [], set()
    current, expected_format = Path(path).resolve(), 'qcow2'
    while True:
        require(current not in seen and len(seen) < 8, 'INVALID_LAYOUT', 'cyclic/deep backing chain')
        seen.add(current)
        with regular(current):
            pass
        # info without --backing-chain does not open the backing image. Validate
        # each local regular backing pathname before allowing QEMU to follow it.
        require(expected_format in ('raw', 'qcow2'), 'UNSUPPORTED', 'backing format unspecified/unsupported')
        node = json.loads(run([BIN/'qemu-img', 'info', '-f', expected_format, '--output=json', current]))
        require(node['format'] == expected_format and expected_format in ('raw','qcow2'),
                'UNSUPPORTED', 'explicit raw/QCOW2 backing formats required')
        specific = node.get('format-specific',{}).get('data',{})
        require(not specific.get('data-file') and not node.get('encrypted'),
                'UNSUPPORTED', 'external data files/encrypted images not supported')
        result.append(dict(info=node, identity=identity(current)))
        backing = node.get('backing-filename')
        if not backing:
            break
        require(':' not in backing and '\x00' not in backing, 'UNSUPPORTED', 'backing protocols forbidden')
        expected_format = node.get('backing-filename-format')
        current = (current.parent/backing).resolve()
    return result


class NBDReader:
    """Single locked QEMU block graph. Each READ yields exactly requested bytes.

    Ledger is NBD logical data returned to the selector, not physical backend
    I/O or guest reads. QEMU cache/metadata/prefetch are deliberately unknown.
    """
    def __init__(self, path, report, work, error_sector=None):
        self.report, self.seq = report, 0
        self.sock = None
        self.proc = None
        self.path = Path(path).resolve()
        self.before = chain(self.path)
        report['overlay_chain_before'] = self.before
        work = Path(work)
        self.socket_path = Path(tempfile.mkdtemp(prefix='f10f-nbd-', dir='/tmp'))/'nbd.sock'
        report['nbd_socket_directory'] = str(self.socket_path.parent)
        self.log = (work/'nbd.log').open('xb')
        args = [BIN/'qemu-nbd', '--read-only', '--persistent', '--socket', self.socket_path]
        if error_sector is not None:
            # Error is injected by QEMU's real block graph, not Python's read method.
            opts = dict(driver='blkdebug', image=dict(driver='qcow2', file=dict(
                driver='file', filename=str(self.path))), **{'inject-error': [dict(
                    event='read_aio', errno=5, sector=error_sector, once=False, immediately=True)]})
            args += ['json:'+json.dumps(dict(driver='raw', file=opts))]
        else:
            args += ['--format=qcow2', self.path]
        report['block_export_executable'] = identity(BIN/'qemu-nbd')
        report['block_export_command'] = [str(x) for x in args]
        self.proc = subprocess.Popen([str(x) for x in args], stdout=self.log, stderr=self.log)
        try:
            deadline = time.monotonic()+10
            while not self.socket_path.exists():
                require(self.proc.poll() is None, 'READ_ERROR', 'qemu-nbd startup failed; see nbd.log')
                require(time.monotonic() < deadline, 'READ_ERROR', 'NBD startup timeout')
                time.sleep(.02)
            self.sock = socket.socket(socket.AF_UNIX)
            self.sock.settimeout(10)
            while True:
                try:
                    self.sock.connect(str(self.socket_path))
                    break
                except ConnectionRefusedError:
                    require(self.proc.poll() is None and time.monotonic() < deadline,
                            'READ_ERROR', 'NBD connection failed; see nbd.log')
                    time.sleep(.02)
            magic, opts, flags = struct.unpack('>QQH', self.recv(18))
            require(magic == 0x4e42444d41474943 and opts == 0x49484156454f5054 and flags & 1,
                    'READ_ERROR', 'unexpected NBD negotiation')
            self.sock.sendall(struct.pack('>I', 3 if flags & 2 else 1))
            self.sock.sendall(struct.pack('>QII', opts, 1, 0))  # EXPORT_NAME, empty
            self.size, transmission = struct.unpack('>QH', self.recv(10))
            if not flags & 2:
                self.recv(124)
            require(transmission & 2, 'READ_ERROR', 'NBD export must be read-only')
            report['logical_size'] = self.size
        except BaseException:
            self.close()
            raise

    def recv(self, size):
        data = bytearray()
        while len(data) < size:
            part = self.sock.recv(size-len(data))
            if not part:
                raise OSError('short NBD reply')
            data.extend(part)
        return bytes(data)

    def read(self, offset, size, purpose):
        require(0 <= size <= 128*1024*1024 and 0 <= offset <= self.size and
                size <= self.size-offset, 'INVALID_LAYOUT', 'bounded logical read outside image')
        event = dict(offset=offset, requested=size, returned=0, purpose=purpose,
                     observer='read_only_NBD_logical_pread', status='ATTEMPTED')
        self.report['reads'].append(event)
        self.seq += 1
        try:
            self.sock.sendall(struct.pack('>IHHQQI', 0x25609513, 0, 0, self.seq, offset, size))
            magic, error, handle = struct.unpack('>IIQ', self.recv(16))
            require(magic == 0x67446698 and handle == self.seq, 'READ_ERROR', 'invalid NBD reply')
            require(error == 0, 'READ_ERROR', f'QEMU block read errno={error}')
            data = self.recv(size)
            event.update(returned=len(data), status='READ')
            return data
        except (OSError, Outcome) as exc:
            event['status'] = 'BLOCK_READ_ERROR'
            raise Outcome('READ_ERROR', str(exc)) from exc

    def close(self):
        if self.sock:
            self.sock.close()
            self.sock = None
        if self.proc:
            self.proc.terminate()
            self.proc.wait(timeout=10)
            if self.proc.stdin:
                self.proc.stdin.close()
            if self.proc.stdout:
                self.proc.stdout.close()
            self.proc = None
        self.log.close()

    def verify_unchanged(self):
        after = chain(self.path)
        self.report['overlay_chain_after'] = after
        require(self.before == after, 'READ_ERROR', 'overlay/backing changed during selection')


class PipeReader(NBDReader):
    """Explicit qemu-io read-only pipe transport where socket bind is denied.

    One persistent block graph holds read-only image locks. Hex dumps are
    decoded with exact byte-count/address checks; real blkdebug errors remain
    failed reads. No raw image conversion or host asset fallback occurs.
    """
    def __init__(self, path, report, work, error_sector=None):
        self.path, self.report = Path(path).resolve(), report
        self.prefetch = int(os.environ.get('CM5_BOOT_PREFETCH','0'))
        require(self.prefetch in (0,65536), 'UNSUPPORTED', 'pipe prefetch must be 0 or 65536')
        self.cache = OrderedDict()
        report['pipe_prefetch'] = dict(bytes=self.prefetch, max_cached_blocks=32,
            ledger='reads records actual QEMU requests/returned bytes, including prefetch; cache hits issue no QEMU read')
        self.before = chain(self.path)
        report['overlay_chain_before'] = self.before
        self.size = self.before[0]['info']['virtual-size']
        report['logical_size'] = self.size
        self.sock = None
        self.log = (Path(work)/'qemu-io.log').open('xb')
        args = [BIN/'qemu-io', '-r']
        if error_sector is None:
            args += ['-f','qcow2',self.path]
        else:
            opts = dict(driver='raw', file=dict(driver='blkdebug', image=dict(driver='qcow2',
                file=dict(driver='file',filename=str(self.path))), **{'inject-error':[dict(
                    event='read_aio',errno=5,sector=error_sector,once=False,immediately=True)]}))
            args += ['json:'+json.dumps(opts)]
        report['block_export_executable'] = identity(BIN/'qemu-io')
        report['block_export_command'] = [str(x) for x in args]
        report['block_transport'] = 'explicit read-only qemu-io pipes; no NBD listener'
        self.proc = subprocess.Popen([str(x) for x in args], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        try:
            self.reply(4096)
        except BaseException:
            self.close()
            raise

    def reply(self, bound):
        result = bytearray()
        deadline = time.monotonic()+30
        while not result.endswith(b'qemu-io> '):
            require(time.monotonic() < deadline, 'READ_ERROR', 'qemu-io response timeout')
            ready, _, _ = select_io.select([self.proc.stdout], [], [], 1)
            if not ready:
                continue
            chunk = os.read(self.proc.stdout.fileno(), 65536)
            require(chunk, 'READ_ERROR', 'qemu-io closed')
            result.extend(chunk)
            require(len(result) <= bound, 'READ_ERROR', 'qemu-io reply bound')
        return bytes(result[:-9])

    def read(self, offset, size, purpose):
        require(0 <= size <= 128*1024*1024 and 0 <= offset <= self.size and
                size <= self.size-offset, 'INVALID_LAYOUT', 'bounded logical read outside image')
        if not self.prefetch:
            return self.uncached_read(offset,size,purpose)
        out = bytearray()
        while len(out) < size:
            current = offset+len(out)
            start = current//self.prefetch*self.prefetch
            if start not in self.cache:
                self.cache[start] = self.uncached_read(start,min(self.prefetch,self.size-start),
                    'pipe transport prefetch for '+purpose)
                if len(self.cache) > 32:
                    self.cache.popitem(last=False)
            block = self.cache[start]
            self.cache.move_to_end(start)
            out.extend(block[current-start:current-start+min(size-len(out),len(block)-(current-start))])
        return bytes(out)

    def uncached_read(self, offset, size, purpose):
        require(0 <= size <= 128*1024*1024 and 0 <= offset <= self.size and
                size <= self.size-offset, 'INVALID_LAYOUT', 'bounded logical read outside image')
        event = dict(offset=offset, requested=size, returned=0, purpose=purpose,
                     observer='read_only_qemu_io_logical_pread', status='ATTEMPTED')
        self.report['reads'].append(event)
        try:
            # FAT reads are normally clusters; chunk larger directory reads to
            # bound the text protocol and retain one logical request ledger row.
            result = bytearray()
            while len(result) < size:
                start = offset+len(result); count = min(65536,size-len(result))
                self.proc.stdin.write(f'read -v {start} {count}\n'.encode()); self.proc.stdin.flush()
                response = self.reply(count*8+8192)
                require(f'read {count}/{count} bytes at offset {start}'.encode() in response,
                        'READ_ERROR', 'QEMU block read failed: '+response[:200].decode(errors='replace'))
                decoded = bytearray()
                for line in response.splitlines():
                    m = re.match(rb'^([0-9a-f]+):  ((?:[0-9a-f]{2} ){1,16})',line)
                    if m:
                        require(int(m[1],16) == start+len(decoded), 'READ_ERROR', 'qemu-io address mismatch')
                        decoded.extend(bytes.fromhex(m[2].decode()))
                require(len(decoded) == count, 'READ_ERROR', 'qemu-io dump length mismatch')
                result.extend(decoded)
            event.update(returned=size,status='READ')
            return bytes(result)
        except (OSError, Outcome) as exc:
            event['status'] = 'BLOCK_READ_ERROR'
            raise Outcome('READ_ERROR',str(exc)) from exc


def LogicalReader(path, report, work, error_sector=None):
    transport = os.environ.get('CM5_BOOT_READER','nbd')
    require(transport in ('nbd','qemu-io'), 'UNSUPPORTED', 'unknown BOOT block transport')
    cls = PipeReader if transport == 'qemu-io' else NBDReader
    return cls(path,report,work,error_sector)
