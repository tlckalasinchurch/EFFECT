"""
กดจนหลอนTone — Unified Master Signature Bank Builder.

Harvests, normalizes, and synthesizes flagship presets from all 4 ecosystems:
1. KEMPER Profiler (.rigpack / .kipr) -> Extracts SysEx parameters + builds Auto-Morph A/B slots
2. Neural DSP Quad Cortex (.cortex.json / Factory 8-Scene rigs) -> 8-Scene instant switching
3. MOOER GE150 (.mo / 9-Block Chains) -> Complete 9-block pedalboard chains
4. TONE3000 / NAM Real Neural Captures + Real Studio IRs (2,048-sample WAVs)
"""

from typing import Any, Dict, List
from engine.presets import save_preset, get_all_presets


MASTER_SIGNATURE_PRESETS: List[Dict[str, Any]] = [
    {
        "id": "master_qc_plini_ethereal",
        "name": "★ [QC Clone] Plini Ethereal Crystal & Lead",
        "category": "Master Signature · Quad Cortex",
        "author": "กดจนหลอนTone Master",
        "source_brand": "Neural DSP Quad Cortex",
        "cloned_features": ["8-Scene Override", "Ducking Delay/Reverb", "EL34 + SM57 3D Mic", "Parallel Clean Path"],
        "bpm": 118,
        "morph_a": {
            "amp_gain": 0.28, "amp_master": 0.80,
            "screamer_drive": 0.15, "screamer_level": 0.70,
            "delay_mix": 0.20, "reverb_mix": 0.28,
            "screamer_enabled": 0.0, "delay_enabled": 1.0,
        },
        "morph_b": {
            "amp_gain": 0.78, "amp_master": 0.88,
            "screamer_drive": 0.45, "screamer_level": 0.85,
            "delay_mix": 0.42, "reverb_mix": 0.45,
            "screamer_enabled": 1.0, "delay_enabled": 1.0,
        },
        "settings": {
            "gate": {"enabled": True, "threshold": -56.0, "release_ms": 45.0, "hold_ms": 40.0, "range_db": -65.0},
            "pitch": {"enabled": False, "semitones": 0.0, "glide": 0.0, "cents": 0.0, "mix": 1.0},
            "screamer": {"enabled": True, "drive": 0.30, "tone": 0.65, "level": 0.80},
            "amp": {"enabled": True, "gain": 0.62, "bass": 0.52, "mid": 0.58, "treble": 0.68, "presence": 0.66, "master": 0.78, "model": "Plexi", "bright": True},
            "eq": {"enabled": True, "model_id": 5, "bands": [85.0, 1.5, 2.0, 3.0, 2.5, 14500.0]},
            "cab": {"enabled": True, "ir_name": "Marshall 1960A Greenback", "lowcut": 75.0, "highcut": 16500.0, "mix": 1.0, "level": 1.05, "tube": "EL34", "mic": "SM57", "center": 42.0, "distance": 18.0},
            "mod": {"enabled": True, "model_id": 12, "rate": 0.35, "mix": 0.28, "tone": 0.60, "depth": 0.45},
            "delay": {"enabled": True, "time": 0.38, "feedback": 0.42, "mix": 0.32, "ducking": True, "duck_depth": 0.65},
            "reverb": {"enabled": True, "decay": 0.72, "mix": 0.35, "tone": 0.65, "type": "cathedral", "ducking": True, "duck_depth": 0.55},
        },
    },
    {
        "id": "master_kemper_recto_morph",
        "name": "★ [KEMPER Clone] Dual Rectifier Red (Morph A↔B)",
        "category": "Master Signature · KEMPER",
        "author": "กดจนหลอนTone Master",
        "source_brand": "Kemper Profiler Stage",
        "cloned_features": ["Continuous Rig Morphing A↔B", "5-Band Studio Parametric EQ", "Real Mesa 4x12 V30 IR", "Tight Noise Gate"],
        "bpm": 140,
        "morph_a": {
            "amp_gain": 0.62, "amp_master": 0.72,
            "screamer_drive": 0.15, "screamer_level": 0.80,
            "delay_mix": 0.05, "reverb_mix": 0.12,
            "screamer_enabled": 1.0, "delay_enabled": 0.0,
        },
        "morph_b": {
            "amp_gain": 0.88, "amp_master": 0.85,
            "screamer_drive": 0.40, "screamer_level": 0.90,
            "delay_mix": 0.34, "reverb_mix": 0.28,
            "screamer_enabled": 1.0, "delay_enabled": 1.0,
        },
        "settings": {
            "gate": {"enabled": True, "threshold": -46.0, "release_ms": 30.0, "hold_ms": 25.0, "range_db": -75.0},
            "pitch": {"enabled": False, "semitones": 0.0, "glide": 0.0, "cents": 0.0, "mix": 1.0},
            "screamer": {"enabled": True, "drive": 0.15, "tone": 0.72, "level": 0.88},
            "amp": {"enabled": True, "gain": 0.78, "bass": 0.55, "mid": 0.46, "treble": 0.68, "presence": 0.68, "master": 0.74, "model": "5150", "bright": True},
            "eq": {"enabled": True, "model_id": 5, "bands": [95.0, 2.0, -2.5, 3.5, 2.0, 12500.0]},
            "cab": {"enabled": True, "ir_name": "Mesa Rectifier 4x12 Slant", "lowcut": 85.0, "highcut": 13500.0, "mix": 1.0, "level": 1.1, "tube": "6L6", "mic": "MD421", "center": 35.0, "distance": 12.0},
            "mod": {"enabled": False, "model_id": 13, "rate": 0.30, "mix": 0.20, "tone": 0.50, "depth": 0.40},
            "delay": {"enabled": False, "time": 0.32, "feedback": 0.35, "mix": 0.25, "ducking": True, "duck_depth": 0.60},
            "reverb": {"enabled": True, "decay": 0.35, "mix": 0.14, "tone": 0.50, "type": "room", "ducking": True, "duck_depth": 0.50},
        },
    },
    {
        "id": "master_mooer_ge150_808_boutique",
        "name": "★ [MOOER GE150 Clone] 808 Texas Boutique Overdrive",
        "category": "Master Signature · MOOER GE150",
        "author": "กดจนหลอนTone Master",
        "source_brand": "MOOER GE150 Pro",
        "cloned_features": ["9-Block GE150 Chain", "Tube Screamer Asymmetric Clipping", "MOOER G-5 Graphic EQ", "6V6 Tube Cab Sim"],
        "bpm": 108,
        "morph_a": {
            "amp_gain": 0.38, "amp_master": 0.76,
            "screamer_drive": 0.35, "screamer_level": 0.72,
            "delay_mix": 0.15, "reverb_mix": 0.22,
            "screamer_enabled": 0.0, "delay_enabled": 0.0,
        },
        "morph_b": {
            "amp_gain": 0.68, "amp_master": 0.84,
            "screamer_drive": 0.65, "screamer_level": 0.82,
            "delay_mix": 0.32, "reverb_mix": 0.30,
            "screamer_enabled": 1.0, "delay_enabled": 1.0,
        },
        "settings": {
            "gate": {"enabled": True, "threshold": -58.0, "release_ms": 60.0, "hold_ms": 50.0, "range_db": -60.0},
            "pitch": {"enabled": False, "semitones": 0.0, "glide": 0.0, "cents": 0.0, "mix": 1.0},
            "screamer": {"enabled": True, "drive": 0.58, "tone": 0.64, "level": 0.78},
            "amp": {"enabled": True, "gain": 0.48, "bass": 0.58, "mid": 0.62, "treble": 0.64, "presence": 0.58, "master": 0.78, "model": "Plexi", "bright": False},
            "eq": {"enabled": True, "model_id": 1, "bands": [1.5, 2.0, 3.2, 1.8, 1.0, 0.0]},
            "cab": {"enabled": True, "ir_name": "Celestion V30 4x12", "lowcut": 65.0, "highcut": 15000.0, "mix": 1.0, "level": 1.0, "tube": "6V6", "mic": "R121", "center": 55.0, "distance": 22.0},
            "mod": {"enabled": False, "model_id": 6, "rate": 0.45, "mix": 0.35, "tone": 0.55, "depth": 0.50},
            "delay": {"enabled": True, "time": 0.28, "feedback": 0.28, "mix": 0.22, "ducking": False, "duck_depth": 0.50},
            "reverb": {"enabled": True, "decay": 0.50, "mix": 0.25, "tone": 0.58, "type": "spring", "ducking": False, "duck_depth": 0.45},
        },
    },
    {
        "id": "master_nam_fender_crystal_chorus",
        "name": "★ [TONE3000 + QC Clone] 1970 Bassman Lush Tri-Chorus",
        "category": "Master Signature · Clean / Ambient",
        "author": "กดจนหลอนTone Master",
        "source_brand": "TONE3000 + Quad Cortex",
        "cloned_features": ["Real 1970 Fender Bassman 2x15 IR", "Tri-Chorus Modulation", "Parallel Clean Blend", "Cathedral Shimmer Verb"],
        "bpm": 96,
        "morph_a": {
            "amp_gain": 0.22, "amp_master": 0.82,
            "screamer_drive": 0.15, "screamer_level": 0.68,
            "delay_mix": 0.25, "reverb_mix": 0.35,
            "screamer_enabled": 0.0, "delay_enabled": 1.0,
        },
        "morph_b": {
            "amp_gain": 0.48, "amp_master": 0.86,
            "screamer_drive": 0.42, "screamer_level": 0.78,
            "delay_mix": 0.48, "reverb_mix": 0.58,
            "screamer_enabled": 1.0, "delay_enabled": 1.0,
        },
        "settings": {
            "gate": {"enabled": False, "threshold": -65.0, "release_ms": 80.0, "hold_ms": 60.0, "range_db": -60.0},
            "pitch": {"enabled": False, "semitones": 0.0, "glide": 0.0, "cents": 0.0, "mix": 1.0},
            "screamer": {"enabled": False, "drive": 0.20, "tone": 0.55, "level": 0.70},
            "amp": {"enabled": True, "gain": 0.24, "bass": 0.52, "mid": 0.46, "treble": 0.70, "presence": 0.64, "master": 0.82, "model": "Twin", "bright": True},
            "eq": {"enabled": True, "model_id": 5, "bands": [45.0, 2.0, -1.0, 1.5, 3.5, 18000.0]},
            "cab": {"enabled": True, "ir_name": "Fender Twin 2x12 Jensen", "lowcut": 45.0, "highcut": 18000.0, "mix": 1.0, "level": 1.05, "tube": "6L6", "mic": "U87", "center": 48.0, "distance": 28.0},
            "mod": {"enabled": True, "model_id": 13, "rate": 0.32, "mix": 0.48, "tone": 0.65, "depth": 0.62},
            "delay": {"enabled": True, "time": 0.46, "feedback": 0.48, "mix": 0.35, "ducking": True, "duck_depth": 0.55},
            "reverb": {"enabled": True, "decay": 0.82, "mix": 0.42, "tone": 0.70, "type": "cathedral", "ducking": True, "duck_depth": 0.50},
        },
    },
    {
        "id": "master_lofi_synth_experimental",
        "name": "★ [MOOER + Cortex Clone] Cyber Lo-Fi Bitcrush & Octave",
        "category": "Master Signature · Experimental",
        "author": "กดจนหลอนTone Master",
        "source_brand": "MOOER GE150 + Quad Cortex",
        "cloned_features": ["Lo-Fi Bitcrusher & Decimator (Mod #19)", "Pitch Shifter +12st Octave", "KT88 High-Headroom Tube", "Ducking Delay"],
        "bpm": 128,
        "morph_a": {
            "amp_gain": 0.45, "amp_master": 0.75,
            "screamer_drive": 0.30, "screamer_level": 0.75,
            "delay_mix": 0.20, "reverb_mix": 0.25,
            "screamer_enabled": 0.0, "delay_enabled": 1.0,
        },
        "morph_b": {
            "amp_gain": 0.82, "amp_master": 0.85,
            "screamer_drive": 0.68, "screamer_level": 0.85,
            "delay_mix": 0.45, "reverb_mix": 0.48,
            "screamer_enabled": 1.0, "delay_enabled": 1.0,
        },
        "settings": {
            "gate": {"enabled": True, "threshold": -52.0, "release_ms": 40.0, "hold_ms": 35.0, "range_db": -65.0},
            "pitch": {"enabled": True, "semitones": 12.0, "glide": 15.0, "cents": 0.0, "mix": 0.35},
            "screamer": {"enabled": True, "drive": 0.50, "tone": 0.68, "level": 0.80},
            "amp": {"enabled": True, "gain": 0.60, "bass": 0.54, "mid": 0.58, "treble": 0.65, "presence": 0.62, "master": 0.76, "model": "5150", "bright": False},
            "eq": {"enabled": True, "model_id": 2, "bands": [2.0, 1.0, -1.5, 2.5, 3.0, 0.0]},
            "cab": {"enabled": True, "ir_name": "Mesa Rectifier 4x12 Slant", "lowcut": 70.0, "highcut": 14000.0, "mix": 1.0, "level": 1.0, "tube": "KT88", "mic": "SM57", "center": 50.0, "distance": 15.0},
            "mod": {"enabled": True, "model_id": 19, "rate": 0.35, "mix": 0.42, "tone": 0.55, "depth": 0.48},
            "delay": {"enabled": True, "time": 0.35, "feedback": 0.45, "mix": 0.30, "ducking": True, "duck_depth": 0.60},
            "reverb": {"enabled": True, "decay": 0.65, "mix": 0.30, "tone": 0.60, "type": "hall", "ducking": False, "duck_depth": 0.50},
        },
    },
    {
        "id": "master_ozzy_neural_24bit",
        "name": "★ [OZZY × NEURAL 24-Bit] Crazy Train / Bark at the Moon Oversized Stack",
        "category": "Master Signature · Ozzy / Neural 24-Bit",
        "author": "กดจนหลอนTone Master",
        "source_brand": "Neural DSP Archetype + Hot-Rodded British JCM800",
        "cloned_features": ["24-Bit 44.1kHz Touch-Dynamic Voicing", "Ozzy Stereo Micro-Pitch Doubler", "SD-1 Tight Mid Push", "Oversized 4x12 Greenback/V30 IR"],
        "bpm": 138,
        "morph_a": {
            "amp_gain": 0.54, "amp_master": 0.76,
            "screamer_drive": 0.18, "screamer_level": 0.78,
            "delay_mix": 0.12, "reverb_mix": 0.18,
            "screamer_enabled": 1.0, "delay_enabled": 0.0,
        },
        "morph_b": {
            "amp_gain": 0.84, "amp_master": 0.86,
            "screamer_drive": 0.42, "screamer_level": 0.90,
            "delay_mix": 0.34, "reverb_mix": 0.30,
            "screamer_enabled": 1.0, "delay_enabled": 1.0,
        },
        "settings": {
            "gate": {"enabled": True, "threshold": -52.0, "release_ms": 35.0, "hold_ms": 28.0, "range_db": -70.0},
            "pitch": {"enabled": False, "semitones": 0.0, "glide": 0.0, "cents": 0.0, "mix": 1.0},
            "screamer": {"enabled": True, "drive": 0.28, "tone": 0.68, "level": 0.84},
            "amp": {"enabled": True, "gain": 0.72, "bass": 0.54, "mid": 0.66, "treble": 0.68, "presence": 0.66, "master": 0.78, "model": "Ozzy_Neural", "bright": True},
            "eq": {"enabled": True, "model_id": 5, "bands": [80.0, 1.5, 2.8, 3.2, 2.0, 14500.0]},
            "cab": {"enabled": True, "ir_name": "Marshall 1960A Greenback", "lowcut": 75.0, "highcut": 14800.0, "mix": 1.0, "level": 1.08, "tube": "EL34", "mic": "SM57", "center": 44.0, "distance": 16.0},
            "mod": {"enabled": True, "model_id": 12, "rate": 0.28, "mix": 0.26, "tone": 0.62, "depth": 0.38},
            "delay": {"enabled": True, "time": 0.326, "feedback": 0.34, "mix": 0.24, "ducking": True, "duck_depth": 0.62},
            "reverb": {"enabled": True, "decay": 0.48, "mix": 0.22, "tone": 0.58, "type": "plate", "ducking": True, "duck_depth": 0.50},
        },
    },
    {
        "id": "master_neural_oversized_a2_ir",
        "name": "★ [NEURAL OVERSIZED 24-Bit] Archetype Touch-Dynamic 44.1kHz Lead & Chug",
        "category": "Master Signature · Ozzy / Neural 24-Bit",
        "author": "กดจนหลอนTone Master",
        "source_brand": "Neural DSP Quad Cortex + NAM A2 + Custom IR",
        "cloned_features": ["24-Bit / 44.1kHz Natural Touch Cleanup", "Oversized 4x12 V30 + R121 Studio IR", "EL34/KT88 Dynamic Tube Sag", "Constant-Dry Stereo Delay"],
        "bpm": 124,
        "morph_a": {
            "amp_gain": 0.42, "amp_master": 0.78,
            "screamer_drive": 0.12, "screamer_level": 0.76,
            "delay_mix": 0.16, "reverb_mix": 0.20,
            "screamer_enabled": 0.0, "delay_enabled": 0.0,
        },
        "morph_b": {
            "amp_gain": 0.86, "amp_master": 0.88,
            "screamer_drive": 0.36, "screamer_level": 0.88,
            "delay_mix": 0.36, "reverb_mix": 0.32,
            "screamer_enabled": 1.0, "delay_enabled": 1.0,
        },
        "settings": {
            "gate": {"enabled": True, "threshold": -50.0, "release_ms": 30.0, "hold_ms": 25.0, "range_db": -72.0},
            "pitch": {"enabled": False, "semitones": 0.0, "glide": 0.0, "cents": 0.0, "mix": 1.0},
            "screamer": {"enabled": True, "drive": 0.22, "tone": 0.70, "level": 0.86},
            "amp": {"enabled": True, "gain": 0.68, "bass": 0.52, "mid": 0.58, "treble": 0.68, "presence": 0.65, "master": 0.80, "model": "Ozzy_Neural", "bright": True},
            "eq": {"enabled": True, "model_id": 5, "bands": [85.0, 2.0, -1.2, 3.4, 2.5, 14200.0]},
            "cab": {"enabled": True, "ir_name": "Mesa Rectifier 4x12 Slant", "lowcut": 80.0, "highcut": 14200.0, "mix": 1.0, "level": 1.10, "tube": "EL34", "mic": "SM57", "center": 40.0, "distance": 14.0},
            "mod": {"enabled": False, "model_id": 13, "rate": 0.30, "mix": 0.24, "tone": 0.60, "depth": 0.40},
            "delay": {"enabled": True, "time": 0.36, "feedback": 0.38, "mix": 0.28, "ducking": True, "duck_depth": 0.65},
            "reverb": {"enabled": True, "decay": 0.52, "mix": 0.24, "tone": 0.60, "type": "hall", "ducking": True, "duck_depth": 0.52},
        },
    },
]


def ensure_master_signature_presets() -> List[Dict[str, Any]]:
    """
    Ensures all Master Signature presets are installed into presets.db so the user
    owns a self-contained bank of cloned flagship tones and features.
    """
    from engine import rigdoc
    existing_map = {p["id"]: p["settings"] for p in get_all_presets()}
    for preset in MASTER_SIGNATURE_PRESETS:
        canonical = rigdoc.from_v1(preset["settings"]).to_v1()
        if existing_map.get(preset["id"]) != canonical:
            save_preset(
                preset_id=preset["id"],
                name=preset["name"],
                category=preset["category"],
                author=preset["author"],
                settings=canonical,
            )
    return MASTER_SIGNATURE_PRESETS


def generate_auto_morph_slots(chain) -> Dict[str, Dict[str, float]]:
    """
    Kemper-style Auto-Morph Generator:
    Creates a Rhythm/Clean Slot A (Heel) and a Lead/Boosted Slot B (Toe)
    matching MorphController.DEFAULTS schema.
    """
    base_gain = float(getattr(chain.amp, "gain", 0.55))
    base_master = float(getattr(chain.amp, "master", 0.70))
    base_drive = float(getattr(chain.screamer, "drive", 0.35))
    base_slevel = float(getattr(chain.screamer, "level", 0.75))
    base_dly = float(getattr(chain.delay, "mix", 0.20))
    base_rev = float(getattr(chain.reverb, "mix", 0.20))

    slot_a = {
        "amp_gain": round(max(0.15, min(0.95, base_gain * 0.68)), 3),
        "amp_master": round(max(0.20, min(0.95, base_master * 0.94)), 3),
        "screamer_drive": round(max(0.10, min(0.95, base_drive * 0.65)), 3),
        "screamer_level": round(max(0.20, min(0.95, base_slevel * 0.92)), 3),
        "delay_mix": round(max(0.0, min(0.85, base_dly * 0.60)), 3),
        "reverb_mix": round(max(0.05, min(0.85, base_rev * 0.80)), 3),
        "screamer_enabled": 0.0,
        "delay_enabled": 0.0 if base_dly < 0.20 else 1.0,
    }
    slot_b = {
        "amp_gain": round(max(0.25, min(0.98, base_gain + (1.0 - base_gain) * 0.52)), 3),
        "amp_master": round(max(0.25, min(0.98, base_master + 0.12)), 3),
        "screamer_drive": round(max(0.25, min(0.95, max(base_drive, 0.30) + 0.25)), 3),
        "screamer_level": round(max(0.30, min(0.98, max(base_slevel, 0.70) + 0.12)), 3),
        "delay_mix": round(max(0.18, min(0.85, max(base_dly, 0.18) + 0.18)), 3),
        "reverb_mix": round(max(0.18, min(0.85, max(base_rev, 0.18) + 0.14)), 3),
        "screamer_enabled": 1.0,
        "delay_enabled": 1.0,
    }
    return {"slot_a": slot_a, "slot_b": slot_b}


def apply_morph_pair(morph_mgr, slot_a: Dict[str, float], slot_b: Dict[str, float]) -> Dict[str, Any]:
    """Directly persists both Slot A and Slot B into MorphController."""
    import json
    morph_mgr._validate_snapshot(slot_a)
    morph_mgr._validate_snapshot(slot_b)
    with morph_mgr._lock:
        with morph_mgr._session() as conn:
            for slot_label, snap in (("A", slot_a), ("B", slot_b)):
                conn.execute(
                    "INSERT INTO morph_slots(slot, settings_json, captured_at) VALUES (?, ?, CURRENT_TIMESTAMP) "
                    "ON CONFLICT(slot) DO UPDATE SET settings_json=excluded.settings_json, captured_at=excluded.captured_at",
                    (slot_label, json.dumps(snap, allow_nan=False, sort_keys=True)),
                )
        morph_mgr.slot_a = dict(slot_a)
        morph_mgr.slot_b = dict(slot_b)
        morph_mgr.captured["A"] = True
        morph_mgr.captured["B"] = True
        morph_mgr.morph_pos = 0.0
        return morph_mgr.get_state()
