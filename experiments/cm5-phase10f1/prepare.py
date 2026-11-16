#!/usr/bin/env python3
"""Establish independent golden-backed acceptance baseline BEFORE fault runs.

Local experiment only. Does not modify golden/capture or derive acceptance from
a fault overlay. All outputs are private; overlay source bytes remain private.
"""
import argparse
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent/'cm5-phase10f'))
import handoff as h
from block_reader import BIN, run

GOLDEN = Path('/home/aweso/cm5-v8-lab/golden/cm5-emmc-userarea.img')
ASSETS = Path('/home/aweso/cm5-phase10-private/physical-boot/boot-assets')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--work',type=Path,required=True)
    a=p.parse_args();w=h.private_dir(a.work)
    before={str(p):h.identity(p) for p in [GOLDEN,*ASSETS.iterdir()]}
    h.write_report(w/'inputs-before.json',before)
    assert before[str(GOLDEN)]['sha256']=='e2fb1a85c2652838793e58f8b13ef908e2e4a4c4295e27297ce742287f69cb87'
    entries=Path('/home/aweso/cm5-phase10-private/physical-boot.sha256').read_text().splitlines()
    capture={Path(line.split()[1]).name:line.split()[0] for line in entries}
    assert all(before[str(p)]['sha256']==capture[p.name] for p in ASSETS.iterdir())
    overlay=w/'emmc.qcow2'
    run([BIN/'qemu-img','create','-f','qcow2','-F','raw','-b',GOLDEN,overlay])
    report=dict(reads=[],files={});reader=h.LogicalReader(overlay,report,w)
    expected={}
    try:
        fat=h.StrictFAT(reader,h.partitions(reader))
        report['root_files']=list(fat.directory())
        for p in ASSETS.iterdir():
            data=fat.file(p.name)
            assert h.sha(data)==capture[p.name]
            expected[p.name]=h.sha(data)
        for name in ['README','vc4-kms-v3d.dtbo','vc4-kms-v3d-pi5.dtbo',
                     'dwc2.dtbo','nospi10.dtbo','overlay_map.dtb']:
            data=fat.file('overlays/'+name)
            (w/name).write_bytes(data)
            expected['overlays/'+name]=h.sha(data)
        reader.verify_unchanged()
    finally:
        reader.close()
        h.write_report(w/'reference-read.json',report)
    h.write_report(w/'accepted-hashes.json',expected)
    h.write_report(w/'baseline-policy.json',dict(
        source='Independently accepted unchanged golden; capture manifest checked; established before fault injection',
        inputs=before,reader=report.get('block_transport','NBD')))
    print(w/'accepted-hashes.json')


if __name__=='__main__':main()
