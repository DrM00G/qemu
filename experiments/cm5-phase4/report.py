#!/usr/bin/env python3
"""Export smoke function results to CSV and Markdown without changing verdicts."""
import csv
import json
from pathlib import Path
import sys
p=Path(sys.argv[1]); r=json.loads(p.read_text())
with p.with_suffix('.csv').open('w') as f:
    w=csv.DictWriter(f,fieldnames=['test','status','errno','bytes','monotonic_ns'])
    w.writeheader(); w.writerows(r['functions'])
lines=['# '+r['experiment_id'],'',r['environment'],'',
       '| Function | Status | errno | Bytes/value |','|---|---|---|---|']
lines += [f"| {v['test']} | {v['status']} | {v['errno']} | {v['bytes']} |" for v in r['functions']]
p.with_suffix('.md').write_text('\n'.join(lines)+'\n')
