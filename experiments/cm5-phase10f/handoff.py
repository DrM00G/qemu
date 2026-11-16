#!/usr/bin/env python3
"""AI-assisted local BOOT experiment, never upstream; no EEPROM firmware executed."""
import copy
import struct
import argparse
import json
import os
from pathlib import Path
import re
import sys

from block_reader import LogicalReader, REPO, chain
from preboot import FAT, Outcome, require, partitions, regular, identity, MAX_FILE
from validate import sha, validate


class StrictFAT(FAT):
    def chain(self, start):
        for cluster in super().chain(start):
            require(cluster < (0xfff0 if self.bits == 16 else 0xffffff0),
                    'INVALID_LAYOUT', 'reserved/bad FAT cluster')
            yield cluster

    def directory(self):
        # Validate the whole allocated root chain even if an early directory
        # terminator means subsequent clusters contain no selected entries.
        if self.bits == 32:
            count = 0
            for cluster in self.chain(self.root_cluster):
                count += self.cluster_bytes
                require(count <= 4*1024*1024, 'UNSUPPORTED', 'root chain exceeds 4MiB')
        yield from super().directory()

    def file(self, name):
        if '/' in name:
            require(re.fullmatch(r'overlays/[A-Za-z0-9_.-]+', name) is not None,
                    'UNSUPPORTED', 'only overlays/ subdirectory supported')
            from captured_audit import directories
            dirs = [d for d in directories(self) if d['short_name'].casefold() == 'overlays']
            require(self.bits == 32 and len(dirs) == 1, 'INVALID_LAYOUT', 'unique FAT32 overlays directory required')
            sub = copy.copy(self); sub.root_cluster = dirs[0]['cluster']
            leaf = name.split('/')[1]
            data = sub.file(leaf)
            self.r.report['files'][name] = self.r.report['files'].pop(leaf)
            return data
        # Phase10A stops after declared length, leaving the final FAT link unchecked.
        data = super().file(name)
        entry = self.r.report['files'][name]
        if entry['size']:
            expected = (entry['size']+self.cluster_bytes-1)//self.cluster_bytes
            count = 0
            for cluster in self.chain(entry['cluster']):
                count += 1
                require(count <= expected, 'INVALID_LAYOUT', 'overlong selected FAT chain')
            require(count == expected, 'INVALID_LAYOUT', 'truncated selected FAT chain')
        else:
            require(entry['cluster'] == 0, 'INVALID_LAYOUT', 'empty file has cluster allocation')
        for extent in entry['extents']:
            extent['guest_sector_first'] = extent['offset']//512
            extent['guest_sector_end_exclusive'] = (extent['offset']+extent['length']+511)//512
        return data


def select_config(fat, report):
    # No inferred model defaults: all four paths must be explicitly selected.
    selected = {}
    active = []
    total = 0
    def parse(name, enabled=True):
        nonlocal total
        require(name not in active and len(active) < 8, 'INVALID_CONFIG', 'cyclic/deep include')
        active.append(name)
        data = fat.file(name)
        total += len(data)
        require(total <= 65536, 'UNSUPPORTED', 'config/include total exceeds 64KiB')
        try:
            text = data.decode('ascii')
        except UnicodeError as exc:
            raise Outcome('INVALID_CONFIG', 'non-ASCII config') from exc
        require('\0' not in text, 'INVALID_CONFIG', 'NUL in config')
        for number, raw in enumerate(text.splitlines(), 1):
            require(len(raw) <= 98 or not raw.strip() or raw.lstrip().startswith('#'),
                    'UNSUPPORTED', f'{name}:{number}: config line exceeds firmware 98-character limit')
            line = raw.split('#', 1)[0].strip()
            if not line:
                continue
            if line.startswith('['):
                require(line in ('[all]', '[none]'), 'UNSUPPORTED', f'{name}:{number}: conditional {line}')
                enabled = line == '[all]'
                continue
            if not enabled:
                continue
            if line.startswith('include '):
                # Included filter state propagates as textual inclusion.
                enabled = parse(line[8:].strip(), enabled)
            elif line.startswith('initramfs '):
                fields = line.split()
                require(len(fields) == 3 and fields[2] == 'followkernel', 'UNSUPPORTED', 'initramfs syntax/address')
                selected['initramfs'] = fields[1]
            elif '=' in line:
                key, value = (x.strip() for x in line.split('=', 1))
                require(key in ('kernel', 'cmdline', 'device_tree'), 'UNSUPPORTED',
                        f'{name}:{number}: directive {key} requires unimplemented semantics')
                selected[{'device_tree': 'dtb'}.get(key, key)] = value
            else:
                raise Outcome('UNSUPPORTED', f'{name}:{number}: config syntax')
        active.pop()
        return enabled
    parse('config.txt')
    require(set(selected) == {'kernel','initramfs','dtb','cmdline'}, 'UNSUPPORTED', 'explicit four-file selection required')
    report['selected'] = selected
    return selected


def select(overlay, work, expected=None, policy='emmc-only', error_sector=None, config_profile=None):
    report = dict(schema=1, status='PENDING', stage='POLICY', reads=[], files={}, selected={},
                  selection_complete=False, process=dict(launched=False),
                  proxy='LAB BOOT selector; no EEPROM instruction execution', policy=policy,
                  guest_reads=None, backend_prefetch=None, firmware_authenticity='NOT_IMPLEMENTED')
    report['source_identities'] = {str(path): identity(path) for path in [
        Path(__file__), Path(__file__).with_name('block_reader.py'),
        Path(__file__).with_name('validate.py'),
        REPO/'experiments/cm5-phase10f1/initramfs_format.py', REPO/'experiments/cm5-phase10a/preboot.py']}
    report['lab_manifest_canonical_sha256'] = (sha(json.dumps(expected,sort_keys=True).encode())
                                               if expected is not None else None)
    buffers, reader = {}, None
    try:
        require(policy == 'emmc-only', 'UNSUPPORTED', 'USB/restart fallback in BOOT_ORDER 0xf14 not implemented')
        reader = LogicalReader(overlay, report, work, error_sector)
        report['stage'] = 'PARTITION_TABLE'
        p = partitions(reader)
        report['stage'] = 'BOOT_FAT'
        fat = StrictFAT(reader, p)
        report['stage'] = 'CONFIG_SELECTION'
        if config_profile is None:
            selected = select_config(fat, report)
        else:
            sys.path.insert(0, str(REPO/'experiments/cm5-phase10f1'))
            from boot_config import select_cm5, PROFILE
            require(config_profile == PROFILE, 'UNSUPPORTED', 'unknown config profile')
            selected = select_cm5(fat, report)
            report['source_identities'].update({str(p): identity(p) for p in
                (REPO/'experiments/cm5-phase10f1').glob('*.py')})
        report['stage'] = 'SELECTED_FILES'
        for kind, name in selected.items():
            data = fat.file(name)
            report['files'][name]['validation'] = validate(kind, data)
            buffers[kind] = data
        # Expected hashes are a separately supplied laboratory acceptance baseline,
        # never generated from the possibly faulted active overlay inside this gate.
        report['stage'] = 'LAB_INTEGRITY'
        require(expected is not None, 'UNSUPPORTED', 'explicit pre-existing lab digest manifest required')
        for name, meta in report['files'].items():
            require(name in expected, 'UNSUPPORTED', 'missing lab digest: '+name)
            require(expected[name] == meta['sha256'], 'INVALID_IMAGE', 'lab digest mismatch: '+name)
        report.update(status='SELECTED', stage='VALIDATED', selection_complete=True)
    except (Outcome, OSError, ValueError, KeyError) as exc:
        report.update(status=getattr(exc,'code','READ_ERROR'), reason=str(exc))
        buffers = {}
    finally:
        if reader:
            try:
                reader.verify_unchanged()
            except (Outcome, OSError, ValueError, KeyError) as exc:
                report['selection_before_identity_check'] = report['status']
                report.update(status=getattr(exc, 'code', 'READ_ERROR'), reason=str(exc), selection_complete=False)
                buffers = {}
            finally:
                reader.close()
    report['logical_bytes_returned'] = sum(e['returned'] for e in report['reads'])
    return report, buffers


def private_dir(path):
    path = Path(path).resolve()
    require(not path.is_relative_to(REPO), 'INVALID_INPUT', 'exports/work must be outside repository')
    path.mkdir(parents=True, exist_ok=False, mode=0o700)
    return path


def export(report, buffers, destination):
    require(report['status'] == 'SELECTED' and report['selection_complete'] and
            set(buffers) == {'kernel','initramfs','dtb','cmdline'}, 'INVALID_INPUT', 'selection incomplete; no exports')
    destination = private_dir(destination)
    exports = {}
    for kind, data in buffers.items():
        path = destination/kind
        with path.open('xb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        path.chmod(0o400)
        meta = identity(path)
        require(meta['sha256'] == sha(data), 'READ_ERROR', 'export hash mismatch')
        exports[kind] = meta
    report['exports'] = exports
    report['dt_handoff'] = dict(mode='EXPLICIT_GENERATED_LAB_DT_SUBSTITUTION',
        selected_dtb_executed=False, selected_input_sha256=sha(buffers['dtb']),
        reason='cm5io-dev generated lab DT substitutes physical DT and recorded config operations; no firmware overlays applied')
    return exports


def verify_launch(report, overlay):
    require(report['status'] == 'SELECTED' and report['selection_complete'], 'INVALID_INPUT', 'selection failed')
    require(chain(overlay) == report['overlay_chain_after'], 'READ_ERROR', 'disk changed after selection')
    for kind, meta in report['exports'].items():
        require(identity(meta['path']) == meta, 'READ_ERROR', 'export changed: '+kind)
    return report['exports']


def write_report(path, report):
    Path(path).write_text(json.dumps(report, indent=2)+'\n')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--overlay', required=True, type=Path)
    p.add_argument('--work', required=True, type=Path, help='new PRIVATE per-run directory')
    p.add_argument('--expected', type=Path, help='pre-existing filename -> SHA256 lab baseline JSON')
    p.add_argument('--boot-order', required=True, choices=('emmc-only','0xf14'))
    p.add_argument('--block-read-error-sector', type=int)
    p.add_argument('--config-profile', choices=('cm5-headless-lab',))
    p.add_argument('--export', action='store_true')
    a = p.parse_args()
    os.umask(0o077)
    work = private_dir(a.work)
    expected = json.loads(a.expected.read_text()) if a.expected else None
    report, buffers = select(a.overlay, work, expected, a.boot_order, a.block_read_error_sector, a.config_profile)
    try:
        if a.export and report['status'] == 'SELECTED':
            export(report, buffers, work/'exports')
    except Outcome as exc:
        report.update(status=exc.code, reason=str(exc))
    write_report(work/'selection.json', report)
    print(json.dumps(dict(status=report['status'], stage=report['stage'],
                         reason=report.get('reason'), report=str(work/'selection.json'))))
    return 0 if report['status'] == 'SELECTED' else 1


if __name__ == '__main__':
    sys.exit(main())
