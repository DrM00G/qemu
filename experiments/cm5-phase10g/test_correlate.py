import hashlib
import unittest
import correlate as c


def message(data):
    return dict(length=len(data),tx_sha256=hashlib.sha256(data).hexdigest(),
                rx_sha256=hashlib.sha256(bytes(x^0xa5 for x in data)).hexdigest())


def boundary(event, time, word):
    return f'dw_apb_ssi_boundary {event} virtual_ns={time} epoch=1 word={word} segment=1 tx=0 rx={word} raw=0x1 mask=0x1 state=0x51'


def frame(value):
    return f'dw_apb_ssi_transfer cs=0x1 bits=8 tx=0x{value:08x} rx=0x{value^0xa5:08x}'


class CorrelationTests(unittest.TestCase):
    def test_split_is_never_framing_pass(self):
        lines=[boundary('arm',0,0),'dw_apb_ssi_cs selected=0x1',frame(0x12),
               'dw_apb_ssi_cs selected=0x0','dw_apb_ssi_cs selected=0x1',frame(0x34),
               'dw_apb_ssi_cs selected=0x0']
        r=c.correlate(lines,[message(bytes([0x12,0x34]))])
        self.assertEqual(r['strict_oracle'],'FAIL')
        self.assertEqual(r['failed_messages'],[0])
        self.assertTrue(r['messages'][0]['diagnostic_concatenated_byte_identity'])
        self.assertFalse(r['messages'][0]['strict_framing'])

    def test_adjacent_message_boundaries(self):
        lines=[boundary('arm',0,0),'dw_apb_ssi_cs selected=0x1',frame(1),
               'dw_apb_ssi_cs selected=0x0','dw_apb_ssi_cs selected=0x1',frame(2),
               'dw_apb_ssi_cs selected=0x0']
        r=c.correlate(lines,[message(b'\1'),message(b'\2')])
        self.assertEqual(r['strict_oracle'],'PASS')
        self.assertEqual(r['failed_messages'],[])
        self.assertEqual(r['messages'][1]['segments'][0]['message_offset'],0)

    def test_exhausted_capture_is_partial(self):
        lines=[boundary('arm',0,0),'dw_apb_ssi_cs selected=0x1',frame(1),
               'dw_apb_ssi_cs selected=0x0',boundary('CAPTURE_EXHAUSTED',0,0)]
        r=c.correlate(lines,[message(b'\1')])
        self.assertEqual(r['status'],'PARTIAL');self.assertTrue(r['capture_exhausted'])

    def test_empty_trace_cannot_pass(self):
        self.assertNotEqual(c.correlate([],[])['status'],'PASS')
