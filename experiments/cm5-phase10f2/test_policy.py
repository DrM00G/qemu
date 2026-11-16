"""Real independent QCOW2 source experiments, never physical USB enumeration."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

import boot_policy as p
sys.path.insert(0,str(p.HERE.parent/'cm5-phase10f'))
from test_handoff import fixture
from block_reader import BIN, run


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.work=Path(tempfile.mkdtemp(prefix='phase10f2-policy-'))
        self.sources={}; self.manifests={}; self.locations={}; self.files={}
        for source in ('emmc','usb'):
            raw=self.work/(source+'.raw')
            loc,expected,files=fixture(raw,payloads={'cmdline.txt':('console='+source+'\n').encode(),'unused.txt':b'unused'})
            disk=self.work/(source+'.qcow2')
            run([BIN/'qemu-img','create','-f','qcow2','-F','raw','-b',raw,disk])
            self.sources[source]=disk;self.manifests[source]=expected;self.locations[source]=loc;self.files[source]=files

    def select(self,emmc=True,usb=False,**kw):
        os.environ['CM5_BOOT_READER']='qemu-io'
        report,buffers=p.select(self.sources['emmc'] if emmc else None,self.work,self.manifests['emmc'],
             usb=self.sources['usb'] if usb else None,usb_expected=self.manifests['usb'],**kw)
        p.h.write_report(self.work/'decision.json',report)
        return report,buffers

    def mutate(self,source,offset,body):
        path=self.work/'patch';path.write_bytes(body)
        run([BIN/'qemu-io','-f','qcow2','-c',f'write -s {path} {offset} {len(body)}',self.sources[source]])

    def test_parse(self):
        self.assertEqual(p.parse_order('0xf14'),['usb-msd','emmc','restart'])
        for order in ('0xf24','0x0','0x14','0xff14','0x100000000','bad',14):
            with self.assertRaises(p.h.Outcome):p.parse_order(order)

    def test_usb_unavailable(self):
        r,b=self.select();self.assertEqual(r['status'],'SELECTED');self.assertEqual(b['cmdline'],self.files['emmc']['cmdline.txt'])
        self.assertEqual(r['boot_source_trace']['selected_source'],'emmc')
        self.assertEqual(r['boot_source_trace']['attempts'][0]['reads'],[])

    def test_usb_priority_and_distinct_bytes(self):
        r,b=self.select(usb=True);self.assertEqual(r['status'],'SELECTED')
        self.assertEqual(b['cmdline'],self.files['usb']['cmdline.txt'])
        self.assertNotEqual(b['cmdline'],self.files['emmc']['cmdline.txt'])
        self.assertEqual(len(r['boot_source_trace']['attempts']),1)
        self.assertEqual(r['boot_source_trace']['selected_source'],'usb-msd')
        self.assertEqual(r['overlay_chain_before'][0]['identity']['path'],str(self.sources['usb']))

    def test_bounded_restart(self):
        r,b=self.select(emmc=False);self.assertEqual(r['status'],'BOUNDED_RESTART');self.assertFalse(b)
        self.assertEqual(len(r['boot_source_trace']['attempts']),4)
        self.assertEqual([t['executed'] for t in r['boot_source_trace']['transitions']],[True,False])

    def test_bad_order_before_reads(self):
        r,b=self.select(order='0xf24');self.assertEqual(r['status'],'UNSUPPORTED');self.assertFalse(r['reads'])

    def test_corrupt_emmc(self):
        self.mutate('emmc',510,b'\0\0');r,b=self.select()
        self.assertEqual(r['status'],'INVALID_LAYOUT');self.assertFalse(b)
        self.assertEqual(r['boot_source_trace']['attempts'][-1]['classification'],'INVALID_PARTITION_OR_FILESYSTEM')

    def test_missing_selected_usb_stops_before_emmc(self):
        self.mutate('usb',self.locations['usb']['kernel.img']['entry'],b'\xe5')
        r,b=self.select(usb=True);self.assertEqual(r['status'],'SELECTED_FILE_UNAVAILABLE');self.assertFalse(b)
        self.assertEqual(len(r['boot_source_trace']['attempts']),1)
        self.assertEqual(r['boot_source_trace']['attempts'][0]['classification'],'SELECTED_FILE_FAILURE')

    def test_unused_corruption(self):
        self.mutate('emmc',self.locations['emmc']['unused.txt']['offset'],b'X')
        r,b=self.select();self.assertEqual(r['status'],'SELECTED');self.assertTrue(b)

    def test_wrong_source_manifest(self):
        self.manifests['usb']=self.manifests['emmc'];r,b=self.select(usb=True)
        self.assertEqual(r['status'],'INVALID_IMAGE');self.assertFalse(b)
        self.assertEqual(len(r['boot_source_trace']['attempts']),1)

    def test_unreadable_usb_stops(self):
        self.sources['usb'].write_bytes(b'not a readable QCOW2 image')
        r,b=self.select(usb=True)
        self.assertEqual(r['boot_source_trace']['attempts'][0]['classification'],'UNREADABLE_MEDIA')
        self.assertFalse(b);self.assertEqual(len(r['boot_source_trace']['attempts']),1)

    def test_invalid_usb_partition_does_not_guess_fallback(self):
        self.mutate('usb',510,b'\0\0');r,b=self.select(usb=True)
        self.assertEqual(r['status'],'INVALID_LAYOUT');self.assertFalse(b)
        self.assertEqual(len(r['boot_source_trace']['attempts']),1)

    def test_unsupported_usb_config_stops(self):
        body=b'unknown=1\n'
        self.mutate('usb',self.locations['usb']['config.txt']['offset'],body)
        r,b=self.select(usb=True)
        self.assertEqual(r['status'],'UNSUPPORTED');self.assertFalse(b)
        self.assertEqual(r['boot_source_trace']['attempts'][0]['classification'],'UNSUPPORTED_FIRMWARE_BEHAVIOR')

    def test_same_identity_rejected(self):
        self.sources['usb']=self.sources['emmc'];r,b=self.select(usb=True)
        self.assertEqual(r['status'],'UNSUPPORTED');self.assertFalse(b)

    def test_error_classifications(self):
        self.assertEqual(p.classify(dict(status='READ_ERROR',stage='BOOT_FAT')),'UNREADABLE_MEDIA')
        self.assertEqual(p.classify(dict(status='UNSUPPORTED',stage='CONFIG_SELECTION')),'UNSUPPORTED_FIRMWARE_BEHAVIOR')


if __name__=='__main__':unittest.main()
