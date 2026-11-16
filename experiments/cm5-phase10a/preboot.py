#!/usr/bin/env python3
"""Bounded firmware-BEHAVIOR proxy; NOT Raspberry Pi firmware.

AI-assisted local experiment only, not for upstream submission. No mounting,
firmware execution or guest launch. Reads only regular raw full-user-area files.
"""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import struct
import subprocess
import zlib

USER_BYTES = 15634268160
MAX_FILE = 128 * 1024 * 1024
MAX_CHAIN = 262144


class Outcome(Exception):
    def __init__(self, code, reason):
        self.code, self.reason = code, reason
        super().__init__(reason)


def require(ok, code, reason):
    if not ok:
        raise Outcome(code, reason)


def regular(path):
    # Resolve aliases before opening, reject devices, FIFOs and symlinks at open.
    path = Path(path).resolve()
    require(stat.S_ISREG(path.stat().st_mode), 'UNSUPPORTED', 'input must be a regular file')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        os.close(fd)
        raise Outcome('UNSUPPORTED', 'input must be a regular file')
    return os.fdopen(fd, 'rb')


def identity(path):
    with regular(path) as f:
        s = os.fstat(f.fileno())
        digest = hashlib.file_digest(f, 'sha256').hexdigest()
    return dict(path=str(Path(path).resolve()), device=s.st_dev, inode=s.st_ino,
                bytes=s.st_size, mtime_ns=s.st_mtime_ns, sha256=digest)


class Reader:
    def __init__(self, path, report, bad_sectors=()):
        self.f = regular(path)
        self.size = os.fstat(self.f.fileno()).st_size
        self.report = report
        self.bad = set(bad_sectors)

    def read(self, offset, size, purpose):
        require(0 <= offset <= self.size and 0 <= size <= self.size - offset,
                'INVALID_LAYOUT', 'read outside user area')
        event = dict(offset=offset, requested=size, returned=0, purpose=purpose,
                     observer='host_proxy_pread', status='ATTEMPTED')
        self.report['reads'].append(event)
        if any(offset // 512 <= s <= (offset + size - 1) // 512 for s in self.bad):
            event['status'] = 'INJECTED_READ_ERROR'
            raise Outcome('READ_ERROR', 'proxy-only injected read error')
        try:
            data = os.pread(self.f.fileno(), size, offset)
        except OSError as e:
            event['status'] = 'IO_ERROR'
            raise Outcome('READ_ERROR', str(e)) from e
        event.update(returned=len(data), status='READ')
        require(len(data) == size, 'READ_ERROR', 'short read')
        return data


def partitions(r):
    mbr = r.read(0, 512, 'MBR')
    require(mbr[510:] == b'\x55\xaa', 'INVALID_LAYOUT', 'MBR signature')
    def entries(data):
        return [dict(type=data[o+4], start=struct.unpack_from('<I', data, o+8)[0],
                     sectors=struct.unpack_from('<I', data, o+12)[0])
                for o in range(446, 510, 16)]
    parts = []
    extended = []
    for n, p in enumerate(entries(mbr), 1):
        if not p['type']:
            continue
        require(p['start'] > 0 and p['sectors'] > 0 and
                (p['start'] + p['sectors']) * 512 <= r.size,
                'INVALID_LAYOUT', 'partition outside user area')
        p['partition'] = n
        parts.append(p)
        if p['type'] in (5, 15, 133):
            extended.append(p)
    primary = sorted(parts, key=lambda p: p['start'])
    require(all(a['start'] + a['sectors'] <= b['start'] for a, b in zip(primary, primary[1:])),
            'INVALID_LAYOUT', 'overlapping primary partitions')
    require(len(extended) <= 1, 'UNSUPPORTED', 'multiple extended partitions')
    for ext in extended:
        base, end = ext['start'], ext['start'] + ext['sectors']
        current, seen, n = base, set(), 5
        while current:
            require(current not in seen and len(seen) < 64 and base <= current < end,
                    'INVALID_LAYOUT', 'invalid/cyclic EBR chain')
            seen.add(current)
            ebr = r.read(current * 512, 512, 'EBR')
            require(ebr[510:] == b'\x55\xaa', 'INVALID_LAYOUT', 'EBR signature')
            p, link, *unused = entries(ebr)
            require(not any(x['type'] for x in unused), 'UNSUPPORTED', 'extra EBR entries')
            require(p['type'] not in (0, 5, 15, 133) and p['start'] > 0 and p['sectors'] > 0,
                    'INVALID_LAYOUT', 'invalid logical partition')
            p['start'] += current
            require(p['start'] + p['sectors'] <= end, 'INVALID_LAYOUT', 'logical partition bounds')
            p['partition'] = n
            parts.append(p)
            n += 1
            require(not link['type'] or link['type'] in (5, 15, 133),
                    'INVALID_LAYOUT', 'invalid EBR link type')
            require(not link['type'] or (link['sectors'] > 0 and
                    base + link['start'] + link['sectors'] <= end),
                    'INVALID_LAYOUT', 'EBR link outside container')
            current = base + link['start'] if link['type'] else 0
        require(not any(p['start'] <= ebr < p['start'] + p['sectors']
                        for p in parts if p['partition'] >= 5 for ebr in seen),
                'INVALID_LAYOUT', 'EBR overlaps logical partition data')
    leaves = sorted((p for p in parts if p['type'] not in (5, 15, 133)), key=lambda p: p['start'])
    require(all(a['start'] + a['sectors'] <= b['start'] for a, b in zip(leaves, leaves[1:])),
            'INVALID_LAYOUT', 'overlapping data partitions')
    r.report['partitions'] = parts
    p1 = next((p for p in parts if p['partition'] == 1), None)
    require(p1 is not None, 'INVALID_LAYOUT', 'no BOOT p1')
    require(p1['type'] in (6, 14, 11, 12), 'UNSUPPORTED', 'BOOT p1 type is not FAT16/FAT32')
    return p1


class FAT:
    """Read-only FAT16/32 root files, including checksum-validated VFAT names.

    Subdirectories, FAT12, non-512 sectors and non-ASCII names are unsupported.
    Only active FAT entries traversed are read; no full volume integrity claim.
    """
    def __init__(self, r, p):
        self.r, self.base, self.limit = r, p['start'] * 512, p['sectors'] * 512
        b = r.read(self.base, 512, 'FAT BPB')
        u16 = lambda o: struct.unpack_from('<H', b, o)[0]
        u32 = lambda o: struct.unpack_from('<I', b, o)[0]
        require(b[510:] == b'\x55\xaa', 'INVALID_LAYOUT', 'BPB signature')
        require(u16(11) == 512, 'UNSUPPORTED', 'only 512-byte FAT sectors supported')
        self.spc, reserved, self.nfats = b[13], u16(14), b[16]
        require(self.spc in (1, 2, 4, 8, 16, 32, 64, 128) and reserved and self.nfats in (1, 2),
                'INVALID_LAYOUT', 'invalid FAT geometry')
        self.roots, total = u16(17), u16(19) or u32(32)
        self.fatsz = u16(22) or u32(36)
        root_sectors = (self.roots * 32 + 511) // 512
        data_sector = reserved + self.nfats * self.fatsz + root_sectors
        require(self.fatsz > 0 and data_sector < total and total * 512 <= self.limit,
                'INVALID_LAYOUT', 'FAT volume outside partition or empty')
        self.clusters = (total - data_sector) // self.spc
        self.bits = 12 if self.clusters < 4085 else 16 if self.clusters < 65525 else 32
        require(self.bits != 12, 'UNSUPPORTED', 'FAT12')
        require((self.clusters + 2) * (self.bits // 8) <= self.fatsz * 512,
                'INVALID_LAYOUT', 'FAT too small for data clusters')
        require((self.bits == 16 and self.roots and u16(22)) or
                (self.bits == 32 and not self.roots and not u16(22) and u16(42) == 0),
                'INVALID_LAYOUT', 'inconsistent FAT variant')
        active = 0
        if self.bits == 32 and u16(40) & 128:
            active = u16(40) & 15
            require(active < self.nfats, 'INVALID_LAYOUT', 'invalid active FAT')
        self.fat = self.base + (reserved + active * self.fatsz) * 512
        self.data = self.base + data_sector * 512
        self.cluster_bytes = self.spc * 512
        self.root_offset = self.base + (reserved + self.nfats * self.fatsz) * 512
        self.root_cluster = u32(44) if self.bits == 32 else None
        r.report['fat'] = dict(bits=self.bits, clusters=self.clusters,
                              cluster_bytes=self.cluster_bytes, active_fat=active)

    def cluster_offset(self, c):
        require(2 <= c < self.clusters + 2, 'INVALID_LAYOUT', 'cluster outside data area')
        return self.data + (c - 2) * self.cluster_bytes

    def chain(self, start):
        seen = set()
        c = start
        while True:
            require(c not in seen and len(seen) < MAX_CHAIN, 'INVALID_LAYOUT', 'cyclic/oversize FAT chain')
            self.cluster_offset(c)
            seen.add(c)
            yield c
            width = self.bits // 8
            b = self.r.read(self.fat + c * width, width, 'FAT chain entry')
            c = int.from_bytes(b, 'little') & (0xfffffff if self.bits == 32 else 0xffff)
            if c >= (0xffffff8 if self.bits == 32 else 0xfff8):
                break

    def directory(self):
        if self.bits == 16:
            chunks = [(self.root_offset, self.roots * 32)]
        else:
            chunks = ((self.cluster_offset(c), self.cluster_bytes) for c in self.chain(self.root_cluster))
        lfn = []
        directory_bytes = 0
        for offset, length in chunks:
            directory_bytes += length
            require(directory_bytes <= 4 * 1024 * 1024, 'UNSUPPORTED', 'root directory exceeds 4 MiB bound')
            data = self.r.read(offset, length, 'BOOT root directory')
            for i in range(0, len(data), 32):
                e = data[i:i+32]
                if e[0] == 0:
                    return
                if e[0] == 229:
                    lfn = []
                    continue
                if e[11] == 15:
                    lfn.append(e)
                    require(len(lfn) <= 20, 'INVALID_LAYOUT', 'too many LFN entries')
                    continue
                raw = e[:11]
                try:
                    name = raw[:8].decode('ascii').rstrip() + ('.' + raw[8:].decode('ascii').rstrip() if raw[8:].strip() else '')
                    if lfn:
                        checksum = 0
                        for byte in raw:
                            checksum = (((checksum & 1) << 7) + (checksum >> 1) + byte) & 255
                        require(lfn[0][0] == (64 | len(lfn)) and
                                all(x[0] == (64 | len(lfn) if j == 0 else len(lfn)-j) and
                                    x[13] == checksum and x[12] == 0 and x[26:28] == b'\0\0'
                                    for j, x in enumerate(lfn)), 'INVALID_LAYOUT', 'invalid LFN sequence/checksum')
                        units = b''.join(x[1:11]+x[14:26]+x[28:32] for x in reversed(lfn))
                        name = units.decode('utf-16le').split('\0')[0].rstrip('\uffff')
                        require(name.isascii(), 'UNSUPPORTED', 'non-ASCII VFAT name')
                except UnicodeError as ex:
                    raise Outcome('UNSUPPORTED', 'unsupported directory encoding') from ex
                lfn = []
                if e[11] & 24:  # directories / volume labels are not selected
                    continue
                cluster = struct.unpack_from('<H', e, 26)[0]
                if self.bits == 32:
                    cluster |= struct.unpack_from('<H', e, 20)[0] << 16
                yield dict(name=name, cluster=cluster, size=struct.unpack_from('<I', e, 28)[0],
                           directory_entry_offset=offset+i)

    def file(self, name):
        require(re.fullmatch(r'[A-Za-z0-9_.-]+', name) and name not in ('.', '..'),
                'UNSUPPORTED', 'only root file names supported')
        matches = [e for e in self.directory() if e['name'].casefold() == name.casefold()]
        require(matches, 'SELECTED_FILE_UNAVAILABLE', 'selected file missing: ' + name)
        require(len(matches) == 1, 'INVALID_LAYOUT', 'ambiguous file name')
        entry = matches[0]
        require(entry['size'] <= MAX_FILE, 'UNSUPPORTED', 'file exceeds 128 MiB bound')
        remaining, data, extents = entry['size'], bytearray(), []
        if remaining:
            for c in self.chain(entry['cluster']):
                length = min(remaining, self.cluster_bytes)
                offset = self.cluster_offset(c)
                data.extend(self.r.read(offset, length, 'file:' + name))
                extents.append(dict(offset=offset, length=length))
                remaining -= length
                if not remaining:
                    break
        require(not remaining, 'INVALID_LAYOUT', 'truncated file chain')
        self.r.report['files'][name] = dict(**entry, sha256=hashlib.sha256(data).hexdigest(),
                                          extents=extents)
        return bytes(data)


DEFAULTS = dict(kernel='kernel_2712.img', initramfs='initramfs_2712-osverified-v8',
                dtb='bcm2712-rpi-cm5-cm5io.dtb', cmdline='cmdline_2712-osverified-v8.txt')


def config(data, selected):
    require(len(data) <= 65536, 'UNSUPPORTED', 'config exceeds 64 KiB bound')
    try:
        text = data.decode('ascii')
    except UnicodeError as e:
        raise Outcome('INVALID_CONFIG', 'non-ASCII config') from e
    enabled = True
    for raw in text.splitlines():
        line = raw.split('#', 1)[0].strip()
        if not line:
            continue
        if line.startswith('['):
            require(line in ('[all]', '[none]', '[cm5]', '[pi5]'), 'UNSUPPORTED', 'config conditional')
            enabled = line != '[none]'
            continue
        if not enabled:
            continue
        if line.startswith('initramfs '):
            fields = line.split()
            require(len(fields) == 3 and fields[2] == 'followkernel', 'UNSUPPORTED', 'initramfs address/multiple files')
            selected['initramfs'] = fields[1]
        elif '=' in line:
            key, value = [x.strip() for x in line.split('=', 1)]
            if key in ('kernel', 'cmdline', 'device_tree'):
                selected[{'device_tree': 'dtb'}.get(key, key)] = value
            else:
                raise Outcome('UNSUPPORTED', 'config directive unsupported: ' + key)
        else:
            raise Outcome('UNSUPPORTED', 'config syntax/include unsupported')


def validate(kind, data):
    if kind == 'kernel':
        require(not data.startswith((b'\x1f\x8b', b'\x7fELF', b'\xfd7zXZ\0')),
                'UNSUPPORTED', 'compressed/ELF kernel loader unsupported')
        require(len(data) >= 64 and data[56:60] == b'ARM\x64', 'INVALID_IMAGE', 'not an uncompressed ARM64 Image header')
        size = struct.unpack_from('<Q', data, 16)[0]
        require(size != 0, 'UNSUPPORTED', 'legacy ARM64 zero image_size unsupported')
        require(size <= len(data), 'INVALID_IMAGE', 'ARM64 Image size invalid')
    elif kind == 'initramfs':
        if data.startswith(b'\x1f\x8b'):
            import io
            try:
                with gzip.GzipFile(fileobj=io.BytesIO(data)) as f:
                    data = f.read(MAX_FILE + 1)
            except (OSError, EOFError, zlib.error) as e:
                raise Outcome('INVALID_IMAGE', 'invalid gzip initramfs') from e
            require(len(data) <= MAX_FILE, 'UNSUPPORTED', 'expanded initramfs exceeds bound')
        require(not data.startswith((b'\xfd7zXZ\0', b'BZh', b'\x28\xb5\x2f\xfd', b'\x04\x22\x4d\x18')),
                'UNSUPPORTED', 'initramfs compression unsupported')
        require(data[:6] in (b'070701', b'070702'), 'INVALID_IMAGE', 'not newc initramfs')
        # Header recognition only: do not equate this with valid archive semantics.
    elif kind == 'dtb':
        require(len(data) >= 40 and data[:4] == b'\xd0\x0d\xfe\xed', 'INVALID_IMAGE', 'DTB header magic/length')
        total, off_struct, off_strings, off_reserve, version, compat, _, strings, tree = struct.unpack_from('>9I', data, 4)
        require(version >= 17 and compat <= 17, 'UNSUPPORTED', 'DTB version unsupported')
        require(40 <= total <= len(data) and compat <= version and
                40 <= off_reserve < total and off_reserve % 8 == 0 and
                40 <= off_struct < total and off_struct % 4 == 0 and off_struct + tree <= total and
                40 <= off_strings <= total and off_strings + strings <= total,
                'INVALID_IMAGE', 'invalid DTB header bounds')
    else:
        require(data and b'\0' not in data and len(data) <= 65536, 'INVALID_IMAGE', 'invalid cmdline')
    return 'HEADER_ONLY_NOT_SEMANTIC_VALIDATION'


def probe(path, policy='emmc-only', overrides=None, bad_sectors=()):
    result = dict(schema=1, proxy='NOT_REAL_RASPBERRY_PI_FIRMWARE',
                  policy=policy, stage='POLICY', status=None, reads=[], files={},
                  selected={}, selection_complete=False,
                  process=dict(launched=False, returncode=None, timeout=False),
                  os_verity_fec='NOT_REACHED', fsw_verity_fec='NOT_REACHED', diagnostics='NOT_RUN')
    r = None
    try:
        require(policy == 'emmc-only', 'UNSUPPORTED',
                '0xf14 tries USB before eMMC; USB/restart policy is not implemented')
        r = Reader(path, result, bad_sectors)
        result['total_user_area_bytes'] = r.size
        result['stage'] = 'PARTITION_TABLE'
        p = partitions(r)
        result['stage'] = 'BOOT_FAT'
        fat = FAT(r, p)
        result['stage'] = 'CONFIG_SELECTION'
        selected = DEFAULTS.copy()
        result['selection_candidates'] = selected
        config(fat.file('config.txt'), selected)
        selected.update(overrides or {})
        result['selected'] = selected.copy()
        result['selection_complete'] = True
        result['selection_precedence'] = 'documented defaults < active config.txt < explicit CLI overrides'
        result['stage'] = 'SELECTED_FILES'
        for kind, name in selected.items():
            data = fat.file(name)
            result['files'][name]['validation'] = validate(kind, data)
        result['stage'] = 'HEADERS_VALIDATED'
        result['status'] = 'UNSUPPORTED'
        result['reason'] = ('BOOT file headers read and checked; semantic image validation and cm5io-dev '
                            'handoff unsupported (machine rejects external DTB). No guest launched.')
    except Outcome as e:
        result.update(status=e.code, reason=e.reason)
    except OSError as e:
        result.update(status='READ_ERROR', reason=str(e))
    finally:
        if r:
            r.f.close()
    result['proxy_bytes_returned'] = sum(e['returned'] for e in result['reads'])
    result['guest_bytes_observed'] = None
    result['inconclusive_for_guest_boot'] = True  # this bounded proxy never launches a guest
    result['classification_scope'] = 'bounded supported representation only; not a prediction of real firmware outcome'
    return result


def summary(result):
    lines = [f"{result['status']}: {result.get('reason', '')}",
             f"Stage: {result['stage']}; proxy bytes returned: {result.get('proxy_bytes_returned', 0)}; "
             f"guest launched: {result['process']['launched']}"]
    for kind in ('golden', 'overlay'):
        if kind in result:
            item = result[kind]
            lines.append(f"{kind}: {item['path']} ({item['bytes']} bytes), SHA256={item['sha256']}")
    for kind, name in result.get('selected', {}).items():
        lines.append(f"Selected {kind}: {name}")
    for name, item in result.get('files', {}).items():
        lines.append(f"Read file: {name}, {item['size']} bytes, SHA256={item['sha256']}")
    if result.get('corruptions'):
        sectors = set()
        for corruption in result['corruptions']:
            sectors.update(corruption.get('physical_guest_sectors', []))
            if 'sector' in corruption:
                sectors.add(corruption['sector'])
        lines.append('Corrupted physical guest sectors: ' + ', '.join(map(str, sorted(sectors))))
    lines.append(f"OS verity/FEC: {result.get('os_verity_fec', 'NOT_REACHED')}; "
                 f"FSW verity/FEC: {result.get('fsw_verity_fec', 'NOT_REACHED')}; "
                 f"diagnostics: {result.get('diagnostics', 'NOT_RUN')}")
    return '\n'.join(lines) + '\n'


def run_probe(golden, output, overlay_dir, policy, xor_sectors=(), bad_sectors=(), overrides=None):
    """Create a fresh full-size raw COW/copy and write only metadata to output."""
    os.umask(0o077)
    output.mkdir(parents=True, exist_ok=False)
    result = dict(status='SKIPPED_WITH_REASON', stage='INPUTS',
                  process=dict(launched=False, returncode=None, timeout=False))
    try:
        if not golden.exists():
            result['reason'] = 'private golden image missing'
        else:
            repo = Path(__file__).resolve().parents[2]
            require(not overlay_dir.resolve().is_relative_to(repo), 'INVALID_INPUT',
                    'captured disk copies must stay outside the public repository')
            before = identity(golden)
            (output/'golden-before.json').write_text(json.dumps(before, indent=2)+'\n')
            require(before['bytes'] == USER_BYTES, 'UNSUPPORTED', 'golden must be exact full user area size')
            require(all(0 <= s < USER_BYTES // 512 for s in list(xor_sectors) + list(bad_sectors)),
                    'INVALID_INPUT', 'fault sector outside user area')
            require(len(set(xor_sectors)) == len(xor_sectors), 'INVALID_INPUT', 'duplicate XOR sector')
            overlay_dir.mkdir(parents=True, exist_ok=False)
            overlay = overlay_dir / 'emmc.raw'
            copy = ['cp', '--reflink=auto', '--sparse=always', '--', str(golden.resolve()), str(overlay)]
            (output/'pending.json').write_text(json.dumps(dict(status='INCONCLUSIVE_UNTIL_RESULT',
                stage='COPY', copy_command=copy, golden=before), indent=2)+'\n')
            subprocess.run(copy, check=True)
            require(overlay.stat().st_size == USER_BYTES, 'HARNESS_ERROR', 'incomplete raw copy')
            require((overlay.stat().st_dev, overlay.stat().st_ino) != (before['device'], before['inode']),
                    'INVALID_INPUT', 'overlay aliases golden')
            overlay.chmod(0o600)
            faults = []
            with overlay.open('r+b') as f:
                for sector in xor_sectors:
                    f.seek(sector * 512)
                    old = f.read(512)
                    require(len(old) == 512, 'READ_ERROR', 'short fault-injection read')
                    f.seek(sector * 512)
                    new = bytes(x ^ 255 for x in old)
                    f.write(new)
                    faults.append(dict(sector=sector, offset=sector*512, length=512,
                                       operation='xor-ff', before_sha256=hashlib.sha256(old).hexdigest(),
                                       after_sha256=hashlib.sha256(new).hexdigest()))
                f.flush()
                os.fsync(f.fileno())
            result = probe(overlay, policy, overrides, bad_sectors)
            result.update(golden=before, overlay=identity(overlay), corruptions=faults,
                          proxy_only_read_error_sectors=list(bad_sectors), copy_command=copy,
                          identity_reads='whole-file host hashing/copy excluded from proxy read ledger')
            result['golden_unchanged'] = identity(golden) == before
            require(result['golden_unchanged'], 'INPUT_CHANGED', 'golden changed concurrently')
    except (Outcome, OSError, subprocess.CalledProcessError) as e:
        result.update(status=e.code if isinstance(e, Outcome) else 'HARNESS_ERROR', reason=str(e))
    (output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    (output / 'summary.txt').write_text(summary(result))
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--golden', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True, help='fresh metadata directory')
    p.add_argument('--overlay-dir', type=Path, help='fresh private directory OUTSIDE repository; default ~/cm5-v8-lab/phase10a/OUTPUT_NAME')
    p.add_argument('--boot-order', choices=('emmc-only', '0xf14'), required=True)
    p.add_argument('--xor-sector', type=int, action='append', default=[])
    p.add_argument('--read-error-sector', type=int, action='append', default=[])
    for key in DEFAULTS:
        p.add_argument('--' + key)
    a = p.parse_args()
    result = run_probe(a.golden, a.output,
                       a.overlay_dir or Path.home()/'cm5-v8-lab/phase10a'/a.output.name,
                       a.boot_order, a.xor_sector, a.read_error_sector,
                       {k: getattr(a, k) for k in DEFAULTS if getattr(a, k)})
    print(summary(result), end='')
    return 0 if result['status'] in ('UNSUPPORTED', 'SKIPPED_WITH_REASON') else 1


if __name__ == '__main__':
    raise SystemExit(main())
