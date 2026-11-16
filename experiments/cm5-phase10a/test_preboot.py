"""Synthetic, nonproprietary FAT fixtures; never mounts a filesystem."""
import gzip
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import preboot as b


def lfn_entries(name, alias):
    checksum = 0
    for byte in alias:
        checksum = (((checksum & 1) << 7) + (checksum >> 1) + byte) & 255
    text = name.encode('utf-16le') + b'\0\0'
    text += b'\xff\xff' * ((-len(text) // 2) % 13)
    result = []
    count = len(text) // 26
    for n in range(count, 0, -1):
        e = bytearray(32)
        e[0], e[11], e[13] = n | (64 if n == count else 0), 15, checksum
        chunk = text[(n-1)*26:n*26]
        e[1:11], e[14:26], e[28:32] = chunk[:10], chunk[10:22], chunk[22:]
        result.append(e)
    return result


def fixture(path, bits=16, config=None):
    """Small FAT16 or sparse FAT32 partition; synthetic Image/newc/DTB headers."""
    kernel = bytearray(700)
    kernel[56:60] = b'ARM\x64'
    struct.pack_into('<Q', kernel, 16, len(kernel))
    dtb = struct.pack('>10I', 0xd00dfeed, 72, 56, 72, 40, 17, 16, 0, 0, 16) + bytes(32)
    files = {'config.txt': config or b'[all]\nkernel=kernel_2712.img\ninitramfs initramfs_2712-osverified-v8 followkernel\ndevice_tree=bcm2712-rpi-cm5-cm5io.dtb\ncmdline=cmdline_2712-osverified-v8.txt\n',
             b.DEFAULTS['kernel']: bytes(kernel), b.DEFAULTS['initramfs']: gzip.compress(b'070701'+bytes(128)),
             b.DEFAULTS['dtb']: dtb, b.DEFAULTS['cmdline']: b'console=ttyAMA0 rdinit=/init\n'}
    total, fatsz, reserved, roots = (5000, 20, 1, 128) if bits == 16 else (70000, 550, 32, 0)
    base = 2048
    data_sector = reserved + fatsz + (roots*32+511)//512
    root_offset = (base + reserved + fatsz)*512 if bits == 16 else (base + data_sector)*512
    mbr = bytearray(512)
    mbr[450] = 14 if bits == 16 else 12
    struct.pack_into('<II', mbr, 454, base, total)
    mbr[510:] = b'\x55\xaa'
    boot = bytearray(512)
    struct.pack_into('<H', boot, 11, 512)
    boot[13] = 1
    struct.pack_into('<H', boot, 14, reserved)
    boot[16] = 1
    struct.pack_into('<H', boot, 17, roots)
    if bits == 16:
        struct.pack_into('<H', boot, 19, total)
        struct.pack_into('<H', boot, 22, fatsz)
    else:
        struct.pack_into('<III', boot, 32, total, fatsz, 0)
        struct.pack_into('<I', boot, 44, 2)
    boot[510:] = b'\x55\xaa'
    entries, locations = bytearray(), {}
    with path.open('wb') as f:
        f.truncate((base+total)*512)
        f.seek(0)
        f.write(mbr)
        f.seek(base*512)
        f.write(boot)
        def fat(c, value):
            f.seek((base+reserved)*512+c*(bits//8))
            f.write(value.to_bytes(bits//8, 'little'))
        eoc = 0xffff if bits == 16 else 0xfffffff
        fat(0, eoc)
        fat(1, eoc)
        if bits == 32:
            # Root occupies two clusters, with chain traversal exercised.
            fat(2, 3)
            fat(3, eoc)
        cluster = 4
        for n, (name, data) in enumerate(files.items()):
            alias = f'FILE{n:04d}DAT'.encode()
            entries.extend(b''.join(lfn_entries(name, alias)))
            e = bytearray(32)
            e[:11], e[11] = alias, 32
            struct.pack_into('<H', e, 26, cluster)
            struct.pack_into('<I', e, 28, len(data))
            entry_offset = root_offset+len(entries)
            entries.extend(e)
            locations[name] = dict(entry=entry_offset,
                offset=(base+data_sector+cluster-2)*512, cluster=cluster)
            for i in range(0, len(data), 512):
                f.seek((base+data_sector+cluster-2)*512)
                f.write(data[i:i+512])
                fat(cluster, cluster+1 if i+512 < len(data) else eoc)
                cluster += 1
        f.seek(root_offset)
        f.write(entries)
    return locations


class ProxyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)/'disk.raw'
        self.loc = fixture(self.path)

    def mutate(self, offset, data):
        with self.path.open('r+b') as f:
            f.seek(offset)
            f.write(data)

    def test_clean_and_explicit_unsupported_handoff(self):
        r = b.probe(self.path)
        self.assertEqual((r['status'], r['stage']), ('UNSUPPORTED', 'HEADERS_VALIDATED'))
        self.assertFalse(r['process']['launched'])
        self.assertEqual(len(r['files']), 5)
        self.assertEqual(r['proxy_bytes_returned'], sum(e['returned'] for e in r['reads']))

    def test_fat32_and_long_names(self):
        fixture(self.path, bits=32)
        r = b.probe(self.path)
        self.assertEqual(r['stage'], 'HEADERS_VALIDATED')
        self.assertEqual(r['fat']['bits'], 32)

    def test_corrupt_mbr(self):
        self.mutate(510, b'\0\0')
        self.assertEqual(b.probe(self.path)['status'], 'INVALID_LAYOUT')

    def test_missing_each_selected_file(self):
        for kind in ('kernel', 'initramfs', 'dtb'):
            with self.subTest(kind=kind):
                loc = fixture(self.path)
                self.mutate(loc[b.DEFAULTS[kind]]['entry'], b'\xe5')
                self.assertEqual(b.probe(self.path)['status'], 'SELECTED_FILE_UNAVAILABLE')

    def test_corrupt_each_selected_header(self):
        for kind in ('kernel', 'initramfs', 'dtb'):
            with self.subTest(kind=kind):
                loc = fixture(self.path)
                self.mutate(loc[b.DEFAULTS[kind]]['offset'], bytes(64))
                self.assertEqual(b.probe(self.path)['status'], 'INVALID_IMAGE')

    def test_unread_boot_fault_does_not_fail(self):
        clean = b.probe(self.path)
        sector = 2048 + 4999
        self.assertFalse(any(e['offset'] <= sector*512 < e['offset']+e['returned'] for e in clean['reads']))
        self.mutate(sector*512, b'\xff'*512)
        damaged = b.probe(self.path)
        self.assertEqual(damaged['stage'], 'HEADERS_VALIDATED')
        self.assertEqual(clean['files'], damaged['files'])

    def test_injected_read_error_has_zero_returned_and_no_fallback(self):
        sector = self.loc[b.DEFAULTS['kernel']]['offset']//512
        r = b.probe(self.path, bad_sectors=[sector])
        self.assertEqual(r['status'], 'READ_ERROR')
        self.assertEqual(r['reads'][-1]['returned'], 0)
        self.assertNotIn(b.DEFAULTS['kernel'], r['files'])
        self.assertFalse(r['process']['launched'])

    def test_unread_injected_error_does_not_fail(self):
        self.assertEqual(b.probe(self.path, bad_sectors=[7047])['stage'], 'HEADERS_VALIDATED')

    def test_config_selection_override_and_missing(self):
        fixture(self.path, config=b'kernel=absent.img\n')
        self.assertEqual(b.probe(self.path)['status'], 'SELECTED_FILE_UNAVAILABLE')
        self.assertEqual(b.probe(self.path, overrides={'kernel': b.DEFAULTS['kernel']})['stage'], 'HEADERS_VALIDATED')

    def test_config_unknown_not_ignored(self):
        for config in (b'include other.txt\n', b'os_prefix=other/\n', b'[gpio4=1]\n', b'dtoverlay=foo\n'):
            fixture(self.path, config=config)
            self.assertEqual(b.probe(self.path)['status'], 'UNSUPPORTED')
            self.assertEqual(b.probe(self.path)['stage'], 'CONFIG_SELECTION')
            self.assertFalse(b.probe(self.path)['selection_complete'])
            self.assertEqual(b.probe(self.path)['selected'], {})

    def test_boot_order_usb_not_fabricated(self):
        r = b.probe(self.path, policy='0xf14')
        self.assertEqual(r['status'], 'UNSUPPORTED')
        self.assertEqual(r['reads'], [])

    def test_file_chain_cycle(self):
        c = self.loc[b.DEFAULTS['kernel']]['cluster']
        self.mutate((2048+1)*512+c*2, c.to_bytes(2, 'little'))
        self.assertEqual(b.probe(self.path)['status'], 'INVALID_LAYOUT')

    def test_invalid_bpb_and_partition_bounds(self):
        self.mutate(2048*512+13, b'\0')
        self.assertEqual(b.probe(self.path)['status'], 'INVALID_LAYOUT')
        fixture(self.path)
        self.mutate(454, (0xffffffff).to_bytes(4, 'little'))
        self.assertEqual(b.probe(self.path)['status'], 'INVALID_LAYOUT')

    def test_lfn_checksum_corruption(self):
        self.mutate((2048+1+20)*512+13, b'\xff')
        self.assertEqual(b.probe(self.path)['status'], 'INVALID_LAYOUT')

    def test_short_pread(self):
        with patch('preboot.os.pread', return_value=b''):
            self.assertEqual(b.probe(self.path)['status'], 'READ_ERROR')

    def test_no_device_access(self):
        # Use a FIFO fixture, not an actual host /dev device.
        import os
        fifo = Path(self.tmp.name)/'fifo'
        os.mkfifo(fifo)
        with patch('preboot.os.open') as opened:
            self.assertEqual(b.probe(fifo)['status'], 'UNSUPPORTED')
            opened.assert_not_called()

    def test_missing_private_golden_cli(self):
        out = Path(self.tmp.name)/'run'
        subprocess.run([sys.executable, str(Path(b.__file__)), '--golden', str(out/'missing'),
                        '--output', str(out), '--boot-order', 'emmc-only'], check=True, capture_output=True)
        self.assertEqual(json.loads((out/'result.json').read_text())['status'], 'SKIPPED_WITH_REASON')

    def test_unsupported_compression_not_invalid_image(self):
        for kind, data in (('kernel', gzip.compress(bytes(80))),
                           ('initramfs', b'\xfd7zXZ\0'+bytes(80))):
            with self.assertRaises(b.Outcome) as error:
                b.validate(kind, data)
            self.assertEqual(error.exception.code, 'UNSUPPORTED')

    def test_bad_gzip_payload_classified(self):
        with self.assertRaises(b.Outcome) as error:
            b.validate('initramfs', b'\x1f\x8b\x08'+bytes(50))
        self.assertEqual(error.exception.code, 'INVALID_IMAGE')

    def test_ebr_geometry_and_cycle(self):
        ext = 7100
        with self.path.open('r+b') as f:
            f.truncate(7200*512)
        e = bytearray(16)
        e[4] = 15
        struct.pack_into('<II', e, 8, ext, 100)
        self.mutate(478, e)
        ebr = bytearray(512)
        ebr[450] = 131
        struct.pack_into('<II', ebr, 454, 1, 20)
        ebr[510:] = b'\x55\xaa'
        self.mutate(ext*512, ebr)
        r = b.probe(self.path)
        self.assertEqual(r['stage'], 'HEADERS_VALIDATED')
        self.assertEqual(r['partitions'][-1]['start'], ext+1)
        ebr[466] = 15
        struct.pack_into('<II', ebr, 470, 0, 100)
        self.mutate(ext*512, ebr)
        self.assertEqual(b.probe(self.path)['status'], 'INVALID_LAYOUT')

    def test_cli_copy_faults_and_golden_protection(self):
        # Run the exact copy/inject/report path on a small synthetic fixture.
        # The production CLI still requires USER_BYTES; no size override exists.
        before = b.identity(self.path)
        self.path.chmod(0o400)
        with patch('preboot.USER_BYTES', before['bytes']):
            r = b.run_probe(self.path, Path(self.tmp.name)/'report',
                            Path(self.tmp.name)/'private-overlay', 'emmc-only', [0])
        self.assertEqual(r['status'], 'INVALID_LAYOUT')
        self.assertTrue(r['golden_unchanged'])
        self.assertEqual(b.identity(self.path), before)
        self.assertEqual(r['corruptions'][0]['sector'], 0)
        self.assertNotEqual(r['overlay']['inode'], before['inode'])

    def test_repo_copy_destination_rejected(self):
        repo = Path(b.__file__).resolve().parents[2]
        r = b.run_probe(self.path, Path(self.tmp.name)/'report', repo/'never-create-overlay', 'emmc-only')
        self.assertEqual(r['status'], 'INVALID_INPUT')
        self.assertFalse((repo/'never-create-overlay').exists())

    def test_fat12_explicitly_unsupported(self):
        self.mutate(2048*512+13, b'\x02')
        self.assertEqual(b.probe(self.path)['status'], 'UNSUPPORTED')

    def test_read_coverage_is_half_open_and_coalesced(self):
        from audit import coverage
        r = coverage([(0, 20), (15, 30), (40, 70), (100, 200)], 10, 100)
        self.assertEqual(r['attempted_ranges'], [[10, 30], [40, 70]])
        self.assertEqual(r['never_attempted_ranges'], [[30, 40], [70, 100]])
        self.assertEqual(r['attempted_unique_bytes']+r['never_attempted_bytes'], 90)


if __name__ == '__main__':
    unittest.main()
