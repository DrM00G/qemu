"""Exercise real interactive-shell upload and repeated invocation over a PTY."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import pty
import re
import select
import subprocess
import sys
import tempfile
import time
import unittest

ROOT=Path(__file__).resolve().parents[2]


class TransportTests(unittest.TestCase):
    def test_cached_observer_executes_exact_bytes_twice(self):
        sys.path.insert(0,str(ROOT/'experiments/cm5-phase10c'))
        spec=importlib.util.spec_from_file_location('phase10c_run',ROOT/'experiments/cm5-phase10c/run.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        work=Path(tempfile.mkdtemp(prefix='phase10g-transport-'))
        remote=work/'observer.py'
        code="import hashlib,json\nfrom pathlib import Path\nprint('P10C_USER_JSON='+json.dumps({'sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}))"
        expected=hashlib.sha256((code+'\n').encode()).hexdigest()
        master,slave=pty.openpty()
        child=subprocess.Popen(['bash','--noprofile','--norc','-i'],stdin=slave,stdout=slave,stderr=slave,
            env=dict(os.environ,PS1='CM5_TEST# ',TERM='xterm'),start_new_session=True)
        os.close(slave);transcript=bytearray()
        def receive(predicate):
            deadline=time.monotonic()+10
            while not predicate(bytes(transcript)):
                self.assertLess(time.monotonic(),deadline,'bounded shell transport timeout')
                if select.select([master],[],[],.1)[0]:transcript.extend(os.read(master,65536))
        try:
            receive(lambda data:b'CM5_TEST# ' in data)
            os.write(master,module.observer_upload(code,str(remote)))
            for count in (1,2):
                os.write(master,module.observer_invoke(str(remote)))
                receive(lambda data:len(re.findall(rb'(?:^|[\r\n])P10C_USER_JSON=(\{[^\r\n]+\})',data))>=count)
            rows=re.findall(rb'(?:^|[\r\n])P10C_USER_JSON=(\{[^\r\n]+\})',transcript)
            self.assertTrue(all(json.loads(r)['sha256']==expected for r in rows))
            self.assertEqual(remote.read_bytes(),(code+'\n').encode())
        finally:
            (work/'transcript.log').write_bytes(transcript)
            os.write(master,b'exit\n')
            try:child.wait(timeout=2)
            except subprocess.TimeoutExpired:
                child.kill();child.wait(timeout=2)
            os.close(master)
