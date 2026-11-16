"""Guards against false-positive evidence normalization and semantic reports."""
import ast
from pathlib import Path
import tempfile
import unittest

from ordering import normalize, semantic_checks
from smp_observer import wrap


class EvidenceTests(unittest.TestCase):
    def test_preserve_causal_order_strip_only_host_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/'mixed.log'
            p.write_text('# starting QEMU: -trace enable=dw_apb_ssi_boundary ignored\n'
                         '[R +0.112] clock_step 1\n'
                         'dw_apb_ssi_boundary complete-after virtual_ns=8000 '
                         'epoch=1 word=1 segment=1 tx=0 rx=1 raw=0x11 mask=0x10 state=0x31\n'
                         '[S +0.113] OK 8000\n')
            rows = normalize(p, None)
            self.assertEqual(len(rows), 3)
            self.assertEqual(rows[0]['payload'], 'clock_step 1')
            self.assertEqual(rows[1]['virtual_ns'], 8000)
            self.assertEqual(rows[1]['fields']['rx'], 1)
            self.assertEqual(rows[2]['payload'], 'OK 8000')

    def test_qmp_reset_request_and_handler_reply_are_retained(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/'reset.log'
            p.write_text('qmp_enter_system_reset {}\n'
                         'qmp_exit_system_reset {} 1\n')
            rows = normalize(p, None)
            self.assertEqual([r['payload'] for r in rows], ['{}', '{} 1'])
            self.assertTrue(all(r['virtual_ns'] is None for r in rows))

    def test_empty_capture_cannot_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/'empty'; p.write_text('TAP version 14\n')
            with self.assertRaises(ValueError):
                normalize(p)

    def test_phantom_completion_or_split_cannot_pass(self):
        events = [dict(event='dw_apb_ssi_cs', fields=dict(selected=1))]
        events += [dict(event='dw_apb_ssi_transfer', fields=dict(tx=w, rx=w ^ 0xa5))
                   for w in (0x12, 0x34)]
        self.assertTrue(all(semantic_checks('h-refill-before-completion', events).values()))
        split = events + [dict(event='dw_apb_ssi_cs', fields=dict(selected=1))]
        self.assertFalse(semantic_checks('h-refill-before-completion', split)['cs_segments'])
        extra = events + [events[-1]]
        self.assertFalse(semantic_checks('h-refill-before-completion', extra)['rx_sequence'])

    def test_stress_cleanup_is_finally_and_after_native_observer(self):
        code = "import mmap\nr['native_rp1'] = {}\nprint('P10C_USER_JSON=', r)\n"
        tree = ast.parse(wrap(code))
        block = next(n for n in tree.body if isinstance(n, ast.Try))
        self.assertTrue(block.finalbody)
        self.assertIsInstance(tree.body[-1], ast.Expr)
        self.assertIn('communicate', ast.unparse(block.finalbody))


if __name__ == '__main__':
    unittest.main()
