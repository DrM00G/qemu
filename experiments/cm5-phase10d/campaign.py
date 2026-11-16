"""Opt-in physical-kernel logical faults; local research, not upstream code."""
import gzip
import hashlib
import json
from pathlib import Path
import re
import stat
import subprocess
import sys

REPO = Path(__file__).resolve().parents[2]
IMG = REPO/'build-arm64-phase1/qemu-img'
IO = REPO/'build-arm64-phase1/qemu-io'
PARTITIONS = {'os': (2, 545259520, 10737418240), 'fsw': (5, 11283726336, 536870912)}
CASES = {'clean': ('os', 0, False), 'os0': ('os', 0, True),
         'os-far': ('os', 262144, True), 'fsw0': ('fsw', 0, True),
         'no-fec': ('os', 0, True)}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2)+'\n')


def regular(path):
    if not stat.S_ISREG(path.stat().st_mode):
        raise ValueError('Only regular files allowed')


def target(case):
    role, block, inject = CASES[case]
    partition, start, size = PARTITIONS[role]
    if not 0 <= block*4096 <= size-4096:
        raise ValueError('Block outside partition')
    return dict(case=case, role=role, partition=partition, block_index=block,
                partition_offset=start, partition_bytes=size, offset=start+block*4096,
                length=4096, inject=inject, pattern_byte=90 if inject else None,
                fec_roots=0 if case == 'no-fec' else 2)


def block_read(overlay, offset, size, dest):
    regular(overlay)
    if dest.exists():
        raise ValueError('Refusing to overwrite block export')
    subprocess.run([str(IMG), 'convert', '--image-opts', '-O', 'raw',
                    f'driver=raw,offset={offset},size={size},file.driver=qcow2,file.file.driver=file,file.file.filename={overlay}', str(dest)],
                   check=True, capture_output=True)
    dest.chmod(0o400)
    data = dest.read_bytes()
    assert len(data) == size
    return data


def prepare(case, out, lab, golden, overlay):
    regular(golden)
    regular(overlay)
    if golden.resolve() == overlay.resolve() or REPO in overlay.resolve().parents:
        raise ValueError('Faults require a private disposable overlay outside checkout')
    chain = json.loads(subprocess.check_output([str(IMG), 'info', '--output=json', '--backing-chain', str(overlay)]))
    if len(chain) != 2 or chain[0]['format'] != 'qcow2' or chain[1]['format'] != 'raw' or Path(chain[1]['filename']).resolve() != golden.resolve():
        raise ValueError('Unexpected backing chain')
    t = target(case)
    with golden.open('rb') as f:
        f.seek(t['offset']); original = f.read(4096)
    before = block_read(overlay, t['offset'], 4096, lab/'target-before.bin')
    assert before == original
    t['golden_sha256'] = digest(original)
    t['raw_before_sha256'] = digest(before)
    if t['inject']:
        cmd = [str(IO), '-f', 'qcow2', '-c', f"write -P 0x5a {t['offset']} 4096", str(overlay)]
        r = subprocess.run(cmd, check=True, capture_output=True, text=True)
        (out/'injection-tool.log').write_text(r.stdout+r.stderr)
        t['injection_command'] = cmd
    after = block_read(overlay, t['offset'], 4096, lab/'target-after-injection.bin')
    assert after == (b'\x5a'*4096 if t['inject'] else original)
    assert not t['inject'] or after != original
    t.update(raw_after_injection_sha256=digest(after),
             physical_guest_sectors=list(range(t['offset']//512, t['offset']//512+8)),
             injected_bytes={'count': 4096, 'encoding': 'repeat-u8', 'value': 90} if t['inject'] else None,
             overlay_path=str(overlay), backing_chain=chain,
             cache_note='Injection completed and writer closed before QEMU starts; fresh guest caches')
    # Compare the full COW allocation containing a fault, not just its 4KiB.
    cluster = chain[0]['cluster-size']
    t['fault_cluster_offset'] = t['offset']//cluster*cluster
    t['fault_cluster_bytes'] = cluster
    t['fault_cluster_before_guest_sha256'] = digest(block_read(overlay, t['fault_cluster_offset'], cluster, lab/'fault-cluster-before-guest.bin'))
    t['pre_guest_extents'] = json.loads(subprocess.check_output([str(IMG), 'map', '--output=json', str(overlay)]))
    save(out/'fault.json', t)
    return t


def observer(code, fault):
    extra = (REPO/'experiments/cm5-phase10d/observe.py').read_text()
    target_fields = {k: fault[k] for k in ('role', 'partition', 'block_index')}
    return code.replace("print('P10C_USER_JSON='", 'FAULT = '+repr(target_fields)+'\n'+extra+"\nprint('P10C_USER_JSON='")


def correction_events(serial):
    return [dict(timestamp=float(m[1]), device=m[2], fec_byte_base=int(m[3]), corrected_errors=int(m[4]))
            for m in re.finditer(r'\[\s*([\d.]+)\] device-mapper: verity-fec: (\d+:\d+): FEC (\d+): corrected (\d+) errors', serial)]


def fec_rsb_base(fault):
    # dm-verity-fec.c logs rsb, not the absolute data-block byte offset.
    protected_blocks = {'os': 2642083, 'fsw': 132105}[fault['role']]
    roots = fault['fec_roots']
    if roots != 2:
        raise ValueError('RS matching only established for captured roots2')
    rounds = (protected_blocks + (255-roots)-1)//(255-roots)
    return (fault['block_index'] % rounds)*4096


def classify(checks, injected, nofec=False, timed_out=False):
    if timed_out or not checks:
        return 'INCONCLUSIVE'
    if nofec:
        return 'EXPECTED_VERITY_REJECTION' if all(checks.values()) else 'INCONCLUSIVE'
    if all(checks.values()):
        return 'PASS_RECOVERED' if injected else 'PASS_CLEAN'
    return 'INCONCLUSIVE'


def finish(out, lab, golden, overlay, fault, run):
    serial = (out/'serial.log').read_text(errors='replace')
    events = correction_events(serial)
    users = json.loads((out/'userspace.json').read_text()) if (out/'userspace.json').exists() else []
    endraw = block_read(overlay, fault['offset'], 4096, lab/'target-after-guest.bin')
    aftercluster = digest(block_read(overlay, fault['fault_cluster_offset'], fault['fault_cluster_bytes'], lab/'fault-cluster-after-guest.bin'))
    extents = json.loads(subprocess.check_output([str(IMG), 'map', '--output=json', str(overlay)]))
    own = [e for e in extents if e['depth'] == 0 and e.get('present')]
    pre = [e for e in fault['pre_guest_extents'] if e['depth'] == 0 and e.get('present')]
    def logs(e):
        return 11821645824 <= e['start'] and e['start']+e['length'] <= 12895387648
    def prior(e):
        return any(p['start'] <= e['start'] and e['start']+e['length'] <= p['start']+p['length'] for p in pre)
    checks = dict(inputs_unchanged=run['inputs_unchanged'], kernel_entry=run['kernel_entry'],
                  initramfs=run['initramfs'], emmc_partitions=run['emmc_partitions'],
                  normal_shutdown=run['returncode'] == 0 and not run['timeout'],
                  raw_target_unchanged_after_injection=digest(endraw) == fault['raw_after_injection_sha256'],
                  fault_cluster_no_guest_content_delta=aftercluster == fault['fault_cluster_before_guest_sha256'],
                  new_allocations_only_logs=all(logs(e) or prior(e) for e in own))
    persistence = False
    if users and run['returncode'] == 0:
        subprocess.run([str(IMG), 'convert', '--image-opts', '-O', 'raw',
            f'driver=raw,offset=11821645824,size=1073741824,file.driver=qcow2,file.file.driver=file,file.file.filename={overlay}',
            str(lab/'logs.ext4')], check=True, capture_output=True)
        (lab/'logs.ext4').chmod(0o400)
        r = subprocess.run(['debugfs', '-R', f'dump /phase10c-public-diagnostic-01.dat {lab}/diagnostic.dat', str(lab/'logs.ext4')], capture_output=True, text=True)
        (out/'persistence-tool.log').write_text(r.stdout+r.stderr)
        persistence = (lab/'diagnostic.dat').exists() and (lab/'diagnostic.dat').read_bytes() == bytes((i*31+7)%251 for i in range(4096))
    if fault['case'] == 'no-fec':
        checks.update(no_fec_table='P10D_NOFEC_TABLE=' in serial and bool(re.search(r'P10D_NOFEC_TABLE=0 20971520 verity [^\r\n]+', serial)),
                      verified_read_rejected='P10D_NOFEC_READ_RC=1' in serial,
                      explicit_eio='Input/output error' in serial,
                      corrupt_status=bool(re.search(r'P10D_NOFEC_STATUS=0 20971520 verity C', serial)),
                      no_systemd=not run['systemd_pid1'],
                      explicit_refusal='P10D_EXPECTED_ROOT_REJECTION=1' in serial,
                      no_fec_correction=not events)
        fsw_table = re.search(r'P10D_FSW_TABLE=([^\r\n]+)', serial)
        checks['fsw_retains_roots2'] = bool(fsw_table) and 'fec_roots 2' in fsw_table[1]
        checks['fsw_remains_valid'] = bool(re.search(r'P10D_FSW_STATUS=0 1048576 verity V', serial))
        table = re.search(r'P10D_NOFEC_TABLE=([^\r\n]+)', serial)
        checks['os_fec_options_absent'] = bool(table) and 'fec_' not in table[1]
    else:
        valid = [u for u in users if u.get('target') == 'active' and u.get('pid1_exe') == '/usr/lib/systemd/systemd' and
                 u.get('os_status','').endswith('verity V') and u.get('fsw_status','').endswith('verity V') and
                 all('fec_roots 2' in u.get(k,'') for k in ('os_table','fsw_table')) and
                 u.get('lower','').startswith('/dev/mapper/cm5_os_verified ext4 ro,') and
                 u.get('fsw','').startswith('/dev/mapper/cm5_fsw_verified ext4 ro,') and
                 u.get('libc_call') and u.get('logs_fsync_readback') and
                 u.get('target_read',{}).get('verified_sha256') == fault['golden_sha256'] and
                 u.get('target_read',{}).get('raw_sha256') == fault['raw_after_injection_sha256']]
        checks.update(functional_two_observations=len(valid)>=2 and valid[-1]['uptime']-valid[0]['uptime'] >=20,
                      host_logs_persistence=persistence, original_initramfs=not run['diagnostic_copy'])
        if fault['inject']:
            checks['target_kernel_correction'] = any(e['device'] == f"179:{fault['partition']}" and
                 e['fec_byte_base'] == fec_rsb_base(fault) and e['corrected_errors'] > 0 for e in events)
            checks['raw_differs_from_golden'] = fault['raw_after_injection_sha256'] != fault['golden_sha256']
        if fault['case'] == 'os-far':
            root = re.search(r'\[\s*([0-9.]+)\] EXT4-fs \(dm-[0-9]+\): mounted filesystem a3680812-', serial)
            checks['full_scan_target_correction_before_root'] = bool(root) and any(
                e['device'] == '179:2' and e['fec_byte_base'] == fec_rsb_base(fault) and
                e['timestamp'] < float(root[1]) and e['corrected_errors'] > 0 for e in events)
    result = dict(schema_version=1, case=fault['case'], status=classify(checks,fault['inject'],fault['case']=='no-fec',run['timeout']),
                  checks=checks, fault=fault, fec_events=events, userspace=users, run=run,
                  raw_after_guest_sha256=digest(endraw), overlay_extents=own,
                  write_attribution='Harness fault allocation recorded before guest; post-guest fault cluster content unchanged; other allocations only LOGS. This is net content/extent evidence, not a per-write event audit.',
                  fec_configuration={'os_roots':fault['fec_roots'],'fsw_roots':2,'metadata':'original captured; never resealed'},
                  physical_limitations='Logical virtual corruption only; no flash ECC, wear, radiation or physical timing claim')
    result['profile'] = 'DIAGNOSTIC_NO_FEC' if fault['case'] == 'no-fec' else 'ORIGINAL_CAPTURED_INITRAMFS'
    result['expected_fec_rsb_byte_base'] = fec_rsb_base(fault) if fault['fec_roots'] == 2 else None
    result['distribution'] = dict(kind='single-4096-byte-replacement' if fault['inject'] else 'none',
                                 tested=True, count=1 if fault['inject'] else 0)
    if fault['case'] == 'no-fec':
        result['verity_observations'] = {tag: re.findall(tag+r'=([^\r\n]+)', serial) for tag in
            ('P10D_NOFEC_TABLE', 'P10D_NOFEC_STATUS', 'P10D_FSW_TABLE', 'P10D_FSW_STATUS')}
    save(out/'recovery-result.json', result)
    (out/'recovery-summary.txt').write_text(result['status']+'\n'+'\n'.join(f'{k}: {v}' for k,v in checks.items())+'\n')
    print('PHASE10D_STATUS='+result['status'], flush=True)


def no_fec_initramfs(out, lab, source):
    sys.path.insert(0,str(REPO/'experiments/cm5-phase10b'))
    from audit import cpio_entries
    sys.path.insert(0,str(REPO/'experiments/cm5-phase10c'))
    from diagnostic import newc
    original=source.read_bytes()
    script_name='scripts/local-top/cm5-fsw-verity'
    hook=next(body for name,body in cpio_entries(original) if name==script_name).decode()
    prefix='veritysetup --fec-device="$OSFL" --fec-roots=2 \\\n'
    assert hook.count(prefix)==1
    hook=hook.replace(prefix,'veritysetup \\\n')
    begin=hook.index('case "$TABLE" in\n  *use_fec_from_device')
    # Keep all original setup through OS map creation, then perform a bounded
    # rejecting read. This diagnostic control never attempts a root handoff.
    hook=hook[:begin]+'''read -r dev < /sys/class/tty/ttyAMA0/dev
mknod /dev/phase10d-serial c ${dev%:*} ${dev#*:}
exec >/dev/phase10d-serial 2>&1
echo P10D_DIAGNOSTIC_NO_FEC_NOT_ORIGINAL=1
echo "P10D_NOFEC_TABLE=$TABLE"
echo "P10D_FSW_TABLE=$(dmsetup table cm5_fsw_verified)"
echo "P10D_FSW_STATUS=$(dmsetup status cm5_fsw_verified)"
dd if=/dev/mmcblk0p2 bs=4096 count=1 2>/run/p10d-raw.log | sha256sum
dd if=/dev/mapper/cm5_os_verified of=/dev/null bs=4096 count=1 2>/run/p10d-read.log
RC=$?
echo "P10D_NOFEC_READ_RC=$RC"
cat /run/p10d-read.log
echo "P10D_NOFEC_STATUS=$(dmsetup status cm5_os_verified)"
echo P10D_EXPECTED_ROOT_REJECTION=1
poweroff -f
sleep 60
exit 1
'''
    # Decompress original archives without extracting captured files into repo.
    pos=0
    while original[pos:pos+6] in (b'070701',b'070702'):
        h=original[pos:pos+110];n=int(h[94:102],16);size=int(h[54:62],16)
        pos=(((pos+110+n+3)&~3)+size+3)&~3
        while pos<len(original) and original[pos]==0:pos+=1
    assert original[pos:pos+4]==b'\x28\xb5\x2f\xfd'
    payload=subprocess.run(['zstd','-d','-c'],input=original[pos:],capture_output=True,check=True).stdout
    extra=newc(script_name,hook.encode(),91001)+newc('TRAILER!!!',b'',0)
    dest=lab/'diagnostic-no-fec.initrd.gz'
    with dest.open('xb') as f:f.write(gzip.compress(original[:pos]+payload+bytes(-len(payload)%4)+extra,mtime=0))
    save(out/'no-fec-provenance.json',dict(original=str(source),original_sha256=digest(original),diagnostic=str(dest),diagnostic_sha256=digest(dest.read_bytes()),
        departure='OS FEC CLI options removed; original pre-scan FEC assertion replaced by explicit rejected-block read, tables/status, forced shutdown; no root boot attempted. FSW roots2 unchanged.'))
    return dest
