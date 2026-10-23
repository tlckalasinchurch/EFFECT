"""
MOOER GE150 Preset Parser, Serializer, and Rig Converter.
Implements the exact JSON schema V1.3.0 discovered during reverse engineering of MOOER Studio.
"""

import json
import logging
from typing import Dict, Any, Optional, Tuple
from engine.mooer_models import (
    MODULE_CATALOG,
    CAB_TUBES,
    CAB_MICS,
    AMP_MODELS,
    CAB_MODELS,
    DS_MODELS,
    EQ_MODELS,
    MOD_MODELS,
    DELAY_MODELS,
    REVERB_MODELS,
)

logger = logging.getLogger(__name__)

CURRENT_SCHEMA = "V1.3.0"
CURRENT_APP = "GE150 Edit"
CURRENT_DEVICE = "MOOER GE150"


def parse_mo_preset(raw_json_or_dict: str | dict) -> Dict[str, Any]:
    """
    Parse and validate a .mo preset format string or dict.
    Returns normalized preset dictionary.
    """
    if isinstance(raw_json_or_dict, (str, bytes)):
        data = json.loads(raw_json_or_dict)
    else:
        data = raw_json_or_dict

    if not isinstance(data, dict):
        raise ValueError("Invalid .mo preset: root must be a JSON object")

    preset_name = data.get("preset_name", "Untitled")
    device = data.get("device", CURRENT_DEVICE)
    schema = data.get("schema", CURRENT_SCHEMA)
    effect_modules = data.get("effectModule", {})
    exp = data.get("Exp", {})

    return {
        "device": device,
        "device_version": data.get("device_version", CURRENT_SCHEMA),
        "app": data.get("app", CURRENT_APP),
        "app_version": data.get("app_version", "V1.3.8"),
        "schema": schema,
        "preset_name": str(preset_name).strip(),
        "Exp": {
            "MODULE_CTRL": int(exp.get("MODULE_CTRL", 0)),
            "PARA_CTRL": int(exp.get("PARA_CTRL", 0)),
            "FUN_SWITCH": int(exp.get("FUN_SWITCH", 0)),
            "VOL_SWITCH": int(exp.get("VOL_SWITCH", 1)),
            "VOL_MIN": int(exp.get("VOL_MIN", 0)),
            "VOL_MAX": int(exp.get("VOL_MAX", 100)),
        },
        "effectModule": effect_modules,
    }


def export_mo_preset(preset_name: str, chain_state: Dict[str, Any]) -> str:
    """
    Serializes a workstation chain state into the exact .mo JSON format
    compatible with MOOER Studio for GE150 and GE150 hardware.
    """
    # Build effectModule dictionary
    modules = {}

    # 1. FX
    fx_state = chain_state.get("fx", {})
    modules["FX"] = {
        "SWITCH": 1 if fx_state.get("enabled", False) else 0,
        "TYPE": int(fx_state.get("model_id", 1)),
        "Data": [
            int(fx_state.get("p1", 50)),
            int(fx_state.get("p2", 50)),
            int(fx_state.get("p3", 50)),
            int(fx_state.get("p4", 50)),
        ],
    }

    # 2. DS / OD
    ds_state = chain_state.get("screamer", {})
    modules["DS"] = {
        "SWITCH": 1 if ds_state.get("enabled", False) else 0,
        "TYPE": int(ds_state.get("model_id", 2)),  # default 808
        "Data": [
            int(ds_state.get("level", 0.7) * 100),
            int(ds_state.get("tone", 0.5) * 100),
            int(ds_state.get("drive", 0.5) * 100),
        ],
    }

    # 3. AMP
    amp_state = chain_state.get("amp", {})
    modules["AMP"] = {
        "SWITCH": 1 if amp_state.get("enabled", True) else 0,
        "TYPE": int(amp_state.get("model_id", 7)),  # default J800
        "Data": [
            int(amp_state.get("gain", 0.65) * 100),
            int(amp_state.get("bass", 0.55) * 100),
            int(amp_state.get("mid", 0.5) * 100),
            int(amp_state.get("treble", 0.6) * 100),
            int(amp_state.get("presence", 0.6) * 100),
            int(amp_state.get("master", 0.7) * 100),
        ],
    }

    # 4. CAB
    cab_state = chain_state.get("cab", {})
    tube_name = cab_state.get("tube", "EL34")
    tube_idx = CAB_TUBES.index(tube_name) if tube_name in CAB_TUBES else 1
    mic_name = cab_state.get("mic", "SM57")
    mic_idx = CAB_MICS.index(mic_name) if mic_name in CAB_MICS else 0
    center_val = int(cab_state.get("center", 50))
    dist_val = int(cab_state.get("distance", 20))

    modules["CAB"] = {
        "SWITCH": 1 if cab_state.get("enabled", True) else 0,
        "TYPE": int(cab_state.get("model_id", 6)),  # 1960 412
        "Data": [tube_idx, mic_idx, center_val, dist_val],
    }

    # 5. NS GATE
    gate_state = chain_state.get("gate", {})
    # convert -60..0 dB to 0..100
    thresh_db = gate_state.get("threshold", -55.0)
    gate_val = int(max(0.0, min(100.0, (thresh_db + 70.0) / 70.0 * 100.0)))
    modules["NS"] = {
        "SWITCH": 1 if gate_state.get("enabled", True) else 0,
        "TYPE": 1,  # NOISE KILLER
        "Data": [gate_val],
    }

    # 6. EQ
    eq_state = chain_state.get("eq", {})
    modules["EQ"] = {
        "SWITCH": 1 if eq_state.get("enabled", False) else 0,
        "TYPE": int(eq_state.get("model_id", 1)),
        "Data": eq_state.get("data", [0, 0, 0, 0, 0]),
    }

    # 7. MOD
    mod_state = chain_state.get("mod", {})
    pitch_state = chain_state.get("pitch", {})
    if pitch_state.get("enabled", False):
        modules["MOD"] = {
            "SWITCH": 1,
            "TYPE": 9,  # PITCH SHIFT
            "Data": [
                int(pitch_state.get("semitones", 0.0)),
                int(pitch_state.get("mix", 0.5) * 100),
                50,
            ],
        }
    else:
        modules["MOD"] = {
            "SWITCH": 1 if mod_state.get("enabled", False) else 0,
            "TYPE": int(mod_state.get("model_id", 12)),  # ANA-CHORUS
            "Data": mod_state.get("data", [50, 50, 50, 50]),
        }

    # 8. DELAY
    delay_state = chain_state.get("delay", {})
    delay_ms = int(delay_state.get("time", 0.35) * 1000)
    delay_fb = int(delay_state.get("feedback", 0.35) * 100)
    delay_mix = int(delay_state.get("mix", 0.25) * 100)
    modules["DLY"] = {
        "SWITCH": 1 if delay_state.get("enabled", False) else 0,
        "TYPE": 1,  # DIGITAL
        "Data": [delay_mix, delay_fb, delay_ms, 0],
    }

    # 9. REVERB
    rev_state = chain_state.get("reverb", {})
    rev_decay = int(rev_state.get("decay", 0.5) * 100)
    rev_mix = int(rev_state.get("mix", 0.2) * 100)
    rev_tone = int(rev_state.get("tone", 0.5) * 100)
    modules["REV"] = {
        "SWITCH": 1 if rev_state.get("enabled", False) else 0,
        "TYPE": 1,  # ROOM
        "Data": [0, rev_mix, rev_decay, rev_tone],
    }

    doc = {
        "device": CURRENT_DEVICE,
        "device_version": CURRENT_SCHEMA,
        "app": CURRENT_APP,
        "app_version": "V1.3.8",
        "schema": CURRENT_SCHEMA,
        "preset_name": preset_name[:16],
        "Exp": {
            "MODULE_CTRL": 0,
            "PARA_CTRL": 0,
            "FUN_SWITCH": 0,
            "VOL_SWITCH": 1,
            "VOL_MIN": 0,
            "VOL_MAX": 100,
        },
        "effectModule": modules,
    }

    return json.dumps(doc, indent=2, ensure_ascii=False)


def mo_to_workstation_preset(mo_doc: Dict[str, Any]) -> Dict[str, Any]:
    """
    Converts a parsed .mo dictionary into the workstation's native preset dictionary.
    """
    name = mo_doc.get("preset_name", "MOOER Preset")
    modules = mo_doc.get("effectModule", {})

    settings = {
        "gate": {"enabled": False, "threshold": -55.0},
        "screamer": {"enabled": False, "drive": 0.5, "tone": 0.5, "level": 0.7, "model_id": 2},
        "amp": {"enabled": True, "gain": 0.65, "bass": 0.5, "mid": 0.5, "treble": 0.6, "presence": 0.6, "master": 0.7, "model_id": 7},
        "cab": {"enabled": True, "tube": "EL34", "mic": "SM57", "center": 50, "distance": 20, "model_id": 6},
        "eq": {"enabled": False, "model_id": 1, "data": [0, 0, 0, 0, 0]},
        "mod": {"enabled": False, "model_id": 12, "rate": 0.5, "mix": 0.5, "tone": 0.5, "depth": 0.5},
        "pitch": {"enabled": False, "semitones": 0.0, "mix": 0.5},
        "delay": {"enabled": False, "time": 0.35, "feedback": 0.3, "mix": 0.25},
        "reverb": {"enabled": False, "decay": 0.5, "mix": 0.2, "tone": 0.5},
    }

    # NS GATE
    ns = modules.get("NS", {})
    if ns:
        settings["gate"]["enabled"] = bool(ns.get("SWITCH", 0))
        data = ns.get("Data", [50])
        val = data[0] if len(data) > 0 else 50
        # Map 0..100 to -70..0 dB
        settings["gate"]["threshold"] = -70.0 + (val / 100.0) * 70.0

    # DS / OD
    ds = modules.get("DS", {})
    if ds:
        settings["screamer"]["enabled"] = bool(ds.get("SWITCH", 0))
        settings["screamer"]["model_id"] = int(ds.get("TYPE", 2))
        data = ds.get("Data", [70, 50, 50])
        if len(data) >= 3:
            settings["screamer"]["level"] = data[0] / 100.0
            settings["screamer"]["tone"] = data[1] / 100.0
            settings["screamer"]["drive"] = data[2] / 100.0

    # AMP
    amp = modules.get("AMP", {})
    if amp:
        settings["amp"]["enabled"] = bool(amp.get("SWITCH", 1))
        model_id = int(amp.get("TYPE", 7))
        settings["amp"]["model_id"] = model_id
        # Look up Amp name
        amp_info = next((a for a in AMP_MODELS if a["id"] == model_id), None)
        if amp_info:
            settings["amp"]["model_name"] = amp_info["name"]
            settings["amp"]["model"] = amp_info["category"]
        data = amp.get("Data", [65, 50, 50, 60, 60, 70])
        if len(data) >= 6:
            settings["amp"]["gain"] = data[0] / 100.0
            settings["amp"]["bass"] = data[1] / 100.0
            settings["amp"]["mid"] = data[2] / 100.0
            settings["amp"]["treble"] = data[3] / 100.0
            settings["amp"]["presence"] = data[4] / 100.0
            settings["amp"]["master"] = data[5] / 100.0

    # CAB
    cab = modules.get("CAB", {})
    if cab:
        settings["cab"]["enabled"] = bool(cab.get("SWITCH", 1))
        model_id = int(cab.get("TYPE", 6))
        settings["cab"]["model_id"] = model_id
        cab_info = next((c for c in CAB_MODELS if c["id"] == model_id), None)
        if cab_info:
            settings["cab"]["cab_name"] = cab_info["name"]
            settings["cab"]["ir_name"] = cab_info["desc"]

        data = cab.get("Data", [1, 0, 50, 20])
        if len(data) >= 4:
            tube_idx = min(len(CAB_TUBES) - 1, max(0, int(data[0])))
            mic_idx = min(len(CAB_MICS) - 1, max(0, int(data[1])))
            settings["cab"]["tube"] = CAB_TUBES[tube_idx]
            settings["cab"]["mic"] = CAB_MICS[mic_idx]
            settings["cab"]["center"] = float(data[2])
            settings["cab"]["distance"] = float(data[3])

    # EQ
    eq = modules.get("EQ", {})
    if eq:
        settings["eq"]["enabled"] = bool(eq.get("SWITCH", 0))
        settings["eq"]["model_id"] = int(eq.get("TYPE", 1))
        settings["eq"]["data"] = eq.get("Data", [0, 0, 0, 0, 0])

    # MOD
    mod = modules.get("MOD", {})
    if mod:
        is_on = bool(mod.get("SWITCH", 0))
        m_type = int(mod.get("TYPE", 12))
        data = mod.get("Data", [50, 50, 50, 50])
        if m_type == 9:  # Pitch Shift
            settings["pitch"]["enabled"] = is_on
            if len(data) >= 2:
                settings["pitch"]["semitones"] = float(data[0])
                settings["pitch"]["mix"] = float(data[1]) / 100.0
        elif m_type == 10:  # Detune
            settings["pitch"]["enabled"] = is_on
            if len(data) >= 2:
                settings["pitch"]["semitones"] = float(data[0]) / 100.0  # cents
                settings["pitch"]["mix"] = float(data[1]) / 100.0
        else:
            settings["mod"]["enabled"] = is_on
            settings["mod"]["model_id"] = m_type
            if len(data) >= 4:
                settings["mod"]["rate"] = data[0] / 100.0
                settings["mod"]["mix"] = data[1] / 100.0
                settings["mod"]["tone"] = data[2] / 100.0
                settings["mod"]["depth"] = data[3] / 100.0

    # DELAY
    dly = modules.get("DLY", {})
    if dly:
        settings["delay"]["enabled"] = bool(dly.get("SWITCH", 0))
        data = dly.get("Data", [25, 35, 350, 0])
        if len(data) >= 3:
            settings["delay"]["mix"] = data[0] / 100.0
            settings["delay"]["feedback"] = data[1] / 100.0
            settings["delay"]["time"] = max(0.04, min(2.5, data[2] / 1000.0))

    # REVERB
    rev = modules.get("REV", {})
    if rev:
        settings["reverb"]["enabled"] = bool(rev.get("SWITCH", 0))
        data = rev.get("Data", [0, 20, 50, 50])
        if len(data) >= 4:
            settings["reverb"]["mix"] = data[1] / 100.0
            settings["reverb"]["decay"] = data[2] / 100.0
            settings["reverb"]["tone"] = data[3] / 100.0

    category = "MOOER GE150"
    if "Clean" in settings["amp"].get("model", ""):
        category = "Clean"
    elif "Lead" in settings["amp"].get("model", "") or "High Gain" in settings["amp"].get("model", ""):
        category = "Lead / Metal"
    elif "Crunch" in settings["amp"].get("model", ""):
        category = "Crunch"

    return {
        "id": f"mooer_{name.lower().replace(' ', '_')[:24]}",
        "name": name,
        "category": category,
        "author": "MOOER GE150",
        "settings": settings,
        "source": "mooer_ge150",
    }


# Factory Presets Cloned from MOOER GE150 Factory Banks
FACTORY_GE150_PRESETS = [
    {
        "device": CURRENT_DEVICE,
        "schema": CURRENT_SCHEMA,
        "preset_name": "01A 65 US DX",
        "effectModule": {
            "FX": {"SWITCH": 0, "TYPE": 7, "Data": [30, 40, 50, 80]},
            "DS": {"SWITCH": 1, "TYPE": 2, "Data": [70, 55, 35]},  # 808
            "AMP": {"SWITCH": 1, "TYPE": 1, "Data": [45, 55, 50, 65, 60, 75]},  # 65 US DX
            "CAB": {"SWITCH": 1, "TYPE": 1, "Data": [3, 0, 45, 15]},  # 6L6 + SM57
            "NS": {"SWITCH": 1, "TYPE": 1, "Data": [40]},
            "EQ": {"SWITCH": 0, "TYPE": 1, "Data": [0, 0, 0, 0, 0]},
            "MOD": {"SWITCH": 0, "TYPE": 12, "Data": [40, 50, 50, 60]},
            "DLY": {"SWITCH": 0, "TYPE": 1, "Data": [25, 30, 360, 0]},
            "REV": {"SWITCH": 1, "TYPE": 1, "Data": [0, 25, 45, 50]},  # Room
        },
    },
    {
        "device": CURRENT_DEVICE,
        "schema": CURRENT_SCHEMA,
        "preset_name": "01B J800 ROCK",
        "effectModule": {
            "FX": {"SWITCH": 0, "TYPE": 7, "Data": [50, 50, 50, 50]},
            "DS": {"SWITCH": 1, "TYPE": 3, "Data": [80, 50, 20]},  # Pure Boost
            "AMP": {"SWITCH": 1, "TYPE": 7, "Data": [68, 55, 65, 60, 65, 70]},  # J800
            "CAB": {"SWITCH": 1, "TYPE": 6, "Data": [1, 0, 50, 10]},  # EL34 + SM57 + 1960
            "NS": {"SWITCH": 1, "TYPE": 1, "Data": [55]},
            "EQ": {"SWITCH": 0, "TYPE": 1, "Data": [0, 0, 0, 0, 0]},
            "MOD": {"SWITCH": 0, "TYPE": 12, "Data": [50, 50, 50, 50]},
            "DLY": {"SWITCH": 1, "TYPE": 1, "Data": [25, 35, 420, 0]},
            "REV": {"SWITCH": 1, "TYPE": 2, "Data": [0, 20, 50, 50]},
        },
    },
    {
        "device": CURRENT_DEVICE,
        "schema": CURRENT_SCHEMA,
        "preset_name": "01C TRI REC LEAD",
        "effectModule": {
            "FX": {"SWITCH": 0, "TYPE": 7, "Data": [50, 50, 50, 50]},
            "DS": {"SWITCH": 1, "TYPE": 2, "Data": [85, 60, 15]},  # 808 Tightener
            "AMP": {"SWITCH": 1, "TYPE": 21, "Data": [75, 50, 45, 65, 70, 68]},  # TRI REC DS
            "CAB": {"SWITCH": 1, "TYPE": 10, "Data": [3, 4, 40, 15]},  # 6L6 + MD421 + REC 412
            "NS": {"SWITCH": 1, "TYPE": 1, "Data": [62]},
            "EQ": {"SWITCH": 1, "TYPE": 1, "Data": [2, -1, -2, 3, 2]},  # V-Curve
            "MOD": {"SWITCH": 0, "TYPE": 12, "Data": [50, 50, 50, 50]},
            "DLY": {"SWITCH": 1, "TYPE": 1, "Data": [30, 40, 480, 0]},
            "REV": {"SWITCH": 1, "TYPE": 4, "Data": [0, 25, 55, 60]},
        },
    },
    {
        "device": CURRENT_DEVICE,
        "schema": CURRENT_SCHEMA,
        "preset_name": "01D JAZZ CHORUS",
        "effectModule": {
            "FX": {"SWITCH": 1, "TYPE": 7, "Data": [25, 40, 60, 80]},  # Yellow Comp
            "DS": {"SWITCH": 0, "TYPE": 1, "Data": [50, 50, 50]},
            "AMP": {"SWITCH": 1, "TYPE": 32, "Data": [35, 50, 50, 65, 55, 80]},  # JAZZ 120
            "CAB": {"SWITCH": 1, "TYPE": 16, "Data": [0, 2, 60, 25]},  # OFF + U87 + JAZZ 212
            "NS": {"SWITCH": 1, "TYPE": 1, "Data": [35]},
            "EQ": {"SWITCH": 0, "TYPE": 1, "Data": [0, 0, 0, 0, 0]},
            "MOD": {"SWITCH": 1, "TYPE": 12, "Data": [35, 65, 55, 70]},  # ANA-CHORUS
            "DLY": {"SWITCH": 1, "TYPE": 1, "Data": [30, 45, 520, 0]},
            "REV": {"SWITCH": 1, "TYPE": 3, "Data": [20, 35, 65, 55]},  # CHURCH
        },
    },
    {
        "device": CURRENT_DEVICE,
        "schema": CURRENT_SCHEMA,
        "preset_name": "02A PV 5050 DJENT",
        "effectModule": {
            "FX": {"SWITCH": 0, "TYPE": 7, "Data": [50, 50, 50, 50]},
            "DS": {"SWITCH": 1, "TYPE": 18, "Data": [80, 65, 30]},  # TIGHT DS
            "AMP": {"SWITCH": 1, "TYPE": 37, "Data": [70, 50, 60, 60, 65, 70]},  # PV 5050 DS
            "CAB": {"SWITCH": 1, "TYPE": 19, "Data": [3, 0, 45, 10]},  # 6L6 + SM57 + PV 412
            "NS": {"SWITCH": 1, "TYPE": 1, "Data": [68]},
            "EQ": {"SWITCH": 1, "TYPE": 2, "Data": [2, 0, 2, 3, 1]},  # HM EQ
            "MOD": {"SWITCH": 0, "TYPE": 9, "Data": [-12, 50, 50]},
            "DLY": {"SWITCH": 0, "TYPE": 1, "Data": [20, 25, 320, 0]},
            "REV": {"SWITCH": 1, "TYPE": 1, "Data": [0, 15, 35, 50]},
        },
    },
]


def get_all_mooer_presets() -> list:
    """Returns factory presets and any custom downloaded .mo presets in custom_mooer/."""
    presets = list(FACTORY_GE150_PRESETS)
    try:
        import config
        import glob
        import os
        custom_dir = str(getattr(config, "CUSTOM_MOOER_DIR", ""))
        if custom_dir and os.path.isdir(custom_dir):
            for p in sorted(glob.glob(os.path.join(custom_dir, "*.mo"))):
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        raw = json.load(f)
                    parsed = parse_mo_preset(raw)
                    parsed["_file_path"] = p
                    presets.append(parsed)
                except Exception as e:
                    logger.warning(f"Error loading custom mooer preset {p}: {e}")
    except Exception as e:
        logger.warning(f"Failed to scan custom_mooer: {e}")
    return presets
