"""Private local regressions, using externally retained captured observations."""
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent/'cm5-phase10j'))
sys.path.insert(0, str(HERE.parent/'cm5-phase10c'))
from events import summarize
spec = importlib.util.spec_from_file_location('phase10k_runner', HERE.parent/'cm5-phase10c/run.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class AssessmentTests(unittest.TestCase):
    def test_message_boundaries_and_unmatched_errors(self):
        result = summarize('\r\n virtual_channel_0 created! \r\n: Sampling...\r\n'
                           'watchdog_task stack size is too small, clamping to 131072\n'
                           'PobcCommTask: Error initializing serial class: denied\n'
                           'UnknownTask: Failed unexpectedly\n')
        self.assertEqual(result['counts']['tasks_created'], 1)
        self.assertEqual(result['counts']['housekeeping'], 1)
        self.assertEqual(result['counts']['tasks_started'], 0)
        self.assertEqual(result['counts']['serial_init_failures'], 1)
        self.assertEqual(result['unmatched'][-1]['text'], 'UnknownTask: Failed unexpectedly')
        self.assertEqual(result['ordered'][0]['text'], 'virtual_channel_0 created!')

    def test_timeline_unique_and_clock_domain(self):
        import json
        with tempfile.TemporaryDirectory() as tmp:
            now = [10.0]
            timeline = runner.HostTimeline(Path(tmp)/'timeline', clock=lambda: now[0])
            now[0] = 12.5
            timeline.console('P10J_UPLOAD_VERIFIED\nP10K_FSW_START=587.14')
            timeline.console('P10J_UPLOAD_VERIFIED')
            rows = [json.loads(x) for x in timeline.path.read_text().splitlines()]
            self.assertEqual([r['event'] for r in rows], ['upload_verified', 'fsw_start'])
            self.assertTrue(all(r['host_seconds'] == 2.5 and r['clock'] == 'host-monotonic' for r in rows))

    def test_expected_errors_do_not_become_crashes(self):
        # Load the actual classifier, rather than accepting a timeout alone.
        spec = importlib.util.spec_from_file_location('phase10k_harness', HERE.parent/'cm5-phase10j/run.py')
        harness = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(harness)
        boot = dict(status='PASS', fsw_workload_complete=True, normal_poweroff=True)
        fsw = dict(status='COMPLETE', exit_status=124)
        text = ('Failed to open /dev/spidev0.0\n'
                'SatnogsCommsTask: Failed to send SPI_IOC_MESSAGE\n'
                'WatchdogTask: run called but not yet implemented\n')
        status, _, events = harness.classify(boot, fsw, text)
        self.assertEqual(status, 'PARTIAL')
        self.assertEqual(len(events['spi_failures']), 1)
        self.assertEqual(harness.classify(boot, fsw, text+'Segmentation fault\n')[0], 'FAIL')

    @unittest.skipUnless(os.environ.get('CM5_PHASE10K_REFERENCE'), 'private captured log not configured')
    def test_captured_300_seconds(self):
        import analyze
        p = Path(os.environ['CM5_PHASE10K_REFERENCE'])
        raw = (p/'fsw-output.log').read_bytes()
        result = summarize(raw.decode())
        expected = dict(analyze.PHYSICAL, serial_init_failures=0)
        for key, value in expected.items():
            self.assertEqual(result['counts'][key], value, key)
        self.assertIn('virtual_channel_0 created!', result['events']['tasks_created'])
        self.assertIn('virtual_channel_1 created!', result['events']['tasks_created'])
        self.assertEqual(result['events']['initializations'][0], 'EventActionComponent: successfully initialized!')
        self.assertEqual(result['events']['initializations'][-1], 'WatchdogTask: successfully initialized!')
        self.assertTrue(all(x.endswith('virtual channel 0') for x in result['events']['packet_routes']))
        self.assertEqual(result['counts']['outbound_sends'], 5)
        # Normalization accepts the actual repeated CR/LF framing and does not
        # conflate watchdog/SPI failures with application crashes.
        self.assertEqual(result['counts']['topology_started'], 1)
        self.assertEqual(result['counts']['stack_clamps'], 11)


if __name__ == '__main__':
    unittest.main()
