"""
Tests for WorldClassAudioProcessor (`engine/world_class_dsp.py`):
Verifies anti-squash dynamics (Crest Factor), 4-model tube topologies,
Constant-Dry effect mixing (zero volume drop when enabling Delay/Reverb/Mod),
Liquid-NAM active tone stack, True Stereo 3D imaging, and Soft-Knee Mastering Limiter.
"""

import unittest
from unittest.mock import patch
import numpy as np

from engine.dsp import GuitarSignalChain
from engine.world_class_dsp import WorldClassAudioProcessor
import server


class TestWorldClassAudioProcessor(unittest.TestCase):
    def setUp(self):
        self.sr = 48000
        self.chain = GuitarSignalChain(sample_rate=self.sr)
        self.chain.noise_gate.enabled = False
        self.hd = WorldClassAudioProcessor(sample_rate=self.sr)
        t = np.arange(4096, dtype=np.float32) / self.sr
        # Dynamic guitar-like signal with pick-attack envelope + harmonics
        env = np.exp(-t * 6.0) * 0.6 + 0.15
        self.guitar = (
            env * (
                0.55 * np.sin(2.0 * np.pi * 110.0 * t)
                + 0.30 * np.sin(2.0 * np.pi * 220.0 * t)
                + 0.15 * np.sin(2.0 * np.pi * 440.0 * t)
            )
        ).astype(np.float32)

    def test_four_amp_models_produce_distinct_voicings_and_crest_factors(self):
        outputs = {}
        crests = {}
        for model in ("Clean", "Twin", "Plexi", "5150"):
            chain = GuitarSignalChain(sample_rate=self.sr)
            chain.noise_gate.enabled = False
            chain.cab.enabled = False
            chain.amp.model = model
            chain.amp.gain = 0.55
            hd = WorldClassAudioProcessor(sample_rate=self.sr)
            hd.auto_level = False
            hd.stereo_width = 0.0
            out = hd.process(chain, self.guitar)[:, 0]
            outputs[model] = out
            rms = float(np.sqrt(np.mean(out ** 2) + 1e-9))
            peak = float(np.max(np.abs(out)) + 1e-9)
            crests[model] = 20.0 * np.log10(peak / rms)

        # Every amp model must be distinct (unlike legacy AmpHead where all 4 were identical)
        self.assertFalse(np.allclose(outputs["Clean"], outputs["5150"], atol=1e-2))
        self.assertFalse(np.allclose(outputs["Twin"], outputs["Plexi"], atol=1e-2))
        # Clean topology must preserve higher dynamic Crest Factor (less squashed) than 5150 high-gain
        self.assertGreater(crests["Clean"], crests["5150"])

    def test_enabling_delay_and_reverb_does_not_drop_dry_attack_volume(self):
        # Measure initial 64-sample pick attack before any delay repeats arrive
        attack_chunk = self.guitar[:128]
        self.chain.delay.enabled = False
        self.chain.reverb.enabled = False
        self.hd.auto_level = False
        dry_out = self.hd.process(self.chain, attack_chunk)
        dry_rms = float(np.sqrt(np.mean(dry_out ** 2)))

        # Reset and enable both Delay (mix=0.40) and Reverb (mix=0.35)
        chain_fx = GuitarSignalChain(sample_rate=self.sr)
        chain_fx.noise_gate.enabled = False
        chain_fx.delay.enabled = True
        chain_fx.delay.time_sec = 0.40
        chain_fx.delay.mix = 0.40
        chain_fx.reverb.enabled = True
        chain_fx.reverb.mix = 0.35
        hd_fx = WorldClassAudioProcessor(sample_rate=self.sr)
        hd_fx.auto_level = False
        fx_out = hd_fx.process(chain_fx, attack_chunk)
        fx_rms = float(np.sqrt(np.mean(fx_out ** 2)))

        # Constant-Dry mix law keeps initial pick attack >= 95% of dry RMS (instead of dropping 42%!)
        self.assertGreaterEqual(fx_rms, dry_rms * 0.95)

    def test_true_stereo_3d_imaging_decorrelates_left_and_right(self):
        self.chain.mod.enabled = True
        self.chain.mod.model_id = 12  # Stereo Chorus
        self.chain.mod.mix = 0.45
        self.chain.delay.enabled = True
        self.chain.delay.mix = 0.30
        self.chain.reverb.enabled = True
        self.chain.reverb.mix = 0.30
        out = self.hd.process(self.chain, self.guitar)
        self.assertEqual(out.shape, (len(self.guitar), 2))
        diff = float(np.max(np.abs(out[:, 0] - out[:, 1])))
        self.assertGreater(diff, 0.01)
        self.assertGreater(self.hd.last_stereo_width_pct, 5.0)

    def test_soft_knee_limiter_prevents_hard_clipping_on_hot_signals(self):
        hot = (self.guitar * 15.0).astype(np.float32)
        self.chain.screamer.enabled = True
        self.chain.screamer.drive = 0.95
        self.chain.amp.gain = 0.95
        self.chain.master_volume = 1.5
        out = self.hd.process(self.chain, hot)
        self.assertTrue(np.all(np.isfinite(out)))
        self.assertLessEqual(float(np.max(np.abs(out))), 0.9801)

    def test_hd_path_is_opt_in_and_does_not_requantize(self):
        # Live audio must stay on GuitarSignalChain.process until the user opts in.
        self.assertFalse(self.hd.enabled)
        self.assertFalse(self.hd.force_nam_ir)
        x = (self.guitar[:256] * 0.3).astype(np.float32)
        self.assertIs(self.hd._quantize_24bit_tpdf(x), x)

    def test_load_pair_bypasses_cab_for_capture_that_includes_cabinet(self):
        import tempfile
        from pathlib import Path
        from unittest import mock

        class FakeCapture:
            enabled = True
            input_gain_db = 0.0

            def __init__(self, includes_cab):
                self.includes_cab = includes_cab

            def set_input_gain_db(self, db):
                self.input_gain_db = db

            def describe(self):
                return {"includes_cab": self.includes_cab}

            def process(self, x):
                return x

        eng = server.engine
        saved = (eng.chain.nam, eng.chain.cab.enabled, eng.hd_dsp.force_nam_ir)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                (Path(tmp) / "custom_nam").mkdir()
                (Path(tmp) / "custom_nam" / "cap.nam").write_bytes(b"{}")
                eng.hd_dsp.force_nam_ir = False
                for includes_cab, expect_cab in ((True, False), (False, True)):
                    eng.chain.cab.enabled = not expect_cab
                    with mock.patch.object(server.config, "PROJECT_ROOT", Path(tmp)), \
                         mock.patch.object(server, "_build_nam_chain", return_value=FakeCapture(includes_cab)):
                        server.load_nam_a2_and_ir_pair({"nam_id": "custom_nam::cap.nam"})
                    self.assertEqual(eng.chain.cab.enabled, expect_cab, f"includes_cab={includes_cab}")
        finally:
            eng.chain.nam, eng.chain.cab.enabled, eng.hd_dsp.force_nam_ir = saved

    def test_output_trim_scales_hd_output_and_auto_level_is_off_by_default(self):
        self.assertFalse(self.hd.auto_level)
        quiet = (self.guitar * 0.05).astype(np.float32)  # stays below the limiter knee

        def render(trim_db):
            chain = GuitarSignalChain(sample_rate=self.sr)
            chain.noise_gate.enabled = False
            hd = WorldClassAudioProcessor(sample_rate=self.sr)
            hd.update_settings({"output_trim_db": trim_db})
            return np.concatenate([hd.process(chain, quiet[i:i + 128]) for i in range(0, len(quiet), 128)])

        flat, up = render(0.0), render(6.0)
        self.assertLess(float(np.max(np.abs(up))), 0.70)
        np.testing.assert_allclose(up, flat * 10 ** (6.0 / 20.0), rtol=1e-4, atol=1e-6)
        self.assertEqual(self.hd.update_settings({"output_trim_db": 99})["output_trim_db"], 12.0)
        self.assertEqual(self.hd.update_settings({"output_trim_db": float("nan")})["output_trim_db"], 12.0)

    def test_spectrum_bands_follow_the_real_output(self):
        eng = server.engine
        saved = (eng._scope.copy(), eng._scope_pos)
        try:
            t = np.arange(4096) / eng.sample_rate
            tone = (0.5 * np.sin(2 * np.pi * 1000.0 * t)).astype(np.float32)
            for i in range(0, len(tone), 128):
                eng._write_scope(tone[i:i + 128])
            bands = eng.spectrum_bands()
            edges = np.geomspace(40.0, min(16000.0, eng.sample_rate / 2), 25)
            loudest = int(np.argmax(bands))
            self.assertTrue(edges[loudest] <= 1000.0 < edges[loudest + 1] * 1.1, (loudest, bands))
            self.assertAlmostEqual(bands[loudest], 20 * np.log10(0.5), delta=1.5)
            eng._scope[:] = 0
            self.assertEqual(max(eng.spectrum_bands()), -90.0)
        finally:
            eng._scope[:], eng._scope_pos = saved

    def test_ai_tone_match_reports_no_match_instead_of_loading_a_random_tone(self):
        from fastapi import HTTPException
        from engine.ai_tone_matcher import match_artist_tone
        self.assertIsNone(match_artist_tone("zzqx nothing like this"))
        with self.assertRaises(HTTPException) as caught:
            server.ai_tone_match_endpoint({"query": "zzqx nothing like this"})
        self.assertEqual(caught.exception.status_code, 404)

    def test_hd_audio_api_endpoints(self):
        st = server.get_hd_audio_status()
        self.assertIn("enabled", st)
        self.assertIn("telemetry", st)
        res = server.update_hd_audio_settings({
            "auto_level": True,
            "pure_cab": 0.80,
            "stereo_width": 0.75,
            "anti_squash": 0.85,
        })
        self.assertTrue(res["success"])
        self.assertAlmostEqual(res["hd_audio"]["pure_cab"], 0.80)
        self.assertAlmostEqual(res["hd_audio"]["stereo_width"], 0.75)
        self.assertAlmostEqual(res["hd_audio"]["anti_squash"], 0.85)

    def test_ozzy_neural_24bit_44k_topology_and_natural_touch_dynamics(self):
        from engine.world_class_dsp import synthesize_studio_24bit_ir
        sr = 44100
        chain = GuitarSignalChain(sample_rate=sr)
        chain.noise_gate.enabled = False
        chain.amp.model = "Ozzy_Neural"
        chain.amp.gain = 0.78
        ir = synthesize_studio_24bit_ir("Ozzy British Oversized 4x12 (24-Bit 44.1kHz)", sample_rate=sr)
        self.assertIsNotNone(ir)
        self.assertEqual(len(ir), 2048)
        chain.cab.set_ir_data(ir, "Ozzy British Oversized 4x12 (24-Bit 44.1kHz)")

        hd = WorldClassAudioProcessor(sample_rate=sr)
        hd.bit_depth = 24
        hd.touch_sensitivity = 0.92
        hd.ozzy_doubler = True

        # Soft picking (in_rms ~ 0.015) vs Hard picking (in_rms ~ 0.25)
        soft_in = (self.guitar * 0.04).astype(np.float32)
        hard_in = (self.guitar * 0.75).astype(np.float32)

        soft_out = hd.process(chain, soft_in)
        soft_rms = float(np.sqrt(np.mean(soft_out ** 2)))

        hard_out = hd.process(chain, hard_in)
        hard_rms = float(np.sqrt(np.mean(hard_out ** 2)))

        # Natural dynamic response: hard picking must be significantly louder than soft picking
        self.assertGreater(hard_rms, soft_rms * 2.5)
        # Ozzy × Neural Stereo Doubler creates wide stereo separation
        stereo_diff = float(np.max(np.abs(hard_out[:, 0] - hard_out[:, 1])))
        self.assertGreater(stereo_diff, 0.01)

    def test_namb_binary_a2_parser_and_nam_a2_ir_pairing_api(self):
        import struct
        from engine.nam import parse_namb_binary
        # Construct a valid 1,871-weight NAM A2-Lite binary (.namb) payload
        weights = np.random.default_rng(7).normal(0, 0.02, size=1871).astype(np.float32)
        raw_namb = b"NAMB" + struct.pack("<II", 2, 1871) + weights.tobytes()
        parsed = parse_namb_binary(raw_namb, filename="test_ozzy_a2.namb")
        self.assertEqual(parsed["version"], "0.7.0")
        self.assertEqual(parsed["architecture"], "SlimmableContainer")
        net = server._build_nam_chain(raw_namb, "test_ozzy_a2.namb", "full")
        out = net.process(self.guitar[:256])
        self.assertEqual(len(out), 256)
        self.assertTrue(np.all(np.isfinite(out)))

        # Test catalog, NAM A2 + IR pairing, and 24-Bit / 44.1 kHz studio mode API
        cat = server.get_nam_a2_and_ir_catalog()
        self.assertTrue(len(cat["nam_a2_models"]) >= 1)
        self.assertIn("Ozzy British Oversized 4x12 (24-Bit 44.1kHz)", cat["studio_24bit_irs"])

        pair_res = server.load_nam_a2_and_ir_pair({
            "ir_name": "Ozzy British Oversized 4x12 (24-Bit 44.1kHz)",
            "quality": "full",
            "enable_cab": True,
        })
        self.assertTrue(pair_res["success"])
        self.assertTrue(server.engine.chain.cab.enabled)

        orig_sr = server.engine.sample_rate
        try:
            with patch.object(server, "persist_audio_path"):
                sr_res = server.activate_24bit_44100_studio_mode({
                    "sample_rate": 44100,
                    "bit_depth": 24,
                    "touch_sensitivity": 0.90,
                    "ozzy_doubler": True,
                })
                self.assertTrue(sr_res["success"])
                self.assertEqual(sr_res["sample_rate"], 44100)
                self.assertEqual(sr_res["bit_depth"], 24)
        finally:
            server.engine.apply_sample_rate(orig_sr)

        from engine.ai_tone_matcher import match_artist_tone
        matched = match_artist_tone("โอไซด์ นูลอ 24bit 44.1")
        self.assertEqual(matched["id"], "ozzy_neural_24bit")
        self.assertEqual(matched["settings"]["amp"]["model"], "Ozzy_Neural")


if __name__ == "__main__":
    unittest.main()
