"""
Pytest configuration for กดจนหลอนTone

Shared fixtures and test configuration.
"""

import pytest
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


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
