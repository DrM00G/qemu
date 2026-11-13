"""Boot-policy safety regressions. Synthetic headers do not prove kernel boot."""
import gzip
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'cm5-phase1'))
from launch import direct_arguments, kernel_diagnostics, parser


class BootPolicyTests(unittest.TestCase):
    def test_missing_or_ambiguous_root_is_refused(self):
        for arguments in [[], ['--append', 'root=/dev/vda root=/dev/vda1'],
                          ['--root-device', '/dev/vda', '--append', 'root=/dev/vda1'],
                          ['--root-device', '/dev/vda', '--append', 'rw'],
                          ['--root-device', '/dev/vda', '--append', 'overlayroot=tmpfs']]:
            with self.subTest(arguments=arguments), self.assertRaises(RuntimeError):
                direct_arguments(parser().parse_args(arguments))

    def test_overlay_initial_root_is_readonly(self):
        args = parser().parse_args(['--root-device', '/dev/vda', '--root-mode', 'overlay',
                                    '--root-fstype', 'ext4', '--root-flags', 'noload'])
        words = direct_arguments(args).split()
        self.assertIn('ro', words)
        self.assertNotIn('rw', words)
        self.assertIn('rootflags=noload', words)
        self.assertIn('fsck.mode=skip', words)
        self.assertIn('overlayroot=tmpfs:recurse=1', words)

    def test_quoted_extra_arguments_are_preserved(self):
        args = parser().parse_args(['--root-device', '/dev/vda', '--append', 'console=ttyAMA0 test="two words"'])
        self.assertIn('test="two words"', direct_arguments(args))

    def test_arm64_header_page_size_and_gzip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'Image'
            header = bytearray(64)
            header[56:60] = b'ARM\x64'
            for bits, expected in [(0, None), (1, 4096), (2, 16384), (3, 65536)]:
                header[24:32] = (bits << 1).to_bytes(8, 'little')
                for compressed in (False, True):
                    path.write_bytes(gzip.compress(header) if compressed else header)
                    self.assertEqual(kernel_diagnostics(path)['header_page_size'], expected)
            path.write_bytes(bytes(64))
            with self.assertRaises(RuntimeError):
                kernel_diagnostics(path)


if __name__ == '__main__':
    unittest.main()
