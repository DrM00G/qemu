"""Reject nonlocal DT edits, incorrect IRQ/range wiring, and unsafe fallback."""
from pathlib import Path
import tempfile
import unittest
import dt_contract as c


class ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='cm5-i-contract-')
        cls.work=Path(cls.tmp.name)/'generated'
        cls.report=c.generate(cls.work)
        cls.base=(cls.work/'base.dtb').read_bytes()
        cls.target=(cls.work/'gpio.dtb').read_bytes()
        cls.reference=c.PHYSICAL.read_bytes()

    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def test_real_generator_change_and_noop(self):
        self.assertTrue(self.report['transformation']['changed'])
        self.assertFalse(self.report['fallback']['changed'])

    def test_other_peripheral_mutation_rejected(self):
        tree=c.d.Tree(self.target)
        tree.set('/pcie@1000120000/rp1/spi@50000','num-cs',c.cells(4))
        with self.assertRaises(ValueError):c.validate(self.base,tree.bytes(),self.reference)

    def test_wrong_vector_or_reserved_lines_rejected(self):
        for key,value in [('interrupts',c.cells(19,4)),
                          ('gpio-reserved-ranges',c.cells(0,19,22,32))]:
            with self.subTest(key=key):
                tree=c.d.Tree(self.target);tree.set(c.GPIO,key,value)
                with self.assertRaises(ValueError):c.validate(self.base,tree.bytes(),self.reference)

    def test_physical_tree_cannot_be_runtime_base(self):
        with self.assertRaises(ValueError):c.validate(self.reference,self.reference,self.reference)

    def test_disabled_profile_cannot_change_tree(self):
        with self.assertRaises(ValueError):c.validate(self.base,self.target,self.reference,False)


if __name__=='__main__':unittest.main()
