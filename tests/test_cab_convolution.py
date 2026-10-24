"""F1 (cab IR tail kept across blocks) and F2 (AmpHead EQ state kept across blocks).

Reference for F1 is one full ``fftconvolve`` of the whole signal; the metric is
the maximum absolute sample error against it, tolerance 1e-5.  Nothing here
touches a golden file.
"""

import tempfile
import threading
import unittest
from pathlib import Path

import numpy as np
from scipy import signal
from scipy.io import wavfile

import config
from engine.convolver import PartitionedConvolver
from engine.dsp import AmpHead, CabinetSimulator

TOL = 1e-5
IR_LENGTHS = (1, 2, 127, 128, 129, 600, 2048, 24000, 48000)
BLOCK_PATTERNS = ((128,), (64,), (512,), (100, 37, 128, 1), (300,))


def _stream(conv, x, sizes):
    out, i, k = [], 0, 0
    while i < len(x):
        size = sizes[k % len(sizes)]
        k += 1
        out.append(conv.process(x[i:i + size]))
        i += size
    return np.concatenate(out)


class ConvolverMatchesFullConvolutionTests(unittest.TestCase):
    def test_seeded_random_input_every_length_and_block_pattern(self):
        rng = np.random.default_rng(3)
        x = rng.standard_normal(20000)
        for length in IR_LENGTHS:
            ir = rng.standard_normal(length) * 0.1
            ref = signal.fftconvolve(x, ir)[:len(x)]
            for sizes in BLOCK_PATTERNS:
                with self.subTest(ir=length, blocks=sizes):
                    err = np.max(np.abs(_stream(PartitionedConvolver(ir), x, sizes) - ref))
                    self.assertLess(err, TOL)

    def test_impulse_returns_the_ir_wherever_it_lands_in_a_block(self):
        rng = np.random.default_rng(5)
        ir = rng.standard_normal(5000) * 0.1
        for at in (0, 1, 127, 128, 129, 1000):
            with self.subTest(at=at):
                x = np.zeros(8000)
                x[at] = 1.0
                out = _stream(PartitionedConvolver(ir), x, (128,))
                np.testing.assert_allclose(out[at:at + len(ir)], ir[:len(out) - at], atol=TOL, rtol=0)
                self.assertLess(np.max(np.abs(out[:at]), initial=0.0), TOL)

    def test_the_tail_beyond_the_first_block_is_kept(self):
        ir = np.zeros(1000)
        ir[500] = 1.0
        x = np.zeros(2000)
        x[0] = 1.0
        out = _stream(PartitionedConvolver(ir), x, (128,))
        self.assertAlmostEqual(out[500], 1.0, delta=TOL)

    def test_reset_forgets_the_history(self):
        rng = np.random.default_rng(7)
        ir = rng.standard_normal(3000) * 0.1
        conv = PartitionedConvolver(ir)
        conv.process(rng.standard_normal(1000))
        conv.reset()
        x = rng.standard_normal(1000)
        np.testing.assert_allclose(conv.process(x), signal.fftconvolve(x, ir)[:1000], atol=TOL, rtol=0)


class CabinetStateTests(unittest.TestCase):
    def _cab(self, ir_length=3000, plain=True):
        """Convolution only: the cut filters and the tube/mic voicing have their own history."""
        cab = CabinetSimulator(sample_rate=48000)
        cab.set_ir_data(np.random.default_rng(11).standard_normal(ir_length) * 0.05, "test")
        if not plain:
            return cab
        cab.hp_b = cab.hp_a = cab.lp_b = cab.lp_a = np.array([1.0])
        cab.hp_zi = cab.lp_zi = np.zeros(0)
        cab._tube_mic_sections = []
        return cab

    def test_block_size_does_not_change_the_cabinet_output(self):
        x = np.random.default_rng(13).standard_normal(6000) * 0.3
        whole = self._cab().process(x.copy())
        for size in (64, 128, 333):
            with self.subTest(block=size):
                cab = self._cab()
                parts = [cab.process(x[i:i + size].copy()) for i in range(0, len(x), size)]
                self.assertLess(np.max(np.abs(np.concatenate(parts) - whole)), TOL)

    def test_a_new_ir_does_not_inherit_the_old_tail(self):
        cab = self._cab()
        impulse = np.zeros(128)
        impulse[0] = 1.0
        cab.process(impulse)
        cab.set_ir_data(np.zeros(2000), "silent")
        cab.hp_b = cab.hp_a = cab.lp_b = cab.lp_a = np.array([1.0])
        cab.hp_zi = cab.lp_zi = np.zeros(0)
        out = cab.process(np.zeros(128))
        self.assertLess(np.max(np.abs(out)), TOL)

    def test_bypass_then_enable_drops_the_tail(self):
        cab = self._cab()
        impulse = np.zeros(128)
        impulse[0] = 1.0
        cab.process(impulse)
        cab.enabled = False
        cab.process(np.zeros(128))
        cab.enabled = True
        self.assertLess(np.max(np.abs(cab.process(np.zeros(128)))), TOL)

    def test_replacing_the_ir_while_blocks_are_processed(self):
        cab = self._cab(plain=False)
        stop = threading.Event()
        errors = []

        def swap():
            rng = np.random.default_rng(17)
            while not stop.is_set():
                try:
                    cab.set_ir_data(rng.standard_normal(int(rng.integers(2, 5000))) * 0.05, "x")
                except Exception as exc:  # pragma: no cover - failure path
                    errors.append(exc)

        worker = threading.Thread(target=swap)
        worker.start()
        try:
            block = np.random.default_rng(19).standard_normal(128) * 0.2
            for _ in range(300):
                self.assertTrue(np.all(np.isfinite(cab.process(block.copy()))))
        finally:
            stop.set()
            worker.join()
        self.assertEqual(errors, [])


class IrLengthCapTests(unittest.TestCase):
    def test_cap_is_one_second_at_the_given_rate(self):
        self.assertEqual(config.ir_max_samples(48000), 48000)
        self.assertEqual(config.ir_max_samples(44100), 44100)

    def test_half_second_ir_is_kept_and_two_seconds_is_cut(self):
        rng = np.random.default_rng(23)
        cap = config.ir_max_samples(48000)
        kept, _ = CabinetSimulator._prepare_ir(rng.standard_normal(24000), 48000, 48000, cap)
        self.assertEqual(len(kept), 24000)
        cut, truncated = CabinetSimulator._prepare_ir(rng.standard_normal(96000), 48000, 48000, cap)
        self.assertEqual(len(cut), 48000)
        self.assertTrue(truncated)

    def test_load_ir_file_keeps_a_long_ir(self):
        cab = CabinetSimulator(sample_rate=48000)
        data = (np.random.default_rng(29).standard_normal(24000) * 0.1).astype(np.float32)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "long.wav"
            wavfile.write(str(path), 48000, data)
            self.assertTrue(cab.load_ir_file(str(path)))
        self.assertEqual(len(cab.ir_data), 24000)


def _reference_eq(amp, blocks, settings):
    """Four stages, filter state carried by hand across blocks and across knob moves."""
    nyq = amp.sample_rate * 0.5
    zis = [None] * 4
    out = []
    for x, (bass, mid, treble, pres) in zip(blocks, settings):
        stages = (amp._shelf(150.0 / nyq, bass, "low"), amp._peak(800.0 / nyq, mid, 1.0),
                  amp._shelf(3500.0 / nyq, treble, "high"), amp._shelf(5500.0 / nyq, pres, "high"))
        for k, (b, a) in enumerate(stages):
            if zis[k] is None:
                zis[k] = np.zeros(max(len(a), len(b)) - 1)
            x, zis[k] = signal.lfilter(b, a, x, zi=zis[k])
        out.append(x)
    return np.concatenate(out)


class ReverbLongBlockTests(unittest.TestCase):
    def test_block_larger_than_shortest_comb_buffer_wraps_repeatedly(self):
        reverb = __import__("engine.dsp", fromlist=["Reverb"]).Reverb(sample_rate=48000)
        reverb.enabled = True
        reverb.mix = 0.4
        x = np.random.default_rng(37).standard_normal(5000).astype(np.float32) * 0.1
        out = reverb.process(x.copy())
        self.assertEqual(out.shape, x.shape)
        self.assertTrue(np.all(np.isfinite(out)))
        self.assertEqual(len(reverb.comb_pos), 4)
        for buf, pos in zip(reverb.comb_buffers, reverb.comb_pos):
            self.assertGreaterEqual(pos, 0)
            self.assertLess(pos, len(buf))

    def test_long_block_processing_matches_irregular_chunks(self):
        from engine.dsp import Reverb
        rng = np.random.default_rng(41)
        x = rng.standard_normal(8000).astype(np.float32) * 0.1
        whole = Reverb(sample_rate=48000)
        whole.enabled = True
        whole.mix = 0.35
        expected = whole.process(x.copy())
        chunked = Reverb(sample_rate=48000)
        chunked.enabled = True
        chunked.mix = 0.35
        chunks = [chunked.process(x[i:i + 333].copy()) for i in range(0, len(x), 333)]
        np.testing.assert_allclose(np.concatenate(chunks), expected, atol=1e-7, rtol=0)


class AmpHeadEqStateTests(unittest.TestCase):
    def setUp(self):
        self.x = np.random.default_rng(31).standard_normal(4096) * 0.2

    def test_block_split_equals_single_pass_at_constant_settings(self):
        g = (6.0, -4.0, 5.0, 3.0)
        whole = AmpHead(sample_rate=48000)._apply_eq(self.x.copy(), *g)
        amp = AmpHead(sample_rate=48000)
        parts = [amp._apply_eq(self.x[i:i + 128].copy(), *g) for i in range(0, len(self.x), 128)]
        self.assertLess(np.max(np.abs(np.concatenate(parts) - whole)), 1e-9)

    def test_state_survives_a_knob_move(self):
        blocks = [self.x[i:i + 128] for i in range(0, 1024, 128)]
        settings = [(6.0, -4.0, 5.0, 3.0)] * 4 + [(-3.0, 2.0, -6.0, 4.0)] * 4
        amp = AmpHead(sample_rate=48000)
        got = np.concatenate([amp._apply_eq(b.copy(), *s) for b, s in zip(blocks, settings)])
        want = _reference_eq(amp, blocks, settings)
        self.assertLess(np.max(np.abs(got - want)), 1e-9)


if __name__ == "__main__":
    unittest.main()
