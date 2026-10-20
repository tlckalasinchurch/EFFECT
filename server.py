from fastapi import FastAPI, HTTPException, UploadFile, File, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel
import html
import os
import re
import logging
import threading
import webbrowser

import config
import t3k_fastapi as t3k
from setup_logging import get_logger

from engine.audio import AudioEngine
from engine.presets import get_all_presets, save_preset
from urllib.parse import quote
from engine import user_library
from engine.rigpack_export import export_rigpack
from engine.kemper_importer import (
    list_installed_kemper_packs,
    read_rigs_from_pack,
    search_packs,
    list_categories,
    get_rig_params,
    get_rig,
    get_rig_for_export,
    find_pack_path,
)
from engine.tone3000_importer import list_tone3000_presets, get_real_cab_ir, get_nam_chain

# Setup logger
logger = get_logger(__name__)

app = FastAPI(title="กดจนหลอนTone")
engine = AudioEngine()

WEB_DIR = config.WEB_DIR

# Guards engine state that the realtime audio thread reads while an
# HTTP handler writes it.
ENGINE_STATE_LOCK = threading.RLock()

# A cab IR swap must not race the audio callback that reads cab.ir_data / cab.zi.
_CAB_IR_LOCK = threading.RLock()

class ParamUpdate(BaseModel):
    section: str  # gate, screamer, amp, cab, delay, reverb, tuner
    param: str
    value: float | bool | str

class PresetLoad(BaseModel):
    preset_id: str

class PresetSave(BaseModel):
    id: str
    name: str
    category: str
    author: str

@app.get("/api/status")
def get_status():
    return engine.get_state()

@app.get("/api/devices")
def get_devices():
    return {
        "devices": engine.get_device_list(),
        "selected_in": engine.input_device,
        "selected_out": engine.output_device,
        "is_running": engine.is_running
    }

@app.post("/api/start")
def start_engine(data: dict = None):
    data = data or {}
    in_id = data.get("input_id", data.get("input_device"))
    out_id = data.get("output_id", data.get("output_device"))
    success, msg = engine.start(input_id=in_id, output_id=out_id)
    return {"success": success, "message": msg, "state": engine.get_state()}

@app.post("/api/stop")
def stop_engine():
    engine.stop()
    return {"success": True, "message": "Engine stopped"}

@app.post("/api/tuner/toggle")
def toggle_tuner(data: dict):
    active = data.get("active", False)
    engine.tuner_active = active
    return {"tuner_active": engine.tuner_active}

@app.post("/api/parameter")
def update_parameter(req: ParamUpdate):
    sec = req.section
    p = req.param
    val = req.value
    
    chain = engine.chain
    if sec == "master":
        if p == "volume": chain.master_volume = float(val)
    elif sec == "input":
        if p == "trim":
            chain.input_trim_db = max(-24.0, min(24.0, float(val)))
    elif sec == "gate":
        if p == "enabled": chain.noise_gate.enabled = bool(val)
        elif p == "threshold": chain.noise_gate.threshold_db = float(val)
        elif p == "hold": chain.noise_gate.hold_ms = float(val)
        elif p == "range": chain.noise_gate.range_db = float(val)
        elif p == "release":
            chain.noise_gate.release_ms = float(val)
            chain.noise_gate.set_timing(chain.noise_gate.attack_ms, chain.noise_gate.release_ms)
    elif sec == "screamer":
        if p == "enabled": chain.screamer.enabled = bool(val)
        elif p == "drive": chain.screamer.drive = float(val)
        elif p == "tone": 
            chain.screamer.tone = float(val)
            chain.screamer._update_filter()
        elif p == "level": chain.screamer.level = float(val)
    elif sec == "amp":
        if p == "enabled": chain.amp.enabled = bool(val)
        elif p == "gain": chain.amp.gain = float(val)
        elif p == "bass": chain.amp.bass = float(val)
        elif p == "mid": chain.amp.mid = float(val)
        elif p == "treble": chain.amp.treble = float(val)
        elif p == "presence": chain.amp.presence = float(val)
        elif p == "master": chain.amp.master = float(val)
        elif p in ("model", "tone_stack"): chain.amp.model = str(val)
        elif p == "bright": chain.amp.bright = bool(val)
    elif sec == "cab":
        if p == "enabled": chain.cab.enabled = bool(val)
        elif p == "level": chain.cab.level = float(val)
        elif p == "lowcut": chain.cab.set_cutoffs(lowcut_hz=float(val))
        elif p == "highcut": chain.cab.set_cutoffs(highcut_hz=float(val))
        elif p == "mix": chain.cab.mix = max(0.0, min(1.0, float(val)))
        elif p == "ir_name":
            with _CAB_IR_LOCK:
                chain.cab.select_cab(str(val))
    elif sec == "delay":
        if p == "enabled": chain.delay.enabled = bool(val)
        elif p == "time": chain.delay.time_sec = float(val)
        elif p == "feedback": chain.delay.feedback = float(val)
        elif p == "mix": chain.delay.mix = float(val)
    elif sec == "reverb":
        if p == "enabled": chain.reverb.enabled = bool(val)
        elif p == "decay": chain.reverb.decay = float(val)
        elif p == "mix": chain.reverb.mix = float(val)
        elif p == "tone": chain.reverb.tone = float(val)
        elif p == "type": chain.reverb.reverb_type = str(val)
    elif sec == "pitch":
        if p == "enabled": chain.pitch_shifter.enabled = bool(val)
        elif p == "semitones": chain.pitch_shifter.set_semitones(float(val))
        elif p == "cents": chain.pitch_shifter.cents = float(val)
        elif p == "glide": chain.pitch_shifter.set_glide(float(val))
        elif p == "mix": chain.pitch_shifter.mix = float(val)
    elif sec == "nam":
        global _NAM_QUALITY
        if p == "quality" and str(val) in ("lite", "full"):
            _NAM_QUALITY = str(val)
        elif p == "enabled" and chain.nam is not None:
            chain.nam.enabled = bool(val)
        elif p == "input_gain" and chain.nam is not None:
            chain.nam.set_input_gain_db(float(val))

    return {"success": True, "state": engine.get_state()}


@app.get("/api/presets")
def list_presets():
    return {"presets": get_all_presets()}

@app.post("/api/preset/load")
def load_preset(req: PresetLoad):
    presets = get_all_presets()
    target = next((p for p in presets if p["id"] == req.preset_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Preset not found")
    engine.chain.nam = None  # built-in presets use the DSP amp
        
    s = target["settings"]
    chain = engine.chain
    
    # Apply gate
    chain.noise_gate.enabled = s["gate"].get("enabled", True)
    chain.noise_gate.threshold_db = s["gate"].get("threshold", -55.0)
    chain.noise_gate.hold_ms = s["gate"].get("hold", s["gate"].get("hold_ms", 50.0))
    chain.noise_gate.release_ms = s["gate"].get("release", s["gate"].get("release_ms", 50.0))
    chain.noise_gate.range_db = s["gate"].get("range", s["gate"].get("range_db", -60.0))
    chain.noise_gate.set_timing(chain.noise_gate.attack_ms, chain.noise_gate.release_ms)
    
    # Apply screamer
    chain.screamer.enabled = s["screamer"].get("enabled", False)
    chain.screamer.drive = s["screamer"].get("drive", 0.4)
    chain.screamer.tone = s["screamer"].get("tone", 0.6)
    chain.screamer.level = s["screamer"].get("level", 0.7)
    chain.screamer._update_filter()
    
    # Apply amp
    chain.amp.enabled = s["amp"].get("enabled", True)
    chain.amp.gain = s["amp"].get("gain", 0.6)
    chain.amp.bass = s["amp"].get("bass", 0.5)
    chain.amp.mid = s["amp"].get("mid", 0.5)
    chain.amp.treble = s["amp"].get("treble", 0.5)
    chain.amp.presence = s["amp"].get("presence", 0.5)
    chain.amp.master = s["amp"].get("master", 0.7)
    chain.amp.model = s["amp"].get("model", "5150")
    
    # Apply cab
    chain.cab.enabled = s["cab"].get("enabled", True)
    chain.cab.select_cab(s["cab"].get("ir_name", "Celestion V30 4x12"))
    chain.cab.set_cutoffs(
        lowcut_hz=s["cab"].get("lowcut", 20.0),
        highcut_hz=s["cab"].get("highcut", 20000.0),
    )
    chain.cab.mix = s["cab"].get("mix", 1.0)
    chain.cab.level = s["cab"].get("level", 1.0)
    
    # Apply delay
    chain.delay.enabled = s["delay"].get("enabled", False)
    chain.delay.time_sec = s["delay"].get("time", 0.35)
    chain.delay.feedback = s["delay"].get("feedback", 0.35)
    chain.delay.mix = s["delay"].get("mix", 0.25)
    
    # Apply reverb
    chain.reverb.enabled = s["reverb"].get("enabled", False)
    chain.reverb.decay = s["reverb"].get("decay", 0.5)
    chain.reverb.mix = s["reverb"].get("mix", 0.2)
    chain.reverb.tone = s["reverb"].get("tone", 0.5)
    chain.reverb.reverb_type = s["reverb"].get("type", "plate")

    # Apply pitch (older presets have no pitch section)
    pitch = s.get("pitch") or {}
    chain.pitch_shifter.enabled = bool(pitch.get("enabled", False))
    chain.pitch_shifter.cents = float(pitch.get("cents", 0.0))
    chain.pitch_shifter.mix = float(pitch.get("mix", 1.0))
    chain.pitch_shifter.set_glide(float(pitch.get("glide", 0.0)))
    chain.pitch_shifter.set_semitones(float(pitch.get("semitones", 0.0)))

    # TONE3000 presets carry a reference to an app-local cached model. Older
    # presets do not have this metadata and continue to use the DSP amp path.
    t3k_meta = s.get("_t3k")
    if isinstance(t3k_meta, dict):
        try:
            chain.nam = _restore_cached_t3k(t3k_meta, chain)
        except (OSError, ValueError, KeyError) as exc:
            logger.warning("Could not restore cached TONE3000 model for %s: %s", req.preset_id, exc)
            raise HTTPException(
                status_code=409,
                detail="พรีเซ็ตนี้ต้องใช้ไฟล์ NAM ในเครื่อง แต่ไฟล์ cache หายหรืออ่านไม่ได้ — "
                       "เลือกโหลดเสียงนี้จาก TONE3000 ใหม่อีกครั้ง",
            ) from exc
    
    return {"success": True, "loaded_preset": target, "state": engine.get_state()}

@app.post("/api/preset/save")
def create_preset(req: PresetSave):
    curr_state = engine.get_state()["chain"]
    # Preserve the source model when saving/duplicating an active TONE3000
    # sound instead of silently converting it to the DSP amp.
    last_load = globals().get("_T3K_STATE", {}).get("last_load") or {}
    if engine.chain.nam is not None and last_load.get("tone_id"):
        curr_state["_t3k"] = _t3k_metadata(last_load)
    save_preset(req.id, req.name, req.category, req.author, curr_state)
    return {"success": True, "message": "Preset saved"}

class KemperRigLoad(BaseModel):
    name: str
    author: str = "Kemper"
    pack_path: str | None = None
    rig_id: int | None = None

@app.get("/api/kemper/categories")
def kemper_categories():
    """Distinct instrument categories (Guitar / Bass / Acoustic) with counts."""
    return {"categories": list_categories()}

@app.get("/api/kemper/search")
def kemper_search(q: str = "", category: str | None = None, limit: int = 100,
                  include_amp: bool = False,
                  gain_min: float | None = None, gain_max: float | None = None):
    """
    Search every installed rig pack.

    `include_amp` also decodes each rig's SysEx payload so the source amp,
    brand, model and cabinet name match the query. That costs one decode per
    rig, so it is opt-in.
    """
    limit = max(1, min(int(limit), 2000))
    hits = search_packs(q, category=category, limit=limit, include_amp=include_amp,
                        gain_min=gain_min, gain_max=gain_max)
    return {"query": q, "category": category, "count": len(hits), "results": hits}

class FavouriteReq(BaseModel):
    key: str
    value: bool

class TagsReq(BaseModel):
    key: str
    tags: list[str]

@app.get("/api/library/user")
def user_library_entries():
    """Favourites and tags, keyed by '<pack filename>::<rig id>'."""
    return {"entries": user_library.get_all()}

@app.post("/api/library/favourite")
def user_library_favourite(req: FavouriteReq):
    try:
        return {"success": True, "entry": user_library.set_favourite(req.key, req.value)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@app.post("/api/library/tags")
def user_library_tags(req: TagsReq):
    try:
        return {"success": True, "entry": user_library.set_tags(req.key, req.tags)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

class ExportReq(BaseModel):
    favourites: bool = False
    tag: str | None = None
    name: str | None = None

@app.post("/api/library/export")
def user_library_export(req: ExportReq):
    """Write the starred and/or tagged Kemper rigs to exports/<name>.rigpack."""
    wanted = (req.tag or "").strip().lower()
    if not req.favourites and not wanted:
        raise HTTPException(status_code=400, detail="Choose favourites and/or a tag")
    rigs, skipped = [], 0
    for key, entry in sorted(user_library.get_all().items()):
        if req.favourites and not entry.get("favourite"):
            continue
        if wanted and wanted not in entry.get("tags", []):
            continue
        filename, _, rid = key.partition("::")
        rig = get_rig_for_export(filename, int(rid))
        if rig:
            rigs.append(rig)
        else:
            skipped += 1  # pack no longer installed
    if not rigs:
        raise HTTPException(status_code=404, detail="No matching rigs to export")
    label = " + ".join(filter(None, ["Favourites" if req.favourites else "", f"#{wanted}" if wanted else ""]))
    name = (req.name or "").strip() or f"My Rigs - {label}"
    try:
        path = export_rigpack(rigs, str(config.EXPORT_DIR), name)
    except (ValueError, RuntimeError, OSError) as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    fname = os.path.basename(path)
    return {"success": True, "filename": fname, "path": path, "count": len(rigs),
            "skipped": skipped, "download_url": f"/api/library/exports/{quote(fname)}"}

@app.get("/api/library/exports/{filename}")
def user_library_download(filename: str):
    path = os.path.join(str(config.EXPORT_DIR), filename)
    if os.path.basename(filename) != filename or not filename.endswith(".rigpack") \
            or not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="Export not found")
    return FileResponse(path, filename=filename, media_type="application/octet-stream")

@app.get("/api/library/user/rigs")
def user_library_rigs(favourites: bool = False, tag: str | None = None):
    """Rigs the user starred and/or tagged, resolved back to full rig rows."""
    wanted = (tag or "").strip().lower()
    rigs = []
    for key, entry in user_library.get_all().items():
        if favourites and not entry.get("favourite"):
            continue
        if wanted and wanted not in entry.get("tags", []):
            continue
        filename, _, rid = key.partition("::")
        pack_path = find_pack_path(filename)
        rig = get_rig(pack_path, int(rid)) if pack_path else None
        if rig:  # pack uninstalled or renumbered: skip rather than show a wrong rig
            rigs.append(rig)
    return {"count": len(rigs), "rigs": rigs}

@app.post("/api/kemper/load")
def load_kemper_rig(req: KemperRigLoad):
    name_lower = req.name.lower()
    chain = engine.chain
    chain.nam = None  # a Kemper rig is played through the DSP amp, not a neural model

    # Intelligently configure DSP engine according to Kemper profile character
    if any(k in name_lower for k in ["clean", "jazz", "acoustic", "twin", "sparkle"]):
        chain.amp.model = "Clean"
        chain.amp.gain = 0.25
        chain.amp.bass = 0.5
        chain.amp.mid = 0.5
        chain.amp.treble = 0.65
        chain.amp.presence = 0.6
        chain.amp.master = 0.8
        chain.screamer.enabled = False
        chain.cab.enabled = True
        chain.cab.select_cab("Fender Twin 2x12 Jensen")
        chain.delay.enabled = False
        chain.reverb.enabled = True
        chain.reverb.decay = 0.35
        chain.reverb.mix = 0.2
        category = "Clean"
    elif any(k in name_lower for k in ["crunch", "plexi", "jcm", "rock", "blues", "ac30", "overdrive", "marshall"]):
        chain.amp.model = "Plexi"
        chain.amp.gain = 0.55
        chain.amp.bass = 0.6
        chain.amp.mid = 0.55
        chain.amp.treble = 0.55
        chain.amp.presence = 0.5
        chain.amp.master = 0.75
        chain.screamer.enabled = True
        chain.screamer.drive = 0.25
        chain.screamer.tone = 0.6
        chain.screamer.level = 0.7
        chain.cab.enabled = True
        chain.cab.select_cab("Marshall 1960A Greenback")
        chain.delay.enabled = False
        chain.reverb.enabled = True
        chain.reverb.decay = 0.3
        chain.reverb.mix = 0.15
        category = "Crunch / Rock"
    elif any(k in name_lower for k in ["lead", "solo", "delay", "space", "ambient"]):
        chain.amp.model = "5150"
        chain.amp.gain = 0.75
        chain.amp.bass = 0.5
        chain.amp.mid = 0.6
        chain.amp.treble = 0.65
        chain.amp.presence = 0.6
        chain.amp.master = 0.7
        chain.screamer.enabled = True
        chain.screamer.drive = 0.3
        chain.screamer.tone = 0.7
        chain.screamer.level = 0.8
        chain.cab.enabled = True
        chain.cab.select_cab("Mesa Rectifier 4x12 Slant")
        chain.delay.enabled = True
        chain.delay.time_sec = 0.38
        chain.delay.feedback = 0.35
        chain.delay.mix = 0.25
        chain.reverb.enabled = True
        chain.reverb.decay = 0.55
        chain.reverb.mix = 0.25
        category = "Lead / Solo"
    else:  # High Gain Metal / Modern default
        chain.amp.model = "5150"
        chain.amp.gain = 0.8
        chain.amp.bass = 0.6
        chain.amp.mid = 0.45
        chain.amp.treble = 0.6
        chain.amp.presence = 0.65
        chain.amp.master = 0.7
        chain.screamer.enabled = True
        chain.screamer.drive = 0.2
        chain.screamer.tone = 0.7
        chain.screamer.level = 0.8
        chain.cab.enabled = True
        chain.cab.select_cab("Celestion V30 4x12")
        chain.delay.enabled = False
        chain.reverb.enabled = True
        chain.reverb.decay = 0.25
        chain.reverb.mix = 0.12
        category = "High Gain Metal"

    # Gain/EQ decoded from the rig itself replace the name-based guesses above;
    # model, cab and effects still come from the heuristic.
    params = get_rig_params(req.pack_path, req.rig_id) if req.pack_path and req.rig_id else None
    if params:
        for field, value in params.items():
            setattr(chain.amp, field, value)

    return {
        "success": True,
        "name": req.name,
        "author": req.author,
        "category": category,
        "params_decoded": params is not None,
        "state": engine.get_state()
    }

@app.get("/api/kemper/packs")
def get_kemper_packs():
    return {"packs": list_installed_kemper_packs()}

@app.get("/api/kemper/rigs")
def get_kemper_rigs(pack_path: str, limit: int = 200, decode: bool = True):
    """
    Rigs in one pack.

    `limit` defaults to 200 rather than the importer's 50 so a normal pack is
    not silently truncated; the response reports what was actually returned.
    """
    if not os.path.exists(pack_path):
        raise HTTPException(status_code=404, detail="Rig pack not found")
    limit = max(1, min(int(limit), 5000))
    rigs = read_rigs_from_pack(pack_path, limit=limit, decode=decode)
    return {"pack_path": pack_path, "limit": limit, "count": len(rigs), "rigs": rigs}

# ------------------------------------------------------------------
# TONE3000 neural presets
#
# Each entry carries the ear-tuned DSP character (same values the previous
# if/elif chain used) plus the real gear names and the recorder-measured
# cabinet IR decoded from the preset file itself.
# ------------------------------------------------------------------
from engine.dsp import CabinetSimulator

_T3K_SETTINGS = {
    "t3k_ampeg_bass_drive": {
        "amp": {"model": "Clean", "gain": 0.35, "bass": 0.75, "mid": 0.50, "treble": 0.45, "presence": 0.40, "master": 0.85},
        "screamer": {"enabled": False, "drive": 0.4, "tone": 0.6, "level": 0.7},
        "gate": True, "delay": None, "reverb": None,
    },
    "t3k_bogner_fullstack": {
        "amp": {"model": "5150", "gain": 0.78, "bass": 0.55, "mid": 0.52, "treble": 0.65, "presence": 0.60, "master": 0.72},
        "screamer": {"enabled": True, "drive": 0.25, "tone": 0.65, "level": 0.80},
        "gate": True, "delay": None, "reverb": {"decay": 0.25, "mix": 0.15},
    },
    "t3k_dumble_spread": {
        "amp": {"model": "Plexi", "gain": 0.52, "bass": 0.55, "mid": 0.62, "treble": 0.60, "presence": 0.55, "master": 0.78},
        "screamer": {"enabled": True, "drive": 0.30, "tone": 0.55, "level": 0.75},
        "gate": True, "delay": None, "reverb": {"decay": 0.45, "mix": 0.22},
    },
    "t3k_marshall_bluesbreaker": {
        "amp": {"model": "Plexi", "gain": 0.55, "bass": 0.60, "mid": 0.58, "treble": 0.55, "presence": 0.50, "master": 0.80},
        "screamer": {"enabled": False, "drive": 0.4, "tone": 0.6, "level": 0.7},
        "gate": False, "delay": None, "reverb": {"decay": 0.35, "mix": 0.18},
    },
    "t3k_matchless_crunch": {
        "amp": {"model": "Plexi", "gain": 0.50, "bass": 0.50, "mid": 0.65, "treble": 0.68, "presence": 0.60, "master": 0.75},
        "screamer": {"enabled": True, "drive": 0.20, "tone": 0.60, "level": 0.70},
        "gate": True, "delay": None, "reverb": {"decay": 0.30, "mix": 0.15},
    },
    "t3k_mesa_pitch_shift": {
        "amp": {"model": "5150", "gain": 0.82, "bass": 0.62, "mid": 0.48, "treble": 0.65, "presence": 0.65, "master": 0.70},
        "screamer": {"enabled": True, "drive": 0.30, "tone": 0.70, "level": 0.85},
        "gate": True, "delay": {"time": 0.32, "feedback": 0.30, "mix": 0.22}, "reverb": {"decay": 0.40, "mix": 0.20},
    },
    "t3k_stereo_crunch_verb": {
        "amp": {"model": "Plexi", "gain": 0.48, "bass": 0.50, "mid": 0.55, "treble": 0.65, "presence": 0.65, "master": 0.75},
        "screamer": {"enabled": True, "drive": 0.35, "tone": 0.65, "level": 0.75},
        "gate": True, "delay": {"time": 0.45, "feedback": 0.45, "mix": 0.35}, "reverb": {"decay": 0.75, "mix": 0.40},
    },
    "t3k_stereo_fuzz": {
        "amp": {"model": "5150", "gain": 0.85, "bass": 0.65, "mid": 0.50, "treble": 0.60, "presence": 0.55, "master": 0.70},
        "screamer": {"enabled": True, "drive": 0.85, "tone": 0.50, "level": 0.85},
        "gate": True, "delay": None, "reverb": {"decay": 0.35, "mix": 0.20},
    },
}


def _install_real_t3k_ir(preset):
    """
    Decode the recorder-measured cabinet IR embedded in a .t3kpreset and
    install it into the engine's cabinet slot (under the cab IR lock).

    Returns an info dict on success, or None when the preset ships no speaker
    IR (in which case the current/synthetic cabinet stays in place).
    """
    if not preset.get("has_real_ir"):
        return None
    decoded = get_real_cab_ir(preset["file_path"])
    if not decoded:
        return None
    source_rate, samples, title = decoded
    try:
        prepared, truncated = CabinetSimulator._prepare_ir(
            samples, source_rate, config.SAMPLE_RATE, config.IR_MAX_LENGTH
        )
    except ValueError as exc:
        logger.warning("TONE3000 IR unusable for %s: %s", preset["id"], exc)
        return None
    with _CAB_IR_LOCK:
        engine.chain.cab.set_ir_data(prepared, title)
    return {
        "ir_name": title,
        "samples": len(prepared),
        "source_rate": int(source_rate),
        "source_samples": int(samples.shape[0]) if hasattr(samples, "shape") else None,
        "truncated": truncated,
        "real": True,
    }

class Tone3000Load(BaseModel):
    id: str
    nam: bool = True              # run the preset's embedded neural models
    nam_quality: str = "lite"     # "lite" (3 ch, safe in real time) or "full" (8 ch)
    nam_input_gain_db: float = 0.0


@app.get("/api/tone3000/presets")
def get_tone3000_presets():
    return {"presets": list_tone3000_presets()}


@app.post("/api/tone3000/load")
def load_tone3000_preset(req: Tone3000Load):
    presets = list_tone3000_presets()
    target = next((p for p in presets if p["id"] == req.id or p["file_name"] == req.id), None)
    if not target:
        raise HTTPException(status_code=404, detail="TONE3000 preset not found")

    chain = engine.chain
    s = _T3K_SETTINGS.get(target["id"], {})
    a = s.get("amp", {})

    # AMP character (ear-tuned values, keyed off the decoded real amp name).
    chain.amp.model = a.get("model", "5150")
    chain.amp.gain = a.get("gain", 0.6)
    chain.amp.bass = a.get("bass", 0.5)
    chain.amp.mid = a.get("mid", 0.5)
    chain.amp.treble = a.get("treble", 0.6)
    chain.amp.presence = a.get("presence", 0.55)
    chain.amp.master = a.get("master", 0.75)

    sc = s.get("screamer") or {}
    chain.screamer.enabled = bool(sc.get("enabled", False))
    chain.screamer.drive = sc.get("drive", 0.4)
    chain.screamer.tone = sc.get("tone", 0.6)
    chain.screamer._update_filter()
    chain.screamer.level = sc.get("level", 0.7)
    chain.noise_gate.enabled = bool(s.get("gate", True))

    # CABINET: install the recorder-measured IR shipped inside the preset.
    # Without a speaker IR the preset falls back to the closest synthetic cab.
    ir_info = _install_real_t3k_ir(target)
    if ir_info is None and target.get("cab_fallback"):
        with _CAB_IR_LOCK:
            chain.cab.select_cab(target["cab_fallback"])
    chain.cab.enabled = True

    dly = s.get("delay")
    if dly:
        chain.delay.enabled = True
        chain.delay.time_sec = dly["time"]
        chain.delay.feedback = dly["feedback"]
        chain.delay.mix = dly["mix"]
    else:
        chain.delay.enabled = False

    rvb = s.get("reverb")
    if rvb:
        chain.reverb.enabled = True
        chain.reverb.decay = rvb["decay"]
        chain.reverb.mix = rvb["mix"]
    else:
        chain.reverb.enabled = False

    # Neural models: when they load, they replace the screamer + amp stand-ins
    # above. Any failure leaves the DSP version playing.
    chain.nam = None
    nam_info = None
    if req.nam and req.nam_quality not in ("lite", "full"):
        raise HTTPException(status_code=400, detail="nam_quality must be 'lite' or 'full'")
    if req.nam:
        try:
            nam_chain = get_nam_chain(target["file_path"], req.nam_quality,
                                      input_gain_db=max(-24.0, min(24.0, req.nam_input_gain_db)))
        except (ValueError, KeyError, NotImplementedError, OSError) as exc:
            logger.warning("NAM unavailable for %s: %s", target["id"], exc)
            nam_info = {"active": False, "error": str(exc)}
        else:
            if nam_chain:
                chain.nam = nam_chain  # assigned last, fully built, so the audio thread never sees a partial chain
                if nam_chain.includes_cab:
                    chain.cab.enabled = False
                nam_info = {"active": True, "quality": req.nam_quality, **nam_chain.describe()}

    return {
        "success": True,
        "preset": target,
        "ir": ir_info,
        "nam": nam_info,
        "state": engine.get_state(),
    }


def _sanitize_ir_filename(raw_name: str) -> str:
    """
    Reduce an untrusted client filename to a safe display name.

    Strips directory components and any character outside a conservative
    allow-list so the value is safe to echo back into the DOM.
    """
    name = os.path.basename(raw_name or "").strip()
    name = re.sub(r"[^A-Za-z0-9._ -]", "_", name)
    name = name.lstrip(".") or "custom_ir.wav"
    return name[:120]


def _decode_and_install_ir(raw_bytes: bytes, display_name: str) -> tuple:
    """
    Blocking worker: decode WAV bytes, normalise, and install into the engine.

    Runs in a worker thread so the event loop (and therefore /api/status
    polling during realtime audio) is never blocked.
    """
    import io
    import numpy as np
    from scipy.io import wavfile
    from engine.dsp import CabinetSimulator

    if not raw_bytes:
        raise ValueError("Uploaded file is empty")

    try:
        sr, data = wavfile.read(io.BytesIO(raw_bytes))
    except Exception as exc:
        raise ValueError(f"Not a readable WAV file: {exc}") from exc

    prepared, truncated = CabinetSimulator._prepare_ir(
        data, sr, config.SAMPLE_RATE, config.IR_MAX_LENGTH
    )

    # Commit only once decoding and validation have fully succeeded.
    with _CAB_IR_LOCK:
        engine.chain.cab.set_ir_data(prepared, display_name)

    return display_name, len(prepared), int(sr), truncated


@app.post("/api/cab/load_ir")
async def load_custom_ir(ir_file: UploadFile = File(...)):
    """
    Upload a custom cabinet IR (.wav).

    Field name MUST match the client FormData key ('ir_file').
    """
    display_name = _sanitize_ir_filename(ir_file.filename)

    suffix = os.path.splitext(display_name)[1].lower()
    if suffix not in config.IR_ALLOWED_SUFFIXES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{suffix or 'none'}'. Only .wav is allowed.",
        )

    # Stream with a hard cap so a huge upload cannot exhaust memory.
    chunks = bytearray()
    declared = ir_file.size
    if declared and declared > config.IR_UPLOAD_MAX_BYTES:
        raise HTTPException(status_code=413, detail="IR file exceeds the 16 MB limit.")

    while True:
        chunk = await ir_file.read(1024 * 256)
        if not chunk:
            break
        chunks.extend(chunk)
        if len(chunks) > config.IR_UPLOAD_MAX_BYTES:
            raise HTTPException(status_code=413, detail="IR file exceeds the 16 MB limit.")

    raw_bytes = bytes(chunks)

    try:
        name, samples, source_rate, truncated = await run_in_threadpool(
            _decode_and_install_ir, raw_bytes, display_name
        )
    except ValueError as exc:
        logger.warning("Rejected custom IR '%s': %s", display_name, exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Failed to decode custom IR '%s': %s", display_name, exc)
        raise HTTPException(status_code=500, detail="Failed to process IR file.") from exc

    # Persist only after the buffer is known-good; a rejected upload leaves
    # no orphan file behind.
    try:
        config.CUSTOM_IR_DIR.mkdir(parents=True, exist_ok=True)
        stored = config.CUSTOM_IR_DIR / name
        stored.write_bytes(raw_bytes)
    except OSError as exc:
        logger.warning("IR applied but could not be persisted: %s", exc)

    logger.info("Loaded custom IR: %s (%d samples from %d Hz)", name, samples, source_rate)

    return {
        "success": True,
        "ir_name": name,
        "samples": samples,
        "sample_rate": source_rate,
        "truncated": truncated,
    }

# Quality used the next time a NAM model is (re)built: "lite" = 3 channels,
# "full" = 8 channels. The UI's Lite/Full buttons set this through
# /api/parameter (section "nam", param "quality").
_NAM_QUALITY = "lite"


def _build_nam_chain(content: bytes, name: str, quality: str):
    """
    Parse a NAM model file (A1 WaveNet or A2 SlimmableContainer JSON) into a
    NamChain. Raises ValueError with a readable message for anything else,
    including TONE3000's binary .namb files.
    """
    import json
    from engine import nam

    binary_hint = (
        "ไฟล์ที่ดาวน์โหลดมาไม่ใช่ .nam แบบ JSON — น่าจะเป็น .namb (NAM A2 binary) "
        "ที่ engine นี้ยังอ่านไม่ได้ ตั้งค่า TONE3000 เป็น Architecture = 1 (A1) แล้วโหลดใหม่"
    )
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError(binary_hint) from exc

    if not text.lstrip().startswith("{"):
        raise ValueError(binary_hint)

    try:
        model_dict = json.loads(text)
    except ValueError as exc:
        raise ValueError(f"Invalid JSON/NAM model file: {exc}") from exc

    net = nam.SlimmableWaveNet(model_dict, build=quality)
    stage = {
        "title": name.replace(".nam", ""),
        "gear_type": model_dict.get("metadata", {}).get("gear_type", "amp"),
        "net": net
    }
    return nam.NamChain([stage])


@app.post("/api/nam/upload")
async def upload_nam_model(nam_file: UploadFile = File(...), quality: str = "all"):
    """
    Upload a standalone Neural Amp Modeler (.nam) model.
    Decodes the WaveNet architecture and installs it into the NAM chain.
    """
    filename = _sanitize_ir_filename(nam_file.filename)
    if not (filename.endswith(".nam") or filename.endswith(".json")):
        raise HTTPException(status_code=400, detail="Only .nam model files are supported.")

    raw_bytes = await nam_file.read()
    if len(raw_bytes) > 50 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="NAM file exceeds 50 MB limit.")

    build_quality = quality if quality in ("lite", "full") else _NAM_QUALITY
    try:
        new_chain = await run_in_threadpool(_build_nam_chain, raw_bytes, filename, build_quality)
    except ValueError as exc:
        logger.warning("Failed to load uploaded NAM model: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.warning("Failed to load uploaded NAM model: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    with ENGINE_STATE_LOCK:
        engine.chain.nam = new_chain
        engine.chain.cab.enabled = not new_chain.includes_cab

    logger.info("Successfully loaded uploaded NAM model: %s", filename)
    return {
        "success": True,
        "filename": filename,
        "details": new_chain.describe(),
        "state": engine.get_state()
    }


@app.post("/api/nam/clear")
def clear_nam_model():
    """Remove the NAM chain and return to the DSP amp stage."""
    with ENGINE_STATE_LOCK:
        engine.chain.nam = None
    return {"success": True, "state": engine.get_state()}

# ------------------------------------------------------------------
# TONE3000 API — OAuth 2.0 PKCE (select_tone / load_tone)
#
# The browser flow: the UI asks for an authorize URL, TONE3000 hands the user
# back to /api/t3k/callback with a code + tone_id, that handler exchanges the
# code, downloads the chosen .nam model and installs it in the NAM AMP block.
# The in-app browser uses the same token to search/browse and load tones
# directly through /api/t3k/tones and /api/t3k/load.
# ------------------------------------------------------------------
_T3K_STATE = {"seq": 0, "last_load": None, "cancel_seq": 0}


def _t3k_metadata(load: dict) -> dict:
    """Keep only stable, non-secret fields needed to restore a cached model."""
    return {
        "tone_id": int(load["tone_id"]),
        "model_id": int(load["model_id"]) if load.get("model_id") is not None else None,
        "architecture": str(load.get("architecture") or "2"),
        "quality": str(load.get("quality") or "lite"),
        "file": str(load.get("file") or "tone.nam"),
        "cache_file": str(load.get("cache_file") or ""),
    }


def _t3k_cache_path(tone_id: int, model_id: int | None, architecture: str):
    config.T3K_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    model_part = str(model_id) if model_id is not None else "auto"
    return config.T3K_CACHE_DIR / f"tone_{int(tone_id)}_model_{model_part}_a{architecture}.nam"


def _cache_t3k_model(raw: bytes, tone_id: int, model_id: int | None, architecture: str) -> str:
    """Persist the downloaded model without exposing it to git or partial writes."""
    path = _t3k_cache_path(tone_id, model_id, architecture)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(raw)
    os.replace(tmp, path)
    return path.name


def _restore_cached_t3k(meta: dict, chain):
    """Build a NAM chain from a previously downloaded TONE3000 model."""
    cache_name = os.path.basename(str(meta.get("cache_file") or ""))
    if not cache_name or cache_name != str(meta.get("cache_file")):
        raise ValueError("invalid TONE3000 cache reference")
    path = config.T3K_CACHE_DIR / cache_name
    raw = path.read_bytes()
    quality = str(meta.get("quality") or "lite")
    restored = _build_nam_chain(raw, str(meta.get("file") or path.name), quality)
    if restored is None:
        raise ValueError("empty NAM chain")
    chain.amp.enabled = True
    chain.cab.enabled = not restored.includes_cab
    return restored

# Gear labels used when auto-saving a TONE3000 tone as a user preset.
T3K_GEAR_LABELS = {
    "amp": "Amp",
    "amp-cab": "Amp + Cab",
    "amp_cab": "Amp + Cab",
    "pedal": "Pedal",
    "outboard": "Outboard",
    "cab": "Cab",
    "space": "Space",
    "experimental": "Experimental",
    "ir": "Cabinet IR",
}


def _save_t3k_preset(tone: dict, creator: str, chain, model_meta: dict | None = None) -> bool:
    """Auto-save a loaded TONE3000 tone as a user preset in presets.db.

    Never raises: preset persistence is a nicety and must not break the load flow.
    Returns True when the preset was written, False otherwise.
    """
    try:
        tone_id = tone.get("id")
        if not tone_id:
            return False
        preset_id = f"t3k_{tone_id}"
        gear = str(tone.get("gear") or "")
        category = T3K_GEAR_LABELS.get(gear, gear.replace("-", " ").title() or "TONE3000")
        name = tone.get("title") or "TONE3000 Tone"
        settings = engine.get_state()["chain"]
        if model_meta:
            settings["_t3k"] = _t3k_metadata(model_meta)
        save_preset(
            preset_id,
            name,
            category,
            creator or "TONE3000",
            settings,
        )
        logger.info("Auto-saved TONE3000 tone %s as preset %s", tone_id, preset_id)
        return True
    except Exception as exc:  # preset saving must not break the load flow
        logger.warning("Failed to auto-save TONE3000 preset: %s", exc)
        return False


class T3KConfigReq(BaseModel):
    client_id: str | None = None
    redirect_uri: str | None = None
    architecture: str | None = None


class T3KConnectReq(BaseModel):
    prompt: str = "select_tone"
    tone_id: int | None = None
    gears: str | None = None


class T3KLoadReq(BaseModel):
    tone_id: int
    model_id: int | None = None
    quality: str | None = None


def _t3k_http_error(exc):
    try:
        status = int(getattr(exc, "status", 502))
    except (TypeError, ValueError):
        status = 502
    if not 400 <= status <= 599:
        status = 502
    return HTTPException(status_code=status, detail=str(exc))


def _t3k_safe_url(value):
    """Only http(s) URLs reach the <img src> / <a href> of the UI."""
    url = str(value or "").strip()
    return url if url.startswith(("https://", "http://")) else ""


def _install_t3k_tone(tone_id: int, model_id: int | None = None,
                      quality: str | None = None) -> dict:
    """
    Download a TONE3000 tone's model and install it as the NAM chain.

    A2 is requested first (the bundled engine decodes SlimmableContainer). If
    the downloaded file is the binary .namb variant this app cannot read, the
    same tone is fetched again with architecture=1 before giving up.
    """
    quality = quality if quality in ("lite", "full") else _NAM_QUALITY
    pkg = t3k.fetch_package(tone_id, model_id)
    try:
        chain = _build_nam_chain(pkg["bytes"], pkg["filename"], quality)
    except ValueError as exc:
        if model_id is not None:
            raise
        logger.warning("TONE3000 model %s unreadable as A2 (%s); retrying A1", tone_id, exc)
        try:
            pkg = t3k.fetch_package(tone_id, None, architecture="1")
        except t3k.T3KError as a1_exc:
            if getattr(a1_exc, "code", None) == "no_models":
                raise t3k.T3KError(
                    "เสียงนี้มีแต่โมเดล A2 ที่ engine อ่านไม่ได้ และไม่มี A1 ให้ fallback — "
                    "เลือกเสียงที่มีป้าย A1 หรือเปลี่ยน Model architecture เป็น A1",
                    400, "no_a1_models") from a1_exc
            raise
        pkg["was_fallback"] = True
        chain = _build_nam_chain(pkg["bytes"], pkg["filename"], quality)

    tone = pkg["tone"]
    model = pkg["model"]
    creator = (tone.get("user") or {}).get("username") or "TONE3000"
    images = tone.get("images") or []

    with ENGINE_STATE_LOCK:
        engine.chain.nam = chain          # assigned fully built: the audio thread never sees a partial chain
        engine.chain.amp.enabled = True
        engine.chain.cab.enabled = not chain.includes_cab

    # Persist the downloaded payload so the preset can rebuild the NAM chain
    # after a restart, even when TONE3000 is temporarily offline.
    cache_file = _cache_t3k_model(
        pkg["bytes"], tone["id"], model.get("id"), pkg["architecture"]
    )
    model_meta = {
        "tone_id": tone.get("id"),
        "model_id": model.get("id"),
        "architecture": pkg["architecture"],
        "quality": quality,
        "file": pkg["filename"],
        "cache_file": cache_file,
    }
    preset_saved = _save_t3k_preset(tone, creator, chain, model_meta)

    _T3K_STATE["seq"] += 1
    info = {
        "seq": _T3K_STATE["seq"],
        "tone_id": tone.get("id"),
        "title": tone.get("title") or pkg["filename"],
        "gear": tone.get("gear"),
        "format": tone.get("format"),
        "creator": creator,
        "image": _t3k_safe_url(images[0] if images else ""),
        "model": model.get("name"),
        "model_id": model.get("id"),
        "model_size": model.get("size"),
        "architecture": pkg["architecture"],
        "fallback_a1": bool(pkg.get("was_fallback")),
        "quality": quality,
        "file": pkg["filename"],
        "cache_file": cache_file,
        "includes_cab": chain.includes_cab,
        "nam": chain.describe(),
        "preset_saved": preset_saved,
    }

    _T3K_STATE["last_load"] = info
    logger.info("Loaded TONE3000 tone %s (%s / %s) as NAM %s",
                tone_id, info["model"], info["file"], quality)
    return info


@app.get("/api/t3k/status")
def t3k_status():
    try:
        state = t3k.status()
    except t3k.T3KError as exc:
        raise _t3k_http_error(exc)
    return {**state, "last_load": _T3K_STATE["last_load"], "seq": _T3K_STATE["seq"],
            "cancel_seq": _T3K_STATE["cancel_seq"], "quality": _NAM_QUALITY,
            "engine_nam": engine.get_state().get("nam")}


@app.post("/api/t3k/config")
def t3k_config(req: T3KConfigReq):
    """Save the publishable key / redirect URI / architecture from the UI."""
    try:
        t3k.save_config(req.client_id, req.redirect_uri, req.architecture)
        state = t3k.status()
    except t3k.T3KError as exc:
        raise _t3k_http_error(exc)
    return {"success": True, **state}


@app.post("/api/t3k/connect")
def t3k_connect(req: T3KConnectReq):
    """Build the authorize URL and open it in the user's default browser."""
    try:
        info = t3k.build_authorize_url(req.prompt, tone_id=req.tone_id, gears=req.gears)
    except t3k.T3KError as exc:
        raise _t3k_http_error(exc)
    try:
        opened = webbrowser.open(info["authorize_url"], new=2)
    except Exception as exc:               # headless box: the URL is still returned
        logger.warning("Could not open system browser: %s", exc)
        opened = False
    return {"success": True, "opened": opened, **info}


@app.post("/api/t3k/logout")
def t3k_logout():
    t3k.clear_tokens()
    return {"success": True}


@app.get("/api/t3k/tones")
def t3k_tones(kind: str = "trending", query: str = "", page: int = 1,
              gear: str | None = None, verified: bool = False):
    """Bounded lists + search for the in-app TONE3000 browser."""
    try:
        if query.strip():
            data = t3k.search_tones(query.strip(), page=page, gear=gear, verified=verified)
        elif kind == "search":
            data = t3k.search_tones("", page=page, gear=gear, verified=verified)
        else:
            data = t3k.list_tones(kind, page=page, gear=gear)
    except t3k.T3KError as exc:
        raise _t3k_http_error(exc)
    return {"kind": kind, "query": query, **data}


@app.get("/api/t3k/tones/{tone_id}")
def t3k_tone_detail(tone_id: int):
    try:
        tone = t3k.get_tone(tone_id)
        models = t3k.list_models(tone_id)
    except t3k.T3KError as exc:
        raise _t3k_http_error(exc)
    return {"tone": tone, "models": models}


@app.post("/api/t3k/load")
def t3k_load(req: T3KLoadReq):
    """Load a tone from the in-app browser into the NAM AMP block."""
    try:
        info = _install_t3k_tone(req.tone_id, req.model_id, req.quality)
    except t3k.T3KError as exc:
        raise _t3k_http_error(exc)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except (KeyError, NotImplementedError, OSError) as exc:
        logger.warning("TONE3000 load failed for %s: %s", req.tone_id, exc)
        raise HTTPException(status_code=400, detail=f"โหลดโมเดลไม่สำเร็จ: {exc}")
    return {"success": True, "load": info, "state": engine.get_state()}


def _t3k_result_page(ok: bool, title: str, message: str, info: dict | None = None) -> str:
    """Self-contained dark page shown in the tab TONE3000 returns to."""
    accent = "#3fb950" if ok else "#e5534b"
    rows = ""
    if info:
        pairs = [
            ("เสียง", info.get("title")),
            ("โมเดล", info.get("model")),
            ("ผู้สร้าง", info.get("creator")),
            ("NAM", f'{info.get("architecture")} • {info.get("quality")}'),
            ("Cab", "อยู่ในตัวโมเดล" if info.get("includes_cab") else "ใช้ IR แยก"),
        ]
        rows = "".join(
            f'<div class="r"><span>{html.escape(str(k))}</span><b>{html.escape(str(v))}</b></div>'
            for k, v in pairs if v
        )
    return f"""<!doctype html><html lang="th"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)} — TONE3000</title>
<style>
  :root {{ color-scheme: dark; }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; min-height:100vh; display:grid; place-items:center;
         background:radial-gradient(900px 500px at 50% -10%, #17202b, #06080c 60%);
         color:#e9edf3; font:15px/1.55 "Segoe UI", "IBM Plex Sans Thai", sans-serif; }}
  .card {{ width:min(460px, calc(100vw - 32px)); background:#10141b; border:1px solid #222b38;
           border-radius:14px; padding:26px 24px; box-shadow:0 24px 60px rgba(0,0,0,.6); }}
  .dot {{ width:12px; height:12px; border-radius:50%; background:{accent};
          box-shadow:0 0 14px {accent}; display:inline-block; margin-right:9px; }}
  .brand {{ font:600 11px/1 "IBM Plex Mono", monospace; letter-spacing:.16em;
            color:#f0b429; text-transform:uppercase; }}
  h1 {{ font-size:20px; margin:12px 0 8px; }}
  p {{ color:#8d99a9; margin:0 0 16px; }}
  .r {{ display:flex; justify-content:space-between; gap:14px; padding:8px 0;
        border-top:1px solid #1a212d; font-size:13px; }}
  .r span {{ color:#8d99a9; }}
  .r b {{ text-align:right; font-weight:600; }}
  .close {{ margin-top:18px; width:100%; padding:10px; border-radius:9px; cursor:pointer;
            border:1px solid rgba(240,180,41,.5); background:rgba(240,180,41,.12); color:#f0b429;
            font-weight:600; font-size:13px; }}
  .tip {{ font-size:11.5px; color:#5d6878; margin-top:10px; text-align:center; }}
</style></head><body>
<div class="card">
  <div class="brand">TONE3000 × กดจนหลอนTone</div>
  <h1><span class="dot"></span>{html.escape(title)}</h1>
  <p>{html.escape(message)}</p>
  {rows}
  <button class="close" onclick="window.close()">ปิดแท็บนี้</button>
  <div class="tip">กลับไปที่หน้าตัวอย่างเสียง (แท็บเดิม) ได้เลย</div>
</div>
<script>
  // Auto-close only when the tab was opened by script (window.opener exists).
  if (window.opener) setTimeout(function () {{ window.close(); }}, 2200);
</script>
</body></html>"""


@app.get("/api/t3k/callback", response_class=HTMLResponse)
def t3k_callback(request: Request):
    query = {k: v for k, v in request.query_params.items()}
    try:
        result = t3k.handle_callback(query)
    except t3k.T3KError as exc:
        logger.warning("TONE3000 callback rejected: %s", exc)
        return HTMLResponse(_t3k_result_page(False, "เชื่อมต่อไม่สำเร็จ", str(exc)), status_code=400)

    if result["canceled"] and not result["tone_id"]:
        _T3K_STATE["cancel_seq"] += 1
        return HTMLResponse(_t3k_result_page(
            True, "ยกเลิกแล้ว", "ยังไม่ได้เลือกเสียง — เปิด TONE3000 แล้วเลือกใหม่ได้ทุกเมื่อ"))

    if not result["tone_id"]:
        return HTMLResponse(_t3k_result_page(
            False, "ไม่พบเสียง", "TONE3000 ไม่ได้ส่ง tone_id กลับมา"), status_code=400)

    try:
        info = _install_t3k_tone(result["tone_id"])
    except t3k.T3KError as exc:
        logger.warning("TONE3000 download failed: %s", exc)
        return HTMLResponse(_t3k_result_page(False, "โหลดเสียงไม่สำเร็จ", str(exc)), status_code=502)
    except ValueError as exc:
        return HTMLResponse(_t3k_result_page(False, "โหลดเสียงไม่สำเร็จ", str(exc)), status_code=400)

    return HTMLResponse(_t3k_result_page(
        True, "โหลดเสียงเรียบร้อย",
        "เสียงถูกติดตั้งเข้า NAM AMP ในแท็บที่เปิดแอปอยู่แล้ว", info))


# Serve frontend
if os.path.exists(WEB_DIR):
    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

@app.get("/")
def index():
    return FileResponse(os.path.join(WEB_DIR, "index.html"))

@app.get("/manus-routes.json")
def manus_routes():
    """Expose the page route inventory without falling back to the SPA shell."""
    return FileResponse(os.path.join(WEB_DIR, "manus-routes.json"), media_type="application/json")

if __name__ == "__main__":
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=False)
