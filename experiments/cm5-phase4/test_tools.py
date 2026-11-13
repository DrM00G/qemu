"""Metadata safety and EBR parsing tests with synthetic regular files."""
import struct
import tempfile
import unittest
from pathlib import Path
from disk_inventory import inventory, regular

class InventoryTests(unittest.TestCase):
    def test_reject_device(self):
        with self.assertRaises(ValueError): regular('/dev/null')

    def test_mbr_ebr_and_cycle(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'disk'
            raw=bytearray(1024*1024)
            def entry(sector,index,kind,start,count):
                struct.pack_into('<B3sB3sII',raw,sector*512+446+16*index,
                                 0,b'\0'*3,kind,b'\0'*3,start,count)
                raw[sector*512+510:sector*512+512]=b'\x55\xaa'
            entry(0,0,0x83,8,8)
            entry(0,1,0x0f,32,100)
            entry(32,0,0x83,1,8)
            p.write_bytes(raw)
            r=inventory(p)
            self.assertEqual([v['number'] for v in r['partitions']],[1,2,5])
            self.assertEqual(r['partitions'][2]['offset'],33*512)
            entry(32,1,0x0f,0,100)
            p.write_bytes(raw)
            with self.assertRaisesRegex(ValueError,'cyclic'): inventory(p)

    def test_bad_signature(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'bad'; p.write_bytes(bytes(1024))
            with self.assertRaises(ValueError): inventory(p)

if __name__=='__main__': unittest.main()
