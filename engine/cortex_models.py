"""
Neural DSP Quad Cortex & Cortex Control Data Models.
Cloned and adapted from reverse-engineered Cortex Control XML layouts and Protobuf v2 schemas.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
import json

# ---------------------------------------------------------------------------
# Quad Cortex Scene Color Palette (Cloned from Cortex Control sceneColours)
# ---------------------------------------------------------------------------
SCENE_COLORS = [
    {"id": 0, "name": "Red", "hex": "#e74c3c", "badge": "A"},
    {"id": 1, "name": "Cyan", "hex": "#00bcd4", "badge": "B"},
    {"id": 2, "name": "Yellow", "hex": "#f1c40f", "badge": "C"},
    {"id": 3, "name": "Violet", "hex": "#9b59b6", "badge": "D"},
    {"id": 4, "name": "Green", "hex": "#2ecc71", "badge": "E"},
    {"id": 5, "name": "Blue", "hex": "#3498db", "badge": "F"},
    {"id": 6, "name": "Amber", "hex": "#e67e22", "badge": "G"},
    {"id": 7, "name": "Magenta", "hex": "#e91e63", "badge": "H"},
]

DEFAULT_SCENE_LABELS = [
    "Clean / Intro",
    "Verse Crunch",
    "Chorus Rhythm",
    "Solo / Lead",
    "Bridge",
    "Outro Ambient",
    "Acoustic / Warm",
    "Special FX",
]

@dataclass
class SceneDefinition:
    index: int  # 0 to 7 (A to H)
    label: str
    color_hex: str
    bypasses: Dict[str, bool] = field(default_factory=dict)  # block_name -> enabled
    param_overrides: Dict[str, Dict[str, float]] = field(default_factory=dict)  # block -> {param: value}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "badge": chr(65 + self.index),
            "label": self.label,
            "color": self.color_hex,
            "bypasses": self.bypasses,
            "param_overrides": self.param_overrides,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SceneDefinition":
        return cls(
            index=int(data.get("index", 0)),
            label=str(data.get("label", f"Scene {chr(65 + int(data.get('index', 0))) }")),
            color_hex=str(data.get("color", SCENE_COLORS[int(data.get("index", 0)) % 8]["hex"])),
            bypasses=data.get("bypasses", {}),
            param_overrides=data.get("param_overrides", {}),
        )


# ---------------------------------------------------------------------------
# Quad Cortex Multi-Scene Factory Presets
# ---------------------------------------------------------------------------
FACTORY_CORTEX_PRESETS = [
    {
        "id": "cortex_british_lead_100",
        "name": "British Lead 100",
        "author": "Neural DSP Cortex",
        "category": "Rock / Lead",
        "tempo": 120,
        "default_scene": 0,
        "base_settings": {
            "gate": {"enabled": True, "threshold": -52.0},
            "screamer": {"enabled": False, "drive": 0.25, "tone": 0.65, "level": 0.8},
            "amp": {"enabled": True, "gain": 0.65, "bass": 0.55, "mid": 0.6, "treble": 0.65, "presence": 0.6, "master": 0.75, "model": "J800"},
            "eq": {"enabled": True, "model_id": 1, "data": [0, 1, 0, 2, 1]},
            "cab": {"enabled": True, "tube": "EL34", "mic": "SM57", "center": 40, "distance": 15, "ir_name": "Marshall 1960A Greenback"},
            "mod": {"enabled": False, "model_id": 12, "rate": 0.4, "mix": 0.35, "depth": 0.5},
            "delay": {"enabled": False, "time": 0.38, "feedback": 0.35, "mix": 0.25},
            "reverb": {"enabled": True, "decay": 0.4, "mix": 0.18, "tone": 0.55},
        },
        "scenes": [
            {
                "index": 0, "label": "Clean Chime", "color": "#2ecc71",
                "bypasses": {"screamer": False, "mod": True, "delay": False, "reverb": True},
                "param_overrides": {"amp": {"gain": 0.25, "master": 0.85}, "mod": {"mix": 0.4}},
            },
            {
                "index": 1, "label": "Verse Crunch", "color": "#f1c40f",
                "bypasses": {"screamer": False, "mod": False, "delay": False, "reverb": True},
                "param_overrides": {"amp": {"gain": 0.55, "master": 0.75}},
            },
            {
                "index": 2, "label": "Chorus Heavy", "color": "#e67e22",
                "bypasses": {"screamer": True, "mod": False, "delay": False, "reverb": True},
                "param_overrides": {"amp": {"gain": 0.70, "master": 0.75}, "screamer": {"drive": 0.2, "level": 0.75}},
            },
            {
                "index": 3, "label": "Solo Boost Lead", "color": "#e74c3c",
                "bypasses": {"screamer": True, "mod": False, "delay": True, "reverb": True},
                "param_overrides": {"amp": {"gain": 0.80, "master": 0.85}, "screamer": {"drive": 0.35, "level": 0.85}, "delay": {"mix": 0.32, "feedback": 0.42}},
            },
            {
                "index": 4, "label": "Ambient Swell", "color": "#9b59b6",
                "bypasses": {"screamer": False, "mod": True, "delay": True, "reverb": True},
                "param_overrides": {"amp": {"gain": 0.30}, "reverb": {"decay": 0.85, "mix": 0.45}, "delay": {"mix": 0.45, "feedback": 0.65}},
            },
            {
                "index": 5, "label": "Octave Lead", "color": "#e91e63",
                "bypasses": {"screamer": True, "pitch": True, "mod": False, "delay": True, "reverb": True},
                "param_overrides": {"pitch": {"semitones": 12.0, "mix": 0.4}},
            },
            {
                "index": 6, "label": "Tight Rhythm", "color": "#3498db",
                "bypasses": {"screamer": True, "mod": False, "delay": False, "reverb": False},
                "param_overrides": {"gate": {"threshold_db": -45.0}, "amp": {"gain": 0.75}},
            },
            {
                "index": 7, "label": "Dry Direct", "color": "#95a5a6",
                "bypasses": {"screamer": False, "mod": False, "delay": False, "reverb": False},
                "param_overrides": {"amp": {"gain": 0.50}},
            },
        ],
    },
    {
        "id": "cortex_american_clean_twin",
        "name": "American Clean Twin",
        "author": "Neural DSP Cortex",
        "category": "Clean / Boutique",
        "tempo": 105,
        "default_scene": 0,
        "base_settings": {
            "gate": {"enabled": False, "threshold": -60.0},
            "screamer": {"enabled": False, "drive": 0.15, "tone": 0.55, "level": 0.65},
            "amp": {"enabled": True, "gain": 0.28, "bass": 0.5, "mid": 0.45, "treble": 0.7, "presence": 0.6, "master": 0.8, "model": "Twin"},
            "eq": {"enabled": False, "model_id": 1, "data": [0, 0, 0, 0, 0]},
            "cab": {"enabled": True, "tube": "6L6", "mic": "U87", "center": 50, "distance": 25, "ir_name": "Fender Twin 2x12 Jensen"},
            "mod": {"enabled": False, "model_id": 12, "rate": 0.35, "mix": 0.45, "depth": 0.6},
            "delay": {"enabled": False, "time": 0.42, "feedback": 0.3, "mix": 0.22},
            "reverb": {"enabled": True, "decay": 0.55, "mix": 0.28, "tone": 0.6},
        },
        "scenes": [
            {
                "index": 0, "label": "Studio Clean", "color": "#2ecc71",
                "bypasses": {"screamer": False, "mod": False, "delay": False, "reverb": True},
                "param_overrides": {"amp": {"gain": 0.22}},
            },
            {
                "index": 1, "label": "Analog Chorus", "color": "#00bcd4",
                "bypasses": {"screamer": False, "mod": True, "delay": False, "reverb": True},
                "param_overrides": {"mod": {"rate": 0.35, "mix": 0.55}},
            },
            {
                "index": 2, "label": "Texas Blues Breakup", "color": "#f1c40f",
                "bypasses": {"screamer": True, "mod": False, "delay": False, "reverb": True},
                "param_overrides": {"screamer": {"drive": 0.45, "tone": 0.6, "level": 0.75}, "amp": {"gain": 0.42}},
            },
            {
                "index": 3, "label": "Warm Slapback", "color": "#e67e22",
                "bypasses": {"screamer": False, "mod": False, "delay": True, "reverb": True},
                "param_overrides": {"delay": {"time_sec": 0.12, "feedback": 0.15, "mix": 0.35}},
            },
            {
                "index": 4, "label": "Cathedral Clouds", "color": "#9b59b6",
                "bypasses": {"screamer": False, "mod": True, "delay": True, "reverb": True},
                "param_overrides": {"reverb": {"decay": 0.85, "mix": 0.48}, "delay": {"time_sec": 0.5, "feedback": 0.6, "mix": 0.4}},
            },
            {
                "index": 5, "label": "Rotary Organ", "color": "#3498db",
                "bypasses": {"screamer": False, "mod": True, "delay": False, "reverb": True},
                "param_overrides": {"mod": {"model_id": 11, "rate": 0.75, "mix": 0.65}},
            },
            {
                "index": 6, "label": "Lo-Fi Vinyl", "color": "#e91e63",
                "bypasses": {"screamer": False, "mod": True, "delay": False, "reverb": True},
                "param_overrides": {"mod": {"model_id": 19, "rate": 0.6, "depth": 0.7, "mix": 0.8}},
            },
            {
                "index": 7, "label": "Spring Reverb Only", "color": "#95a5a6",
                "bypasses": {"screamer": False, "mod": False, "delay": False, "reverb": True},
                "param_overrides": {"reverb": {"reverb_type": "spring", "decay": 0.65, "mix": 0.4}},
            },
        ],
    },
    {
        "id": "cortex_high_gain_rectifier",
        "name": "High Gain Rectifier",
        "author": "Neural DSP Cortex",
        "category": "Metal / Modern",
        "tempo": 135,
        "default_scene": 0,
        "base_settings": {
            "gate": {"enabled": True, "threshold": -48.0},
            "screamer": {"enabled": True, "drive": 0.15, "tone": 0.7, "level": 0.85},
            "amp": {"enabled": True, "gain": 0.78, "bass": 0.5, "mid": 0.42, "treble": 0.68, "presence": 0.68, "master": 0.7, "model": "5150"},
            "eq": {"enabled": True, "model_id": 2, "data": [3, 1, -2, 3, 2]},
            "cab": {"enabled": True, "tube": "6L6", "mic": "MD421", "center": 35, "distance": 10, "ir_name": "Mesa Rectifier 4x12 Slant"},
            "mod": {"enabled": False, "model_id": 12, "rate": 0.5, "mix": 0.3, "depth": 0.5},
            "delay": {"enabled": False, "time": 0.34, "feedback": 0.35, "mix": 0.25},
            "reverb": {"enabled": True, "decay": 0.35, "mix": 0.15, "tone": 0.5},
        },
        "scenes": [
            {
                "index": 0, "label": "Djent Rhythm", "color": "#e74c3c",
                "bypasses": {"screamer": True, "mod": False, "delay": False, "reverb": False},
                "param_overrides": {"gate": {"threshold_db": -42.0}, "amp": {"gain": 0.72}},
            },
            {
                "index": 1, "label": "Liquid Solo", "color": "#00bcd4",
                "bypasses": {"screamer": True, "mod": False, "delay": True, "reverb": True},
                "param_overrides": {"amp": {"gain": 0.85, "master": 0.8}, "delay": {"time_sec": 0.42, "mix": 0.35, "feedback": 0.45}},
            },
            {
                "index": 2, "label": "Clean Intro", "color": "#2ecc71",
                "bypasses": {"screamer": False, "mod": True, "delay": False, "reverb": True},
                "param_overrides": {"amp": {"gain": 0.22, "master": 0.85}, "mod": {"mix": 0.45}},
            },
            {
                "index": 3, "label": "Octave Drop Solo", "color": "#9b59b6",
                "bypasses": {"screamer": True, "pitch": True, "delay": True, "reverb": True},
                "param_overrides": {"pitch": {"semitones": -12.0, "mix": 0.45}},
            },
            {
                "index": 4, "label": "Brutal Scoop", "color": "#f1c40f",
                "bypasses": {"screamer": True, "mod": False, "delay": False, "reverb": False},
                "param_overrides": {"eq": {"data": [5, -2, -6, 4, 3]}},
            },
            {
                "index": 5, "label": "Ambient Lead", "color": "#e67e22",
                "bypasses": {"screamer": True, "delay": True, "reverb": True},
                "param_overrides": {"delay": {"mix": 0.45, "feedback": 0.65}, "reverb": {"decay": 0.75, "mix": 0.35}},
            },
            {
                "index": 6, "label": "Heavy Staccato", "color": "#e91e63",
                "bypasses": {"screamer": True, "delay": False, "reverb": False},
                "param_overrides": {"gate": {"threshold_db": -38.0}},
            },
            {
                "index": 7, "label": "Bypass Mute", "color": "#95a5a6",
                "bypasses": {"screamer": False, "amp": False, "cab": False, "delay": False, "reverb": False},
            },
        ],
    },
]
