"""Private policy/guard regressions; no captured FSW execution on host."""
import ast
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import generation as g
import seal


class GuardTests(unittest.TestCase):
    def test_ranges_and_owned_regular_file_edits(self):
        seal.bounded(512,512,1024)
        for args in [(-1,1,1024),(0,0,1024),(1024,1,1024),(512,513,1024),(2**64,4096,1024)]:
            with self.assertRaises(ValueError):seal.bounded(*args)
        with tempfile.TemporaryDirectory() as tmp:
            b=seal.Builder(Path(tmp)/'owned')
            p=b.out/'file';p.write_bytes(b'probe');b.writable(p)
            p.chmod(0o400)
            with self.assertRaises(ValueError):b.writable(p)
            link=b.out/'symlink';link.symlink_to(p)
            with self.assertRaises(ValueError):g.regular(link)
            hard=b.out/'alias';os.link(p,hard)
            with self.assertRaises(ValueError):g.regular(p)
            fifo=b.out/'fifo';os.mkfifo(fifo)
            with self.assertRaises(ValueError):g.regular(fifo)
            external=Path(tmp)/'outside';external.write_bytes(b'probe')
            with self.assertRaises(ValueError):b.writable(external)

    def test_manifest_pin_and_generation_local_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'generation.json';p.write_text('{}');p.chmod(0o400)
            for digest in ('', '0'*64):
                with self.assertRaises(ValueError):g.load(p,digest)
            for name in ('../image','/dev/test','sub/image','image:protocol'):
                with self.assertRaises(ValueError):g.artifact(dict(_directory=tmp,artifacts={'image':{'name':name}}),'image')

    def test_direct_launcher_has_no_elf_payload_and_forbids_upload(self):
        path=g.ROOT/'experiments/cm5-phase10j/run.py'
        sys.path.insert(0,str(path.parent))
        spec=importlib.util.spec_from_file_location('m_harness',path)
        harness=importlib.util.module_from_spec(spec);spec.loader.exec_module(harness)
        code=harness.direct_payload_code(dict(generation_id='probe',expected_tables={},installed_elf={'bytes':5125072}),30)
        tree=ast.parse(code)
        assigned=[x.targets[0].id for x in tree.body if isinstance(x,ast.Assign) and isinstance(x.targets[0],ast.Name)]
        self.assertNotIn('PAYLOAD',assigned)
        self.assertNotIn('elf.read_bytes(',code)
        self.assertNotIn('b64decode',code)
        self.assertLess(len(code),20000)
        with tempfile.TemporaryDirectory() as tmp:
            work=Path(tmp)/'must-not-be-created'
            result=subprocess.run([sys.executable,str(path),'--execution-mode',g.MODE,
                '--sealed-generation','unused','--generation-sha256','0'*64,
                '--boot-profile','operational','--fsw','must-not-upload','--work',str(work)],capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0);self.assertFalse(work.exists())
            self.assertIn('no --fsw upload',result.stderr)

    def test_guest_rejects_unverified_mounts_and_distinguishes_loader_errors(self):
        tree=ast.parse((Path(__file__).with_name('guest_direct.py')).read_text())
        definitions=ast.Module(body=[x for x in tree.body if isinstance(x,(ast.Import,ast.ImportFrom,ast.FunctionDef))],type_ignores=[])
        ns={};exec(compile(definitions,'guest-helper-tests','exec'),ns)
        ns['require_mount']('/dev/mapper/cm5_fsw_verified ext4 ro,noatime,norecovery','/dev/mapper/cm5_fsw_verified')
        for text in ('/dev/mmcblk0p5 ext4 ro,norecovery','/dev/mapper/cm5_fsw_verified ext4 rw,norecovery','/dev/mapper/cm5_fsw_verified ext4 ro'):
            with self.assertRaises(RuntimeError):ns['require_mount'](text,'/dev/mapper/cm5_fsw_verified')
        self.assertEqual(ns['failure_stage'](127,'error while loading shared libraries',False),'dynamic-loading')
        self.assertEqual(ns['failure_stage'](126,'cannot execute',False),'executable-launch')
        self.assertEqual(ns['failure_stage'](139,'segmentation fault',True),'application-operation')
        self.assertIsNone(ns['failure_stage'](124,'',True))


@unittest.skipUnless(os.environ.get('CM5_PHASE10M_ORIGINAL'),'private captured initramfs not configured')
class CapturedPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original=Path(os.environ['CM5_PHASE10M_ORIGINAL']).read_bytes()
        cls.root='a'*64
        cls.candidate=g.construct_initramfs(cls.original,cls.root)

    def test_only_declared_fsw_pin_override_and_original_scan_policy(self):
        base=g.original_profile.construct(self.original)
        self.assertTrue(self.candidate.startswith(base))
        tail=self.candidate[(len(base)+3)&~3:]
        entries=list(g.original_profile.cpio_entries(tail))
        self.assertEqual(entries[0][0],'etc/cm5-verity/fsw.roothash')
        self.assertEqual(entries[0][1].strip(),self.root.encode())
        self.assertEqual(entries[1],('TRAILER!!!',b''));self.assertEqual(len(entries),2)
        with self.assertRaises(ValueError):g.construct_initramfs(self.original,'not a root')

    def test_wrong_kernel_root_or_candidate_refused(self):
        roots=dict(g.original_profile.cpio_entries(self.original))
        expected=dict(os_table=['']*11+[roots['etc/cm5-verity/os.roothash'].decode().strip()],fsw_table=['']*11+[self.root])
        manifest=dict(fsw_root=self.root,artifacts={'initramfs':{'sha256':g.sha(self.candidate)}},
                      expected_tables=expected,generation_id='test',_manifest_sha256='fixture')
        self.assertEqual(g.approve(self.original,self.candidate,manifest,g.original_profile.KERNEL_SHA)['generation_id'],'test')
        with self.assertRaises(ValueError):g.approve(self.original,self.candidate,manifest,'0'*64)
        with self.assertRaises(ValueError):g.approve(self.original,self.candidate[:-1]+b'x',manifest,g.original_profile.KERNEL_SHA)
        manifest['expected_tables']['os_table'][11]='0'*64
        with self.assertRaises(ValueError):g.approve(self.original,self.candidate,manifest,g.original_profile.KERNEL_SHA)


if __name__=='__main__':unittest.main()
