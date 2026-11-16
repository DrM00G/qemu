#!/usr/bin/env python3
"""Bounded disposable BOOT faults; run only after clean selected V8 PASS.

Private manifests/mutations/commands stay outside checkout. Public evidence
records outcomes separately. No physical firmware behavior is inferred.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import struct
import sys

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'cm5-phase10f'))
import handoff as h
from block_reader import BIN,run,REPO
from prepare import GOLDEN


def verify_mutation(disk, offset, expected, destination):
    # QEMU raw offset/size views require sector alignment. Export one sector,
    # then compare the exact mutated byte(s); never convert the full image.
    sector=offset//512*512
    assert offset+len(expected)<=sector+512 and not destination.exists()
    run([BIN/'qemu-img','convert','--image-opts','-O','raw',
         f'driver=raw,offset={sector},size=512,file.driver=qcow2,file.file.driver=file,file.file.filename={disk}',destination])
    destination.chmod(0o400)
    actual=destination.read_bytes()[offset-sector:offset-sector+len(expected)]
    assert actual==expected
    return h.sha(actual)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--clean',type=Path,required=True)
    p.add_argument('--expected',type=Path,required=True)
    p.add_argument('--work',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--boot-selection-policy', choices=('emmc-only','eeprom-fixture-0xf14'), default='emmc-only')
    p.add_argument('--cases',nargs='+',default=['mbr','geometry','missing-kernel','gzip',
        'missing-initramfs','malformed-initramfs','dtb','digest','outside'])
    a=p.parse_args();os.umask(0o077)
    clean=json.loads((a.clean/'result.json').read_text())
    base=json.loads((a.clean/'recovery-result.json').read_text())
    native=json.loads((a.clean/'native-result.json').read_text())
    assert clean['status']=='PASS' and base['status']=='PASS_CLEAN' and native['status']=='PASS'
    selection=json.loads(Path(clean['boot_selection_report']).read_text())
    w=h.private_dir(a.work);out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    outcomes=[]
    def file_byte(kind,index=0):
        meta=selection['files'][selection['selected'][kind]]
        for e in meta['extents']:
            if index < e['length']:return e['offset']+index
            index-=e['length']
        raise ValueError('file offset outside extents')
    def missing(kind):
        meta=selection['files'][selection['selected'][kind]]
        # Rename first UTF16 code unit of LFN ordinal 1 (adjacent to short slot).
        # LFN checksum covers unchanged short name, so directory remains valid.
        off=meta['directory_entry_offset']-32
        with GOLDEN.open('rb') as f:f.seek(off);entry=f.read(32)
        assert entry[11]==15 and entry[0]&31==1
        return off+1,b'x\0'
    for case in a.cases:
        d=w/case;d.mkdir();disk=d/'emmc.qcow2'
        run([BIN/'qemu-img','create','-f','qcow2','-F','raw','-b',GOLDEN,disk])
        if case=='mbr':offset,data=510,b'\0\0'
        elif case=='geometry':offset,data=454,b'\xff'*8
        elif case=='missing-kernel':offset,data=missing('kernel')
        elif case=='gzip':
            n=selection['files'][selection['selected']['kernel']]['size']
            offset=file_byte('kernel',n-8)
            with GOLDEN.open('rb') as f:f.seek(offset);data=bytes([f.read(1)[0]^1])
        elif case=='missing-initramfs':offset,data=missing('initramfs')
        elif case=='malformed-initramfs':offset,data=file_byte('initramfs'),b'X'
        elif case=='dtb':offset,data=file_byte('dtb'),b'\0'
        elif case=='digest':
            offset=file_byte('cmdline');data=b'X'
        elif case=='outside':
            # Select an independently audited UNUSED file (issue.txt), not free
            # padding. Prove its payload byte is outside the actual clean read
            # ledger, and verify that remains true in this fault run.
            audit=json.loads(Path('/home/aweso/cm5-v8-lab/phase10f/f-captured-audit-20261114-01/audit.json').read_text())
            unused=next(e for e in audit['root_files'] if e['name']=='issue.txt')
            p1=next(p for p in selection['partitions'] if p['partition']==1)
            base=p1['start']*512
            with GOLDEN.open('rb') as f:
                f.seek(base);bpb=f.read(512)
                f.seek(unused['directory_entry_offset']);entry=f.read(32)
                assert entry[:11]==b'ISSUE   TXT'
                cluster=struct.unpack_from('<H',entry,26)[0] | (struct.unpack_from('<H',entry,20)[0]<<16)
                assert cluster==unused['cluster']
                data_sector=struct.unpack_from('<H',bpb,14)[0]+bpb[16]*struct.unpack_from('<I',bpb,36)[0]
                offset=base+(data_sector+(cluster-2)*bpb[13])*512
                f.seek(offset);data=bytes([f.read(1)[0]^1])
            assert all(not (r['offset']<=offset<r['offset']+r['returned']) for r in selection['reads'])
        else:raise ValueError(case)
        patch=d/'patch.bin';patch.write_bytes(data)
        run([BIN/'qemu-io','-f','qcow2','-c',f'write -s {patch} {offset} {len(data)}',disk])
        h.write_report(d/'mutation.json',dict(case=case,offset=offset,bytes=len(data),sha256=h.sha(data)))
        output=out/(out.name+'-'+case)
        command=[sys.executable,str(REPO/'experiments/cm5-phase10c/run.py'),
            '--control-pipes','--dma','--batch','--profile','native','--boot-selection-policy',a.boot_selection_policy,
            '--boot-config-profile','cm5-headless-lab','--boot-overlay',str(disk),
            '--boot-expected',str(a.expected.resolve()),'--timeout','600','--output',str(output)]
        if case=='outside':command+=['--debug-shell','--poweroff-after-validation','--recovery-case','clean','--native-rp1-test']
        h.write_report(d/'runner-command.json',command)
        with (d/'runner.log').open('xb') as stream:r=subprocess.run(command,stdout=stream,stderr=subprocess.STDOUT)
        result=json.loads((output/'result.json').read_text())
        if case!='outside':
            assert r.returncode==1 and result['status']=='BOOT_SELECTION_STOPPED'
            assert not result['process']['launched'] and not (output/'process.json').exists()
            sel=json.loads(Path(result['private_report']).read_text())
            assert 'exports' not in sel
            record=dict(case=case,passed=True,selection=sel['status'],stage=sel['stage'],
                guest_launched=False,kernel_entry=False,root_verification='NOT_REACHED',operational_survival='NOT_REACHED')
        else:
            sel=json.loads(Path(result['boot_selection_report']).read_text())
            assert all(not (r['offset']<=offset<r['offset']+r['returned']) for r in sel['reads'])
            recovered=json.loads((output/'recovery-result.json').read_text())
            native=json.loads((output/'native-result.json').read_text())
            assert result['status']=='PASS' and recovered['status']=='PASS_CLEAN' and native['status']=='PASS'
            readback=verify_mutation(disk,offset,data,d/'mutated-sector-after-guest.bin')
            record=dict(case=case,passed=True,selection='SELECTED',guest_launched=True,
                kernel_entry=result['kernel_entry'],root_verification='BOTH_VALID',operational_survival='PASS_WITH_LOGS_AND_SPI',
                unused_file='issue.txt',mutation_retained_sha256=readback)
        record['result']=str(output/'result.json');outcomes.append(record)
        h.write_report(out/'result.json',dict(status='RUNNING',outcomes=outcomes))
        print(json.dumps(record),flush=True)
    h.write_report(out/'result.json',dict(status='PASS',outcomes=outcomes,scope='software proxy only; no boot-ROM/EEPROM behavior'))


if __name__=='__main__':main()
