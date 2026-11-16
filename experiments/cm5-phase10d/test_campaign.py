"""Scientific result gates plus real regular-file/QCOW2 injection tests."""
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import campaign as c


class EvidenceTests(unittest.TestCase):
    def test_strict_classification(self):
        self.assertEqual(c.classify({},True),'INCONCLUSIVE')
        self.assertEqual(c.classify({'digest':True,'correction':True},True),'PASS_RECOVERED')
        self.assertEqual(c.classify({'digest':True,'correction':False},True),'INCONCLUSIVE')
        self.assertEqual(c.classify({'digest':True,'correction':True},True,timed_out=True),'INCONCLUSIVE')
        self.assertEqual(c.classify({'functional':True},False),'PASS_CLEAN')
        self.assertEqual(c.classify({'eio':True,'corrupt':True},True,nofec=True),'EXPECTED_VERITY_REJECTION')
        self.assertEqual(c.classify({'eio':True,'corrupt':False},True,nofec=True),'INCONCLUSIVE')

    def test_fec_parser_device_and_byte_base(self):
        log='[ 12.34] device-mapper: verity-fec: 179:2: FEC 1073741824: corrected 4096 errors\n'
        self.assertEqual(c.correction_events(log),[dict(timestamp=12.34,device='179:2',fec_byte_base=1073741824,corrected_errors=4096)])
        self.assertEqual(c.correction_events('kernel loaded FEC module; boot succeeded'),[])

    def test_offsets(self):
        self.assertEqual(c.target('os0')['offset'],545259520)
        self.assertEqual(c.target('os-far')['offset'],1619001344)
        self.assertEqual(c.target('fsw0')['offset'],11283726336)
        self.assertEqual(c.target('no-fec')['offset'],c.target('os0')['offset'])

    def test_fec_interleaver_base_is_not_absolute_offset(self):
        self.assertEqual(c.fec_rsb_base(c.target('os0')),0)
        self.assertEqual(c.fec_rsb_base(c.target('fsw0')),0)
        self.assertEqual(c.fec_rsb_base(c.target('os-far')),4276224)
        other=c.target('os-far');other['block_index']+=10444
        self.assertEqual(c.fec_rsb_base(other),4276224)
        with self.assertRaises(ValueError):c.fec_rsb_base(c.target('no-fec'))

    def test_observer_compiles_and_preserves_default(self):
        original=(c.REPO/'experiments/cm5-phase10c/observe.py').read_text()
        code=c.observer(original,c.target('os0'))
        ast.parse(code)
        self.assertIn('os.O_DIRECT',code)
        self.assertLess(max(map(len,code.splitlines())),4096)
        self.assertIn('P10C_USER_JSON=',code)

    def test_injection_and_boundaries_real_qcow2(self):
        with tempfile.TemporaryDirectory(prefix='cm5-10d-fixture-') as tmp:
            d=Path(tmp); golden=d/'golden.raw'; overlay=d/'overlay.qcow2'
            # Tiny synthetic partition, not a captured image or metadata.
            data=bytes((i*13)%251 for i in range(65536))
            golden.write_bytes(data)
            subprocess.run([str(c.IMG),'create','-f','qcow2','-F','raw','-b',str(golden),str(overlay)],check=True,capture_output=True)
            out=d/'out';lab=d/'lab';out.mkdir();lab.mkdir()
            with patch.dict(c.PARTITIONS,{'os':(2,4096,32768)}):
                fault=c.prepare('os0',out,lab,golden,overlay)
            self.assertEqual(fault['raw_after_injection_sha256'],hashlib.sha256(b'\x5a'*4096).hexdigest())
            self.assertEqual(golden.read_bytes(),data)
            prefix=c.block_read(overlay,0,4096,d/'prefix')
            suffix=c.block_read(overlay,8192,4096,d/'suffix')
            self.assertEqual(prefix,data[:4096]);self.assertEqual(suffix,data[8192:12288])
            with self.assertRaises(ValueError):c.block_read(overlay,0,4096,d/'prefix')
            self.assertTrue((out/'fault.json').exists())

    def test_wrong_backing_rejected(self):
        with tempfile.TemporaryDirectory(prefix='cm5-10d-backing-') as tmp:
            d=Path(tmp);golden=d/'golden';other=d/'other';overlay=d/'overlay'
            golden.write_bytes(bytes(65536));other.write_bytes(bytes(65536))
            subprocess.run([str(c.IMG),'create','-f','qcow2','-F','raw','-b',str(other),str(overlay)],check=True,capture_output=True)
            with self.assertRaises(ValueError):c.prepare('os0',d,d,golden,overlay)

    def test_diagnostic_changes_only_one_hook(self):
        source=Path('/home/aweso/cm5-phase10-private/physical-boot/boot-assets/initramfs_2712-osverified-v8')
        if not source.is_file():self.skipTest('private captured initramfs unavailable')
        import gzip
        import sys
        sys.path.insert(0,str(c.REPO/'experiments/cm5-phase10b'))
        from audit import cpio_entries
        original=source.read_bytes()
        with tempfile.TemporaryDirectory(prefix='cm5-10d-diagnostic-') as tmp:
            d=Path(tmp);out=d/'out';lab=d/'lab';out.mkdir();lab.mkdir()
            dest=c.no_fec_initramfs(out,lab,source)
            before={n:b for n,b in cpio_entries(original)}
            after={n:b for n,b in cpio_entries(gzip.decompress(dest.read_bytes()))}
            changed={n for n in before.keys()|after.keys() if before.get(n)!=after.get(n)}
            self.assertEqual(changed,{'scripts/local-top/cm5-fsw-verity'})
            hook=after['scripts/local-top/cm5-fsw-verity']
            self.assertNotIn(b'--fec-device="$OSFL"',hook)
            self.assertIn(b'--fec-device="$FL" --fec-roots=2',hook)
            self.assertIn(b'P10D_EXPECTED_ROOT_REJECTION=1',hook)
            self.assertEqual(source.read_bytes(),original)


if __name__=='__main__':unittest.main()
