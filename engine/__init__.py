"""
กดจนหลอนTone - Audio Engine Package

Core DSP and audio processing modules for guitar rig simulation.
"""

from .audio import AudioEngine, freq_to_note
from .dsp import (
    GuitarSignalChain,
    NoiseGate,
    Overdrive,
    AmpHead,
    CabinetSimulator,
    Delay,
    Reverb
)
from .presets import get_all_presets, save_preset, init_db
from .kemper_importer import list_installed_kemper_packs, read_rigs_from_pack
from .tone3000_importer import list_tone3000_presets

__all__ = [
    # Audio Engine
    'AudioEngine',
    'freq_to_note',
    # DSP Modules
    'GuitarSignalChain',
    'NoiseGate',
    'Overdrive',
    'AmpHead',
    'CabinetSimulator',
    'Delay',
    'Reverb',
    # Preset Management
    'get_all_presets',
    'save_preset',
    'init_db',
    # Importers
    'list_installed_kemper_packs',
    'read_rigs_from_pack',
    'list_tone3000_presets',
]

__version__ = '1.0.0'
