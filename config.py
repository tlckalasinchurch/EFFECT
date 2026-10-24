"""
Configuration management for กดจนหลอนTone

Centralized configuration for audio settings, paths, and application behavior.
"""

import os
import sys

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, 'reconfigure'):
        try:
            _stream.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass
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
USER_LIBRARY_PATH = PROJECT_ROOT / "user_library.json"
EXPORT_DIR = PROJECT_ROOT / "exports"
CUSTOM_RIGS_DIR = PROJECT_ROOT / "custom_rigs"
CUSTOM_MOOER_DIR = PROJECT_ROOT / "custom_mooer"
CUSTOM_CORTEX_DIR = PROJECT_ROOT / "custom_cortex"
CUSTOM_IR_DIR = PROJECT_ROOT / "custom_irs"

for _d in (EXPORT_DIR, CUSTOM_RIGS_DIR, CUSTOM_MOOER_DIR, CUSTOM_CORTEX_DIR, CUSTOM_IR_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# Audio Settings File (Persistent user configuration)
SETTINGS_FILE = PROJECT_ROOT / "audio_settings.json"

# Audio Configuration Defaults
SAMPLE_RATE = int(os.getenv("SAMPLE_RATE", "48000"))
BUFFER_SIZE = int(os.getenv("BUFFER_SIZE", "128"))
BLOCK_SIZE = BUFFER_SIZE

# Line 6 UX1 Default Devices (WASAPI).
#
# These used to be hard-coded to 17/15.  PortAudio device indices are not
# stable: they shift whenever Windows adds or removes an endpoint, and on this
# machine 17 is now a SteelSeries virtual input while 15 has no outputs at all.
# Leaving them unset lets AudioEngine.detect_ux1_pair() choose the real UX1.
def _env_device(name):
    raw = os.getenv(name)
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


DEFAULT_INPUT_DEVICE = _env_device("AUDIO_INPUT_DEVICE")
DEFAULT_OUTPUT_DEVICE = _env_device("AUDIO_OUTPUT_DEVICE")
DEFAULT_INPUT_NAME = None
DEFAULT_OUTPUT_NAME = None

def load_audio_settings():
    """Load persistent audio settings from json if available."""
    global SAMPLE_RATE, BUFFER_SIZE, BLOCK_SIZE, DEFAULT_INPUT_DEVICE, DEFAULT_OUTPUT_DEVICE, LATENCY_MS
    global DEFAULT_INPUT_NAME, DEFAULT_OUTPUT_NAME
    if SETTINGS_FILE.exists():
        try:
            import json
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if "sample_rate" in data and int(data["sample_rate"]) > 0:
                SAMPLE_RATE = int(data["sample_rate"])
            if "buffer_size" in data and int(data["buffer_size"]) > 0:
                BUFFER_SIZE = int(data["buffer_size"])
                BLOCK_SIZE = BUFFER_SIZE
            if "input_device" in data and data["input_device"] is not None:
                DEFAULT_INPUT_DEVICE = int(data["input_device"])
            if "output_device" in data and data["output_device"] is not None:
                DEFAULT_OUTPUT_DEVICE = int(data["output_device"])
            DEFAULT_INPUT_NAME = data.get("input_device_name")
            DEFAULT_OUTPUT_NAME = data.get("output_device_name")
        except Exception:
            pass
    LATENCY_MS = (BUFFER_SIZE / SAMPLE_RATE) * 1000

def save_audio_settings(sample_rate=None, buffer_size=None, input_device=None, output_device=None,
                        input_name=None, output_name=None):
    """Persist audio settings to disk.

    Names are stored alongside the PortAudio indices because the indices are
    not stable across device changes; the name is what the user recognises.
    """
    global SAMPLE_RATE, BUFFER_SIZE, BLOCK_SIZE, DEFAULT_INPUT_DEVICE, DEFAULT_OUTPUT_DEVICE, LATENCY_MS
    global DEFAULT_INPUT_NAME, DEFAULT_OUTPUT_NAME
    if sample_rate is not None and int(sample_rate) > 0:
        SAMPLE_RATE = int(sample_rate)
    if buffer_size is not None and int(buffer_size) > 0:
        BUFFER_SIZE = int(buffer_size)
        BLOCK_SIZE = BUFFER_SIZE
    if input_device is not None:
        try:
            DEFAULT_INPUT_DEVICE = int(input_device)
        except (ValueError, TypeError):
            pass
    if output_device is not None:
        try:
            DEFAULT_OUTPUT_DEVICE = int(output_device)
        except (ValueError, TypeError):
            pass
    if input_name is not None:
        DEFAULT_INPUT_NAME = str(input_name)
    if output_name is not None:
        DEFAULT_OUTPUT_NAME = str(output_name)

    LATENCY_MS = (BUFFER_SIZE / SAMPLE_RATE) * 1000

    import json
    data = {
        "sample_rate": SAMPLE_RATE,
        "buffer_size": BUFFER_SIZE,
        "input_device": DEFAULT_INPUT_DEVICE,
        "output_device": DEFAULT_OUTPUT_DEVICE,
        "input_device_name": DEFAULT_INPUT_NAME,
        "output_device_name": DEFAULT_OUTPUT_NAME
    }
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass

load_audio_settings()

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

# Cached TONE3000 model payloads.  Preset metadata points to these files so a
# loaded tone can be restored after the application is restarted.
T3K_CACHE_DIR = PROJECT_ROOT / "tone3000_cache"

# Cabinet IR limits (shared by the DSP layer and the upload endpoint)
IR_MAX_SECONDS = 1.0  # Longest IR kept; longer files are truncated


def ir_max_samples(sample_rate):
    """IR length cap in samples at ``sample_rate``."""
    return int(IR_MAX_SECONDS * sample_rate)


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
    if SAMPLE_RATE not in [44100, 48000, 88200, 96000]:
        errors.append(f"Invalid sample rate: {SAMPLE_RATE} Hz")
    
    # Validate buffer size
    if BUFFER_SIZE not in [64, 128, 256, 512, 1024, 2048]:
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
