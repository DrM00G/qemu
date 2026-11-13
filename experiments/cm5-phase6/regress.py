#!/usr/bin/env python3
"""Real-kernel SPI and V8 regressions; no golden-image writes or FEC sweeps."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import selectors
import shutil
import subprocess
import sys
import time

here = Path(__file__).resolve().parent
repo = here.parent.parent
phase5 = repo / 'experiments/cm5-phase5'
sys.path.insert(0, str(repo / 'experiments/cm5-phase4'))
from endpoints import Endpoints

p = argparse.ArgumentParser()
p.add_argument('--platform', choices=('virt', 'cm5io-dev'), required=True)
p.add_argument('--mode', choices=('spi', 'v8'), required=True)
p.add_argument('--qemu', type=Path, default=repo / 'build-arm64-phase1/qemu-system-aarch64')
p.add_argument('--output', type=Path, required=True)
p.add_argument('--timeout', type=int, default=240)
p.add_argument('--native-mip', action='store_true')
p.add_argument('--mip-module', type=Path)
p.add_argument('--native-emmc', action='store_true')
p.add_argument('--mmc-module', type=Path)
p.add_argument('--memory', type=int, help='guest RAM in MiB; defaults stay unchanged')
p.add_argument('--os-verity', action='store_true')
p.add_argument('--os-corrupt-block-zero', action='store_true')
p.add_argument('--phase9-case', choices=('reproduce', 'clean', 'os0', 'os1', 'no-fec', 'fsw0', 'trim'))
a = p.parse_args()
if a.phase9_case:
    if not (a.native_emmc and a.native_mip and a.os_verity and a.mode == 'v8'):
        p.error('Phase 9 requires native eMMC/MIP V8 with OS verity')
    sys.path.insert(0, str(repo / 'experiments/cm5-phase9'))
    import profile9
if a.native_emmc and (a.platform != 'cm5io-dev' or not a.mmc_module):
    p.error('--native-emmc requires cm5io-dev and --mmc-module')
if a.memory is not None and a.memory <= 0:
    p.error('--memory must be positive')
if a.os_verity and (not a.native_emmc or a.mode != 'v8'):
    p.error('--os-verity requires native eMMC V8')
if a.os_corrupt_block_zero and not a.os_verity:
    p.error('--os-corrupt-block-zero requires --os-verity')
if a.native_mip and (a.platform != 'cm5io-dev' or not a.mip_module):
    p.error('--native-mip requires cm5io-dev and --mip-module')
out = a.output.resolve()
out.mkdir(parents=True, exist_ok=False)
os.chmod(out, 0o700)
qemu = a.qemu.resolve()
kernel = Path.home() / 'cm5-phase3-kernel/build/arch/arm64/boot/Image'
cmd = [str(qemu), '-M', 'cm5io-dev' if a.platform == 'cm5io-dev' else
       'virt,highmem=off,gic-version=3', '-cpu', 'cortex-a76', '-accel', 'tcg',
       '-smp', '4' if a.platform == 'cm5io-dev' else '2',
       '-m', str(a.memory or (2048 if a.mode == 'v8' else 1024)), '-display', 'none',
       '-monitor', 'none', '-serial', 'stdio', '-no-reboot',
       '-kernel', str(kernel), '-trace', 'enable=dw_apb_ssi_*',
       '-trace', 'enable=rp1_msix', '-d', 'unimp,guest_errors',
       '-D', str(out / 'peripheral.log')]
if a.native_mip:
    cmd[cmd.index('-M') + 1] = 'cm5io-dev,native-mip=on'
    cmd += ['-trace', 'enable=bcm2712_mip_*']
if a.phase9_case:
    cmd += ['-L', str(repo / 'pc-bios'), '-trace', 'enable=sdcard_erase*']
if a.native_emmc:
    cmd[cmd.index('-M') + 1] += ',native-emmc=on'
    golden = Path.home() / 'cm5-v8-lab/golden/cm5-emmc-userarea.img'
    if not golden.is_file() or golden.stat().st_size != 15634268160:
        raise RuntimeError('expected regular-file captured user area')
    lab = Path.home() / ('cm5-v8-lab/phase9' if a.phase9_case else 'cm5-v8-lab/phase8') / out.name
    lab.mkdir(parents=True, exist_ok=False)
    if shutil.disk_usage(lab).free < 2 * 1024**3:
        raise RuntimeError('less than 2GiB free for disposable overlay')
    overlay = lab / 'emmc.qcow2'
    subprocess.run([str(repo / 'build-arm64-phase1/qemu-img'), 'create', '-f',
                    'qcow2', '-F', 'raw', '-b', str(golden), str(overlay)], check=True)
    if a.os_corrupt_block_zero:
        subprocess.run([str(repo / 'build-arm64-phase1/qemu-io'), '-f', 'qcow2',
                        '-c', 'write -P 0x5a 545259520 4096', str(overlay)], check=True)
        (out / 'corruption.json').write_text(json.dumps(dict(
            target=str(overlay), offset=545259520, length=4096, pattern=0x5a,
            golden_modified=False, logical_os_block=0), indent=2))
    if a.phase9_case in ('os1', 'fsw0'):
        profile9.inject(repo, overlay, out, a.phase9_case)
    cmd += ['-drive', f'file={overlay},format=qcow2,if=none,id=native',
            '-device', 'emmc,drive=native,boot-partition-size=0,rpmb-partition-size=0',
            '-trace', 'enable=bcm2712_sdhci_*', '-trace', 'enable=sdhci_send_command',
            '-trace', 'enable=sdcard_normal_command', '-trace', 'enable=sdcard_read_block']

def add_emmc(stage):
    shutil.copy2(a.mmc_module, stage / 'sdhci-brcmstb.ko')
    subprocess.run(['aarch64-linux-gnu-gcc', '-static', '-O2', '-Wall', '-Wextra',
                    str(repo / 'experiments/cm5-phase8/read-range.c'),
                    '-o', str(stage / 'read-range')], check=True)
    # Only digests leave these known block ranges; no filesystem contents printed.
    sectors = [0, 16384, 1064960, 22036480, 22038528, 23089152, 25188352]
    expected = {}
    with golden.open('rb') as stream:
        for sector in sectors:
            stream.seek(sector * 512)
            expected[str(sector)] = hashlib.sha512(stream.read(4096)).hexdigest()
    original_os_digest = expected['1064960']
    if a.os_corrupt_block_zero:
        expected['1064960'] = hashlib.sha512(bytes([0x5a]) * 4096).hexdigest()
    if a.phase9_case == 'fsw0':
        expected['22038528'] = hashlib.sha512(bytes([0x5a]) * 4096).hexdigest()
    (out / 'expected-emmc-digests.json').write_text(json.dumps(expected, indent=2))
    hook = '''insmod /sdhci-brcmstb.ko || echo EMMC_MODULE_FAILED
for i in $(seq 1 30); do [ -b /dev/mmcblk0p7 ] && break; sleep 1; done
echo EMMC_BINDING_BEGIN
readlink /sys/bus/platform/devices/1000fff000.mmc/driver
cat /sys/block/mmcblk0/size /sys/block/mmcblk0/queue/logical_block_size /sys/block/mmcblk0/ro
for part in /sys/block/mmcblk0/mmcblk0p*; do
    echo EMMC_PARTITION=${part##*/}
    cat "$part/start" "$part/size"
done
echo EMMC_BINDING_END
echo EMMC_GUEST_MEMTOTAL=$(awk '/^MemTotal:/ {print $2}' /proc/meminfo)
'''
    for sector in sectors:
        hook += (f'echo EMMC_DIGEST_SECTOR={sector}\n'
                 f'/read-range /dev/mmcblk0 {sector} | sha512sum\n')
    init = stage / 'init'
    lines = init.read_text().splitlines(keepends=True)
    mount_lines = [i for i, line in enumerate(lines)
                   if line.startswith(('mount -t sysfs', 'mount -t devtmpfs'))]
    if len(mount_lines) != 2:
        raise RuntimeError('expected sysfs and devtmpfs mounts')
    lines.insert(max(mount_lines) + 1, hook)
    content = ''.join(lines)
    if a.mode == 'v8':
        content = content.replace('/dev/vda', '/dev/mmcblk0p')
        content = content.replace('/dev/vdb6', '/dev/mmcblk0p6')
        content = content.replace('mkdir -p /lower /ram /newroot', '''for p in 1 2 5 7; do
    blockdev --setro /dev/mmcblk0p$p || fail partition_readonly
done
mkdir -p /lower /ram /newroot''')
        content = content.replace('# Only this RAM view changes;', '''echo EMMC_NATIVE_MOUNTS_BEGIN
grep -E 'mmcblk|/dev/mapper/cm5-os|/dev/dm-' /proc/mounts
echo EMMC_OS_BLOCK_RO=$(cat /sys/class/block/mmcblk0p2/ro)
echo EMMC_NATIVE_MOUNTS_END
# Only this RAM view changes;''')
        # Native profile mounts original FSW p5 independently, read-only.
        (stage / 'cm5-fsw-map').unlink()
        if a.os_verity:
            subprocess.run(['aarch64-linux-gnu-gcc', '-static', '-O2', '-Wall', '-Wextra',
                            str(repo / 'experiments/cm5-phase8/loop-ro.c'),
                            '-o', str(stage / 'loop-ro')], check=True)
            derived = Path.home() / 'cm5-v8-lab/derived-fsw'
            root_hash = (derived / 'os.roothash').read_text().strip()
            if not re.fullmatch('[0-9a-f]{64}', root_hash):
                raise RuntimeError('invalid captured root hash')
            # Original hash/FEC files are read from captured RECOVERY over eMMC.
            # Their geometry is preserved from the Phase 4 extraction record.
            verity = f'''mkdir -p /metadata
mount -t ext4 -o ro,noload /dev/mmcblk0p7 /metadata || fail os_metadata_mount
/loop-ro /dev/loop6 /metadata/cm5-verity-v2/os/os.hash || fail os_hash_loop
/loop-ro /dev/loop7 /metadata/cm5-verity-v2/os/os.fec || fail os_fec_loop
dmsetup create --readonly --noudevsync cm5-os --table '0 20971520 verity 1 /dev/mmcblk0p2 /dev/loop6 4096 4096 2621440 1 sha256 {root_hash} d1399d65d6f4daf0f16dd1f8426ac78819520857cbf1e10b0432bb88b96c4f1c 8 use_fec_from_device /dev/loop7 fec_roots 2 fec_blocks 2642083 fec_start 0' || fail os_verity_map
dmsetup mknodes
echo OS_VERITY_DIGEST
/read-range /dev/mapper/cm5-os 0 | sha512sum
dmsetup status cm5-os
echo OS_VERITY_EXPECTED={original_os_digest}
'''
            content = content.replace('mount -t ext4 -o ro,noload /dev/mmcblk0p2 /lower',
                verity + 'mount -t ext4 -o ro,noload /dev/mapper/cm5-os /lower')
            content = content.replace('echo EMMC_NATIVE_MOUNTS_BEGIN', '''mkdir -p /newroot/mnt/os-metadata
mount --move /metadata /newroot/mnt/os-metadata || fail move_metadata
echo EMMC_NATIVE_MOUNTS_BEGIN''')
    init.write_text(content)

def add_mip(stage):
    shutil.copy2(a.mip_module, stage / 'irq-bcm2712-mip.ko')
    init = stage / 'init'
    lines = init.read_text().splitlines(keepends=True)
    hook = '''insmod /irq-bcm2712-mip.ko
echo MIP_BINDINGS_BEGIN
for p in /sys/bus/platform/devices/*msi*; do
    echo MIP_PLATFORM=$p
    readlink "$p/driver"
done
echo MIP_BINDINGS_END
'''
    # Load before V8 waits for block devices; sysfs is already mounted here.
    for i, line in enumerate(lines):
        if line.startswith('mount -t sysfs'):
            lines.insert(i + 1, hook)
            break
    else:
        raise RuntimeError('expected sysfs mount in preserved init')
    init.write_text(''.join(lines))

def pack(stage, dest):
    spec = importlib.util.spec_from_file_location('builder',
        repo / 'experiments/cm5-phase3/prepare-initramfs.py')
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    builder.pack(stage, dest)
if a.platform == 'virt':
    cmd += ['-device', 'rp1-pci,id=rp1,addr=1', '-dtb',
            str(phase5 / ('artifacts/v8.dtb' if a.mode == 'v8' else 'artifacts/spi.dtb'))]
cmd += ['-device', 'ssi-test-slave,bus=spi,cs=0,xor-mask=' +
        ('0' if a.mode == 'v8' else '0xa5')]
if a.mode == 'spi':
    initrd = phase5 / 'artifacts/guest/spi-initrd.gz'
    if a.native_mip or a.native_emmc:
        stage = out / 'stage'
        shutil.copytree(phase5 / 'artifacts/guest/stage', stage, symlinks=True)
        if a.native_emmc:
            add_emmc(stage)
        if a.native_mip:
            add_mip(stage)
        initrd = lab / 'initrd.gz' if a.native_emmc else out / 'initrd.gz'
        pack(stage, initrd)
    cmd += ['-nic', 'none', '-append', 'console=ttyAMA0 rdinit=/init panic=-1']
else:
    stage = out / 'stage'
    # Known-good Phase 5 V8 stage already has the real-spidev diagnostic hook.
    shutil.copytree(phase5 / 'artifacts/v8-verified/stage', stage, symlinks=True)
    if a.native_emmc:
        add_emmc(stage)
    if a.native_mip:
        add_mip(stage)
    if a.phase9_case:
        profile9.prepare(repo, stage, out, a.phase9_case)
    endpoints = Endpoints(out / 'network.jsonl')
    (stage / 'cm5-network').write_text(
        'export CM5_TCP_PORT=%d CM5_UDP_PORT=%d CM5_ROOT_TEST=1\n' %
        (endpoints.ports['tcp'], endpoints.ports['udp']))
    initrd = lab / 'initrd.gz' if a.native_emmc else out / 'initrd.gz'
    spec = importlib.util.spec_from_file_location('builder',
        repo / 'experiments/cm5-phase3/prepare-initramfs.py')
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    builder.pack(stage, initrd)
    original = json.loads((phase5 / 'artifacts/v8-verified/command.json').read_text())
    golden = Path.home() / 'cm5-v8-lab/golden/cm5-emmc-userarea.img'
    if not a.native_emmc:
        overlay = out / 'logs.qcow2'
        subprocess.run([str(repo / 'build-arm64-phase1/qemu-img'), 'create', '-f',
                        'qcow2', '-F', 'raw', '-b', str(golden), str(overlay)], check=True)
    bus = ',bus=cm5-expansion' if a.platform == 'cm5io-dev' else ''
    slot = 2
    for i, arg in enumerate(original):
        if arg == '-drive':
            drive = original[i + 1]
            if a.native_emmc:
                continue
            if 'logs.qcow2' in drive:
                drive = f'file={overlay},format=qcow2,if=none,id=v8disk{slot}'
            cmd += ['-drive', drive, '-device',
                    f'virtio-blk-pci,drive=v8disk{slot},addr={slot}{bus}']
            slot += 1
    cmd += ['-netdev', 'user,id=v8net', '-device',
            f'virtio-net-pci,netdev=v8net,addr=7{bus}',
            '-append', 'console=ttyAMA0 rdinit=/init panic=-1 systemd.unit=multi-user.target']
cmd += ['-initrd', str(initrd)]
(out / 'command.json').write_text(json.dumps(cmd, indent=2) + '\n')
inputs = {}
for path in (qemu, kernel, initrd):
    with path.open('rb') as stream:
        inputs[str(path)] = hashlib.file_digest(stream, 'sha256').hexdigest()
(out / 'inputs.json').write_text(json.dumps(inputs, indent=2) + '\n')
proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
sel = selectors.DefaultSelector()
sel.register(proc.stdout, selectors.EVENT_READ)
raw = bytearray()
started = time.monotonic()
last_sample = -1
echoed = timeout = False
try:
    with (out / 'serial.log').open('wb') as stream:
        while sel.get_map():
            if a.phase9_case and time.monotonic() - started - last_sample >= 1:
                last_sample = time.monotonic() - started
                profile9.host_sample(proc.pid, out, last_sample)
            if a.native_emmc and not (out / 'block-backend-protection.json').exists():
                for fd in Path(f'/proc/{proc.pid}/fd').glob('*'):
                    try:
                        if fd.resolve() != golden:
                            continue
                        info = Path(f'/proc/{proc.pid}/fdinfo/{fd.name}').read_text()
                        flags = int(re.search(r'^flags:\s+([0-7]+)', info, re.M)[1], 8)
                        (out / 'block-backend-protection.json').write_text(json.dumps(
                            dict(golden=str(golden), access_mode=flags & os.O_ACCMODE,
                                 read_only=(flags & os.O_ACCMODE) == os.O_RDONLY), indent=2))
                        break
                    except (OSError, TypeError):
                        pass
            if time.monotonic() - started > a.timeout:
                timeout = True
                break
            for key, _ in sel.select(.5):
                data = os.read(key.fileobj.fileno(), 65536)
                if not data:
                    sel.unregister(key.fileobj)
                    continue
                stream.write(data)
                stream.flush()
                raw.extend(data)
                if a.phase9_case:
                    chunk = data.decode(errors='replace')
                    guest_times = re.findall(r'\[\s*(\d+\.\d+)\]', chunk)
                    markers = re.findall(r'(?:PHASE9_[A-Z_]+|V8_[A-Z_]+)=[^\r\n]*', chunk)
                    with (out / 'timeline.jsonl').open('a') as timeline:
                        timeline.write(json.dumps(dict(wall_seconds=time.monotonic()-started,
                            last_guest_seconds=float(guest_times[-1]) if guest_times else None,
                            markers=markers, serial_bytes=len(data))) + '\n')
                if a.mode == 'v8' and not echoed and b'\x10\x20\x30\x40' in raw:
                    proc.stdin.write(b'\x10\x20\x30\x40')
                    proc.stdin.flush()
                    echoed = True
finally:
    if proc.poll() is None:
        proc.kill()
    proc.wait()
serial = raw.decode(errors='replace')
trace = (out / 'peripheral.log').read_text()
events = re.findall(r'dw_apb_ssi_transfer cs=0x1 bits=8 tx=0x([0-9a-f]+) rx=0x([0-9a-f]+)', trace)
checks = dict(qemu_exit=proc.returncode == 0, no_timeout=not timeout,
              no_kernel_panic='Kernel panic' not in serial and 'BUG:' not in serial)
if a.native_mip:
    checks['native_mip_bound'] = serial.count('drivers/mip_msi') >= 2
    # V8 console loglevel can suppress dev_dbg; verify actual init MMIO writes.
    checks['native_mip_initialized'] = all(trace.count(
        f'bcm2712_mip_mmio write=1 offset=0x{offset:x} value=0x{value:x}') >= 2
        for offset, value in ((0x40, 0), (0x50, 0), (0x60, 0xffffffff),
                              (0x70, 0xffffffff), (0x20, 0xffffffff),
                              (0x30, 0xffffffff)))
    checks['native_mip_delivery'] = bool(re.search(
        r'bcm2712_mip_raise first=0 vector=19 delivered=1', trace))
    checks['no_gicv2m'] = 'GICv2m:' not in serial
if a.native_emmc:
    checks['brcmstb_bound'] = '/drivers/sdhci-brcmstb' in serial
    if a.memory == 8192:
        memory = re.search(r'EMMC_GUEST_MEMTOTAL=(\d+)', serial)
        checks['eight_gib_visible'] = bool(memory and int(memory[1]) > 7 * 1024**2)
    checks['emmc_card'] = 'mmcblk0:' in serial and 'mmc0: new MMC card' in serial
    checks['capacity_sector_overlay_rw'] = '30535680\r\n512\r\n0' in serial
    checks['partitions'] = all(f'EMMC_PARTITION=mmcblk0p{i}' in serial for i in (1, 2, 3, 5, 6, 7))
    geometry = {1: (16384, 1048576), 2: (1064960, 20971520),
                3: (22036480, 2), 5: (22038528, 1048576),
                6: (23089152, 2097152), 7: (25188352, 5345279)}
    checks['partition_geometry'] = all(re.search(
        rf'EMMC_PARTITION=mmcblk0p{part}\s+{start}\s+{size}\s', serial)
        for part, (start, size) in geometry.items())
    if a.mode == 'v8':
        lower_device = '/dev/mapper/cm5-os' if a.os_verity else '/dev/mmcblk0p2'
        checks['native_os_lower'] = lower_device + ' /newroot/media/root-ro ext4 ro,' in serial
        checks['native_fsw'] = '/dev/mmcblk0p5 /newroot/opt/fsw ext4 ro,' in serial
        checks['native_logs'] = '/dev/mmcblk0p6 /newroot/var/log/flight ext4 rw,' in serial
        checks['os_block_ro'] = 'EMMC_OS_BLOCK_RO=1' in serial
        checks['no_virtio_storage'] = 'virtio-blk' not in ' '.join(cmd)
        if a.os_verity:
            sys.path.insert(0, str(repo / 'experiments/cm5-phase8'))
            from verification import os_checks
            checks.update(os_checks(serial, a.os_corrupt_block_zero))
    checks['block_digests'] = all(re.search(
        rf'EMMC_DIGEST_SECTOR={sector}\s+{digest}\s', serial)
        for sector, digest in json.loads((out / 'expected-emmc-digests.json').read_text()).items())
    checks['controller_commands'] = 'sdhci_send_command' in trace
    checks['card_reads'] = 'sdcard_read_block' in trace
    checks['bcm2712_configuration'] = 'bcm2712_sdhci_cfg write=1 offset=0x0 value=0x80000000' in trace
if a.mode == 'spi':
    txs = re.findall(r'SPI_IOC_MESSAGE\(1\) mode=\d+ hz=\d+ len=(\d+) TX=([0-9a-f]+)', serial)
    rxs = re.findall(r'SPI_RESULT ret=(-?\d+) errno=(\d+) RX=([0-9a-f]+)', serial)
    expected = []
    checks['all_messages'] = len(txs) == len(rxs) == 72
    for (length, txhex), (ret, err, rxhex) in zip(txs, rxs):
        tx, rx = bytes.fromhex(txhex), bytes.fromhex(rxhex)
        checks['all_messages'] &= (len(tx) == len(rx) == int(ret) == int(length)
                                   and int(err) == 0 and rx == bytes(b ^ 0xa5 for b in tx))
        expected.extend(zip(tx, rx))
    checks['trace_matches_all_bytes'] = len(expected) == 5448 and expected == [
        (int(tx, 16), int(rx, 16)) for tx, rx in events]
    checks['guest_pass'] = 'SPI_DIAGNOSTIC=PASS failures=0' in serial
    checks['rp1_bound'] = 'bus/pci/drivers/rp1' in serial
    checks['interrupt_driver'] = 'rp1_irq_chip  19 Level' in serial
else:
    checks['target_active'] = 'V8_TARGET=active' in serial
    checks['original_diagnostic'] = 'V8_DIAGNOSTIC_EXIT=0' in serial
    checks['spi_diagnostic'] = 'V8_RP1_SPI_DIAGNOSTIC_EXIT=0' in serial
    checks['trace_echo'] = [(int(tx, 16), int(rx, 16)) for tx, rx in events] == [
        (0x10, 0x10), (0x20, 0x20), (0x30, 0x30), (0x40, 0x40)]
result = dict(platform=a.platform, mode=a.mode,
              native_mip=a.native_mip,
              native_emmc=a.native_emmc,
              os_verity=a.os_verity, os_corrupt_block_zero=a.os_corrupt_block_zero,
              status='PASS' if all(checks.values()) else 'FAIL',
              returncode=proc.returncode, checks=checks, traced_words=len(events))
if a.phase9_case:
    result.update(profile9.evaluate(serial, trace, stage, out, a.phase9_case,
                                   checks, time.monotonic() - started))
(out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))
raise SystemExit(0 if result['status'] in ('PASS', 'EXPECTED_FAILURE') else 1)
