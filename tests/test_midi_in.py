import unittest

from engine.midi_in import MidiSceneListener, SCENE_CC, scene_from_message


class TestMidiScene(unittest.TestCase):
    def test_cc_value_selects_scene(self):
        for v in range(8):
            self.assertEqual(scene_from_message(0xB0, SCENE_CC, v), v)

    def test_ignores_other_messages(self):
        self.assertIsNone(scene_from_message(0xB0, SCENE_CC, 8))    # out of range
        self.assertIsNone(scene_from_message(0xB0, 44, 1))          # other CC
        self.assertIsNone(scene_from_message(0x90, SCENE_CC, 1))    # note on

    def test_channel_filter(self):
        self.assertEqual(scene_from_message(0xB2, SCENE_CC, 3, channel=2), 3)
        self.assertIsNone(scene_from_message(0xB1, SCENE_CC, 3, channel=2))
        self.assertEqual(scene_from_message(0xB9, SCENE_CC, 3), 3)  # any channel

    def test_callback_dispatch(self):
        got = []
        lis = MidiSceneListener(got.append)
        lis._on_midi(None, 0x3C3, 0, 0xB0 | (SCENE_CC << 8) | (5 << 16), 0)
        lis._on_midi(None, 0x3C4, 0, 0xB0 | (SCENE_CC << 8) | (6 << 16), 0)  # not MIM_DATA
        self.assertEqual(got, [5])

    def test_start_stop_does_not_raise(self):
        lis = MidiSceneListener(lambda i: None)
        self.assertGreaterEqual(lis.start(), 0)
        lis.stop()


if __name__ == "__main__":
    unittest.main()
