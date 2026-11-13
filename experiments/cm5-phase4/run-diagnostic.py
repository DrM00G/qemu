#!/usr/bin/env python3
"""Validated JSON frontend; explicit hardware opt-in is mandatory."""
import argparse
import json
import subprocess
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('config')
p.add_argument('--executable', required=True)
a=p.parse_args()
c=json.load(open(a.config))
allowed={'logs_new_file','uart','spi','duration_seconds','approved_hardware_mapping'}
if set(c)-allowed:
    p.error('unknown configuration field')
for key in ('uart','spi'):
    if c.get(key,'-')!='-' and not c.get('approved_hardware_mapping',False):
        p.error('device transfers require explicit approved_hardware_mapping')
if type(c.get('duration_seconds',5)) is not int or not 1<=c.get('duration_seconds',5)<=3600:
    p.error('duration must be 1..3600 seconds')
raise SystemExit(subprocess.call([a.executable,c['logs_new_file'],c.get('uart','-'),
                                 c.get('spi','-'),str(c.get('duration_seconds',5))]))
