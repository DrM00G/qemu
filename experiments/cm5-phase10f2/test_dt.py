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
