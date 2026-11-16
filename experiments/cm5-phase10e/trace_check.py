"""Check logical CS boundaries and synthetic byte streams, not electrical timing."""
import hashlib
import re


def check(lines, messages):
    segments=[];active=None;tx=bytearray();rx=bytearray();errors=[]
    def flush():
        if tx:
            segments.append(dict(length=len(tx),tx_sha256=hashlib.sha256(tx).hexdigest(),rx_sha256=hashlib.sha256(rx).hexdigest()))
            tx.clear();rx.clear()
    for line in lines:
        m=re.search(r'dw_apb_ssi_cs selected=0x([0-9a-f]+)',line)
        if m:
            selected=int(m[1],16)
            if selected!=active:
                flush();active=selected
            if selected not in (0,1):errors.append('unexpected chip select')
        m=re.search(r'dw_apb_ssi_transfer cs=0x([0-9a-f]+) bits=(\d+) tx=0x([0-9a-f]+) rx=0x([0-9a-f]+)',line)
        if m:
            cs,bits,a,b=(int(m[1],16),int(m[2]),int(m[3],16),int(m[4],16))
            if cs!=1 or active!=1 or bits!=8:errors.append('frame outside CS0/eight-bit mode')
            if b!=a^0xa5:errors.append('incorrect synthetic response')
            tx.append(a&255);rx.append(b&255)
    flush()
    expected=[{k:m[k] for k in ('length','tx_sha256','rx_sha256')} for m in messages]
    if segments!=expected:errors.append('CS-delimited segments do not equal submitted message hashes/lengths')
    return dict(status='PASS' if not errors and bool(messages) else 'FAIL',segments=segments,expected_messages=len(expected),errors=sorted(set(errors)),electrical_timing_validated=False)
