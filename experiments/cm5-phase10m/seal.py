#!/usr/bin/env python3
"""Build one private regular-file FSW generation offline. Never upstream."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import uuid

import generation as g


def bounded(offset, length, size):
    if type(offset) is not int or type(length) is not int or length <= 0 or offset < 0 or offset > size-length:
        raise ValueError('Invalid partition byte range')


def copy_range(source, target, offset, length):
    g.regular(source)
    bounded(offset, length, source.stat().st_size)
    with source.open('rb') as src, target.open('xb') as dst:
        src.seek(offset)
        left = length
        while left:
            data = src.read(min(left, 8*1024*1024))
            if not data:
                raise ValueError('Short source read')
            dst.write(data); left -= len(data)
        dst.flush(); os.fsync(dst.fileno())


def range_sha(path, offset, length):
    import hashlib
    bounded(offset, length, path.stat().st_size)
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        stream.seek(offset)
        while length:
            data = stream.read(min(length, 8*1024*1024))
            if not data:
                raise ValueError('Short range hash')
            digest.update(data); length -= len(data)
    return digest.hexdigest()


class Builder:
    def __init__(self, out):
        self.out = out.resolve()
        if self.out.is_relative_to(g.ROOT) or not re.fullmatch(r'[A-Za-z0-9_./-]+', str(self.out)):
            raise ValueError('Require a private tool-safe output path outside checkout')
        self.out.mkdir(parents=True, exist_ok=False, mode=0o700)
        self.owner = (self.out.stat().st_dev, self.out.stat().st_ino)

    def writable(self, path):
        if (self.out.stat().st_dev, self.out.stat().st_ino) != self.owner or path.parent != self.out:
            raise ValueError('Output ownership/range changed')
        s = g.regular(path).stat()
        if s.st_uid != os.getuid() or not s.st_mode & stat.S_IWUSR:
            raise ValueError('Only newly owned writable regular files may be edited')

    def run(self, args, name):
        args = list(map(str, args))
        r = subprocess.run(args, capture_output=True, text=True)
        (self.out/(name+'.log')).write_text(r.stdout+r.stderr)
        with (self.out/'commands.jsonl').open('a') as stream:
            stream.write(json.dumps(dict(command=args, returncode=r.returncode, log=name+'.log'))+'\n')
        if r.returncode:
            raise RuntimeError('Tool failed: '+name)
        return r.stdout+r.stderr

    def debug(self, image, command, name, write=False):
        if write:
            self.writable(image)
        return self.run(['debugfs', *(['-w'] if write else []), '-R', command, image], name)

    def dump(self, image, member, name):
        target = self.out/name
        if target.exists():
            raise ValueError('Refusing dump overwrite')
        self.debug(image, f'dump {member} {target}', 'dump-'+name)
        g.regular(target)
        return target

    def install(self, image, source, member, name, remove=False, mode='0100600'):
        if remove:
            self.debug(image, 'rm '+member, name+'-remove', True)
        self.debug(image, f'write {source} {member}', name+'-write', True)
        for field, value in [('mode', mode), ('uid', '0'), ('gid', '0')]:
            self.debug(image, f'set_inode_field {member} {field} {value}', name+'-'+field, True)
        readback = self.dump(image, member, name+'-readback')
        if g.file_sha(readback) != g.file_sha(source):
            raise ValueError('Offline filesystem installation readback mismatch')


def build(args):
    os.umask(0o077)
    for path in (args.golden, args.fsw, args.original_initramfs, args.boot_expected, args.inventory):
        g.regular(path)
        if not re.fullmatch(r'[A-Za-z0-9_./-]+', str(path.resolve())):
            raise ValueError('Require tool-safe regular source paths')
    capacity = shutil.disk_usage(args.output.parent)
    if capacity.free < 30_000_000_000:
        raise ValueError('Require at least 30 GB free before generation construction')
    for tool in ('debugfs', 'e2fsck', 'veritysetup'):
        if not shutil.which(tool):
            raise ValueError('Missing offline tool: '+tool)
    if args.golden.stat().st_size != g.USER_BYTES or g.file_sha(args.golden) != g.GOLDEN_SHA:
        raise ValueError('Original golden identity mismatch')
    if g.file_sha(args.fsw) != g.FSW_SHA:
        raise ValueError('Approved ELF identity mismatch')
    original = args.original_initramfs.read_bytes()
    g.original_profile.construct(original)  # Pin and validate captured framing/hook.
    inventory = json.loads(args.inventory.read_text())
    sys.path.insert(0, str(g.ROOT/'experiments/cm5-phase10a'))
    from preboot import Reader, partitions
    reader = Reader(args.golden, {'reads': []})
    try:
        partitions(reader)
        actual = reader.report['partitions']
    finally:
        reader.f.close()
    if actual != inventory['partitions']:
        raise ValueError('Actual partition table differs from Phase10L inventory')
    ranges = {p['partition']: (p['start']*512, p['sectors']*512) for p in actual}
    if ranges[5][1] != 536870912:
        raise ValueError('Unexpected FSW partition geometry')
    b = Builder(args.output)
    (b.out/'capacity.json').write_text(json.dumps(dict(zip(['total','used','free'],capacity)), indent=2)+'\n')
    (b.out/'source-inventory.json').write_text(json.dumps(inventory, indent=2)+'\n')
    parts = {}
    for role, number in [('fsw',5), ('recovery',7)]:
        image = b.out/(role+'.data')
        copy_range(args.golden, image, *ranges[number]); parts[role] = image
        stats = b.debug(image, 'stats', role+'-stats-before')
        free = int(re.search(r'Free blocks:\s+(\d+)', stats)[1])*int(re.search(r'Block size:\s+(\d+)', stats)[1])
        if 'Filesystem state:         clean' not in stats or free < 32*1024*1024:
            raise ValueError('Offline filesystem prerequisite failed: '+role)
        b.run(['e2fsck','-fn',image], role+'-fsck-before')
    # All modification prerequisites above pass before editing extracted files.
    old = {}
    for role in ('os', 'fsw'):
        old[role] = {}
        for suffix in ('hash', 'fec', 'roothash', 'SHA256SUMS'):
            leaf = suffix if suffix == 'SHA256SUMS' else role+'.'+suffix
            old[role][suffix] = b.dump(parts['recovery'], '/cm5-verity-v2/'+role+'/'+leaf, 'original-'+role+'-'+suffix)
        for line in old[role]['SHA256SUMS'].read_text().splitlines():
            digest, leaf = line.split()
            suffix = leaf.split('.')[-1]
            if suffix not in old[role] or g.file_sha(old[role][suffix]) != digest:
                raise ValueError('Original metadata checksum inventory mismatch')
    entries = dict(g.original_profile.cpio_entries(original))
    for role in ('os','fsw'):
        if entries['etc/cm5-verity/'+role+'.roothash'].strip() != old[role]['roothash'].read_bytes().strip():
            raise ValueError('Captured root pin and RECOVERY root differ')
        if inventory['tables'][role+'_table'].split()[11] != old[role]['roothash'].read_text().strip():
            raise ValueError('Recorded runtime root differs')
    b.run(['veritysetup','dump',old['fsw']['hash']], 'original-fsw-verity-dump')
    b.run(['veritysetup','verify','--fec-device='+str(old['fsw']['fec']), '--fec-roots=2',
           '--root-hash-file='+str(old['fsw']['roothash']),parts['fsw'],old['fsw']['hash']], 'original-fsw-verify')
    b.install(parts['fsw'], args.fsw, '/RpiDeployment.elf', 'install-elf', mode='0100755')
    elf_stat = b.debug(parts['fsw'], 'stat /RpiDeployment.elf', 'installed-elf-stat')
    b.debug(parts['fsw'], 'blocks /RpiDeployment.elf', 'installed-elf-blocks')
    if not re.search(r'Mode:\s+0755', elf_stat):
        raise ValueError('ELF executable permission not confirmed')
    b.run(['e2fsck','-fn',parts['fsw']], 'fsw-fsck-sealed')
    fsw_digest = g.file_sha(parts['fsw'])
    new = {s:b.out/('fsw.'+s) for s in ('hash','fec','roothash')}
    for path in new.values():
        path.open('xb').close()
    salt = inventory['tables']['fsw_table'].split()[12]
    verity_uuid = str(uuid.uuid5(uuid.NAMESPACE_OID,fsw_digest))
    b.run(['veritysetup','format','--format=1','--hash=sha256', '--data-block-size=4096',
           '--hash-block-size=4096','--data-blocks=131072','--fec-roots=2',
           '--fec-device='+str(new['fec']), '--root-hash-file='+str(new['roothash']),
           '--salt='+salt,'--uuid='+verity_uuid,parts['fsw'],new['hash']], 'new-fsw-verity-format')
    root = new['roothash'].read_text().strip()
    if not re.fullmatch(r'[0-9a-f]{64}',root):
        raise ValueError('No new FSW root')
    b.run(['veritysetup','dump',new['hash']], 'new-fsw-verity-dump')
    b.run(['veritysetup','verify','--fec-device='+str(new['fec']), '--fec-roots=2',
           '--root-hash-file='+str(new['roothash']),parts['fsw'],new['hash']], 'new-fsw-verify')
    sums = b.out/'FSW-SHA256SUMS'
    sums.write_text(''.join(g.file_sha(new[s])+'  fsw.'+s+'\n' for s in ('hash','fec','roothash')))
    for suffix, source in [*new.items(),('SHA256SUMS',sums)]:
        leaf = suffix if suffix == 'SHA256SUMS' else 'fsw.'+suffix
        b.install(parts['recovery'], source, '/cm5-verity-v2/fsw/'+leaf,'new-'+leaf,True,
                  mode='0100644' if suffix=='SHA256SUMS' else '0100600')
    for suffix, source in old['os'].items():
        leaf = suffix if suffix == 'SHA256SUMS' else 'os.'+suffix
        check = b.dump(parts['recovery'], '/cm5-verity-v2/os/'+leaf, 'preserved-os-'+suffix)
        if g.file_sha(check) != g.file_sha(source):
            raise ValueError('OS metadata changed')
    b.run(['e2fsck','-fn',parts['recovery']], 'recovery-fsck-sealed')
    image = b.out/'sealed-emmc.img'
    copy_range(args.golden,image,0,g.USER_BYTES)
    b.writable(image)
    with image.open('r+b') as dest:
        for role, num in [('fsw',5),('recovery',7)]:
            offset,length=ranges[num]; bounded(offset,length,g.USER_BYTES)
            dest.seek(offset)
            with parts[role].open('rb') as src:
                shutil.copyfileobj(src,dest,8*1024*1024)
        dest.flush(); os.fsync(dest.fileno())
    # Every byte outside the two authorized partition ranges remains original.
    protected = []; cursor=0
    for offset,length in sorted([ranges[5],ranges[7]]):
        if offset>cursor: protected.append((cursor,offset-cursor))
        cursor=offset+length
    if cursor<g.USER_BYTES: protected.append((cursor,g.USER_BYTES-cursor))
    proofs=[]
    for offset,length in protected:
        original_sha=range_sha(args.golden,offset,length)
        if range_sha(image,offset,length)!=original_sha:
            raise ValueError('Unauthorized full-image byte change')
        proofs.append(dict(offset=offset,length=length,sha256=original_sha))
    for role,num in [('fsw',5),('recovery',7)]:
        if range_sha(image,*ranges[num])!=g.file_sha(parts[role]):
            raise ValueError('Assembly readback mismatch')
    (b.out/'unchanged-ranges.json').write_text(json.dumps(proofs,indent=2)+'\n')
    initrd=b.out/'initramfs-sealed-operational'
    initrd.write_bytes(g.construct_initramfs(original,root))
    boot=b.out/'boot-expected.json';copy_range(args.boot_expected,boot,0,args.boot_expected.stat().st_size)
    artifacts={}
    for key,path in dict(image=image,initramfs=initrd,boot_manifest=boot,
                         fsw_hash=new['hash'],fsw_fec=new['fec'],fsw_pin=new['roothash']).items():
        path.chmod(0o400)
        artifacts[key]=dict(name=path.name,bytes=path.stat().st_size,sha256=g.file_sha(path))
    tables={k:g.canonical_table(inventory['tables'][k]) for k in ('os_table','fsw_table')}
    tables['fsw_table'][11]=root
    manifest=dict(schema=g.SCHEMA,created_utc=datetime.now(timezone.utc).isoformat(),
        original_golden=dict(sha256=g.GOLDEN_SHA,bytes=g.USER_BYTES),
        installed_elf=dict(path=g.ELF_PATH,sha256=g.FSW_SHA,bytes=args.fsw.stat().st_size,mode='0755',uid=0,gid=0),
        fsw_root=root,kernel_sha256=g.original_profile.KERNEL_SHA,
        original_initramfs_sha256=g.original_profile.ORIGINAL_SHA,
        original_boot_manifest_sha256=g.file_sha(args.boot_expected),
        execution_mode=g.MODE,boot_profile='operational',
        verification=dict(format=1,algorithm='sha256',data_block_size=4096,hash_block_size=4096,
            data_blocks=131072,hash_start_block=1,fec_roots=2,fec_start=0,fec_blocks=132105,salt=salt,hash_uuid=verity_uuid),
        expected_tables=tables,partitions=actual,artifacts=artifacts,
        preservation=dict(unchanged_ranges=proofs,os_metadata={k:g.file_sha(v) for k,v in old['os'].items()}),
        baseline_contract=dict(duration_guest_seconds=30,exit_status=124,initializations=20,tasks_created=11,
            tasks_started=10,minimum_housekeeping=1,minimum_packet_routes=1,elf_uart_bytes=0),
        provenance=dict(builder_sha256=g.file_sha(Path(__file__)),policy_source_sha256=g.file_sha(Path(g.__file__)),
            phase10l_inventory_sha256=g.file_sha(args.inventory),physical_eeprom_executed=False,
            original_boot_files_unchanged=True,initramfs_handoff='explicit generation lab substitution',
            sealed_once_for_approved_fsw=True,corruption_injected=False))
    manifest['generation_id']=g.sha(g.canonical(manifest))
    target=b.out/'generation.json'
    target.write_text(json.dumps(manifest,indent=2)+'\n');target.chmod(0o400)
    pin=g.file_sha(target)
    (b.out/'GENERATION-SHA256').write_text(pin+'  generation.json\n')
    if g.file_sha(args.golden)!=g.GOLDEN_SHA:
        raise ValueError('Golden identity changed')
    for path in b.out.iterdir():
        if path.is_file() and path.name!='commands.jsonl':path.chmod(0o400)
    print(json.dumps(dict(status='SEALED',manifest=str(target),manifest_sha256=pin,
                         generation_id=manifest['generation_id'],image_sha256=artifacts['image']['sha256'],fsw_root=root),indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('golden','fsw','original-initramfs','boot-expected','inventory','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    build(parser.parse_args())
