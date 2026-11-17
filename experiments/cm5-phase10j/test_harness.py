"""Transport and classification checks; never execute guest FSW on the host."""
import ast
import base64
import hashlib
import importlib.util
import json
import re
import os
from pathlib import Path
import pty
import select
import shlex
import subprocess
import sys
import tempfile
import time
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run as harness
sys.path.insert(0, str(HERE.parent/'cm5-phase10c'))
spec = importlib.util.spec_from_file_location('c_runner', HERE.parent/'cm5-phase10c/run.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class HarnessTests(unittest.TestCase):
    def test_large_payload_exact_bytes_over_canonical_pty(self):
        data = os.urandom(256*1024)
        code = harness.payload_code(data, 30)
        tree = ast.parse(code)
        self.assertEqual(base64.b64decode(ast.literal_eval(tree.body[0].value)), data)
        self.assertLess(max(map(len, code.splitlines())), 3000)
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp)/'payload.py'
            master, slave = pty.openpty()
            proc = subprocess.Popen(['bash', '--noprofile', '--norc', '-i'], stdin=slave,
                stdout=slave, stderr=slave, start_new_session=True,
                env=dict(os.environ, PS1='P10J_TEST# ', TERM='dumb'))
            os.close(slave)
            os.set_blocking(master, False)
            pending = runner.observer_upload(code, str(destination))
            check = 'import hashlib,pathlib; print("HASH="+hashlib.sha256(pathlib.Path('+repr(str(destination))+').read_bytes()).hexdigest())'
            pending += ('python3 -c '+shlex.quote(check)+'\n').encode()
            expected = hashlib.sha256((code+'\n').encode()).hexdigest().encode()
            received = bytearray()
            deadline = time.monotonic()+30
            try:
                while b'HASH='+expected not in received:
                    self.assertLess(time.monotonic(), deadline, 'PTY transfer stalled')
                    readable, writable, _ = select.select([master], [master] if pending else [], [], .01)
                    if readable:
                        received.extend(os.read(master, 65536))
                    if writable:
                        count = os.write(master, pending[:512])
                        pending = pending[count:]
                self.assertEqual(destination.read_bytes(), (code+'\n').encode())
            finally:
                proc.kill(); proc.wait(); os.close(master)

    def test_acknowledged_upload_large_payload(self):
        # Exercise several MiB through the real receiver, with a slow sender.
        # This executes only a generated checksum probe, never flight software.
        data = base64.b64encode(os.urandom(5*1024*1024)).decode()
        code = 'DATA='+repr(data)+"\nprint('PROBE='+__import__('hashlib').sha256(DATA.encode()).hexdigest(),flush=True)\n"
        expected = hashlib.sha256(data.encode()).hexdigest().encode()
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp)/'probe.py'
            bootstrap, frames = runner.workload_upload(code, str(destination))
            master, slave = pty.openpty()
            proc = subprocess.Popen(['bash','--noprofile','--norc','-i'], stdin=slave,
                stdout=slave, stderr=slave, start_new_session=True,
                env=dict(os.environ, PS1='TEST# ', TERM='dumb'))
            os.close(slave)
            os.set_blocking(master, False)
            received = bytearray(); index = 0
            pending = b'stty -echo\n'+bootstrap
            deadline = time.monotonic()+60
            try:
                while b'PROBE='+expected not in received:
                    self.assertLess(time.monotonic(), deadline, 'acknowledged transfer stalled')
                    readable,writable,_ = select.select([master],[master] if pending else [],[],.001)
                    if readable: received.extend(os.read(master,65536))
                    if writable:
                        count=os.write(master,pending[:128]);pending=pending[count:]
                    acknowledgements = re.findall(rb'(?:^|[\r\n])P10J_UPLOAD_ACK=(\d+)[\r\n]',received)
                    if not pending and acknowledgements and int(acknowledgements[-1])==index and index<len(frames):
                        pending=frames[index];index+=1
                self.assertEqual(destination.read_bytes(),code.encode())
                self.assertIn(b'P10J_UPLOAD_VERIFIED',received)
            finally:
                proc.kill();proc.wait();os.close(master)

    def test_completion_record_waits_for_final_newline(self):
        record = dict(status='COMPLETE', partitions='{"nested": {"value": 1}}',
                      output_base64='A'*100000, exit_status=124)
        line = '\nP10J_RESULT='+json.dumps(record)
        # A UART read can end at any character, including a nested close brace.
        for stop in (line.index('}}')+2, 65536, len(line)-1, len(line)):
            self.assertIsNone(runner.workload_result(line[:stop]))
        self.assertEqual(runner.workload_result(line+'\r\n'),record)

    def test_missing_result_is_inconclusive(self):
        self.assertEqual(harness.classify({}, {}, '')[0], 'INCONCLUSIVE')

    def test_timeout_without_baseline_review_is_partial(self):
        self.assertEqual(harness.classify(dict(status='PASS', fsw_workload_complete=True, normal_poweroff=True),
            dict(status='COMPLETE', exit_status=124), 'topology initialized')[0], 'PARTIAL')

    def test_missing_loader_fails_even_if_timeout_status_124(self):
        self.assertEqual(harness.classify(dict(status='PASS'), dict(status='COMPLETE', exit_status=124),
            'error while loading shared libraries: missing.so')[0], 'FAIL')

    def test_normal_early_exit_is_failure_against_timeout_contract(self):
        self.assertEqual(harness.classify({}, dict(status='COMPLETE', exit_status=0), '')[0], 'FAIL')


if __name__ == '__main__':
    unittest.main()
