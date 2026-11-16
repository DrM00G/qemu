"""Exercise the full public observer upload through an actual canonical PTY."""
import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import pty
import select
import subprocess
import sys
import tempfile
import time
import unittest
import observer

ROOT=Path(__file__).resolve().parents[2]


class TransportTests(unittest.TestCase):
    def test_complete_observer_exact_bytes_and_syntax_over_pty(self):
        sys.path.insert(0,str(ROOT/'experiments/cm5-phase10c'))
        spec=importlib.util.spec_from_file_location('i_runner',ROOT/'experiments/cm5-phase10c/run.py')
        runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
        code=observer.wrap((ROOT/'experiments/cm5-phase10c/observe.py').read_text())
        tree=ast.parse(code)
        assignment=next(n for n in tree.body if isinstance(n,ast.Assign) and
                        isinstance(n.targets[0],ast.Name) and n.targets[0].id=='GPIO_CODE')
        self.assertEqual(ast.literal_eval(assignment.value),(observer.HERE/'guest_gpio.py').read_text())
        self.assertLess(max(len(l.encode()) for l in code.splitlines()),3000)
        with tempfile.TemporaryDirectory(prefix='cm5-i-pty-') as tmp:
            remote=Path(tmp)/'observer.py';expected=(code+'\n').encode()
            master,slave=pty.openpty()
            child=subprocess.Popen(['bash','--noprofile','--norc','-i'],stdin=slave,stdout=slave,stderr=slave,
                env=dict(os.environ,PS1='CM5_I# ',TERM='xterm'),start_new_session=True)
            os.close(slave);transcript=bytearray()
            def receive(marker):
                limit=time.monotonic()+15
                while marker not in transcript:
                    self.assertLess(time.monotonic(),limit,'canonical PTY upload timeout')
                    if select.select([master],[],[],.1)[0]:transcript.extend(os.read(master,65536))
            try:
                receive(b'CM5_I# ')
                payload=runner.observer_upload(code,str(remote))
                while payload:
                    n=os.write(master,payload);payload=payload[n:]
                # Never execute the GPIO/FSW observer on the host: parse/hash only.
                check="import ast,hashlib,pathlib; p=pathlib.Path("+repr(str(remote))+"); b=p.read_bytes(); ast.parse(b); print('CM5_I_SHA='+hashlib.sha256(b).hexdigest())"
                os.write(master,('python3 -c '+__import__('shlex').quote(check)+'\n').encode())
                receive(b'CM5_I_SHA='+hashlib.sha256(expected).hexdigest().encode())
                self.assertEqual(remote.read_bytes(),expected)
            finally:
                os.write(master,b'exit\n')
                try:child.wait(timeout=2)
                except subprocess.TimeoutExpired:child.kill();child.wait(timeout=2)
                os.close(master)


if __name__=='__main__':unittest.main()
