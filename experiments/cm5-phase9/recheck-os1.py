#!/usr/bin/env python3
"""Correct the RS-offset log parser against retained evidence, no guest rerun."""
import json
from pathlib import Path
import re

run = Path(__file__).resolve().parent/'artifacts/matrix-os1'
result = json.loads((run/'result.json').read_text())
serial = (run/'serial.log').read_text()
assert result['phase9']['case'] == 'os1'
result['checks']['target_fec_correction'] = bool(re.search(
    r'verity-fec: 179:2: FEC 4096: corrected [1-9][0-9]* errors',serial))
result['status'] = 'PASS' if all(result['checks'].values()) else 'FAIL'
result['parser_correction'] = 'Linux reports RS base byte offset4096 for logical block1'
with (run/'result-rechecked.json').open('x') as stream:
    stream.write(json.dumps(result,indent=2)+'\n')
print(result['status'])
raise SystemExit(0 if result['status']=='PASS' else 1)
