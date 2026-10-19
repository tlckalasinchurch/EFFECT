"""
Configuration management for กดจนหลอนTone

Centralized configuration for audio settings, paths, and application behavior.
"""

import os
from pathlib import Path
from typing import Optional

# Project Paths
# NOTE: config.py lives at the project root, so `.parent` IS the project root.
# The previous `.parent.parent` resolved to the Desktop folder, which made
# WEB_DIR/DB_PATH point at non-existent siblings and created CUSTOM_IR_DIR
# outside the project.
PROJECT_ROOT = Path(__file__).parent
ENGINE_DIR = PROJECT_ROOT / "engine"
WEB_DIR = PROJECT_ROOT / "web"
DOCS_DIR = PROJECT_ROOT / "docs"
DB_PATH = PROJECT_ROOT / "presets.db"

# Audio Configuration
SAMPLE_RATE = int(os.getenv("SAMPLE_RATE", "48000"))
BUFFER_SIZE = int(os.getenv("BUFFER_SIZE", "512"))
BLOCK_SIZE = BUFFER_SIZE

# Line 6 UX1 Default Devices (WASAPI)
DEFAULT_INPUT_DEVICE = int(os.getenv("AUDIO_INPUT_DEVICE", "17"))
DEFAULT_OUTPUT_DEVICE = int(os.getenv("AUDIO_OUTPUT_DEVICE", "15"))

# Latency calculation
LATENCY_MS = (BUFFER_SIZE / SAMPLE_RATE) * 1000

# Kemper Rig Packs
KEMPER_PACK_DIR = r"C:\Program Files\Kemper Amps\Rig Manager\Rig Packs"

# TONE3000 Factory Presets
TONE3000_FACTORY_DIR = r"C:\ProgramData\TONE3000\Presets\Factory"

# Tuner Configuration
TUNER_MIN_FREQ = 60.0
TUNER_MAX_FREQ = 1200.0
TUNER_THROTTLE_HZ = 15  # Throttle to 15 Hz
TUNER_SIGNAL_THRESHOLD = 0.015  # Minimum signal level for pitch detection

# DSP Configuration
DSP_NUMPY_DTYPE = "float32"
DSP_CLIP_LIMIT = 1.0

# Cabinet IR Configuration
IR_NORMALIZATION_GAIN = 0.35

# Web Server Configuration
WEB_HOST = os.getenv("WEB_HOST", "127.0.0.1")
WEB_PORT = int(os.getenv("WEB_PORT", "8000"))

# Logging Configuration
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Window Configuration
WINDOW_TITLE = "กดจนหลอนTone - Guitar Rig & Amp Modeler"
WINDOW_WIDTH = 1320
WINDOW_HEIGHT = 900
WINDOW_MIN_WIDTH = 1080
WINDOW_MIN_HEIGHT = 740
WINDOW_BG_COLOR = "#181a1f"

# Performance Monitoring
ENABLE_PERFORMANCE_MONITORING = os.getenv("ENABLE_PERFORMANCE_MONITORING", "false").lower() == "true"

# Custom IR Directory
CUSTOM_IR_DIR = PROJECT_ROOT / "custom_irs"

# Cabinet IR limits (shared by the DSP layer and the upload endpoint)
IR_MAX_LENGTH = 2048  # Maximum IR length in samples
IR_UPLOAD_MAX_BYTES = 16 * 1024 * 1024  # Hard cap on uploaded .wav payload
IR_ALLOWED_SUFFIXES = {".wav"}


def get_audio_device_names() -> tuple[Optional[int], Optional[int]]:
    """
    Get input and output device IDs from environment or defaults.
    
    Returns:
        tuple: (input_device_id, output_device_id)
    """
    input_id = os.getenv("AUDIO_INPUT_DEVICE")
    output_id = os.getenv("AUDIO_OUTPUT_DEVICE")
    
    return (
        int(input_id) if input_id else DEFAULT_INPUT_DEVICE,
        int(output_id) if output_id else DEFAULT_OUTPUT_DEVICE
    )


def validate_config() -> bool:
    """
    Validate configuration settings.
    
    Returns:
        bool: True if configuration is valid
    """
    errors = []
    
    # Validate sample rate
    if SAMPLE_RATE not in [44100, 48000, 96000]:
        errors.append(f"Invalid sample rate: {SAMPLE_RATE} Hz")
    
    # Validate buffer size
    if BUFFER_SIZE not in [256, 512, 1024, 2048]:
        errors.append(f"Invalid buffer size: {BUFFER_SIZE}")
    
    # Validate paths
    if not ENGINE_DIR.exists():
        errors.append(f"Engine directory not found: {ENGINE_DIR}")
    
    if not WEB_DIR.exists():
        errors.append(f"Web directory not found: {WEB_DIR}")
    
    if errors:
        print("Configuration Errors:")
        for error in errors:
            print(f"  - {error}")
        return False
    
    return True


def print_config():
    """Print current configuration for debugging."""
    print("=" * 60)
    print("กดจนหลอนTone - Configuration")
    print("=" * 60)
    print(f"Sample Rate: {SAMPLE_RATE} Hz")
    print(f"Buffer Size: {BUFFER_SIZE} samples")
    print(f"Latency: {LATENCY_MS:.2f} ms")
    print(f"Input Device: {DEFAULT_INPUT_DEVICE}")
    print(f"Output Device: {DEFAULT_OUTPUT_DEVICE}")
    print(f"Web Server: {WEB_HOST}:{WEB_PORT}")
    print(f"Log Level: {LOG_LEVEL}")
    print(f"Project Root: {PROJECT_ROOT}")
    print("=" * 60)


if __name__ == "__main__":
    print_config()
    print(f"\nConfiguration Valid: {validate_config()}")
