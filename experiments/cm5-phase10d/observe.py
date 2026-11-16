# Appended to the Phase10C public observer in guest RAM; no guest source file.
import mmap

def direct_digest(path, block):
    # Anonymous mmap provides page-aligned memory on this 16KiB-page kernel.
    # O_DIRECT avoids the block-device page cache, including the full OS scan.
    fd = os.open(path, os.O_RDONLY | os.O_DIRECT)
    try:
        with mmap.mmap(-1, 4096) as buf:
            count = os.preadv(fd, [buf], block*4096)
            if count != 4096:
                raise OSError('short target read: '+str(count))
            return hashlib.sha256(buf).hexdigest()
    finally:
        os.close(fd)

r['target_read'] = dict(method='O_DIRECT aligned preadv 4096; raw first, verified second',
    block_index=FAULT['block_index'], role=FAULT['role'],
    uptime_start=float(Path('/proc/uptime').read_text().split()[0]))
try:
    r['target_read']['raw_sha256'] = direct_digest('/dev/mmcblk0p'+str(FAULT['partition']), FAULT['block_index'])
    r['target_read']['verified_sha256'] = direct_digest('/dev/mapper/cm5_'+FAULT['role']+'_verified', FAULT['block_index'])
except OSError as error:
    r['target_read']['error'] = str(error)
r['target_read']['uptime_end'] = float(Path('/proc/uptime').read_text().split()[0])
