import unittest

from engine.kemper_midi import frame_kemper_sysex, parse_kemper_sysex


class KemperSysExTests(unittest.TestCase):
    def test_short_message_round_trips(self):
        expected = (b"\x01\x02\x03", 0x04, b"\x05\x06")
        self.assertEqual(parse_kemper_sysex(frame_kemper_sysex(*expected)), expected)

    def test_long_message_uses_extended_length(self):
        value = bytes([0x01]) * 140
        frame = frame_kemper_sysex(b"\x01\x02\x03", 4, value)
        self.assertTrue(frame[1] & 0x80)
        self.assertEqual(parse_kemper_sysex(frame), (b"\x01\x02\x03", 4, value))

    def test_rejects_invalid_framing_manufacturer_and_payload(self):
        valid = frame_kemper_sysex(b"\x01\x02\x03", 4, b"\x05")
        for invalid in (valid[:-1], valid + b"\x00", b"\xF1" + valid[1:]):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    parse_kemper_sysex(invalid)
        wrong_vendor = bytearray(valid)
        wrong_vendor[4] ^= 1
        with self.assertRaises(ValueError):
            parse_kemper_sysex(wrong_vendor)
        high_bit = bytearray(valid)
        high_bit[8] = 0x80
        with self.assertRaises(ValueError):
            parse_kemper_sysex(high_bit)

    def test_frame_rejects_bad_fields(self):
        for args in ((b"\x01", 0, b""), (b"\x01\x02\x03", 128, b""),
                     (b"\x01\x02\x03", 0, b"\x80")):
            with self.subTest(args=args):
                with self.assertRaises(ValueError):
                    frame_kemper_sysex(*args)


if __name__ == "__main__":
    unittest.main()
