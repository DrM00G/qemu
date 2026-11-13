"""Phase 9 hooks for the existing runner. AI-assisted local experiment only."""
import hashlib
import json
from pathlib import Path
import re
import subprocess

def inject(repo, overlay, out, case):
    role, block = ('os', 1) if case == 'os1' else ('fsw', 0)
    offset = (545259520 if role == 'os' else 11283726336) + block * 4096
    subprocess.run([str(repo / 'build-arm64-phase1/qemu-io'), '-f', 'qcow2',
        '-c', f'write -P 0x5a {offset} 4096', str(overlay)], check=True)
    (out/'corruption.json').write_text(json.dumps(dict(target=str(overlay),
        offset=offset, length=4096, pattern=0x5a, role=role, block=block), indent=2))

def prepare(repo, stage, out, case):
    init = stage/'init'
    text = init.read_text()
    monitor = '''#!/bin/sh
for i in $(seq 1 8); do
 sleep 30
 echo PHASE9_SNAPSHOT_BEGIN=$(cut -d' ' -f1 /proc/uptime)
 cat /proc/interrupts
 cat /proc/diskstats | grep -E 'mmcblk0|dm-'
 systemctl list-jobs --no-pager
 ps -eo pid,stat,wchan:32,comm | grep -E 'fstrim|rcu|mmc|systemd|cm5'
 if [ "$i" = 3 ] || [ "$i" = 6 ]; then
  echo w > /proc/sysrq-trigger
  echo l > /proc/sysrq-trigger
 fi
 echo PHASE9_SNAPSHOT_END
done
'''
    (stage/'cm5-monitor').write_text(monitor)
    (stage/'cm5-monitor').chmod(0o755)
    text = text.replace('cp /cm5-observe /newroot/run-cm5-observe', '''cp /cm5-observe /newroot/run-cm5-observe
cp /cm5-monitor /newroot/run-cm5-monitor
cp /read-range /newroot/run-cm5-read-range
cat > /newroot/etc/systemd/system/cm5-monitor.service <<'MONITOR'
[Unit]
After=local-fs.target
[Service]
Type=simple
ExecStart=/run-cm5-monitor
StandardOutput=journal+console
StandardError=journal+console
[Install]
WantedBy=multi-user.target
MONITOR
ln -s ../cm5-monitor.service /newroot/etc/systemd/system/multi-user.target.wants/cm5-monitor.service''')
    if case == 'reproduce':
        init.write_text(text)
        return
    metadata = Path.home()/'cm5-v8-lab/phase9/metadata'
    audit = json.loads((metadata/'audit.json').read_text())
    assert all(v['status'] == 'PASS' for v in audit['partitions'].values())
    (out/'metadata-audit.json').write_text(json.dumps(audit, indent=2))
    expected = {}
    with (Path.home()/'cm5-v8-lab/golden/cm5-emmc-userarea.img').open('rb') as f:
        for role, offset in [('os',545259520), ('os1',545263616), ('fsw',11283726336)]:
            f.seek(offset)
            expected[role] = hashlib.sha512(f.read(4096)).hexdigest()
    (out/'verified-read-expectations.json').write_text(json.dumps(expected, indent=2))
    if case == 'no-fec':
        text = text.replace(' 8 use_fec_from_device /dev/loop7 fec_roots 2 fec_blocks 2642083 fec_start 0', '')
        begin = text.index('echo OS_VERITY_DIGEST')
        end = text.index('mount -t ext4 -o ro,noload /dev/mapper/cm5-os /lower', begin)
        text = text[:begin] + '''echo PHASE9_NO_FEC_READ_BEGIN
/read-range /dev/mapper/cm5-os 0 > /run/rejected-read
echo PHASE9_NO_FEC_READ_EXIT=$?
dmsetup status cm5-os
echo PHASE9_EXPECTED_ROOT_REJECTION
poweroff -f
sleep 10
exit 1
''' + text[end:]
        init.write_text(text)
        return
    fsw = audit['partitions']['fsw']
    mapping = f'''/loop-ro /dev/loop4 /metadata/cm5-verity-v2/fsw/fsw.hash || fail fsw_hash_loop
/loop-ro /dev/loop5 /metadata/cm5-verity-v2/fsw/fsw.fec || fail fsw_fec_loop
dmsetup create --readonly --noudevsync cm5-fsw --table '0 1048576 verity 1 /dev/mmcblk0p5 /dev/loop4 4096 4096 131072 1 sha256 {fsw['root']} {fsw['salt']} 8 use_fec_from_device /dev/loop5 fec_roots 2 fec_blocks 132105 fec_start 0' || fail fsw_verity_map
dmsetup mknodes
echo PHASE9_FSW_DIGEST
/read-range /dev/mapper/cm5-fsw 0 | sha512sum
dmsetup status cm5-fsw
echo PHASE9_OS1_RAW_DIGEST
/read-range /dev/mmcblk0p2 8 | sha512sum
echo PHASE9_OS1_VERIFIED_DIGEST
/read-range /dev/mapper/cm5-os 8 | sha512sum
echo PHASE9_VERIFIED_STORAGE_READY
'''
    text = text.replace('dmsetup status cm5-os\n', 'dmsetup status cm5-os\n'+mapping, 1)
    text = text.replace('FSW_DEVICE=/dev/mmcblk0p5', 'FSW_DEVICE=/dev/mapper/cm5-fsw')
    text = text.replace("mmcblk|/dev/mapper/cm5-os|/dev/dm-", "mmcblk|/dev/mapper/cm5-os|/dev/mapper/cm5-fsw|/dev/dm-")
    text = text.replace('Type=oneshot\nExecStart=/run-cm5-observe', 'Type=simple\nExecStart=/run-cm5-observe')
    subprocess.run(['aarch64-linux-gnu-gcc','-O2','-Wall',str(repo/'experiments/cm5-phase4/diagnostic.c'),
                    '-ldl','-o',str(stage/'cm5-diagnostic')], check=True)
    original = (stage/'cm5-observe').read_text()
    network = original[:original.index('if [ -b /dev/mapper/cm5-fsw ]; then')]
    observer = network + '''echo PHASE9_WAIT_TARGET=$(cut -d' ' -f1 /proc/uptime)
for i in $(seq 1 120); do
 systemctl is-active --quiet multi-user.target && break
 sleep 1
done
echo V8_TARGET=$(systemctl is-active multi-user.target)
echo PHASE9_TARGET_TIME=$(cut -d' ' -f1 /proc/uptime)
echo V8_PAGESIZE=$(getconf PAGESIZE)
/run-cm5-dmsetup status cm5-os
/run-cm5-dmsetup status cm5-fsw
/run-cm5-dmsetup table cm5-os > "$OUT/os-table.txt"
/run-cm5-dmsetup table cm5-fsw > "$OUT/fsw-table.txt"
CM5_FSW_DEVICE=/dev/mapper/cm5-fsw CM5_FSW_BLOCK=0 \
 /run-cm5-diagnostic /var/log/flight/cm5-diagnostic-phase9.dat - /dev/spidev0.0 20 > "$OUT/diagnostic-phase9.jsonl" 2>&1 &
pid=$!
echo PHASE9_DIAGNOSTIC_PID=$pid
sleep 2
kill -0 "$pid" && echo PHASE9_DIAGNOSTIC_RUNNING=1
ps -p "$pid" -o pid,stat,comm
wait "$pid"
echo V8_DIAGNOSTIC_EXIT=$?
echo PHASE9_DIAGNOSTIC_BEGIN
cat "$OUT/diagnostic-phase9.jsonl"
echo PHASE9_DIAGNOSTIC_END
/run-cm5-dmsetup status cm5-os
/run-cm5-dmsetup status cm5-fsw
cat /proc/interrupts > "$OUT/interrupts-final.txt"
systemctl list-jobs --no-pager > "$OUT/jobs-final.txt"
dmesg > "$OUT/dmesg.txt"
journalctl -b --no-pager > "$OUT/journal.txt"
echo PHASE9_COLLECTION_DONE=$(cut -d' ' -f1 /proc/uptime)
sync
systemctl poweroff
'''
    (stage/'cm5-observe').write_text(observer)
    if case == 'trim':
        observer = observer.replace('echo V8_PAGESIZE=', '''echo PHASE9_TRIM_BEGIN=$(cut -d' ' -f1 /proc/uptime)
fstrim -v /var/log/flight
echo PHASE9_TRIM_EXIT=$?
echo PHASE9_TRIM_END=$(cut -d' ' -f1 /proc/uptime)
echo V8_PAGESIZE=''')
        (stage/'cm5-observe').write_text(observer)
    init.write_text(text)

def host_sample(pid, out, wall):
    sample = dict(wall_seconds=wall, host={}, qemu={}, threads=[])
    for name in ('pressure/cpu','pressure/memory','pressure/io','meminfo','loadavg'):
        try:
            sample['host'][name] = Path('/proc',name).read_text()
        except OSError:
            pass
    for name in ('stat','status','io','schedstat'):
        try:
            sample['qemu'][name] = Path(f'/proc/{pid}/{name}').read_text()
        except OSError:
            pass
    for task in Path(f'/proc/{pid}/task').glob('*'):
        try:
            sample['threads'].append(dict(tid=task.name,comm=(task/'comm').read_text().strip(),
                wchan=(task/'wchan').read_text().strip(),schedstat=(task/'schedstat').read_text()))
        except OSError:
            pass
    with (out/'host-samples.jsonl').open('a') as f:
        f.write(json.dumps(sample)+'\n')

def marked_digest(serial, marker):
    region = serial.split(marker,1)[-1]
    match = re.search(r'^([0-9a-f]{128})\s+-\s*$',region,re.M)
    return match[1] if match else None

def evaluate(serial, trace, stage, out, case, checks, wall):
    observations = dict(case=case,wall_seconds=wall,rcu_stall='detected stalls' in serial,
        stages=dict(re.findall(r'PHASE9_([A-Z_]+)=([0-9]+(?:\.[0-9]+)?)',serial)),
        fec_events=re.findall(r'verity-fec: ([^\r\n]*FEC [0-9]+: corrected [0-9]+ errors)',serial))
    if case == 'reproduce':
        checks['no_rcu_stall'] = not observations['rcu_stall']
        return dict(phase9=observations,status='PASS' if all(checks.values()) else 'FAIL')
    if case == 'no-fec':
        rejected = ('PHASE9_NO_FEC_READ_EXIT=4' in serial and 'PHASE9_EXPECTED_ROOT_REJECTION' in serial
            and 'verity C' in serial and 'V8_SWITCH_ROOT' not in serial
            and checks['qemu_exit'] and checks['no_timeout'])
        return dict(phase9=observations,expected_rejection=rejected,
                    status='EXPECTED_FAILURE' if rejected else 'FAIL')
    expected = json.loads((out/'verified-read-expectations.json').read_text())
    checks['native_fsw'] = '/dev/mapper/cm5-fsw /newroot/opt/fsw ext4 ro,' in serial
    checks['fsw_verity_valid'] = bool(re.search(r'0 1048576 verity V\b',serial))
    checks['fsw_verified_digest'] = marked_digest(serial,'PHASE9_FSW_DIGEST') == expected['fsw']
    checks['os1_verified_digest'] = marked_digest(serial,'PHASE9_OS1_VERIFIED_DIGEST') == expected['os1']
    checks['no_rcu_stall'] = not observations['rcu_stall']
    checks['diagnostic_process_running'] = 'PHASE9_DIAGNOSTIC_RUNNING=1' in serial
    region = serial.split('PHASE9_DIAGNOSTIC_BEGIN',1)[-1].split('PHASE9_DIAGNOSTIC_END',1)[0]
    records = []
    for line in region.splitlines():
        try:
            records.append(json.loads(line[line.index('{'):line.rindex('}')+1]))
        except ValueError:
            pass
    observations['diagnostic'] = records
    for name in ('fsw_verified_read','file_fsync_readback','sealed_lower','os_file_read','spi_loopback'):
        checks['diagnostic_'+name] = any(r.get('test')==name and r.get('status')=='PASS' for r in records)
    beats = [r for r in records if r.get('test')=='heartbeat' and r.get('status')=='PASS']
    checks['sustained_heartbeat'] = len(beats)==20 and beats[-1]['monotonic_ns']-beats[0]['monotonic_ns'] >= 19_000_000_000
    checks['collection_complete'] = 'PHASE9_COLLECTION_DONE=' in serial
    if case == 'trim':
        checks['explicit_trim_completed'] = 'PHASE9_TRIM_EXIT=0' in serial and 'sdcard_erase_elapsed' in trace
    events = re.findall(r'dw_apb_ssi_transfer cs=0x1 bits=8 tx=0x([0-9a-f]+) rx=0x([0-9a-f]+)',trace)
    checks['trace_echo'] = [(int(a,16),int(b,16)) for a,b in events] == [(a,a) for a in (16,32,48,64)]*2
    if case in ('os0','os1','fsw0'):
        device,block = ('179:5',0) if case=='fsw0' else ('179:2',1 if case=='os1' else 0)
        # Linux logs rsb, the interleaver's byte base, not the logical block.
        # For the selected blocks0/1 (well below fec->rounds), rsb = block*4096.
        checks['target_fec_correction'] = bool(re.search(
            rf'verity-fec: {device}: FEC {block * 4096}: corrected [1-9][0-9]* errors',serial))
    if case == 'os1':
        checks['os1_raw_fault'] = marked_digest(serial,'PHASE9_OS1_RAW_DIGEST') == hashlib.sha512(bytes([0x5a])*4096).hexdigest()
    checks['persistent_logs_host_readback'] = False
    if checks['qemu_exit'] and checks['collection_complete']:
        lab = Path.home()/'cm5-v8-lab/phase9'/out.name
        repo = Path(__file__).resolve().parents[2]
        export = lab/'logs-export.ext4'
        subprocess.run([str(repo/'build-arm64-phase1/qemu-img'),'convert','--image-opts','-O','raw',
            f'driver=raw,offset=11821645824,size=1073741824,file.driver=qcow2,file.file.driver=file,file.file.filename={lab / "emmc.qcow2"}',
            str(export)],check=True,capture_output=True)
        datafile = lab/'diagnostic-persistent.dat'
        subprocess.run(['debugfs','-R',f'dump /cm5-diagnostic-phase9.dat {datafile}',str(export)],
                       check=True,capture_output=True)
        checks['persistent_logs_host_readback'] = datafile.is_file() and datafile.read_bytes()==bytes((i*31+7)%251 for i in range(4096))
    return dict(phase9=observations,status='PASS' if all(checks.values()) else 'FAIL')
