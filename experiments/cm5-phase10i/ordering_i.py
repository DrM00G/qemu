#!/usr/bin/env python3
"""Preserve H's repeat harness and add GPIO traces/tests without changing H."""
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'experiments/cm5-phase10h'))
import ordering as h

h.CASES['rp1'] += ['i-gpio-registers-errors','i-gpio-msix-edge-level-mask',
                   'i-gpio-reset-clock','i-gpio-spi-isolation-bme']
h.CASES['cm5io'] += ['native-gpio-msix-mip-reset']
h.EVENTS += ['rp1_gpio_access','rp1_gpio_irq']

if __name__=='__main__':
    try:
        h.main()
    except SystemExit as error:
        if error.code:
            raise
    summary=Path(sys.argv[sys.argv.index('--summary')+1])
    result=json.loads(summary.read_text())
    old=json.loads((ROOT/'experiments/cm5-phase10h/ordering-results.json').read_text())
    previous={(c['suite'],c['name']):c for c in old['cases']}
    matches={}
    for c in result['cases']:
        key=(c['suite'],c['name'])
        if key in previous:
            matches[c['name']]=all(c[k]==previous[key][k] for k in
                                   ('events_sha256','protocol_sha256'))
    result['phase10h_trace_preservation']=matches
    for name in ['hw/gpio/rp1-gpio.c','include/hw/gpio/rp1-gpio.h','hw/gpio/trace-events',
                 'experiments/cm5-phase10i/ordering_i.py']:
        result['sources'][name]=hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
    result['status']='PASS' if result['status']=='PASS' and all(matches.values()) else 'FAIL'
    summary.write_text(json.dumps(result,indent=2)+'\n')
    (Path(result['private_evidence'])/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    print('H preservation:',sum(matches.values()),'/',len(matches))
    raise SystemExit(result['status']!='PASS')
