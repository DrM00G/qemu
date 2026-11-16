import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import dt_pipeline as d


class DTTests(unittest.TestCase):
    def setUp(self):
        self.work=Path(tempfile.mkdtemp(prefix='phase10f2-dt-'))
        self.base=self.compile('base','/dts-v1/; / { compatible="brcm,bcm2712"; usb: usb {status="disabled";}; spi10: spi {status="okay";}; };')
        self.mapping=self.compile('map','/dts-v1/; / { test {bcm2712="nospi10";}; denied {bcm2711;}; nospi10 {bcm2712;}; };')
        self.overlay=self.compile('overlay','/dts-v1/; /plugin/; / { compatible="brcm,bcm2712"; fragment@0 {target=<&spi10>; __overlay__ {status="disabled";};}; };')

    def compile(self,name,source):
        p=self.work/(name+'.dts');p.write_text(source)
        out=self.work/(name+'.dtb')
        subprocess.run([str(d.TOOLS/'dtc'),'-@','-I','dts','-O','dtb','-o',str(out),str(p)],check=True,capture_output=True)
        return out.read_bytes()

    def apply(self,**kw):
        args=dict(base=self.base,mapping=self.mapping,overlays={'nospi10':self.overlay},name='test',params={},work=self.work/'apply')
        args.update(kw);return d.transform(**args)

    def test_map_and_apply(self):
        r,out=self.apply();self.assertEqual(r['resolved'],'nospi10');self.assertNotEqual(r['input_sha256'],r['output_sha256'])
        self.assertEqual(d.Tree(out).get('/spi','status'),b'disabled\0');self.assertTrue((self.work/'apply/tree.diff').read_text())
        self.assertFalse(r['runtime_installed'])

    def test_missing_symbol(self):
        base=self.compile('missing','/dts-v1/; / { compatible="brcm,bcm2712"; };')
        with self.assertRaisesRegex(d.h.Outcome, 'missing base symbol'):self.apply(base=base)

    def test_map_excludes_soc(self):
        with self.assertRaises(d.h.Outcome):d.resolve(self.mapping,'denied')
        self.assertEqual(d.resolve(self.mapping,'dwc2'),'dwc2')

    def test_invalid_parameter(self):
        with self.assertRaises(d.h.Outcome):self.apply(params={'speed':'unknown'})

    def test_runtime_rejected(self):
        with self.assertRaises(d.h.Outcome):self.apply(target='lab-runtime')

    def test_dormant_rejected(self):
        overlay=self.compile('dormant','/dts-v1/; /plugin/; / { fragment@0 {target=<&spi10>; __dormant__ {status="disabled";};}; };')
        with self.assertRaises(d.h.Outcome):self.apply(overlays={'nospi10':overlay})

    def test_malformed_rejected(self):
        with self.assertRaises(d.h.Outcome):self.apply(base=self.base[:-5])

    def test_bad_fixup(self):
        tree=d.Tree(self.overlay);tree.set('/__fixups__','spi10',b'/fragment@0:target:9\0')
        with self.assertRaises(d.h.Outcome):self.apply(overlays={'nospi10':tree.bytes()})

    def test_wrong_board(self):
        base = self.compile('wrong-board', '/dts-v1/; / { compatible="brcm,bcm2711"; };')
        with self.assertRaisesRegex(d.h.Outcome, 'requires BCM2712'):
            self.apply(base=base)

    def test_unknown_fixup(self):
        tree = d.Tree(self.overlay)
        tree.set('/__fixups__', 'unknown', b'/fragment@0:target:0\0')
        with self.assertRaisesRegex(d.h.Outcome, 'missing base symbol'):
            self.apply(overlays={'nospi10': tree.bytes()})

    def test_conflicting_target(self):
        tree = d.Tree(self.overlay)
        tree.set('/fragment@0', 'target-path', b'/spi\0')
        with self.assertRaisesRegex(d.h.Outcome, 'one fragment target'):
            self.apply(overlays={'nospi10': tree.bytes()})

    def test_bad_override_encoding(self):
        overlay = self.compile('bad-override', '/dts-v1/; /plugin/; / { fragment@0 {target=<&usb>; u: __overlay__ {dr_mode="otg";};}; __overrides__ {dr_mode=<&u>,"wrong";}; };')
        with self.assertRaisesRegex(d.h.Outcome, 'override encoding'):
            self.apply(name='dwc2', overlays={'dwc2': overlay}, params={'dr_mode':'host'})

    def test_property_bound(self):
        with self.assertRaisesRegex(d.h.Outcome, 'update bound'):
            d.Tree(self.base).set('/spi', 'value', b'x'*262145)

    def test_file_size_bound_before_read(self):
        path = self.work/'oversized.dtb'
        with path.open('wb') as stream:stream.truncate(2*1024*1024+1)
        with self.assertRaisesRegex(d.h.Outcome, 'input size bound'):
            d.bounded_read(path)

    def test_tool_hash_mismatch(self):
        path = self.work/'dtc'; path.write_bytes(b'wrong tool')
        with self.assertRaisesRegex(d.h.Outcome, 'tool hash mismatch'):
            d.accepted_tool(path)

    def test_overlay_order(self):
        # Same property, last explicitly applied overlay wins.
        r, first = self.apply()
        enable = self.compile('enable', '/dts-v1/; /plugin/; / { fragment@0 {target=<&spi10>; __overlay__ {status="okay";};}; };')
        _, second = self.apply(base=first, overlays={'nospi10':enable}, work=self.work/'second')
        self.assertEqual(d.Tree(second).get('/spi', 'status'), b'okay\0')
        self.assertNotEqual(d.h.sha(first), d.h.sha(second))

    def test_conflicting_fixup_location(self):
        tree = d.Tree(self.overlay)
        tree.set('/__fixups__', 'usb', b'/fragment@0:target:0\0')
        with self.assertRaisesRegex(d.h.Outcome, 'conflicting fixup'):
            self.apply(overlays={'nospi10': tree.bytes()})

    def test_unknown_local_fixup(self):
        overlay = self.compile('bad-local', '/dts-v1/; /plugin/; / { fragment@0 {target=<&spi10>; u: __overlay__ {status="disabled"; link=<&u>;};}; };')
        tree = d.Tree(overlay)
        tree.set('/__local_fixups__/fragment@0/__overlay__', 'missing', b'\0'*4)
        with self.assertRaises(d.h.Outcome):
            self.apply(overlays={'nospi10':tree.bytes()})

    def test_dwc2_parameter_applied(self):
        overlay=self.compile('dwc2-valid','/dts-v1/; /plugin/; / { fragment@0 {target=<&usb>; u: __overlay__ {dr_mode="otg"; status="okay";};}; __overrides__ {dr_mode=<&u>,"dr_mode";}; };')
        r,out=self.apply(name='dwc2',overlays={'dwc2':overlay},params={'dr_mode':'host'})
        self.assertEqual(d.Tree(out).get('/usb','dr_mode'),b'host\0')
        self.assertEqual(d.Tree(out).get('/usb','status'),b'okay\0')
        self.assertNotEqual(r['overlay_sha256'],r['parameterized_overlay_sha256'])

    def test_dwc2_string_parameter(self):
        overlay=self.compile('dwc2','/dts-v1/; /plugin/; / { fragment@0 {target=<&usb>; __overlay__ {u: usb-child {dr_mode="otg";};};}; __overrides__ {dr_mode=<&u>,"dr_mode";}; };')
        # Supported encoding additionally requires exact captured target path.
        with self.assertRaises(d.h.Outcome):self.apply(name='dwc2',overlays={'dwc2':overlay},params={'dr_mode':'host'})


if __name__=='__main__':unittest.main()
