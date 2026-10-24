"""Phase 7 software-side acceptance checks.

These tests do NOT open Line 6 UX1 hardware and must never be read as a live
ASIO round-trip measurement. They pin the production-path contracts that Phase 6
claimed, so a later Windows+UX1 run can be compared against honest telemetry.
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.audio import AudioEngine  # noqa: E402
from engine.cpp_host import find_cpp_host_binary  # noqa: E402


class TestNativeCppPathHonesty(unittest.TestCase):
    def test_audio_path_info_does_not_invent_ux1_latency(self):
        engine = AudioEngine()
        engine.native_cpp_active = True
        engine.cpp_host_info = {
            "backend": "realtime_pacer",
            "asio_running": False,
            "asio_driver": "",
            "sample_rate": 48000,
            "buffer_size": 128,
            "roundtrip_latency_ms": None,
            "input_ms": None,
            "output_ms": None,
            "metrics": {"avg_ms": 0.01},
        }
        path = engine.audio_path_info()
        self.assertFalse(path["native_cpp_asio"])
        self.assertNotEqual(path.get("reported_io_ms"), 17.5)
        self.assertIsNone(path.get("reported_io_ms"))
        self.assertEqual(path["backend"], "realtime_pacer")
        self.assertEqual(path["warning"], "native_cpp_not_asio")

    def test_audio_path_info_reports_live_asio_numbers_when_provided(self):
        engine = AudioEngine()
        engine.native_cpp_active = True
        engine.cpp_host_info = {
            "backend": "asio: ASIO UX1",
            "asio_running": True,
            "asio_driver": "ASIO UX1",
            "sample_rate": 48000,
            "buffer_size": 128,
            "roundtrip_latency_ms": 17.65,
            "input_ms": 5.83,
            "output_ms": 11.82,
            "metrics": {"avg_ms": 0.004},
        }
        path = engine.audio_path_info()
        self.assertTrue(path["native_cpp_asio"])
        self.assertEqual(path["reported_io_ms"], 17.65)
        self.assertEqual(path["driver"], "ASIO UX1")
        self.assertIsNone(path["warning"])

    def test_native_cpp_active_skips_portaudio_stream(self):
        engine = AudioEngine()
        engine.native_cpp_active = True
        with patch.object(engine, "_open_stream", side_effect=AssertionError("PortAudio must not open")):
            ok, msg = engine.start()
        self.assertTrue(ok)
        self.assertIn("Native C++", msg)
        self.assertTrue(engine.is_running)
        self.assertIsNone(engine.stream)


class TestCppHostDiscovery(unittest.TestCase):
    def test_finder_returns_none_or_existing_file(self):
        found = find_cpp_host_binary()
        if found is None:
            self.assertFalse((ROOT / "cpp_engine" / "build" / "hack_effect_host").exists())
        else:
            self.assertTrue(os.path.isfile(found))


class TestGuiDoesNotHardcodeLatency(unittest.TestCase):
    def test_app_js_toast_does_not_claim_17_5_ms(self):
        text = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        self.assertNotIn("17.5 ms UX1", text)
        self.assertIn("cppBridge.connect()", text)
        self.assertIn("type: 'set_scene'", text)
        self.assertIn("type: 'set_bypass'", text)


if __name__ == "__main__":
    unittest.main()
