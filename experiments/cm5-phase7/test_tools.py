#!/usr/bin/env python3
"""Meaningful safety/parser tests; synthetic fixtures are not physical data."""
import importlib.util
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE / 'physical-probes'))
from hardware_facts import describe_dt, dt_from_blob, dt_from_dir, partition_facts
spec = importlib.util.spec_from_file_location('comparison', HERE / 'compare-hardware.py')
comparison = importlib.util.module_from_spec(spec)
spec.loader.exec_module(comparison)

class HardwareToolsTest(unittest.TestCase):
    def test_private_properties_never_become_facts(self):
        props = {'/': {'compatible': b'raspberrypi,5-compute-module\0',
                       'serial-number': b'SECRET-SERIAL-12345\0'},
                 '/chosen': {'bootargs': b'password=private 192.0.2.77\0'},
                 '/ethernet': {'mac-address': bytes.fromhex('001122334455')}}
        text = json.dumps(describe_dt(props))
        for secret in ('SECRET-SERIAL', 'password', '192.0.2.77', '001122334455'):
            self.assertNotIn(secret, text)

    def test_missing_observation_is_unavailable(self):
        result = comparison.compare({}, {})
        self.assertTrue(all(r['status'] == 'UNAVAILABLE' for r in result['capabilities']))
        self.assertFalse(result['physical_measurements_available'])

    def test_untrusted_fact_string_is_not_reported(self):
        secret = 'token=secret serial=12345 host=192.0.2.88'
        facts = {'cpu.models': {'value': [secret], 'source': secret}}
        result = comparison.compare(facts, facts)
        self.assertNotIn(secret, json.dumps(result))
        row = next(r for r in result['capabilities'] if r['feature'] == 'cpu.models')
        self.assertEqual(row['status'], 'UNAVAILABLE')

    def test_mip_fields_compare_independent_of_node_name(self):
        cells = lambda *v: struct.pack('>' + 'I' * len(v), *v)
        props = dict(compatible=b'brcm,bcm2712-mip\0',
                     reg=cells(0x10, 0x130000, 0, 0xc0, 0xff, 0xfffff000, 0, 0x1000))
        props['msi-ranges'] = cells(99, 0, 128, 1, 64)
        props['brcm,msi-offset'] = cells(0)
        a = describe_dt({'/odd-physical-name': props})
        b = describe_dt({'/qemu-name': props})
        row = next(r for r in comparison.compare(a, b)['capabilities'] if r['feature'] == 'interrupt.mip0')
        self.assertEqual(row['status'], 'MATCH')
        self.assertEqual(row['physical_value']['msi_address'], 0xfffffff000)

    def test_partition_names_and_uuids_not_published(self):
        text = json.dumps({'blockdevices': [dict(name='mmcblk0p7', type='part',
            label='RECOVERY', size=4096, start=2048, uuid='SECRET-UUID', fstype='ext4')]})
        facts = partition_facts(text)
        self.assertNotIn('mmcblk', json.dumps(facts))
        self.assertNotIn('SECRET', json.dumps(facts))
        self.assertEqual(facts[0]['number'], 7)
        self.assertEqual(facts[0]['start_sector_512'], 2048)

    def test_malformed_fdt_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'bad.dtb'
            p.write_bytes(b'not a DT')
            with self.assertRaises(ValueError):
                dt_from_blob(p)

    def test_gic_cells_and_bus_translation_are_normalized(self):
        c = lambda *v: struct.pack('>' + 'I' * len(v), *v)
        physical = {'/': {'#address-cells': c(2), '#size-cells': c(2)},
            '/soc': {'#address-cells': c(1), '#size-cells': c(1),
                     'ranges': c(0, 0x10, 0, 0x80000000)},
            '/soc/gic': {'compatible': b'arm,gic-400\0',
                         'reg': c(0x7fff9000, 0x1000)}}
        qemu = {'/': {'#address-cells': c(2), '#size-cells': c(2)},
            '/different-name': {'compatible': b'arm,cortex-a15-gic\0',
                'reg': c(0x10, 0x7fff9000, 0, 0x1000)}}
        a, b = describe_dt(physical), describe_dt(qemu)
        for key in ('interrupt.controllers', 'interrupt.gic_resources'):
            self.assertEqual(a[key]['value'], b[key]['value'])

if __name__ == '__main__':
    unittest.main()
