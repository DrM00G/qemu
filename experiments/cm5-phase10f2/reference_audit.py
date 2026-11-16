#!/usr/bin/env python3
"""Inspect the selected active BOOT tree; never replace the compatible guest DT.

Physical operations are independent experiments, not a claim that skipping an
unsupported earlier operation reproduces a complete firmware-selected tree.
"""
import argparse
import json
from pathlib import Path
import sys

import boot_policy as policy
import dt_pipeline as d
h = policy.h


def audit(overlay, expected, work):
    work = h.private_dir(work)
    selected = work/'selection'; selected.mkdir()
    report, buffers = policy.select(overlay, selected, expected, config_profile='cm5-headless-lab')
    h.write_report(selected/'decision.json', report)
    h.require(report['status'] == 'SELECTED', 'UNSUPPORTED', 'BOOT selection did not complete')
    ledger = dict(reads=[], files={})
    reader = h.LogicalReader(overlay, ledger, work)
    rows = []
    try:
        fat = h.StrictFAT(reader, h.partitions(reader))
        # Re-read the physical DT in this locked graph. Reject changes between graphs.
        base = fat.file(report['selected']['dtb'])
        h.require(base == buffers['dtb'], 'READ_ERROR', 'selected DT changed')
        mapping = fat.file('overlays/overlay_map.dtb')
        for row in report['config_directives']:
            if not row.get('active'):
                continue
            directive = row['directive']
            if directive.startswith('dtparam='):
                rows.append(dict(operation='dtparam', value=directive.split('=',1)[1],
                    physical_reference='UNSUPPORTED', reason='captured base tree has no supported audio override; firmware semantics not established',
                    lab_compatibility='EXPLICIT_HEADLESS_SUBSTITUTION'))
            if not directive.startswith('dtoverlay='):
                continue
            fields = directive.split('=',1)[1].split(',')
            name, params = fields[0], dict(x.split('=',1) for x in fields[1:])
            item = dict(requested=name, parameters=params, lab_compatibility='EXPLICIT_HEADLESS_SUBSTITUTION')
            try:
                resolved = d.resolve(mapping,name); item['resolved'] = resolved
                overlay_bytes = fat.file('overlays/'+resolved+'.dtbo')
                # Acceptance is independent of transformation inputs and faults.
                for path in ('overlays/overlay_map.dtb','overlays/'+resolved+'.dtbo',report['selected']['dtb']):
                    h.require(expected.get(path) == ledger['files'][path]['sha256'], 'INVALID_IMAGE', 'unaccepted DT source '+path)
                transformed, after = d.transform(base,mapping,{resolved:overlay_bytes},name,params,work/name)
                item.update(transformed)
                # Confirm the two evidenced property effects independently of the diff.
                tree = d.Tree(after)
                symbol = 'usb' if name == 'dwc2' else 'spi10'
                node = d.string(d.Tree(base).get('/__symbols__',symbol))
                item['observed_status'] = d.string(tree.get(node,'status'))
                if name == 'dwc2':
                    item['observed_dr_mode'] = d.string(tree.get(node,'dr_mode'))
                    h.require(item['observed_dr_mode'] == 'host' and item['observed_status'] == 'okay', 'INVALID_IMAGE', 'dwc2 postcondition')
                else:
                    h.require(item['observed_status'] == 'disabled', 'INVALID_IMAGE', 'nospi10 postcondition')
            except (h.Outcome, OSError, ValueError, KeyError) as exc:
                item.update(status='UNSUPPORTED',reason=str(exc))
            rows.append(item)
        reader.verify_unchanged()
    finally:
        reader.close(); h.write_report(work/'read-provenance.json',ledger)
    result = dict(schema=1, status='PARTIAL_PHYSICAL_REFERENCE', full_config_applied=False,
        operations_independent=True, runtime_installed=False,
        runtime='EXPLICIT_GENERATED_LAB_DT_SUBSTITUTION', operations=rows,
        selected_dtb_sha256=h.sha(base), overlay_map_sha256=h.sha(mapping),
        input_overlay_unchanged=ledger['overlay_chain_before']==ledger['overlay_chain_after'])
    h.write_report(work/'audit.json',result)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--overlay',type=Path,required=True);p.add_argument('--expected',type=Path,required=True)
    p.add_argument('--work',type=Path,required=True)
    a=p.parse_args();result=audit(a.overlay,json.loads(a.expected.read_text()),a.work)
    print(json.dumps(dict(status=result['status'], audit=str(a.work/'audit.json'))))


if __name__ == '__main__':main()
