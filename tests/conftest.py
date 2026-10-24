"""
Pytest configuration for กดจนหลอนTone

Shared fixtures and test configuration.
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import MagicMock

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# sounddevice imports libportaudio at module import. On Linux CI / this
# sandbox there is no PortAudio, so we install a stub before engine.audio
# is imported. Tests that patch engine.audio.sd still work.
try:
    import sounddevice as _sd  # noqa: F401
except OSError:
    _stub = MagicMock(name="sounddevice_stub")
    _stub.query_devices.return_value = []
    _stub.query_hostapis.return_value = []
    _stub.default.device = (None, None)
    _stub.default.samplerate = 48000
    _stub.WasapiSettings = MagicMock
    sys.modules["sounddevice"] = _stub


@pytest.fixture
def sample_rate():
    """Fixture for sample rate."""
    return 48000


@pytest.fixture
def buffer_size():
    """Fixture for buffer size."""
    return 512


@pytest.fixture
def numpy_block(buffer_size):
    """Fixture for a numpy audio block."""
    import numpy as np
    return np.random.randn(buffer_size).astype(np.float32) * 0.1
