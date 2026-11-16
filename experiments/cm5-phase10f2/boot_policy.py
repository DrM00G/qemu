#!/usr/bin/env python3
"""Local firmware-BEHAVIOR proxy; no EEPROM instructions or USB enumeration.

Only declared device absence permits fallback. Firmware handling of arbitrary
media/file/config failures is deliberately outside this evidenced subset.
"""
import argparse
import json
from pathlib import Path
import re
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent/'cm5-phase10f'))
import handoff as h

MODES = {1: 'emmc', 4: 'usb-msd', 15: 'restart'}


def parse_order(value):
    h.require(isinstance(value, str) and re.fullmatch(r'0x[0-9a-fA-F]{1,8}', value),
              'UNSUPPORTED', 'BOOT_ORDER must be explicit uint32 hex')
    modes = [int(x, 16) for x in value[2:][::-1]]
    h.require(all(x in MODES for x in modes), 'UNSUPPORTED', 'unsupported BOOT_ORDER nibble')
    h.require(15 not in modes[:-1] and modes[-1] == 15 and len(modes) > 1,
              'UNSUPPORTED', 'supported sequence requires terminal RESTART and a source')
    return [MODES[x] for x in modes]


def classify(report):
    if report['status'] == 'SELECTED':
        return 'SELECTED'
    if report['status'] == 'READ_ERROR':
        return 'UNREADABLE_MEDIA'
    if report['status'] == 'INVALID_LAYOUT':
        return 'INVALID_PARTITION_OR_FILESYSTEM'
    if report['status'] == 'UNSUPPORTED':
        return 'UNSUPPORTED_FIRMWARE_BEHAVIOR'
    if report['stage'] in ('SELECTED_FILES', 'LAB_INTEGRITY') or report['status'] == 'SELECTED_FILE_UNAVAILABLE':
        return 'SELECTED_FILE_FAILURE'
    return 'INVALID_CONFIGURATION'


def select(emmc, work, expected=None, order='0xf14', config_profile=None,
           usb=None, usb_expected=None, max_restarts=1):
    """Each present source uses its own locked read graph and acceptance manifest.

    None means operator-declared unavailable, never probed hardware. One restart
    means two complete attempts at most; budget is a lab limit, not MAX_RESTARTS.
    """
    trace = dict(schema=1, order=order, physical_eeprom_value='UNCONFIRMED_FIXTURE',
                 proxy='software firmware-BEHAVIOR proxy', usb_enumeration_performed=False,
                 max_restarts=max_restarts, attempts=[], transitions=[], selected_source=None)
    empty = dict(status='UNSUPPORTED', stage='POLICY', selection_complete=False,
                 process=dict(launched=False), reads=[], files={}, selected={}, boot_source_trace=trace)
    try:
        modes = parse_order(order)
        h.require(type(max_restarts) is int and 0 <= max_restarts <= 3,
                  'UNSUPPORTED', 'lab restart budget must be 0..3')
        # Do not permit two source labels to identify the same active file.
        if usb is not None and emmc is not None:
            h.require(Path(usb).resolve() != Path(emmc).resolve() and
                      not (Path(usb).exists() and Path(emmc).exists() and
                           Path(usb).samefile(emmc)), 'UNSUPPORTED', 'source identities alias')
        sources = {'emmc': (emmc, expected), 'usb-msd': (usb, usb_expected)}
        for cycle in range(max_restarts+1):
            for mode in modes:
                if mode == 'restart':
                    trace['transitions'].append(dict(state='RESTART', cycle=cycle,
                        next_cycle=cycle+1, executed=cycle < max_restarts))
                    if cycle == max_restarts:
                        empty.update(status='BOUNDED_RESTART', reason='lab restart budget exhausted')
                        return empty, {}
                    continue
                path, manifest = sources[mode]
                row = dict(source=mode, cycle=cycle, image=None, reads=[], classification='DEVICE_UNAVAILABLE')
                trace['attempts'].append(row)
                if path is None:
                    row['reason'] = 'operator-declared unavailable; no device enumeration performed'
                    row['next_action'] = 'NEXT_SOURCE'
                    continue
                if not isinstance(manifest, dict) or not manifest:
                    row.update(classification='MISSING_ACCEPTANCE_MANIFEST',
                               next_action='STOP_UNCERTAIN_FALLBACK')
                    empty.update(status='UNSUPPORTED', reason='present source requires independent acceptance manifest')
                    return empty, {}
                attempt_work = Path(work)/f'{cycle}-{mode}'
                attempt_work.mkdir(mode=0o700)
                report, buffers = h.select(path, attempt_work, manifest, config_profile=config_profile)
                # An active source may share immutable base data, but must not
                # itself be a backing node of the other active source.
                other = emmc if mode == 'usb-msd' else usb
                if other is not None and Path(other).exists():
                    st = Path(other).stat()
                    if any((n['identity']['device'], n['identity']['inode']) ==
                           (st.st_dev, st.st_ino) for n in report.get('overlay_chain_before', [])):
                        report.update(status='UNSUPPORTED', stage='POLICY', selection_complete=False,
                                      reason='active source aliases selected backing chain')
                        buffers = {}
                row.update(classification=classify(report), image=report.get('overlay_chain_before'),
                           reads=report['reads'], partition=next((x for x in report.get('partitions', []) if x['partition'] == 1), None),
                           status=report['status'], stage=report['stage'], reason=report.get('reason'))
                h.write_report(attempt_work/'selection.json', report)
                if report['status'] == 'SELECTED':
                    row['next_action'] = 'LAUNCH_ELIGIBLE'
                    trace['selected_source'] = mode
                    report['boot_source_trace'] = trace
                    report['selected_source_path'] = str(Path(path).resolve())
                    return report, buffers
                # No guessed fallback from failures after a device is present.
                row['next_action'] = 'STOP_UNCERTAIN_FALLBACK'
                report['boot_source_trace'] = trace
                report['firmware_fallback'] = 'UNSUPPORTED_UNCERTAIN; no next source or guest launch'
                return report, {}
    except (h.Outcome, OSError, ValueError) as exc:
        empty.update(status=getattr(exc, 'code', 'READ_ERROR'), reason=str(exc))
    return empty, {}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--emmc', type=Path)
    p.add_argument('--usb', type=Path, help='disposable regular QCOW2 synthetic USB-MSD; no host USB access')
    p.add_argument('--expected', type=Path)
    p.add_argument('--usb-expected', type=Path)
    p.add_argument('--order', default='0xf14')
    p.add_argument('--max-restarts', type=int, default=1)
    p.add_argument('--config-profile', choices=('cm5-headless-lab',))
    p.add_argument('--work', type=Path, required=True)
    a = p.parse_args(); work = h.private_dir(a.work)
    load = lambda x: json.loads(x.read_text()) if x else None
    report, _ = select(a.emmc, work, load(a.expected), a.order, a.config_profile,
                       a.usb, load(a.usb_expected), a.max_restarts)
    h.write_report(work/'decision.json', report)
    print(json.dumps(dict(status=report['status'], trace=str(work/'decision.json'))))
    return 0 if report['status'] == 'SELECTED' else 1


if __name__ == '__main__':
    sys.exit(main())
