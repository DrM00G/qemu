#!/usr/bin/env python3
"""Aggregate completed real-V8 evidence; does not rerun guests or change verdicts."""
import argparse
import csv
import json
import os
from pathlib import Path
os.umask(0o077)
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--output',type=Path,required=True)
p.add_argument('runs',type=Path,nargs='+');a=p.parse_args()
if a.output.resolve().is_relative_to(Path(__file__).resolve().parents[2]):p.error('lab output required')
a.output.mkdir(exist_ok=False)
rows=[]
for run in a.runs:
    r=json.loads((run/'v8-result.json').read_text())
    rows.append({k:r[k] for k in ['experiment_id','status','actual_v8','linux_boot','page_size',
                                  'fsw_complete_read','fec_correction','logical_recovery','uart_status','production_services']})
with (a.output/'regression.csv').open('w') as f:
    w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
(a.output/'regression.json').write_text(json.dumps(rows,indent=2)+'\n')
print(json.dumps(rows,indent=2))
raise SystemExit(0 if all(r['status']=='PASS' and r['actual_v8'] for r in rows) else 1)
