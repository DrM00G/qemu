"""Host-only ACK/wakeup regressions with benign generated checksum probes."""
import base64
import importlib.util
import os
from pathlib import Path
import selectors
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent/'cm5-phase10c'))
spec = importlib.util.spec_from_file_location('l_runner', HERE.parent/'cm5-phase10c/run.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class TransportTests(unittest.TestCase):
    def test_fragmented_and_stale_ack(self):
        text = ''
        for part in ('\r\nP10J_UP', 'LOAD_ACK=', '0'):
            text += part
            self.assertFalse(runner.upload_acknowledged(text, 0))
        text += '\r\n'
        self.assertTrue(runner.upload_acknowledged(text, 0))
        self.assertFalse(runner.upload_acknowledged(text, 1))
        text += 'P10J_UPLOAD_ACK=1\r\n'
        self.assertFalse(runner.upload_acknowledged(text, 0))
        self.assertTrue(runner.upload_acknowledged(text, 1))
        self.assertTrue(runner.upload_acknowledged('\nP10J_UPLOAD_ACK=0\nP10J_UPLOAD_ACK=1\n', 1))

    def test_debug_wakes_idle_main_and_registration_is_temporary(self):
        master, guest = socket.socketpair()
        read_fd, write_fd = os.pipe()
        sel = selectors.DefaultSelector()
        sel.register(read_fd, selectors.EVENT_READ)
        worker = threading.Thread(target=lambda: (time.sleep(.025), guest.sendall(b'\nP10J_UPLOAD_ACK=0\n')))
        try:
            worker.start()
            start = time.monotonic()
            self.assertEqual(runner.wait_console(sel, master, 1), [])
            self.assertLess(time.monotonic()-start, .5)
            self.assertTrue(runner.upload_acknowledged(master.recv(1024).decode(), 0))
            self.assertEqual(len(sel.get_map()), 1)
            # Missing ACK: bounded wait expires, with no authorization to send.
            self.assertEqual(runner.wait_console(sel, master, .02), [])
            self.assertFalse(runner.upload_acknowledged('', 0))
        finally:
            worker.join(); sel.close(); master.close(); guest.close()
            os.close(read_fd); os.close(write_fd)

    def test_delayed_real_receiver_preserves_frames_and_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            remote = Path(tmp)/'probe.py'
            code = 'DATA='+repr(base64.b64encode(os.urandom(32768)).decode())+"\nprint('BENIGN_PROBE_COMPLETE',flush=True)\n"
            bootstrap, frames = runner.workload_upload(code, str(remote))
            proc = subprocess.Popen(['bash', '-c', bootstrap.decode()], stdin=subprocess.PIPE,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            os.set_blocking(proc.stdout.fileno(), False)
            console = ''; sent = 0; deadline = time.monotonic()+10
            sel = selectors.DefaultSelector()
            try:
                while 'BENIGN_PROBE_COMPLETE' not in console:
                    self.assertLess(time.monotonic(), deadline)
                    try:
                        console += os.read(proc.stdout.fileno(), 65536).decode()
                    except BlockingIOError:
                        pass
                    if sent < len(frames) and runner.upload_acknowledged(console, sent):
                        if sent == 1:
                            time.sleep(.025)
                        proc.stdin.write(frames[sent]); proc.stdin.flush(); sent += 1
                    runner.wait_console(sel, proc.stdout, .02)
                self.assertEqual(sent, len(frames))
                self.assertIn('P10J_UPLOAD_VERIFIED', console)
                self.assertEqual(remote.read_bytes(), code.encode())
                proc.wait(timeout=2)
            finally:
                if proc.poll() is None:
                    proc.kill(); proc.wait()
                proc.stdin.close(); proc.stdout.close(); sel.close()

    def test_failed_or_incomplete_frame_never_executes_launcher(self):
        with tempfile.TemporaryDirectory() as tmp:
            remote = Path(tmp)/'must-not-exist.py'
            bootstrap, frames = runner.workload_upload("raise AssertionError('must not execute')\n", str(remote))
            corrupt = bytearray(base64.b64decode(frames[0])); corrupt[0] ^= 1
            for damage in (base64.b64encode(corrupt)+b'\n', frames[0].rstrip(b'\n'), b'!\n'):
                proc = subprocess.run(['bash', '-c', bootstrap.decode()], input=damage,
                                      capture_output=True, timeout=5)
                self.assertIn(b'P10J_RESULT=', proc.stdout)
                self.assertIn(b'ERROR', proc.stdout)
                self.assertNotIn(b'P10J_UPLOAD_VERIFIED', proc.stdout)
                self.assertFalse(remote.exists())


if __name__ == '__main__':
    unittest.main()
