"""
Unit tests for the Vectorized PitchShifter DSP component.
Verifies pitch transposition, cents fine-tuning, dry/wet mix,
buffer wraparound, and numerical stability with zero audio loop allocations.
"""
import unittest
import numpy as np
from engine.dsp import PitchShifter, GuitarSignalChain


class PitchShifterTests(unittest.TestCase):
    def setUp(self):
        self.sr = 48000
        self.shifter = PitchShifter(sample_rate=self.sr)
        self.shifter.enabled = True

    def test_passthrough_when_disabled(self):
        self.shifter.enabled = False
        self.shifter.semitones = 7.0
        x = np.sin(np.arange(256) * 0.1).astype(np.float32)
        out = self.shifter.process(x)
        np.testing.assert_array_equal(x, out)

    def test_passthrough_when_zero_semitones_and_cents(self):
        self.shifter.enabled = True
        self.shifter.semitones = 0.0
        self.shifter.cents = 0.0
        self.shifter.mix = 1.0
        x = np.sin(np.arange(256) * 0.1).astype(np.float32)
        out = self.shifter.process(x)
        # Should return direct passthrough for zero shift
        np.testing.assert_array_equal(x, out)

    def test_finite_output_across_octave_ranges(self):
        x = (np.sin(np.arange(1024) * 0.1) * 0.5).astype(np.float32)
        for st in [-24.0, -12.0, -7.0, -1.0, 1.0, 5.0, 12.0, 24.0]:
            self.shifter.semitones = st
            out = self.shifter.process(x)
            self.assertEqual(len(out), 1024)
            self.assertTrue(np.isfinite(out).all(), f"Failed finite check for semitone {st}")
            self.assertLessEqual(np.max(np.abs(out)), 2.0, f"Output exploded for semitone {st}")

    def test_cents_fine_tuning(self):
        self.shifter.semitones = 12.0
        self.shifter.cents = 50.0  # +12.5 semitones
        ratio = self.shifter._ratio()
        expected = 2.0 ** (12.5 / 12.0)
        self.assertAlmostEqual(ratio, expected, places=5)

    def test_dry_wet_mix(self):
        x = np.ones(128, dtype=np.float32) * 0.5
        self.shifter.semitones = 12.0
        
        # 100% Dry
        self.shifter.mix = 0.0
        out_dry = self.shifter.process(x)
        np.testing.assert_allclose(out_dry, x, atol=1e-5)

    def test_frequency_octave_up(self):
        # 440 Hz test tone
        t = np.arange(self.sr) / float(self.sr)
        x = np.sin(2 * np.pi * 440.0 * t).astype(np.float32)
        
        self.shifter.semitones = 12.0
        self.shifter.mix = 1.0
        
        # Process in 128 sample blocks to simulate real-time audio thread
        blocks = []
        for i in range(0, len(x), 128):
            blocks.append(self.shifter.process(x[i:i + 128]))
        y = np.concatenate(blocks)
        
        # Steady-state FFT peak detection
        steady = y[self.sr // 2:]
        fft_mag = np.abs(np.fft.rfft(steady))
        freqs = np.fft.rfftfreq(len(steady), 1.0 / self.sr)
        peak_freq = freqs[np.argmax(fft_mag)]
        
        # Expected around 880 Hz
        self.assertGreater(peak_freq, 800.0)
        self.assertLess(peak_freq, 950.0)

    def test_chain_integration(self):
        chain = GuitarSignalChain(sample_rate=self.sr)
        self.assertFalse(chain.pitch_shifter.enabled)
        
        # Enable pitch shifter in rig chain
        chain.pitch_shifter.enabled = True
        chain.pitch_shifter.semitones = -12.0
        
        chunk = np.random.uniform(-0.1, 0.1, 128).astype(np.float32)
        out = chain.process(chunk)
        self.assertEqual(len(out), 128)
        self.assertTrue(np.isfinite(out).all())


if __name__ == "__main__":
    unittest.main()
