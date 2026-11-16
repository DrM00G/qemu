"""Runs only inside the disposable QEMU guest via original GPIO cdev v1 ABI."""
import errno
import fcntl
import glob
import json
import os
from pathlib import Path
import select
import struct


def irq_counts():
    rows = []
    for line in Path('/proc/interrupts').read_text().splitlines():
        if 'pinctrl-rp1' in line:
            counts = []
            for word in line.split(':', 1)[1].split():
                if not word.isdecimal():
                    break
                counts.append(int(word))
            rows.append(dict(irq=line.split(':')[0].strip(), counts=counts))
    return rows


handles = []
try:
    found = []
    seen = set()
    discovered = []
    for path in sorted(glob.glob('/dev/gpiochip*')):
        fd = os.open(path, os.O_RDONLY)
        buf = bytearray(68)
        fcntl.ioctl(fd, 0x8044b401, buf, True)
        name, label, count = struct.unpack('=32s32sI', buf)
        identity = os.fstat(fd).st_rdev
        discovered.append(dict(path=path,label=label.rstrip(b'\0').decode(),
                               name=name.rstrip(b'\0').decode(),lines=count,rdev=identity))
        if label.rstrip(b'\0') == b'pinctrl-rp1' and identity not in seen:
            seen.add(identity)
            found.append((path, fd, count))
        else:
            os.close(fd)
    if len(found) != 1:
        raise RuntimeError('expected exactly one original pinctrl-rp1 GPIO chip')
    path, chip, count = found[0]
    handles.append(chip)
    rejected = []
    for line in (19, 22, 28, 53, 54):
        request = bytearray(struct.pack('=64II64B32sII', line, *([0]*63),
            2, *([0]*64), b'cm5-i-reserved', 1, 0))
        try:
            fcntl.ioctl(chip, 0xc16cb403, request, True)
        except OSError as error:
            rejected.append(dict(line=line, errno=error.errno))
        else:
            os.close(struct.unpack_from('=I', request, 360)[0])
            raise RuntimeError('reserved/unsupported GPIO request succeeded')
    request = bytearray(struct.pack('=64II64B32sII', 20, *([0]*63),
        2, *([0]*64), b'cm5-i-output', 1, 0))
    assert len(request) == 364
    fcntl.ioctl(chip, 0xc16cb403, request, True)
    out = struct.unpack_from('=I', request, 360)[0]
    handles.append(out)
    duplicate = bytearray(request)
    try:
        fcntl.ioctl(chip, 0xc16cb403, duplicate, True)
    except OSError as error:
        if error.errno != errno.EBUSY:
            raise
        ownership_rejected = error.errno
    else:
        os.close(struct.unpack_from('=I', duplicate, 360)[0])
        raise RuntimeError('exclusive GPIO ownership was not enforced')
    event = bytearray(struct.pack('=III32sI', 21, 1, 3, b'cm5-i-input', 0))
    fcntl.ioctl(chip, 0xc030b404, event, True)
    inp = struct.unpack_from('=I', event, 44)[0]
    handles.append(inp)
    before = irq_counts()
    records = []
    for value in (1, 0, 1, 0):
        values = bytearray(64); values[0] = value
        fcntl.ioctl(out, 0xc040b409, values, True)
        if not select.select([inp], [], [], 2)[0]:
            raise RuntimeError('GPIO21 edge interrupt timed out')
        data = os.read(inp, 16)
        stamp, edge = struct.unpack_from('=QI', data)
        output = bytearray(64); input_value = bytearray(64)
        fcntl.ioctl(out, 0xc040b408, output, True)
        fcntl.ioctl(inp, 0xc040b408, input_value, True)
        if edge != (1 if value else 2) or output[0] != value or input_value[0] != value:
            raise RuntimeError('GPIO direction/value/edge mismatch')
        records.append(dict(output=value,input=input_value[0],edge=edge,
                            guest_monotonic_ns=stamp))
    extra = bool(select.select([inp], [], [], 0.05)[0])
    after = irq_counts()
    delta = sum(sum(r['counts']) for r in after)-sum(sum(r['counts']) for r in before)
    if extra or delta < 4:
        raise RuntimeError('unexpected extra event or missing GPIO IRQ accounting')
    driver = Path('/sys/bus/platform/devices/1f000d0000.gpio/driver')
    result = dict(status='PASS',chip=path,label='pinctrl-rp1',ngpio=count,
        discovered_chips=discovered,
        driver=driver.resolve().name if driver.exists() else None,
        stimulus='synthetic QEMU GPIO20->21 loopback; no physical wiring claimed',
        clock='guest-monotonic-ns',records=records,reserved_rejections=rejected,
        irq_before=before,irq_after=after,irq_delta=delta,no_extra_event=not extra,ownership_rejected=ownership_rejected)
except Exception as error:
    result = dict(status='ERROR',error=str(error),discovered_chips=locals().get('discovered',[]))
finally:
    for fd in reversed(handles):
        os.close(fd)
print(json.dumps(result))
