#!/usr/bin/env python3
"""Private audit only: inspect same active overlay, never stage captured host bytes."""
import argparse
import copy
import json
import os
from pathlib import Path
import struct

from block_reader import BIN, LogicalReader, run
from handoff import StrictFAT, private_dir, select, write_report
from preboot import DEFAULTS, Outcome, identity, partitions
from validate import validate


def directories(fat):
    # Audit raw root directory slots for short directory names (not file selection).
    chunks = ([(fat.root_offset, fat.roots*32)] if fat.bits == 16 else
              ((fat.cluster_offset(c),fat.cluster_bytes) for c in fat.chain(fat.root_cluster)))
    count = 0
    result = []
    for offset,length in chunks:
        count += length
        if count > 4*1024*1024:
            raise Outcome('UNSUPPORTED','directory audit bound')
        data = fat.r.read(offset,length,'audit root directory slots')
        for i in range(0,len(data),32):
            e = data[i:i+32]
            if not e[0]:
                return result
            if e[0] == 229 or e[11] == 15 or not e[11]&16:
                continue
            result.append(dict(short_name=e[:11].decode('ascii',errors='replace').strip(),
                cluster=struct.unpack_from('<H',e,26)[0] | (struct.unpack_from('<H',e,20)[0]<<16)))
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--work',type=Path,required=True)
    p.add_argument('--golden',type=Path,default=Path('/home/aweso/cm5-v8-lab/golden/cm5-emmc-userarea.img'))
    p.add_argument('--assets',type=Path,default=Path('/home/aweso/cm5-phase10-private/physical-boot/boot-assets'))
    a = p.parse_args()
    os.umask(0o077)
    work = private_dir(a.work)
    before = {str(path):identity(path) for path in [a.golden,*a.assets.iterdir()] if path.is_file()}
    write_report(work/'inputs-before.json',before)
    overlay = work/'emmc.qcow2'
    command = [BIN/'qemu-img','create','-f','qcow2','-F','raw','-b',a.golden,overlay]
    run(command)
    report = dict(reads=[],files={},note='AUDIT candidates only; NOT completed firmware/config selection',
                  command=[str(x) for x in command])
    reader = LogicalReader(overlay,report,work)
    try:
        fat = StrictFAT(reader,partitions(reader))
        report['root_files'] = list(fat.directory())
        report['root_directories'] = directories(fat)
        overlay_dir = next((d for d in report['root_directories'] if d['short_name'].upper()=='OVERLAYS'),None)
        if overlay_dir and fat.bits == 32:
            sub = copy.copy(fat); sub.root_cluster = overlay_dir['cluster']
            report['overlay_files'] = list(sub.directory())
        report['comparison'] = {}
        for name in ['config.txt',*DEFAULTS.values()]:
            item = {}
            try:
                data = fat.file(name)
                item.update(exists_in_active_overlay=True,sha256=report['files'][name]['sha256'],bytes=len(data))
                host = a.assets/name
                if host.is_file():
                    item['host_capture_sha256'] = before[str(host)]['sha256']
                    item['equals_separate_host_capture'] = item['sha256']==item['host_capture_sha256']
                kind = next((k for k,v in DEFAULTS.items() if v==name),None)
                if kind:
                    try: item['validation'] = validate(kind,data)
                    except Outcome as exc: item['validation'] = dict(status=exc.code,reason=str(exc))
                if name == 'config.txt':
                    # Private output only, source config is never copied into checkout.
                    (work/'active-config.txt').write_bytes(data)
                    report['config_directives'] = [dict(line=i,text=line) for i,line in enumerate(
                        data.decode('ascii').splitlines(),1) if line.strip() and not line.lstrip().startswith('#')]
            except Outcome as exc:
                item.update(exists_in_active_overlay=False,status=exc.code,reason=str(exc))
            report['comparison'][name] = item
        reader.verify_unchanged()
    finally:
        reader.close()
        write_report(work/'audit.json',report)
    selection_work = work/'selection'; selection_work.mkdir()
    selection,_ = select(overlay,selection_work)
    write_report(selection_work/'selection.json',selection)
    after = {str(path):identity(path) for path in [a.golden,*a.assets.iterdir()] if path.is_file()}
    write_report(work/'inputs-after.json',after)
    summary = dict(private_audit=str(work/'audit.json'), golden_and_host_assets_unchanged=before==after,
                   selection_status=selection['status'],selection_reason=selection.get('reason'),
                   launched=False,comparison=report['comparison'],overlay_file_count=len(report.get('overlay_files',[])))
    write_report(work/'summary.json',summary)
    print(json.dumps(summary,indent=2))


if __name__ == '__main__':
    main()
