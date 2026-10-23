"""
Tests for MOOER GE150 Signal Chain DSP processing, Tube & Mic voicings, EQ, and Modulation.
"""

import unittest
import numpy as np
from engine.dsp import GuitarSignalChain, GraphicEqualizer, ModulationProcessor, CabinetSimulator
from engine.mooer_preset import FACTORY_GE150_PRESETS, mo_to_workstation_preset

class TestMooerDsp(unittest.TestCase):
    def setUp(self):
        self.sr = 48000
        self.chain = GuitarSignalChain(sample_rate=self.sr)
        # 128 samples of test guitar tone (fundamental + harmonics)
        t = np.arange(128) / self.sr
        self.input_block = (0.3 * np.sin(2.0 * np.pi * 220.0 * t) +
                            0.2 * np.sin(2.0 * np.pi * 440.0 * t) +
                            0.1 * np.sin(2.0 * np.pi * 880.0 * t)).astype(np.float32)

    def test_apply_all_factory_presets(self):
        for preset in FACTORY_GE150_PRESETS:
            self.chain.apply_mooer_preset(preset)
            out = self.chain.process(self.input_block)
            self.assertEqual(len(out), 128)
            self.assertTrue(np.all(np.isfinite(out)))
            self.assertGreater(float(np.max(np.abs(out))), 1e-4)
            self.assertLessEqual(float(np.max(np.abs(out))), 1.0)

    def test_apply_preset_leaves_the_screamer_tone_filter_untouched(self):
        """The GE150 import has never rebuilt the tone biquad (deliberate, for now).

        apply_mooer_preset stores `tone` without calling _update_filter(), so a
        loaded preset keeps whatever tone filter the chain already had. That is
        a bug -- the sound does not match the knob -- but it is preserved so the
        registry rewrite could not change the audio. Fixing it means deleting
        hook=False in engine/dsp.py and re-recording the golden evidence; this
        test is here so that change cannot happen unnoticed.
        See docs/SIGNAL_CHAIN_READINESS.md section 10.3.
        """
        fresh_filter = self.chain.screamer.b.copy()
        preset = FACTORY_GE150_PRESETS[0]
        s = mo_to_workstation_preset(preset)["settings"]["screamer"]
        self.chain.screamer.tone = 0.9
        self.chain.screamer._update_filter()
        knob_filter = self.chain.screamer.b.copy()
        self.assertFalse(np.array_equal(knob_filter, fresh_filter))

        self.chain.apply_mooer_preset(preset)
        self.assertEqual(self.chain.screamer.tone, s["tone"])
        # Coefficients are stale on purpose: they still describe tone 0.9.
        self.assertTrue(np.array_equal(self.chain.screamer.b, knob_filter))

    def test_tube_voicings(self):
        cab = CabinetSimulator(sample_rate=self.sr)
        for tube in ["OFF", "EL34", "EL84", "6L6", "6V6"]:
            cab.set_tube_and_mic(tube=tube, mic="SM57", center=50, distance=20)
            out = cab.process(self.input_block)
            self.assertTrue(np.all(np.isfinite(out)))
            self.assertGreater(float(np.max(np.abs(out))), 1e-4)

    def test_graphic_equalizer_modes(self):
        eq = GraphicEqualizer(sample_rate=self.sr)
        eq.enabled = True
        # Mode 1: Mooer G (5 bands)
        eq.set_bands([3.0, -2.0, 4.0, -1.0, 2.0], model_id=1)
        out1 = eq.process(self.input_block)
        self.assertTrue(np.all(np.isfinite(out1)))

        # Mode 2: Mooer HM (5 bands)
        eq.set_bands([2.0, 2.0, -4.0, 3.0, 1.0], model_id=2)
        out2 = eq.process(self.input_block)
        self.assertTrue(np.all(np.isfinite(out2)))

        # Mode 3: Mooer G-6 (6 bands)
        eq.set_bands([1.0, 2.0, 3.0, -2.0, -1.0, 4.0], model_id=3)
        out3 = eq.process(self.input_block)
        self.assertTrue(np.all(np.isfinite(out3)))

        # Mode 4: Custom Parametric (3 bands)
        eq.set_bands([4.0, -3.0, 2.0], model_id=4, custom_freqs=[250.0, 1200.0, 5000.0])
        out4 = eq.process(self.input_block)
        self.assertTrue(np.all(np.isfinite(out4)))

    def test_modulation_modes(self):
        mod = ModulationProcessor(sample_rate=self.sr)
        mod.enabled = True

        # Chorus (Model 12)
        mod.model_id = 12
        out_chorus = mod.process(self.input_block)
        self.assertTrue(np.all(np.isfinite(out_chorus)))

        # Flanger (Model 4)
        mod.model_id = 4
        out_flanger = mod.process(self.input_block)
        self.assertTrue(np.all(np.isfinite(out_flanger)))

        # Tremolo (Model 6)
        mod.model_id = 6
        out_trem = mod.process(self.input_block)
        self.assertTrue(np.all(np.isfinite(out_trem)))

        # Lo-Fi Bitcrusher (Model 19)
        mod.model_id = 19
        out_lofi = mod.process(self.input_block)
        self.assertTrue(np.all(np.isfinite(out_lofi)))

if __name__ == "__main__":
    unittest.main()
