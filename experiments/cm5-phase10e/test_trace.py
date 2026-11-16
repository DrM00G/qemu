import hashlib
import unittest
from trace_check import check


def expected(data):
    return {'length':len(data),'tx_sha256':hashlib.sha256(data).hexdigest(),
            'rx_sha256':hashlib.sha256(bytes(x^0xa5 for x in data)).hexdigest()}


class TraceTests(unittest.TestCase):
    def test_message_boundaries_and_bytes(self):
        lines=['dw_apb_ssi_cs selected=0x1','dw_apb_ssi_transfer cs=0x1 bits=8 tx=0x12 rx=0xb7','dw_apb_ssi_cs selected=0x0']
        self.assertEqual(check(lines,[expected(b'\x12')])['status'],'PASS')
        self.assertEqual(check(lines,[expected(b'\x13')])['status'],'FAIL')
        self.assertEqual(check(lines,[])['status'],'FAIL')

    def test_fragmentation_is_not_message_success(self):
        lines=['dw_apb_ssi_cs selected=0x1','dw_apb_ssi_transfer cs=0x1 bits=8 tx=0x12 rx=0xb7','dw_apb_ssi_cs selected=0x0',
               'dw_apb_ssi_cs selected=0x1','dw_apb_ssi_transfer cs=0x1 bits=8 tx=0x13 rx=0xb6','dw_apb_ssi_cs selected=0x0']
        self.assertEqual(check(lines,[expected(b'\x12\x13')])['status'],'FAIL')

    def test_wrong_select_and_reply(self):
        lines=['dw_apb_ssi_cs selected=0x2','dw_apb_ssi_transfer cs=0x2 bits=8 tx=0x12 rx=0x00','dw_apb_ssi_cs selected=0x0']
        self.assertEqual(check(lines,[expected(b'\x12')])['status'],'FAIL')


if __name__=='__main__':unittest.main()
