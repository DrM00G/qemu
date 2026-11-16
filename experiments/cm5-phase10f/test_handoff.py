"""Nonproprietary fixtures; actual QCOW2 and QEMU block errors, no devices."""
import gzip
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import handoff as h
from block_reader import BIN, LogicalReader, run
from validate import sha, validate, newc


def archive(payload=b'hello'):
    def entry(name, body):
        name = name.encode()+b'\0'
        fields = [1, 0o100644, 0, 0, 1, 0, len(body), 0, 0, 0, 0, len(name), 0]
        head = b'070701'+b''.join(f'{x:08x}'.encode() for x in fields)+name
        head += bytes(-len(head)%4)
        head += body
        return head+bytes(-len(head)%4)
    return entry('init', payload)+entry('TRAILER!!!', b'')


def fixture(path, config=None, includes=None, payloads=None):
    kernel = bytearray(1024)
    kernel[64:] = bytes(range(256))*3 + bytes(192)
    struct.pack_into('<Q', kernel, 16, len(kernel))
    kernel[56:60] = b'ARM\x64'
    tree = struct.pack('>I',1)+bytes(4)+struct.pack('>II',2,9)
    dtb = struct.pack('>10I', 0xd00dfeed, 72, 56, 72, 40, 17, 16, 0, 0, 16)+bytes(16)+tree
    files = {'config.txt': config if config is not None else b'[all]\nkernel=kernel.img\ninitramfs initrd followkernel\ndevice_tree=board.dtb\ncmdline=cmdline.txt\n',
             'kernel.img': gzip.compress(kernel, mtime=0), 'initrd': gzip.compress(archive(), mtime=0),
             'board.dtb': dtb, 'cmdline.txt': b'console=ttyAMA0 rdinit=/init\n'}
    files.update(includes or {})
    files.update(payloads or {})
    base, sectors, fatsz, roots = 2048, 5000, 20, 128
    data_sector = 1+fatsz+8
    locations = {}
    with path.open('xb') as f:
        f.truncate((base+sectors)*512)
        mbr = bytearray(512); mbr[450] = 14
        struct.pack_into('<II', mbr, 454, base, sectors); mbr[510:] = b'\x55\xaa'
        f.write(mbr)
        bpb = bytearray(512)
        struct.pack_into('<H', bpb, 11, 512); bpb[13] = 1
        struct.pack_into('<H', bpb, 14, 1); bpb[16] = 1
        struct.pack_into('<HH', bpb, 17, roots, sectors)
        struct.pack_into('<H', bpb, 22, fatsz); bpb[510:] = b'\x55\xaa'
        f.seek(base*512); f.write(bpb)
        f.seek((base+1)*512); f.write(b'\xf8\xff\xff\xff')
        cluster = 2
        for i,(name,data) in enumerate(files.items()):
            entry = bytearray(32)
            parts = name.upper().split('.')
            entry[:11] = parts[0].ljust(8).encode()+(parts[1] if len(parts)>1 else '').ljust(3).encode()
            entry[11] = 32
            struct.pack_into('<H',entry,26,cluster); struct.pack_into('<I',entry,28,len(data))
            off = (base+1+fatsz)*512+i*32
            f.seek(off); f.write(entry)
            locations[name] = dict(entry=off, offset=(base+data_sector+cluster-2)*512, cluster=cluster)
            for j in range(0,len(data),512):
                f.seek((base+data_sector+cluster-2)*512); f.write(data[j:j+512])
                f.seek((base+1)*512+cluster*2)
                f.write(struct.pack('<H',cluster+1 if j+512<len(data) else 0xffff))
                cluster += 1
    return locations, {name:sha(data) for name,data in files.items()}, files


class HandoffTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Preserve synthetic test artifacts too. Each run uses a unique private dir.
        cls.root = Path(tempfile.mkdtemp(prefix='phase10f-tests-', dir='/home/aweso/cm5-v8-lab'))
        cls.counter = 0

    def setUp(self):
        type(self).counter += 1
        self.work = self.root/f'{self.counter:03d}-{self._testMethodName}'
        self.work.mkdir()
        self.raw = self.work/'base.raw'
        self.loc,self.expected,self.files = fixture(self.raw)
        self.overlay = self.work/'disk.qcow2'
        run([BIN/'qemu-img','create','-f','qcow2','-F','raw','-b',self.raw,self.overlay])
        self.initial = h.identity(self.raw)
        self.n = 0

    def mutate(self, offset, data):
        # Write only the disposable overlay; qemu-io write -s takes exact bytes.
        source = self.work/f'mutation-{self.n}.bin'
        source.write_bytes(data)
        run([BIN/'qemu-io','-f','qcow2','-c',f'write -s {source} {offset} {len(data)}',self.overlay])
        self.n += 1

    def select(self, **kw):
        work = self.work/f'select-{self.n}'; work.mkdir(); self.n += 1
        report,buffers = h.select(self.overlay, work, self.expected, **kw)
        h.write_report(work/'result.json',report)
        self.assertEqual(h.identity(self.raw),self.initial)
        return report,buffers

    def test_clean_selected_export_and_launch_gate(self):
        r,b = self.select()
        self.assertEqual(r['status'],'SELECTED',r)
        self.assertEqual(b, {kind:self.files[name] for kind,name in r['selected'].items()})
        h.export(r,b,self.work/'exports')
        exports = h.verify_launch(r,self.overlay)
        self.assertEqual(exports['kernel']['sha256'], self.expected['kernel.img'])
        self.assertFalse(r['dt_handoff']['selected_dtb_executed'])
        self.assertTrue(all(Path(v['path']).stat().st_mode & 0o222 == 0 for v in exports.values()))
        self.assertFalse(r['process']['launched'])

    def test_overlay_mbr_mutation_seen(self):
        self.mutate(510,b'\0\0')
        r,b = self.select(); self.assertEqual(r['status'],'INVALID_LAYOUT'); self.assertEqual(b,{})

    def test_bad_fat_bpb(self):
        self.mutate(2048*512+13,b'\0')
        self.assertEqual(self.select()[0]['status'],'INVALID_LAYOUT')

    def test_missing_required_each(self):
        for name in ('kernel.img','initrd','board.dtb'):
            # independent overlay for each fault
            current = self.overlay
            self.overlay = self.work/f'{name}.qcow2'
            run([BIN/'qemu-img','create','-f','qcow2','-F','raw','-b',self.raw,self.overlay])
            self.mutate(self.loc[name]['entry'],b'\xe5')
            r,b = self.select(); self.assertEqual(r['status'],'SELECTED_FILE_UNAVAILABLE'); self.assertEqual(b,{})
            self.overlay = current

    def test_header_and_payload_each(self):
        for name, delta in [('kernel.img',0),('kernel.img',40),('initrd',0),('initrd',35),('board.dtb',0),('board.dtb',60)]:
            current = self.overlay
            self.overlay = self.work/f'corrupt-{self.n}.qcow2'
            run([BIN/'qemu-img','create','-f','qcow2','-F','raw','-b',self.raw,self.overlay])
            value = self.files[name][delta]^0xff
            self.mutate(self.loc[name]['offset']+delta,bytes([value]))
            r,b = self.select(); self.assertEqual(r['status'],'INVALID_IMAGE',r); self.assertEqual(b,{})
            self.overlay = current

    def test_digest_detects_structurally_valid_payload_change(self):
        # Valid cmdline alteration bypasses structure checks but fails pinned digest.
        self.mutate(self.loc['cmdline.txt']['offset'],b'C')
        r,b = self.select(); self.assertEqual(r['stage'],'LAB_INTEGRITY')
        self.assertEqual(r['status'],'INVALID_IMAGE'); self.assertEqual(b,{})

    def test_outside_read_set(self):
        clean,_ = self.select(); offset = 7047*512
        self.assertFalse(any(e['offset'] <= offset < e['offset']+e['returned'] for e in clean['reads']))
        self.mutate(offset,b'\xff'*512)
        r,_ = self.select(); self.assertEqual(r['status'],'SELECTED'); self.assertEqual(clean['files'],r['files'])

    def test_real_qemu_block_error(self):
        sector = self.loc['kernel.img']['offset']//512
        r,b = self.select(error_sector=sector)
        self.assertEqual(r['status'],'READ_ERROR',r)
        self.assertEqual(r['reads'][-1]['returned'],0); self.assertEqual(b,{})
        self.assertTrue('errno=5' in r['reason'] or 'Input/output error' in r['reason'], r['reason'])

    def test_real_error_outside_read_set(self):
        r,_ = self.select(error_sector=7047)
        self.assertEqual(r['status'],'SELECTED',r)

    def test_final_fat_link_cycle_and_truncation(self):
        c = self.loc['kernel.img']['cluster']
        self.mutate((2048+1)*512+c*2,struct.pack('<H',c))
        self.assertEqual(self.select()[0]['status'],'INVALID_LAYOUT')

    def test_unsupported_directives_and_policy(self):
        for directive in (b'dtparam=spi=on\n', b'dtoverlay=spi0-1cs\n', b'unknown=1\n',b'[pi5]\n'):
            self.mutate(self.loc['config.txt']['offset'],directive+b'#'*(len(self.files['config.txt'])-len(directive)))
            r,b = self.select(); self.assertEqual(r['status'],'UNSUPPORTED'); self.assertEqual(b,{})
            self.assertFalse(r['process']['launched'])
        r,_ = self.select(policy='0xf14'); self.assertEqual(r['reads'],[])

    def test_cli_export_flag_preserves_unsupported_classification(self):
        directive = b'dtparam=spi=on\n'
        self.mutate(self.loc['config.txt']['offset'],directive+b'#'*(len(self.files['config.txt'])-len(directive)))
        work = self.work/'cli-selection'
        proc = subprocess.run([sys.executable,str(Path(h.__file__)), '--overlay',str(self.overlay),
            '--work',str(work),'--boot-order','emmc-only','--export'],capture_output=True)
        self.assertEqual(proc.returncode,1)
        report=json.loads((work/'selection.json').read_text())
        self.assertEqual(report['status'],'UNSUPPORTED')
        self.assertFalse((work/'exports').exists())
        self.assertFalse(report['process']['launched'])

    def test_export_and_disk_tamper_prevent_gate(self):
        r,b = self.select(); h.export(r,b,self.work/'exports')
        self.mutate(7047*512,b'X')
        with self.assertRaises(h.Outcome): h.verify_launch(r,self.overlay)
        r,b = self.select(); h.export(r,b,self.work/'exports2')
        p = Path(r['exports']['kernel']['path']); p.chmod(0o600); p.write_bytes(b'changed')
        with self.assertRaises(h.Outcome): h.verify_launch(r,self.overlay)

    def test_failed_selection_cannot_export(self):
        self.mutate(510,b'\0\0'); r,b = self.select()
        with self.assertRaises(h.Outcome): h.export(r,b,self.work/'exports')
        self.assertFalse((self.work/'exports').exists())

    def additional_fixture(self, **options):
        self.raw = self.work/f'base-{self.n}.raw'
        self.loc,self.expected,self.files = fixture(self.raw,**options)
        self.initial = h.identity(self.raw)
        self.overlay = self.work/f'disk-{self.n}.qcow2'
        self.n += 1
        run([BIN/'qemu-img','create','-f','qcow2','-F','raw','-b',self.raw,self.overlay])

    def test_includes_filters_and_cycle(self):
        config = self.files['config.txt']
        self.additional_fixture(config=b'include extra.txt\n',includes={'extra.txt':config})
        r,_ = self.select(); self.assertEqual(r['status'],'SELECTED',r)
        self.additional_fixture(config=b'include config.txt\n')
        self.assertEqual(self.select()[0]['status'],'INVALID_CONFIG')
        self.additional_fixture(config=b'[none]\nunknown=1\n[all]\n'+config)
        self.assertEqual(self.select()[0]['status'],'SELECTED')

    def test_missing_manifest_and_explicit_selection(self):
        self.expected = None
        self.assertEqual(self.select()[0]['status'],'UNSUPPORTED')
        self.additional_fixture(config=b'kernel=kernel.img\n')
        self.assertEqual(self.select()[0]['status'],'UNSUPPORTED')

    def test_truncated_and_oversize_declared_files(self):
        # Claim two clusters for a file whose chain ends after one.
        self.mutate(self.loc['kernel.img']['entry']+28,struct.pack('<I',700))
        self.assertEqual(self.select()[0]['status'],'INVALID_LAYOUT')
        self.mutate(self.loc['kernel.img']['entry']+28,struct.pack('<I',h.MAX_FILE+1))
        self.assertEqual(self.select()[0]['status'],'UNSUPPORTED')

    def test_newc_semantics_and_zstd_not_sniffed_valid(self):
        validate('initramfs', archive()+bytes(20)+archive(b'second'))
        for data in (archive()[:-10], b'070701'+bytes(104), archive()+b'\x28\xb5\x2f\xfdgarbage'):
            with self.assertRaises(h.Outcome): validate('initramfs',data)
        with self.assertRaises(h.Outcome) as exc: validate('initramfs',archive()+b'\x28\xb5\x2f\xfd')
        self.assertEqual(exc.exception.code,'INVALID_IMAGE')

    def test_arm64_memory_footprint_can_exceed_file_size(self):
        import struct
        decoded = bytearray(gzip.decompress(self.files['kernel.img']))
        struct.pack_into('<Q', decoded, 16, 4096)
        self.assertEqual(validate('kernel',gzip.compress(decoded))['memory_image_bytes'],4096)

    def test_gzip_crc_and_expansion_limit(self):
        data = bytearray(self.files['kernel.img']); data[-8] ^= 1
        with self.assertRaises(h.Outcome): validate('kernel',data)
        with patch('validate.MAX_FILE',64):
            with self.assertRaises(h.Outcome): validate('kernel',self.files['kernel.img'])


if __name__ == '__main__':
    unittest.main()
