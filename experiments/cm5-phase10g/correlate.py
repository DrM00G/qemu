#!/usr/bin/env python3
"""Independent diagnostic correlation. Concatenated bytes NEVER establish framing.

Associates trace byte positions with submitted messages, then SSI enable epochs.
Virtual timestamps are QEMU clock observations, not physical elapsed times.
"""
import argparse
import bisect
import hashlib
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'cm5-phase10e'))
from trace_check import check


def fields(text):
    return {k:int(v, 16 if v.startswith('0x') else 10)
            for k,v in re.findall(r'(\w+)=(-?(?:0x[0-9a-f]+|[0-9]+))',text)}


def correlate(lines, messages):
    ends=[]; total=0
    for message in messages:
        total += message['length']; ends.append(total)
    tx=bytearray(); rx=bytearray(); segments=[]; active=0; current=None
    events=[]; epoch=0; epochs={}; packet=None; exhausted=False
    notifications=[]; deliveries=[]
    for number,line in enumerate(lines,1):
        m=re.search(r'dw_apb_ssi_cs selected=0x([0-9a-f]+)',line)
        if m:
            active=int(m[1],16)
            if active:
                current=dict(index=len(segments),start=len(tx),end=len(tx))
                segments.append(current)
        m=re.search(r'dw_apb_ssi_transfer cs=0x([0-9a-f]+) bits=(\d+) tx=0x([0-9a-f]+) rx=0x([0-9a-f]+)',line)
        if m:
            assert int(m[2])==8 and active==int(m[1],16)==1
            tx.append(int(m[3],16));rx.append(int(m[4],16))
            current['end']=len(tx)
            epochs.setdefault(epoch,set()).add(bisect.bisect_right(ends,len(tx)-1))
        m=re.search(r'dw_apb_ssi_boundary (\S+) (.*)',line)
        if m:
            exhausted |= m[1]=='CAPTURE_EXHAUSTED'
            f=fields(m[2]);epoch=f['epoch'];state=f['state']
            packet=dict(line=number,event=m[1],cursor=len(tx),**f,
                ser=state&15,enabled=bool(state&16),busy=bool(state&32),
                irq=bool(state&64),tx_threshold=(state>>8)&63,rx_threshold=(state>>16)&63)
            events.append(packet)
        m=re.search(r'dw_apb_ssi_timer (\S+) (.*)',line)
        if m and packet is not None:
            packet['timer']=fields(m[2])
        m=re.search(r'rp1_spi_notify (.*)',line)
        if m:
            f=fields(m[1]);events.append(dict(event='rp1-notify',line=number,cursor=len(tx),epoch=epoch,**f));notifications.append(f)
        m=re.search(r'rp1_spi_state (\S+) (.*)',line)
        if m:
            f=fields(m[2]);events.append(dict(event='rp1-'+m[1],line=number,cursor=len(tx),epoch=epoch,**f))
        m=re.search(r'bcm2712_mip_timed (.*)',line)
        if m:
            f=fields(m[1]);events.append(dict(event='mip-delivery',line=number,cursor=len(tx),epoch=epoch,**f));deliveries.append(f)
            if (notifications and notifications[-1]['vector']==f['vector'] and
                    'delivery_virtual_ns' not in notifications[-1] and f['delivered']):
                notifications[-1]['delivery_virtual_ns']=f['virtual_ns']
                notifications[-1]['notify_to_mip_virtual_ns']=f['virtual_ns']-notifications[-1]['virtual_ns']
    oracle=check(lines,messages)
    rows=[];start=0
    for i,message in enumerate(messages):
        end=ends[i]
        actual=[s for s in segments if s['end']>start and s['start']<end]
        source_epochs=[e for e,indices in epochs.items() if i in indices]
        related=[e for e in events if e['epoch'] in source_epochs]
        drains=[e for e in related if e['event']=='complete-after' and e['tx']==0]
        gaps=[]
        for drain in drains:
            refill=next((e for e in related if e['line']>drain['line'] and e['event']=='refill-idle'),None)
            if refill:
                gaps.append(dict(word=drain['word'],drain_virtual_ns=drain['virtual_ns'],
                    refill_virtual_ns=refill['virtual_ns'],gap_virtual_ns=refill['virtual_ns']-drain['virtual_ns'],
                    callback_lateness_ns=drain['timer']['callback_ns']-drain['timer']['deadline_ns']))
        framed=len(actual)==1 and actual[0]['start']==start and actual[0]['end']==end
        byte_identity=(hashlib.sha256(tx[start:end]).hexdigest()==message['tx_sha256'] and
                       hashlib.sha256(rx[start:end]).hexdigest()==message['rx_sha256'])
        row=dict(message=i,length=message['length'],epochs=source_epochs,
            segments=[dict(index=s['index'],message_offset=max(start,s['start'])-start,
                           length=min(end,s['end'])-max(start,s['start'])) for s in actual],
            strict_framing=framed,diagnostic_concatenated_byte_identity=byte_identity,
            within_message_drain_refill=gaps)
        if not framed or i in (0,3,32,35):row['events']=related
        rows.append(row);start=end
    return dict(schema=1,status='PASS' if oracle['status']=='PASS' and not exhausted else 'PARTIAL',
        strict_oracle=oracle['status'],diagnostic_only=True,capture_exhausted=exhausted,
        submitted_messages=len(messages),completed_bytes=len(tx),cs_segments=len([s for s in segments if s['end']>s['start']]),
        failed_messages=[r['message'] for r in rows if not r['strict_framing']],
        ssi_rates=[dict(input_hz=hz,baud=baud,divider_speed_hz=hz/baud)
                   for hz,baud in sorted({(e['timer']['input_hz'],e['timer']['baud'])
                       for e in events if e['event']=='arm' and e.get('timer',{}).get('baud',0)})],
        paired_notifications=sum('delivery_virtual_ns' in n for n in notifications),
        max_notify_to_mip_virtual_ns=max((n.get('notify_to_mip_virtual_ns',0) for n in notifications),default=None),
        notifications=len(notifications),mip_deliveries=sum(d['delivered'] for d in deliveries),
        undelivered_mip=sum(not d['delivered'] for d in deliveries),messages=rows,
        clock_semantics='QEMU_CLOCK_VIRTUAL; includes emulator/trace overhead under host-clock TCG; no physical timing inference')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();users=json.loads((a.run/'userspace.json').read_text())
    messages=[m for u in users for m in u.get('native_rp1',{}).get('spi',{}).get('messages',[])]
    lines=(a.run/'hardware.log').read_text().splitlines()
    result=correlate(lines,messages)
    result['guest_wall_seconds']=json.loads((a.run/'result.json').read_text())['wall_seconds']
    a.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='messages'}))


if __name__=='__main__':main()
