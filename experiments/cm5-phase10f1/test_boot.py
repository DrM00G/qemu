"""Local policy/archive tests, including original read-only captured reference."""
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent/'cm5-phase10f'))
import block_reader
from block_reader import Outcome
from validate import validate
from test_handoff import archive, fixture
from boot_config import select_cm5, SUBSTITUTIONS


def compress(data):
    return subprocess.run(['zstd','-q','-c','--check'], input=data,
                          capture_output=True, check=True).stdout


class FakeFAT:
    def __init__(self, files):
        self.files = files
    def file(self, name):
        if name not in self.files:
            raise Outcome('SELECTED_FILE_UNAVAILABLE', 'missing '+name)
        return self.files[name]
    def directory(self):
        return [dict(name=n) for n in self.files]


class ConfigTests(unittest.TestCase):
    def select(self, text, files=None):
        self.report = {}
        return select_cm5(FakeFAT({'config.txt':text.encode(), **(files or {})}), self.report)

    def test_model_and_precedence(self):
        s = self.select('[cm4]\nkernel=bad\n[cm5]\nkernel=a\n[pi5]\nkernel=b\n[all]\ninitramfs i followkernel\n')
        self.assertEqual(s, dict(kernel='b',dtb='bcm2712-rpi-cm5-cm5io.dtb',cmdline='cmdline.txt',initramfs='i'))

    def test_inactive_unknown_directive(self):
        self.select('[none]\nunknown=1\ninclude missing\n[all]\ninitramfs i followkernel')

    def test_unknown_filter_fails_even_inactive(self):
        with self.assertRaises(Outcome): self.select('[none]\n[unknown]\n')

    def test_active_unknown_fails(self):
        for line in ('dtparam=spi=on','dtoverlay=unknown','os_prefix=x','armstub=x','kernel_address=1'):
            with self.subTest(line=line), self.assertRaises(Outcome): self.select(line)

    def test_include_textual_state_and_last_assignment(self):
        s=self.select('kernel=a\ninclude extra\nkernel=skipped\n[all]\ninitramfs i followkernel',
                      {'extra':b'kernel=b\n[none]\n'})
        self.assertEqual(s['kernel'],'b')

    def test_include_cycle_and_bound(self):
        for data in (b'include config.txt',b'#'+b'x'*65536):
            with self.assertRaises(Outcome): self.select('include extra',{'extra':data})

    def test_defaults_and_auto(self):
        s=self.select('auto_initramfs=1',{'kernel_2712.img':b''})
        self.assertEqual(s['initramfs'],'initramfs_2712')
        s=self.select('auto_initramfs=1',{'kernel8.img':b''})
        self.assertEqual(s['kernel'],'kernel8.img');self.assertEqual(s['initramfs'],'initramfs8')

    def test_auto_override_and_explicit_selection(self):
        s=self.select('auto_initramfs=1\nauto_initramfs=0\ninitramfs original followkernel')
        self.assertEqual(s['initramfs'],'original')
        with self.assertRaises(Outcome): self.select('auto_initramfs=1\ninitramfs original followkernel')

    def test_substitutions_recorded_and_bounded(self):
        # Minimal valid flattened tree, supplied only as overlay structure fixture.
        import struct
        tree=struct.pack('>I',1)+bytes(4)+struct.pack('>II',2,9)
        dt=struct.pack('>10I',0xd00dfeed,72,56,72,40,17,16,0,0,16)+bytes(16)+tree
        for (k,v),reason in SUBSTITUTIONS.items():
            with self.subTest(k=k,v=v):
                f={'overlays/'+v.split(',')[0]+'.dtbo':dt} if k=='dtoverlay' else {}
                self.select(k+'='+v+'\ninitramfs i followkernel',f)
                row=self.report['config_directives'][0]
                self.assertEqual(row['category'],'LAB_SUBSTITUTION');self.assertEqual(row['reason'],reason)
                with self.assertRaises(Outcome): self.select(k+'='+v+'BAD')

    def test_missing_overlay_stops(self):
        with self.assertRaises(Outcome): self.select('dtoverlay=nospi10\ninitramfs i followkernel')

    def test_missing_initramfs_policy_stops(self):
        with self.assertRaises(Outcome): self.select('kernel=kernel.img')


class ArchiveTests(unittest.TestCase):
    def check(self, data): return validate('initramfs',data)
    def test_concatenated_formats(self):
        a=archive()
        prefix=a+bytes(16)+compress(a)+compress(a)+gzip.compress(a)
        pad=bytes(-len(prefix)%4)
        r=self.check(prefix+pad+a)
        self.assertEqual(r['archives'],5)
        self.assertEqual(r['decoded_sha256'],hashlib.sha256(a+bytes(16)+a*3+pad+a).hexdigest())

    def test_captured_read_only(self):
        p=Path('/home/aweso/cm5-phase10-private/physical-boot/boot-assets/initramfs_2712-osverified-v8')
        data=p.read_bytes();self.assertEqual(hashlib.sha256(data).hexdigest(),'fcaade1e3aab0d79a51a170f556d25d0d1476bc17518099de54f5ebe16feab5b')
        r=self.check(data);self.assertEqual((r['archives'],r['entries'],r['decoded_bytes']),(2,1091,63190528))
        self.assertEqual(r['segments'][1]['decoded_sha256'],'53a9a5df5cadba05da9719869096a93646ce45ab054c1f8ce55c53a74ca85d48')

    def test_truncated_frames(self):
        frame=compress(archive())
        for n in (1,4,8,len(frame)-1):
            with self.subTest(n=n), self.assertRaises(Outcome):self.check(archive()+frame[:n])

    def test_frame_checksum(self):
        f=bytearray(compress(archive()));f[-1]^=1
        with self.assertRaises(Outcome):self.check(f)

    def test_bad_decoded_archive(self):
        for a in (b'garbage',archive()[:-1],archive().replace(b'TRAILER!!!',b'NOTRAILER!')):
            with self.subTest(),self.assertRaises(Outcome):self.check(compress(a))

    def test_overexpansion(self):
        f=compress(archive(b'x'*200000))
        with patch('validate.MAX_FILE',10000), self.assertRaises(Outcome):self.check(f)

    def test_window_bound(self):
        # Unknown-content-size frame declaring a >64MiB window.
        with self.assertRaises(Outcome):self.check(b'\x28\xb5\x2f\xfd\x00\xa8\x01\x00\x00')

    def test_unsupported_and_trailing(self):
        for extra in (b'BZh',b'\x50\x2a\x4d\x18'+bytes(4),b'x'):
            with self.subTest(extra=extra),self.assertRaises(Outcome):self.check(archive()+extra)

    def test_padding_and_trailer(self):
        a=bytearray(archive());a[115]=1
        with self.assertRaises(Outcome):self.check(a)

    def test_malformed_newc_fields_and_boundaries(self):
        base=archive()
        cases=[]
        for offset,patch_data in ((6,b'z'),(94,b'00000000'),(54,b'7fffffff'),(114,b'x')):
            b=bytearray(base);b[offset:offset+len(patch_data)]=patch_data;cases.append(bytes(b))
        cases.extend([base[:109],base[:-4]])
        for data in cases:
            with self.subTest(),self.assertRaises(Outcome):self.check(compress(data))

    def test_global_archive_and_segment_limits(self):
        with self.assertRaises(Outcome):self.check(archive()*129)
        with self.assertRaises(Outcome):self.check(compress(bytes(64)))

    def test_unaligned_uncompressed_and_decoded_archive(self):
        for data in (b'\0'+archive(),compress(b'\0'+archive())):
            with self.subTest(),self.assertRaises(Outcome):self.check(data)


if __name__=='__main__':unittest.main()
