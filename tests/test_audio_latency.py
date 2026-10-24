"""Regression tests for the audio path / latency fixes.

Background (measured on the real Line 6 UX1):
  * Opening the UX1 WASAPI stream from an uninitialised (worker) thread fails
    with "WdmSyncIoctl ... GLE = 0x490".
  * The old code then fell back to the system default devices and reported
    success, so the player heard ~107 ms instead of ~44 ms with no warning.
  * Saved device indices (17/15) are not stable; index 15 has no outputs at
    all, so that pair can never open.

These tests use a fake device table and a fake stream so they never touch real
hardware.
"""

import sys
import threading
import unittest
from unittest.mock import MagicMock, patch

from engine import audio as audio_module
from engine.audio import AudioEngine, ensure_com_initialized

# Fake PortAudio layout mirroring this machine: the UX1 exposes separate
# WASAPI input/output endpoints, DirectSound exposes an input-only endpoint,
# and a virtual device also provides an input.
DEVICES = [
    {  # 0: UX1 output (WASAPI)
        "name": "Speakers (Line 6 UX1)", "hostapi": 2,
        "max_input_channels": 0, "max_output_channels": 2,
        "default_samplerate": 48000.0,
        "default_low_input_latency": 0.003, "default_low_output_latency": 0.003,
    },
    {  # 1: UX1 input (WASAPI)
        "name": "Digital Audio Interface (Line 6 UX1)", "hostapi": 2,
        "max_input_channels": 2, "max_output_channels": 0,
        "default_samplerate": 48000.0,
        "default_low_input_latency": 0.003, "default_low_output_latency": 0.003,
    },
    {  # 2: unrelated virtual input, occupies the "stale index" role
        "name": "SteelSeries Sonar - Stream", "hostapi": 1,
        "max_input_channels": 2, "max_output_channels": 0,
        "default_samplerate": 48000.0,
        "default_low_input_latency": 0.120, "default_low_output_latency": 0.120,
    },
    {  # 3: UX1 input over DirectSound -- no output channels at all
        "name": "Digital Audio Interface (Line 6 UX1)", "hostapi": 1,
        "max_input_channels": 2, "max_output_channels": 0,
        "default_samplerate": 48000.0,
        "default_low_input_latency": 0.120, "default_low_output_latency": 0.120,
    },
    {  # 4: the same output endpoint exposed over MME (high latency)
        "name": "Speakers (Line 6 UX1)", "hostapi": 0,
        "max_input_channels": 0, "max_output_channels": 2,
        "default_samplerate": 48000.0,
        "default_low_input_latency": 0.090, "default_low_output_latency": 0.090,
    },
]
HOSTAPIS = [
    {"name": "MME"}, {"name": "Windows DirectSound"},
    {"name": "Windows WASAPI"}, {"name": "ASIO"},
]
UX1_IN, UX1_OUT = 1, 0


def fake_query_devices(device=None, kind=None):
    if kind == "input":
        return dict(DEVICES[UX1_IN], index=UX1_IN)
    if kind == "output":
        return dict(DEVICES[UX1_OUT], index=UX1_OUT)
    if device is None:
        return [dict(d, index=i) for i, d in enumerate(DEVICES)]
    return dict(DEVICES[int(device)], index=int(device))


class FakeStream:
    """Records construction and optionally fails for a given device pair."""

    fail_pairs = set()
    opened = []

    def __init__(self, **kwargs):
        FakeStream.opened.append(kwargs.get("device"))
        if kwargs.get("device") in FakeStream.fail_pairs:
            raise RuntimeError("WdmSyncIoctl: DeviceIoControl GLE = 0x00000490")
        self.kwargs = kwargs
        self.latency = (0.022, 0.022)  # driver-reported 22 ms in + 22 ms out
        self.active = False

    def start(self):
        self.active = True

    def stop(self):
        self.active = False

    def close(self):
        self.active = False


class AudioPathTestCase(unittest.TestCase):
    def setUp(self):
        FakeStream.opened = []
        FakeStream.fail_pairs = set()
        self._patches = [
            patch.object(audio_module.sd, "query_devices", side_effect=fake_query_devices),
            patch.object(audio_module.sd, "query_hostapis", return_value=HOSTAPIS),
            patch.object(audio_module.sd, "Stream", side_effect=lambda **kw: FakeStream(**kw)),
        ]
        for p in self._patches:
            p.start()
            self.addCleanup(p.stop)

    def make_engine(self):
        return AudioEngine(sample_rate=48000, block_size=128)


class DeviceValidationTests(AudioPathTestCase):
    def test_output_only_device_cannot_be_an_input(self):
        engine = self.make_engine()
        self.assertFalse(engine._device_usable(UX1_OUT, True))
        self.assertTrue(engine._device_usable(UX1_OUT, False))

    def test_device_without_outputs_cannot_be_an_output(self):
        engine = self.make_engine()
        # Index 3 is how audio_settings.json described the UX1 output.
        self.assertFalse(engine._device_usable(3, False))

    def test_unknown_index_is_unusable(self):
        engine = self.make_engine()
        self.assertFalse(engine._device_usable(999, True))

    def test_resolver_replaces_stale_output_index(self):
        engine = self.make_engine()
        resolved_in, resolved_out, replaced = engine._resolve_device_pair(2, 3)
        self.assertEqual((resolved_in, resolved_out), (2, UX1_OUT))
        self.assertTrue(replaced)

    def test_resolver_replaces_input_index_that_has_no_inputs(self):
        engine = self.make_engine()
        resolved_in, resolved_out, replaced = engine._resolve_device_pair(UX1_OUT, UX1_OUT)
        self.assertEqual((resolved_in, resolved_out), (UX1_IN, UX1_OUT))
        self.assertTrue(replaced)

    def test_resolver_keeps_a_valid_pair(self):
        engine = self.make_engine()
        self.assertEqual(engine._resolve_device_pair(2, UX1_OUT), (2, UX1_OUT, False))

    def test_saved_name_wins_over_a_stale_index(self):
        # audio_settings.json said index 2, but the saved name is the UX1.
        engine = AudioEngine(
            sample_rate=48000, block_size=128,
            preferred_input=2,
            preferred_input_name="Digital Audio Interface (Line 6 UX1)",
        )
        self.assertEqual(engine.input_device, UX1_IN)

    def test_saved_name_prefers_wasapi_over_mme_and_directsound(self):
        engine = AudioEngine(
            sample_rate=48000, block_size=128,
            preferred_input_name="Digital Audio Interface (Line 6 UX1)",
            preferred_output_name="Speakers (Line 6 UX1)",
        )
        self.assertEqual(engine.input_device, UX1_IN)   # WASAPI, not DirectSound
        self.assertEqual(engine.output_device, UX1_OUT)  # WASAPI, not MME

    def test_select_devices_updates_the_described_pair(self):
        engine = self.make_engine()
        engine.select_devices(2, UX1_OUT)
        path = engine.audio_path_info()
        self.assertEqual(engine.stream_device_pair, (2, UX1_OUT))
        self.assertEqual(path["input"]["name"], "SteelSeries Sonar - Stream")
        self.assertEqual(path["output"]["name"], "Speakers (Line 6 UX1)")

    def test_saved_index_used_when_name_is_unknown(self):
        engine = AudioEngine(
            sample_rate=48000, block_size=128,
            preferred_input=2,
            preferred_input_name="Device That Was Unplugged",
        )
        self.assertEqual(engine.input_device, 2)


class EngineStartTests(AudioPathTestCase):
    def test_start_opens_the_ux1_wasapi_pair_and_reports_real_latency(self):
        engine = self.make_engine()
        ok, msg = engine.start()
        self.assertTrue(ok, msg)
        self.assertFalse(engine.using_fallback)
        self.assertEqual(engine.input_device, UX1_IN)
        self.assertEqual(engine.output_device, UX1_OUT)
        self.assertEqual(FakeStream.opened[-1], (UX1_IN, UX1_OUT))

        path = engine.audio_path_info()
        self.assertEqual(path["reported_io_ms"], 44.0)
        self.assertEqual(path["input_ms"], 22.0)
        self.assertEqual(path["output_ms"], 22.0)
        self.assertEqual(path["output"]["hostapi"], "Windows WASAPI")
        self.assertIsNone(path["warning"])
        engine.stop()

    def test_stale_pair_is_resolved_before_opening(self):
        """A saved pair with an output-less device never reaches PortAudio."""
        engine = self.make_engine()
        ok, msg = engine.start(input_id=2, output_id=3)
        self.assertTrue(ok, msg)
        self.assertFalse(engine.using_fallback)
        self.assertNotIn((2, 3), FakeStream.opened)
        self.assertEqual(FakeStream.opened[-1], (2, UX1_OUT))

    def test_resolved_pair_failure_retries_with_detected_ux1(self):
        FakeStream.fail_pairs = {(2, UX1_OUT)}
        engine = self.make_engine()
        ok, msg = engine.start(input_id=2, output_id=3)
        self.assertTrue(ok, msg)
        self.assertFalse(engine.using_fallback)
        self.assertEqual(FakeStream.opened[-1], (UX1_IN, UX1_OUT))

    def test_default_fallback_is_flagged_not_hidden(self):
        # Every explicit pair fails; only the system default opens.
        FakeStream.fail_pairs = {(2, UX1_OUT), (UX1_IN, UX1_OUT)}
        engine = self.make_engine()
        ok, msg = engine.start(input_id=2, output_id=3)
        self.assertTrue(ok, msg)
        self.assertTrue(engine.using_fallback)
        self.assertEqual(FakeStream.opened[-1], None)  # default-device stream
        path = engine.audio_path_info()
        self.assertEqual(path["warning"], "fallback")
        self.assertEqual(path["reported_io_ms"], 44.0)
        self.assertIn("WdmSyncIoctl", path["error"])

    def test_fallback_warning_reaches_get_state(self):
        FakeStream.fail_pairs = {(2, UX1_OUT), (UX1_IN, UX1_OUT)}
        engine = self.make_engine()
        engine.start(input_id=2, output_id=3)
        state = engine.get_state()
        self.assertEqual(state["audio_path"]["warning"], "fallback")
        self.assertEqual(state["audio_stats"]["stream_latency"]["reported_io_ms"], 44.0)
        engine.stop()

    def test_dsp_over_budget_is_reported_not_hidden(self):
        engine = self.make_engine()
        engine.start()
        # A TONE3000 NAM chain at 48k/128 measures ~2.9 ms for a 2.67 ms block.
        engine.callback_ms_avg = 2.9
        engine._over_budget_windows = 2
        engine._window_blocks = 150
        path = engine.audio_path_info()
        self.assertEqual(path["warning"], "dsp_over_budget")
        self.assertAlmostEqual(path["dsp_avg_ms"], 2.9, places=2)
        self.assertEqual(path["dsp_window_blocks"], 150)
        engine.stop()

    def test_callback_average_follows_the_latest_window(self):
        """A heavier chain must raise the warning within one window, not hours."""
        engine = self.make_engine()
        engine.start()
        engine._callback_warmup = 0
        for _ in range(audio_module.STATS_WINDOW_BLOCKS):
            engine._record_block_time(1.0)
        self.assertAlmostEqual(engine.callback_stats()["avg_ms"], 1.0, places=2)
        self.assertIsNone(engine.audio_path_info()["warning"])

        # One heavy window is not enough: loading a chain always costs one.
        for _ in range(audio_module.STATS_WINDOW_BLOCKS):
            engine._record_block_time(3.4)
        self.assertAlmostEqual(engine.callback_stats()["avg_ms"], 3.4, places=2)
        self.assertIsNone(engine.audio_path_info()["warning"])

        for _ in range(audio_module.STATS_WINDOW_BLOCKS):
            engine._record_block_time(3.4)
        self.assertEqual(engine.audio_path_info()["warning"], "dsp_over_budget")
        engine.stop()

    def test_failed_start_reports_failure_instead_of_silent_success(self):
        FakeStream.fail_pairs = {(2, UX1_OUT), (UX1_IN, UX1_OUT), None}
        engine = self.make_engine()
        ok, msg = engine.start(input_id=2, output_id=3)
        self.assertFalse(ok)
        self.assertFalse(engine.is_running)

    def test_audio_stats_exposes_percentiles(self):
        engine = self.make_engine()
        engine._callback_warmup = 0
        for v in (0.5, 1.0, 1.5, 2.0):
            engine._record_block_time(v)
        stats = engine.get_state()["audio_stats"]
        self.assertIn("p50_ms", stats)
        self.assertIn("p95_ms", stats)
        self.assertIn("p99_ms", stats)
        self.assertIn("p99_9_ms", stats)
        self.assertIn("callback_errors", stats)
        self.assertIn("nonfinite_blocks", stats)
        self.assertIsNotNone(stats["p99_ms"])
        self.assertEqual(stats["callback_errors"], 0)


class DevicePersistenceTests(unittest.TestCase):
    """Saved devices describe the user's intent, never the fallback pair."""

    def _persist(self, path_info):
        import server

        stub = MagicMock()
        stub.sample_rate = 48000
        stub.block_size = 128
        stub.audio_path_info.return_value = path_info
        with patch.object(server, "engine", stub), \
                patch.object(server.config, "save_audio_settings") as save:
            server.persist_audio_path()
        return save.call_args.kwargs

    def test_fallback_pair_is_not_saved(self):
        kwargs = self._persist({
            "using_fallback": True,
            "input": {"id": 3, "name": "Microphone (Realtek)"},
            "output": {"id": 2, "name": "Speakers (Realtek)"},
        })
        self.assertEqual(kwargs["sample_rate"], 48000)
        self.assertEqual(kwargs["buffer_size"], 128)
        for key in ("input_device", "output_device", "input_name", "output_name"):
            self.assertNotIn(key, kwargs)

    def test_real_pair_is_saved_with_names(self):
        kwargs = self._persist({
            "using_fallback": False,
            "input": {"id": UX1_IN, "name": "Digital Audio Interface (Line 6 UX1)"},
            "output": {"id": UX1_OUT, "name": "Speakers (Line 6 UX1)"},
        })
        self.assertEqual(kwargs["input_device"], UX1_IN)
        self.assertEqual(kwargs["output_device"], UX1_OUT)
        self.assertEqual(kwargs["input_name"], "Digital Audio Interface (Line 6 UX1)")
        self.assertEqual(kwargs["output_name"], "Speakers (Line 6 UX1)")


class ComInitialisationTests(unittest.TestCase):
    def test_ensure_com_initialized_is_idempotent(self):
        results = []

        def run():
            results.append(ensure_com_initialized())
            results.append(ensure_com_initialized())

        t = threading.Thread(target=run)
        t.start()
        t.join()
        if sys.platform == "win32":
            self.assertEqual(results, [True, True])
        else:
            self.assertEqual(results, [False, False])


if __name__ == "__main__":
    unittest.main()
