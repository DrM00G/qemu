import copy
import unittest
import runtime_compat as r


class RuntimeTests(unittest.TestCase):
    def nodes(self):
        return {'/':dict(compatible=['qemu,cm5io-dev']),
                r.RP1_SPI:dict(compatible=['snps,dw-apb-ssi'],status='okay')}

    def test_nospi10_preserves_rp1(self):
        nodes=self.nodes(); before=copy.deepcopy(nodes)
        report=r.nospi10(nodes)
        self.assertEqual(nodes,before)
        self.assertEqual(report['effect'],'VALIDATED_ABSENCE_NO_CHANGE')
        self.assertFalse(report['runtime_installed'])

    def test_physical_spi_conflict(self):
        nodes=self.nodes();nodes[r.PHYSICAL_SPI]={}
        with self.assertRaisesRegex(r.d.h.Outcome,'unexpectedly declared'):r.nospi10(nodes)

    def test_wrong_board(self):
        nodes=self.nodes();nodes['/']['compatible']=['brcm,bcm2712']
        with self.assertRaisesRegex(r.d.h.Outcome,'wrong runtime board'):r.nospi10(nodes)

    def test_disabled_rp1_rejected(self):
        nodes=self.nodes();nodes[r.RP1_SPI]['status']='disabled'
        with self.assertRaisesRegex(r.d.h.Outcome,'missing/incompatible'):r.nospi10(nodes)

    def test_output_hash_mismatch(self):
        with self.assertRaisesRegex(r.d.h.Outcome,'output hash mismatch'):
            r.compare(b'',{'fdt_sha256':'wrong'},'expected')
