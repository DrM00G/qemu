"""Private captured-profile regressions. Never execute captured hook on host."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import lab_profile as profile


@unittest.skipUnless(os.environ.get('CM5_PHASE10L_ORIGINAL'), 'private original not configured')
class ProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = Path(os.environ['CM5_PHASE10L_ORIGINAL']).read_bytes()
        cls.derived = profile.construct(cls.original)
        cls.hook = next(b for n, b in profile.cpio_entries(cls.original) if n == profile.HOOK)
        cls.patched = profile.patch_hook(cls.hook)

    def test_exact_derivative_and_rejection_policy(self):
        policy = profile.approve(self.original, self.derived, profile.KERNEL_SHA)
        self.assertFalse(policy['derivative_matches_original_boot_manifest'])
        self.assertTrue(self.derived.startswith(self.original))
        extra = self.derived[(len(self.original)+3)&~3:]
        entries = list(profile.cpio_entries(extra))
        self.assertEqual(entries, [(profile.HOOK, self.patched), ('TRAILER!!!', b'')])
        with self.assertRaises(ValueError):
            profile.approve(self.original, self.derived[:-1]+b'x', profile.KERNEL_SHA)
        with self.assertRaises(ValueError):
            profile.approve(self.original, self.derived, '0'*64)
        with self.assertRaises(ValueError):
            profile.construct(b'not the captured original')
        subprocess.run(['sh', '-n'], input=self.patched, check=True)

    def test_mapping_assertions_and_handoff_unchanged(self):
        start = self.hook.index(b"os_log '[4/6]")
        self.assertEqual(self.hook[:start], self.patched[:start])
        # Mapper status must remain outside the conditional scan block.
        status = b'STATUS="$(dmsetup status cm5_os_verified)"'
        end = b"os_log '[5/6]"
        self.assertEqual(self.hook[self.hook.index(status):self.hook.index(end)],
                         self.patched[self.patched.index(status):self.patched.index(b'if [ "$CM5_LAB_OS_SCAN" = strict ]; then', self.patched.index(status))])
        tail = b"os_log '[6/6]"
        self.assertEqual(self.hook[self.hook.index(tail):], self.patched[self.patched.index(tail):])

    def exercise_scan_fragment(self, cmdline='', fail_at=0, state='V'):
        # Execute ONLY the isolated scan/status fragment with mocked dd,
        # dmsetup and os_fail. No device, mapper, mount or FSW code is executed.
        text = self.patched.decode()
        fragment = text[text.index('CM5_LAB_OS_SCAN=strict'):text.index("os_log '[6/6]")]
        with tempfile.TemporaryDirectory() as tmp:
            fragment = fragment.replace('/run/', tmp+'/')
            prelude = '''os_log() { echo "$*"; }
os_fail() { echo "REJECT:$*"; exit 9; }
cat() { if [ "$1" = /proc/cmdline ]; then printf '%s\\n' "$TEST_CMDLINE"; else /bin/cat "$@"; fi; }
dd() { N=$((N+1)); printf '%s' "$N" > "$COUNTER"; [ "$N" != "$FAIL_AT" ]; }
dmsetup() { echo "0 20971520 verity $STATE"; }
N=0
'''
            count = Path(tmp)/'counter'
            result = subprocess.run(['sh', '-c', prelude+fragment], capture_output=True,
                text=True, timeout=5, env=dict(os.environ, TEST_CMDLINE=cmdline,
                    FAIL_AT=str(fail_at), STATE=state, COUNTER=str(count)))
            return result, int(count.read_text()) if count.exists() else 0

    def test_strict_scan_operational_skip_and_fail_closed(self):
        for arg in ('', 'cm5_lab_os_scan=strict'):
            result, count = self.exercise_scan_fragment(arg)
            self.assertEqual((result.returncode, count), (0, 40))
            self.assertIn('Verified OS full read PASS', result.stdout)
        result, count = self.exercise_scan_fragment(profile.PARAMETER)
        self.assertEqual((result.returncode, count), (0, 0))
        self.assertIn('exhaustive OS scan NOT performed', result.stdout)
        self.assertNotIn('Verified OS full read PASS', result.stdout)
        result, count = self.exercise_scan_fragment('', fail_at=3)
        self.assertEqual((result.returncode, count), (9, 3))
        for arg in (profile.PARAMETER, ''):
            result, _ = self.exercise_scan_fragment(arg, state='C')
            self.assertEqual(result.returncode, 9)
            self.assertNotIn('Verified OS full read PASS', result.stdout)
        for arg in ('cm5_lab_os_scan=garbage', profile.PARAMETER+' '+profile.PARAMETER):
            result, count = self.exercise_scan_fragment(arg)
            self.assertEqual((result.returncode, count), (9, 0))


if __name__ == '__main__':
    unittest.main()
