#!/usr/bin/env python3
"""Assert actual retained outcomes and write the Phase 9 comparison report."""
import hashlib
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
OUT = HERE/'artifacts'
LAB = Path.home()/'cm5-v8-lab/phase9'

def result(path):
    checked = path/'result-rechecked.json'
    return json.loads((checked if checked.exists() else path/'result.json').read_text())

def passing(path):
    x = result(path)
    assert x['status'] == 'PASS', str(path)
    assert all(x['checks'].values()), str(path)
    return x

functions = ('kernel_boot','os_verification','fsw_verification','systemd_target',
    'diagnostic_process','filesystem_operations','persistent_logs','rp1_spi',
    'sustained_heartbeat','result_collection')
report = dict(local_experiment=True,metadata_regenerated=False,cases={},regressions={})
for case in ('clean','os0','os1','no-fec','fsw0'):
    run = OUT/f'matrix-{case}'
    x = result(run)
    serial = (run/'serial.log').read_text()
    c = x['checks']
    stages = dict(x['phase9']['stages'])
    for name, pattern in (
        ('initramfs',r'Run /init as init process'),
        ('mmc_driver',r'mmc0: SDHCI controller'),
        ('os_ext4',r'EXT4-fs \(dm-0\): mounted'),
        ('fsw_ext4',r'EXT4-fs \(dm-1\): mounted'),
        ('systemd',r'systemd\[1\]: systemd [0-9]'),
        ('poweroff',r'reboot: Power down')):
        found = re.search(r'\[\s*(\d+\.\d+)\][^\r\n]*'+pattern,serial)
        if found:
            stages[name] = float(found[1])
    if case == 'no-fec':
        assert x['status']=='EXPECTED_FAILURE' and x['expected_rejection']
        assert c['block_digests'] and not x['phase9']['fec_events']
        outcomes = {k:'NOT_REACHED_EXPECTED' for k in functions}
        outcomes['kernel_boot'] = 'PASS'
        outcomes['os_verification'] = 'DETECTED_EIO_ROOT_REFUSED'
        outcomes['result_collection'] = 'PASS_CONTROL'
    else:
        assert x['status']=='PASS' and all(c.values()), case
        os_states = re.findall(r'0 20971520 verity ([VC])\b',serial)
        fsw_states = re.findall(r'0 1048576 verity ([VC])\b',serial)
        assert os_states[-1]=='V' and fsw_states[-1]=='V'
        assert 'detected stalls' not in serial
        outcomes = dict(
            kernel_boot=c['brcmstb_bound'] and c['emmc_card'],
            os_verification=c['native_os_lower'] and c['os_verity_read'] and c['os_verity_valid'],
            fsw_verification=c['native_fsw'] and c['fsw_verified_digest'] and c['fsw_verity_valid'],
            systemd_target=c['target_active'],
            diagnostic_process=c['diagnostic_process_running'] and c['original_diagnostic'],
            filesystem_operations=all(c['diagnostic_'+k] for k in ('file_fsync_readback','sealed_lower','os_file_read','fsw_verified_read')),
            persistent_logs=c['persistent_logs_host_readback'],
            rp1_spi=c['diagnostic_spi_loopback'] and c['trace_echo'] and c['native_mip_delivery'],
            sustained_heartbeat=c['sustained_heartbeat'],
            result_collection=c['collection_complete'] and c['qemu_exit'] and c['no_timeout'])
        assert all(outcomes.values())
        outcomes = {k:'PASS' for k in functions}
    report['cases'][case] = dict(status=x['status'],evidence=str(run),functions=outcomes,
        wall_seconds=x['phase9']['wall_seconds'],guest_stages=stages,
        fec_logged_events=x['phase9']['fec_events'],
        raw_block_digests_pass=c['block_digests'],rcu_stall=x['phase9']['rcu_stall'])
    protection = json.loads((run/'block-backend-protection.json').read_text())
    assert protection['read_only'] and protection['access_mode']==0

before = result(OUT/'repro-before-2')
after = passing(OUT/'repro-after')
assert before['phase9']['rcu_stall'] and not after['phase9']['rcu_stall']
trim = passing(OUT/'trim-validated')
trace = (OUT/'trim-validated/peripheral.log').read_text()
erases = [tuple(map(int,m)) for m in re.findall(r'sdcard_erase_elapsed bytes=(\d+) elapsed_ns=(\d+)',trace)]
assert erases and trim['checks']['explicit_trim_completed']
report['diagnosis'] = dict(rcu_reproduced=True,old_boot_reliability='REPRODUCED_RCU',
    before_wall_seconds=before['phase9']['wall_seconds'],after_wall_seconds=after['phase9']['wall_seconds'],
    root_cause='synchronous per-sector high-capacity card erase latency',
    actual_hardware_fix=True,explicit_trim=dict(status='PASS',commands=len(erases),
        bytes=sum(v[0] for v in erases),device_seconds=sum(v[1] for v in erases)/1e9,
        max_command_seconds=max(v[1] for v in erases)/1e9),
    host=json.loads((OUT/'host-diagnosis.json').read_text()))

for platform in ('virt','cm5io-dev'):
    for mode in ('spi','v8'):
        path=LAB/f'preserved-regressions/fallbacks/{platform}-{mode}'
        report['regressions'][platform+'-'+mode]=dict(status=passing(path)['status'],evidence=str(path))
for mode in ('spi','v8'):
    for name,path in (
        ('native-mip-'+mode,LAB/f'preserved-regressions/native-{mode}'),
        ('native-emmc-'+mode,LAB/f'preserved-native-emmc-{mode}')):
        report['regressions'][name]=dict(status=passing(path)['status'],evidence=str(path))
report['regressions']['os-verity']=dict(status=passing(LAB/'preserved-os-verity')['status'],evidence=str(LAB/'preserved-os-verity'))
report['regressions']['eight-gib']=dict(status=passing(OUT/'phase9-native-8g')['status'],evidence=str(OUT/'phase9-native-8g'))
qtests = {}
for name,count in [('rp1',5),('cm5io',2),('bcm2712-mip',3),('bcm2712-sdhci',4)]:
    text=(OUT/f'qtest-{name}-final.log').read_text()
    assert len(re.findall(r'^ok \d+ ',text,re.M))==count and 'not ok' not in text
    qtests[name]=count
report['hardware_qtests']=qtests
golden_before=(REPO/'experiments/cm5-phase8/artifacts/golden-final.sha256').read_text().split()[0]
golden_after=(OUT/'golden-final.sha256').read_text().split()[0]
assert golden_before==golden_after
report['golden_sha256']=golden_after
audit=json.loads((LAB/'metadata/audit.json').read_text())
assert audit['recovery_matches_exact_capture'] and all(v['status']=='PASS' for v in audit['partitions'].values())
report['metadata_audit']=dict(evidence=str(LAB/'metadata/audit.json'),data_blocks_checked={k:v['data_blocks_checked'] for k,v in audit['partitions'].items()})
baseline={name:digest for digest,name in (line.split(maxsplit=1) for line in (OUT/'baseline-hashes.txt').read_text().splitlines())}
for name in ('hw/sd/sdhci.c','hw/sd/bcm2712-sdhci.c'):
    assert hashlib.sha256((REPO/name).read_bytes()).hexdigest()==baseline[name]
report['actual_source_changes']=['hw/sd/sd.c','hw/sd/trace-events','tests/qtest/bcm2712-sdhci-test.c',
    'experiments/cm5-phase4/diagnostic.c','experiments/cm5-phase6/regress.py',
    'experiments/cm5-phase9/profile9.py','experiments/cm5-phase9/metadata-audit.py',
    'experiments/cm5-phase9/run.sh','experiments/cm5-phase9/matrix.sh',
    'experiments/cm5-phase9/remaining-matrix.sh','experiments/cm5-phase9/finish-matrix.sh',
    'experiments/cm5-phase9/recheck-os1.py','experiments/cm5-phase9/hardware.sh',
    'experiments/cm5-phase9/regressions.sh','experiments/cm5-phase9/summarize.py']
report['status']='PASS'
(OUT/'validation.json').write_text(json.dumps(report,indent=2)+'\n')
lines=['# Phase 9 actual matrix results','',
    '| Case | Outcome | Wall seconds | Target guest seconds | Logged FEC events |',
    '| --- | --- | ---: | ---: | ---: |']
for name,r in report['cases'].items():
    lines.append(f"| {name} | {r['status']} | {r['wall_seconds']:.2f} | {r['guest_stages'].get('TARGET_TIME','not reached')} | {len(r['fec_logged_events'])} |")
lines += ['','All four successful boot cases satisfy each condition below. The no-FEC control intentionally refuses root.','',
          '| Condition | clean | os0 | os1 | no-fec | fsw0 |','| --- | --- | --- | --- | --- | --- |']
for name in functions:
    lines.append('| '+name+' | '+' | '.join(report['cases'][case]['functions'][name] for case in report['cases'])+' |')
lines += ['','FEC event labels are kernel RS-base byte offsets, not physical ECC counts. Full stages/digests, inputs, logs and failure records remain in the linked run directories.',
          '', 'Preservation: 14 hardware qtests and 10 guest regressions PASS (including the8 GiB smoke). Golden whole-file SHA-256 unchanged.']
(HERE/'RESULTS.md').write_text('\n'.join(lines)+'\n')
print('PASS: complete native OS/FSW verification and fault matrix, expected no-FEC refusal, 14 hardware qtests, 10 preservation regressions, golden unchanged.')
