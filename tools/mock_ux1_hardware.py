#!/usr/bin/env python3
"""Mock hardware smoke test for Line 6 POD Studio UX1.

This test replaces sounddevice discovery and the PortAudio stream with an
in-memory fake. It verifies the hardware-facing integration without requiring
an audio interface or opening a real input/output device.

Run from the project root:
    python tools/mock_ux1_hardware.py

The project dependencies are still required (numpy, scipy, sounddevice), but
no physical UX1, ASIO driver, microphone, or speaker is required.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import patch

import numpy as np

# When executed as `python tools/mock_ux1_hardware.py`, Python puts the tools
# directory (not the project root) on sys.path. Add the root explicitly so the
# script is also convenient to run via an absolute path from any directory.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.audio import AudioEngine


MOCK_HOSTAPIS = [
    {"name": "MME"},
    {"name": "Windows DirectSound"},
    {"name": "Windows WASAPI"},
    {"name": "ASIO"},
]

MOCK_DEVICES = [
    {
        "name": "Line 6 POD Studio UX1 (MME)",
        "hostapi": 0,
        "max_input_channels": 2,
        "max_output_channels": 2,
        "default_samplerate": 48000.0,
        "default_low_input_latency": 0.120,
        "default_low_output_latency": 0.120,
    },
    {
        "name": "Line 6 POD Studio UX1 (WASAPI)",
        "hostapi": 2,
        "max_input_channels": 2,
        "max_output_channels": 2,
        "default_samplerate": 48000.0,
        "default_low_input_latency": 0.012,
        "default_low_output_latency": 0.012,
    },
    {
        "name": "Line 6 POD Studio UX1",  # preferred ASIO pair
        "hostapi": 3,
        "max_input_channels": 2,
        "max_output_channels": 2,
        "default_samplerate": 48000.0,
        "default_low_input_latency": 0.003,
        "default_low_output_latency": 0.004,
    },
    {
        "name": "Mock Monitor Output",
        "hostapi": 2,
        "max_input_channels": 0,
        "max_output_channels": 2,
        "default_samplerate": 48000.0,
        "default_low_input_latency": 0.0,
        "default_low_output_latency": 0.010,
    },
]


@dataclass
class MockStream:
    """Small sounddevice.Stream-compatible object used by the test."""

    kwargs: dict[str, Any]
    latency: tuple[float, float] = (0.0031, 0.0047)
    active: bool = False

    def start(self) -> None:
        self.active = True

    def stop(self) -> None:
        self.active = False

    def close(self) -> None:
        self.active = False


class MockSoundDevice:
    """Only the sounddevice surface used by AudioEngine."""

    def __init__(self) -> None:
        self.last_stream: MockStream | None = None

    @staticmethod
    def query_devices() -> list[dict[str, Any]]:
        return MOCK_DEVICES

    @staticmethod
    def query_hostapis() -> list[dict[str, str]]:
        return MOCK_HOSTAPIS

    def Stream(self, **kwargs: Any) -> MockStream:
        self.last_stream = MockStream(kwargs)
        return self.last_stream


def run_mock(buffer_size: int = 256) -> dict[str, Any]:
    mock_sd = MockSoundDevice()
    with patch("engine.audio.sd", mock_sd):
        engine = AudioEngine(sample_rate=48000, block_size=buffer_size)

        devices = engine.get_device_list()
        ok, message = engine.start()
        if not ok:
            raise AssertionError(f"mock stream did not start: {message}")

        assert engine.input_device == 2, engine.input_device
        assert engine.output_device == 2, engine.output_device
        assert mock_sd.last_stream is not None
        assert mock_sd.last_stream.kwargs["device"] == (2, 2)
        assert mock_sd.last_stream.kwargs["latency"] == "low"
        assert mock_sd.last_stream.active

        frames = buffer_size
        indata = np.zeros((frames, 1), dtype=np.float32)
        outdata = np.zeros((frames, 2), dtype=np.float32)
        engine._audio_callback(indata, outdata, frames, {}, None)
        assert outdata.shape == (frames, 2)
        assert np.isfinite(outdata).all()

        state = engine.get_state()
        stats = state["audio_stats"]
        stream_latency = stats["stream_latency"]
        assert stream_latency["input_ms"] == 3.1
        assert stream_latency["output_ms"] == 4.7
        assert stream_latency["reported_io_ms"] == 7.8
        assert stats["xruns"] == {
            "input_underflow": 0,
            "input_overflow": 0,
            "output_underflow": 0,
            "output_overflow": 0,
        }

        engine.stop()
        assert not engine.is_running

        return {
            "selected_input": engine.input_device,
            "selected_output": engine.output_device,
            "selected_hostapi": devices[2]["hostapi_name"],
            "buffer_size": buffer_size,
            "engine_buffer_ms": round(buffer_size / 48000 * 1000, 2),
            "hardware_input_ms": stream_latency["input_ms"],
            "hardware_output_ms": stream_latency["output_ms"],
            "hardware_io_ms": stream_latency["reported_io_ms"],
            "callback_shape": list(outdata.shape),
            "xruns": stats["xruns"],
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--buffer", type=int, default=256, choices=(128, 256, 512, 1024))
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON only")
    args = parser.parse_args()

    try:
        result = run_mock(args.buffer)
    except Exception as exc:  # clear non-zero result for CI/smoke usage
        print(f"MOCK UX1 FAILED: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    else:
        print("MOCK UX1 HARDWARE: PASS")
        print(f"  selected device: {result['selected_input']} / {result['selected_hostapi']}")
        print(f"  engine buffer:   {result['buffer_size']} samples ({result['engine_buffer_ms']:.2f} ms)")
        print(f"  hardware I/O:    {result['hardware_io_ms']:.2f} ms (in {result['hardware_input_ms']:.2f} + out {result['hardware_output_ms']:.2f})")
        print(f"  callback:        {result['callback_shape'][0]} frames × {result['callback_shape'][1]} channels")
        print("  xruns:           0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
