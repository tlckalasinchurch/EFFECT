from fastapi import FastAPI, HTTPException, UploadFile, File, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel
import html
import json
import os
import re
import logging
import threading
import time
import uvicorn
import webbrowser

import config
import t3k_fastapi as t3k
from setup_logging import get_logger

from engine.audio import AudioEngine
from engine.device_mode import mode_for_source
from engine import param_access
from engine.presets import get_all_presets, save_preset
from engine.master_bank import MASTER_SIGNATURE_PRESETS, ensure_master_signature_presets, generate_auto_morph_slots, apply_morph_pair
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
    read_single_kipr,
    get_custom_kipr_files,
)
from engine.tone3000_importer import list_tone3000_presets, get_real_cab_ir, get_nam_chain
from engine.mooer_models import MODULE_CATALOG, AMP_MODELS, CAB_MODELS, DS_MODELS, EQ_MODELS, MOD_MODELS
from engine.mooer_preset import parse_mo_preset, export_mo_preset, mo_to_workstation_preset, FACTORY_GE150_PRESETS, get_all_mooer_presets
from engine.cortex_models import SCENE_COLORS, DEFAULT_SCENE_LABELS, FACTORY_CORTEX_PRESETS
from engine.cortex_scenes import CortexSceneManager
from engine.midi_in import MidiSceneListener
from engine.morph import MorphController

# Setup logger
logger = get_logger(__name__)

app = FastAPI(title="กดจนหลอนTone")
engine = AudioEngine(
    sample_rate=config.SAMPLE_RATE,
    block_size=config.BUFFER_SIZE,
    preferred_input=config.DEFAULT_INPUT_DEVICE,
    preferred_output=config.DEFAULT_OUTPUT_DEVICE,
    preferred_input_name=config.DEFAULT_INPUT_NAME,
    preferred_output_name=config.DEFAULT_OUTPUT_NAME,
)
cortex_mgr = CortexSceneManager()
morph_mgr = MorphController(db_path=str(config.DB_PATH))

WEB_DIR = config.WEB_DIR

# Serialises HTTP/MIDI handlers that write engine state against each other.
# The audio callback takes neither this lock nor _CAB_IR_LOCK, so they do NOT
# protect what it reads; several writers (e.g. /api/parameter) take no lock.
ENGINE_STATE_LOCK = threading.RLock()

# Serialises cab IR swaps against the IR upload endpoints (writer vs writer).
# The audio callback does not take it.
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
    st = engine.get_state()
    st["cortex"] = cortex_mgr.get_state()
    st["morph"] = morph_mgr.get_state()
    return st

@app.get("/api/devices")
def get_devices():
    return {
        "devices": engine.get_device_list(),
        "selected_in": engine.input_device,
        "selected_out": engine.output_device,
        "is_running": engine.is_running,
        "asio_drivers": engine.get_asio_drivers()
    }

@app.get("/api/settings")
def get_audio_settings():
    path = engine.audio_path_info()
    # ``latency_ms`` is the real driver-reported round trip, not just the
    # block deadline: the deadline alone (2.67 ms at 48k/128) made a 106 ms
    # fallback path look fast in the UI.
    latency_ms = path.get("reported_io_ms")
    if latency_ms is None:
        latency_ms = round((engine.block_size / engine.sample_rate) * 1000, 2)
    return {
        "sample_rate": engine.sample_rate,
        "buffer_size": engine.block_size,
        "input_device": engine.input_device,
        "output_device": engine.output_device,
        "latency_ms": latency_ms,
        "buffer_ms": path.get("buffer_ms"),
        "audio_path": path,
    }


def persist_audio_path():
    """Store sample rate, buffer and the *user's* device pair.

    Names are stored alongside the PortAudio indices because the indices are
    not stable.  The fallback pair is never saved: while ``using_fallback`` is
    set, ``audio_path_info()`` describes the system default devices, so saving
    them would replace the user's real choice with whatever Windows picked --
    one UX1 dropout would pin the 107 ms path permanently.
    """
    path = engine.audio_path_info()
    devices = {}
    if not path["using_fallback"]:
        devices = {
            "input_device": path["input"]["id"],
            "output_device": path["output"]["id"],
            "input_name": path["input"]["name"],
            "output_name": path["output"]["name"],
        }
    config.save_audio_settings(
        sample_rate=engine.sample_rate,
        buffer_size=engine.block_size,
        **devices,
    )

@app.post("/api/settings")
def update_audio_settings(data: dict):
    sr = data.get("sample_rate")
    buf = data.get("buffer_size", data.get("block_size"))
    in_id = data.get("input_id")
    out_id = data.get("output_id")

    if sr:
        with ENGINE_STATE_LOCK:
            engine.apply_sample_rate(int(sr))
    if buf:
        engine.block_size = int(buf)
    if in_id is not None or out_id is not None:
        engine.select_devices(in_id, out_id)

    if engine.is_running:
        success, msg = engine.start(
            input_id=engine.input_device,
            output_id=engine.output_device,
            sample_rate=engine.sample_rate,
            block_size=engine.block_size
        )
        persist_audio_path()
        return {"success": success, "message": msg, "state": engine.get_state()}

    persist_audio_path()
    return {"success": True, "message": f"Settings saved: {engine.sample_rate}Hz / {engine.block_size} samples", "state": engine.get_state()}

@app.post("/api/start")
def start_engine(data: dict = None):
    data = data or {}
    in_id = data.get("input_id", data.get("input_device"))
    out_id = data.get("output_id", data.get("output_device"))
    sr = data.get("sample_rate")
    buf = data.get("buffer_size", data.get("block_size"))

    success, msg = engine.start(input_id=in_id, output_id=out_id, sample_rate=sr, block_size=buf)
    # Persist what actually opened: start() may have resolved a stale index or
    # replaced the pair with the detected UX1.
    persist_audio_path()
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

def _is_known_parameter(section: str, param: str) -> bool:
    """True when engine/params.py declares this (section, parameter) pair."""
    try:
        param_access.resolve(section, param)
    except (KeyError, param_access.ServerOwnedParameter):
        return False
    return True


@app.post("/api/parameter")
def update_parameter(req: ParamUpdate):
    try:
        sec = req.section
        p = req.param
        val = req.value
    
        chain = engine.chain
        if sec == "nam":
            # NAM is optional and its build quality is not a DSP value at all, so it
            # keeps the guarded branch the registry cannot express.
            global _NAM_QUALITY
            if p == "quality" and str(val) in ("lite", "full"):
                _NAM_QUALITY = str(val)
                if chain.nam is not None:
                    for stg in getattr(chain.nam, "stages", []):
                        net = stg.get("net")
                        if hasattr(net, "select"):
                            net.select(0.5 if _NAM_QUALITY == "lite" else 1.0)
            elif chain.nam is not None and _is_known_parameter(sec, p):
                param_access.set(chain, sec, p, val)
        elif _is_known_parameter(sec, p):
            if sec == "cab" and p == "ir_name":
                # The IR swap is the one write that must hold the same lock as the IR
                # upload endpoints, which live in this module rather than in the DSP.
                param_access.set(chain, sec, p, val, lock=_CAB_IR_LOCK)
            else:
                param_access.set(chain, sec, p, val)
        # A section or parameter the registry does not know has always been a silent
        # no-op here; keep that instead of turning a stray knob into a 500.
    except param_access.NonFiniteValue as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"success": True, "state": engine.get_state()}


@app.get("/api/presets")
def list_presets():
    ensure_master_signature_presets()
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

    # The preset remembers which hardware it was voiced for; older presets have
    # no "device" section and stay generic. A hand-edited preset must not make
    # the load fail, so an unknown name logs and falls back.
    device = s.get("device") or {}
    try:
        mode = device.get("mode", "generic")
        # Legacy GE150/Cortex/Kemper modes were not usable; ignore them.
        if mode not in ("generic", "nam"):
            mode = "generic"
        chain.set_device_mode(mode)
    except ValueError:
        logger.warning(
            "Preset %s names an unknown device mode %r; loading as generic",
            req.preset_id, device.get("mode"),
        )
        chain.set_device_mode("generic")

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
            chain.set_device_mode(mode_for_source("tone3000"))
        except (OSError, ValueError, KeyError) as exc:
            logger.warning("Could not restore cached TONE3000 model for %s: %s", req.preset_id, exc)
            raise HTTPException(
                status_code=409,
                detail="พรีเซ็ตนี้ต้องใช้ไฟล์ NAM ในเครื่อง แต่ไฟล์ cache หายหรืออ่านไม่ได้ — "
                       "เลือกโหลดเสียงนี้จาก TONE3000 ใหม่อีกครั้ง",
            ) from exc
    
    # Apply Extended Blocks (EQ, Cab Tube/Mic, Mod, Ducking) & Master Morph Slots
    if "bright" in s.get("amp", {}):
        chain.amp.bright = bool(s["amp"]["bright"])
    cab_s = s.get("cab") or {}
    if any(k in cab_s for k in ("tube", "mic", "center", "distance")):
        chain.cab.set_tube_and_mic(
            tube=cab_s.get("tube", chain.cab.tube),
            mic=cab_s.get("mic", chain.cab.mic),
            center=cab_s.get("center", chain.cab.center),
            distance=cab_s.get("distance", chain.cab.distance),
        )
    eq_s = s.get("eq") or {}
    if eq_s:
        chain.eq.enabled = bool(eq_s.get("enabled", False))
        bands = eq_s.get("bands", eq_s.get("data"))
        if bands is not None:
            chain.eq.set_bands(bands, model_id=eq_s.get("model_id", chain.eq.model_id))
        elif "model_id" in eq_s:
            chain.eq.set_model(eq_s["model_id"])
    mod_s = s.get("mod") or {}
    if mod_s:
        chain.mod.enabled = bool(mod_s.get("enabled", False))
        chain.mod.model_id = int(mod_s.get("model_id", chain.mod.model_id))
        chain.mod.rate = float(mod_s.get("rate", chain.mod.rate))
        chain.mod.mix = float(mod_s.get("mix", chain.mod.mix))
        chain.mod.tone = float(mod_s.get("tone", chain.mod.tone))
        chain.mod.depth = float(mod_s.get("depth", chain.mod.depth))
    if "ducking" in s.get("delay", {}):
        chain.delay.ducking = bool(s["delay"]["ducking"])
    if "duck_depth" in s.get("delay", {}):
        chain.delay.duck_depth = float(s["delay"]["duck_depth"])
    if "ducking" in s.get("reverb", {}):
        chain.reverb.ducking = bool(s["reverb"]["ducking"])
    if "duck_depth" in s.get("reverb", {}):
        chain.reverb.duck_depth = float(s["reverb"]["duck_depth"])

    master_meta = next((m for m in MASTER_SIGNATURE_PRESETS if m["id"] == req.preset_id), None)
    if master_meta and "morph_a" in master_meta and "morph_b" in master_meta:
        try:
            apply_morph_pair(morph_mgr, master_meta["morph_a"], master_meta["morph_b"])
        except Exception as exc:
            logger.warning("Failed to apply master morph pair: %s", exc)

    st = engine.get_state()
    st["morph"] = morph_mgr.get_state()
    return {"success": True, "loaded_preset": target, "state": st, "morph": st["morph"]}


@app.get("/api/master-bank/presets")
def get_master_bank_presets():
    """Returns the unified กดจนหลอนTone Master Signature Bank cloned from all 4 brands."""
    ensure_master_signature_presets()
    return {"presets": MASTER_SIGNATURE_PRESETS}


@app.post("/api/morph/auto")
def auto_generate_morph_slots():
    """Kemper-style Auto-Morph A<->B generator around the live amplifier & FX state."""
    with ENGINE_STATE_LOCK:
        pair = generate_auto_morph_slots(engine.chain)
        morph_state = apply_morph_pair(morph_mgr, pair["slot_a"], pair["slot_b"])
    return {"success": True, "morph": morph_state, "state": engine.get_state()}


@app.post("/api/tempo/sync")
def sync_tempo_bpm(data: dict):
    """MOOER GE150 / Quad Cortex Tap Tempo & BPM Delay Sync."""
    bpm = float(data.get("bpm", 120.0))
    bpm = max(30.0, min(300.0, bpm))
    sub = str(data.get("subdivision", "1/4")).lower()
    beat_sec = 60.0 / bpm
    mult = 0.75 if sub in ("1/8d", "dotted") else (0.5 if sub == "1/8" else 1.0)
    delay_sec = max(0.02, min(2.0, round(beat_sec * mult, 3)))
    with ENGINE_STATE_LOCK:
        engine.chain.delay.time_sec = delay_sec
    return {"success": True, "bpm": round(bpm, 1), "subdivision": sub, "delay_time_sec": delay_sec, "state": engine.get_state()}


@app.get("/api/ai-tone/profiles")
def get_ai_tone_profiles():
    """Returns curated Artist & Song Tone DNA profiles for AI Tone Matching."""
    from engine.ai_tone_matcher import ARTIST_TONE_PROFILES
    return {"profiles": ARTIST_TONE_PROFILES}


@app.post("/api/ai-tone/match")
def ai_tone_match_endpoint(data: dict):
    """Matches an artist, song, or tone description and synthesizes the full 9-block rig + Morph A/B."""
    from engine.ai_tone_matcher import match_artist_tone
    query = str(data.get("query") or data.get("id") or "")
    prof = match_artist_tone(query)
    if prof is None:
        raise HTTPException(status_code=404, detail=f"No tone profile matches '{query}'")
    s = prof["settings"]
    chain = engine.chain

    with ENGINE_STATE_LOCK:
        chain.nam = None
        for block in ("gate", "pitch", "screamer", "amp", "cab", "mod", "delay", "reverb"):
            if block in s:
                param_access.apply_settings(chain, block, s[block])
        eq_s = s.get("eq") or {}
        if eq_s:
            chain.eq.enabled = bool(eq_s.get("enabled", False))
            if "bands" in eq_s:
                chain.eq.set_bands(eq_s["bands"], model_id=eq_s.get("model_id", 5))
        par = prof.get("parallel") or {}
        chain.parallel_enabled = bool(par.get("enabled", False))
        chain.parallel_blend = float(par.get("blend", 0.3))
        if "morph_a" in prof and "morph_b" in prof:
            apply_morph_pair(morph_mgr, prof["morph_a"], prof["morph_b"])

    st = engine.get_state()
    st["morph"] = morph_mgr.get_state()
    return {"success": True, "matched_profile": prof, "state": st, "morph": st["morph"]}


@app.get("/api/hd-audio/status")
def get_hd_audio_status():
    """Returns World-Class HD DSP Mastering & Acoustic Engine state and telemetry."""
    if getattr(engine, "hd_dsp", None) is None:
        return {"enabled": False}
    return engine.hd_dsp.get_status()


@app.post("/api/hd-audio/update")
def update_hd_audio_settings(data: dict):
    """Updates World-Class HD DSP settings (auto_level, pure_cab, stereo_width, anti_squash, liquid_nam_eq)."""
    if getattr(engine, "hd_dsp", None) is None:
        raise HTTPException(status_code=500, detail="HD Audio Processor not initialized")
    with ENGINE_STATE_LOCK:
        status = engine.hd_dsp.update_settings(data or {})
    return {"success": True, "hd_audio": status, "state": engine.get_state()}

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


# ---------------------------------------------------------------------------
# MOOER GE150 Reverse-Engineered Endpoints
# ---------------------------------------------------------------------------
@app.get("/api/mooer/models")
def get_mooer_models():
    """Returns the complete 9-stage GE150 model catalog cloned from factory specs."""
    return {"catalog": MODULE_CATALOG}

@app.get("/api/mooer/presets")
def get_mooer_presets():
    """Returns factory and installed MOOER GE150 presets."""
    all_mo = get_all_mooer_presets()
    formatted = [mo_to_workstation_preset(p) for p in all_mo]
    return {"presets": formatted}

@app.post("/api/mooer/preset/load")
def load_mooer_preset(data: dict):
    """Loads a factory or user MOOER preset by name or index into the live audio engine."""
    all_mo = get_all_mooer_presets()
    name = data.get("name") or data.get("preset_name")
    target = next((p for p in all_mo if p.get("preset_name") == name or p.get("name") == name), None)
    if not target and "index" in data:
        idx = int(data["index"])
        if 0 <= idx < len(all_mo):
            target = all_mo[idx]
    if not target:
        raise HTTPException(status_code=404, detail="MOOER preset not found")

    with ENGINE_STATE_LOCK:
        engine.chain.nam = None
        engine.chain.apply_mooer_preset(target)
    return {"success": True, "preset": mo_to_workstation_preset(target), "state": engine.get_state()}

@app.post("/api/mooer/import")
async def import_mooer_preset_file(file: UploadFile = File(...)):
    """Upload, save, and load a .mo preset file directly from MOOER GE150."""
    content = await file.read()
    try:
        mo_doc = parse_mo_preset(content.decode("utf-8"))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid .mo preset format: {e}")

    # Persist to custom_mooer folder
    safe_name = re.sub(r"[^\w\-. ]", "_", mo_doc.get("preset_name") or "custom_mo").strip()
    save_path = config.CUSTOM_MOOER_DIR / f"{safe_name}.mo"
    try:
        save_path.write_bytes(content)
    except Exception as e:
        logger.warning(f"Could not persist uploaded .mo to disk: {e}")

    with ENGINE_STATE_LOCK:
        engine.chain.nam = None
        engine.chain.apply_mooer_preset(mo_doc)
    return {"success": True, "preset": mo_to_workstation_preset(mo_doc), "state": engine.get_state()}

@app.get("/api/mooer/export")
def export_current_to_mooer(name: str = "Custom Preset"):
    """Export current workstation chain state to a valid .mo GE150 JSON file."""
    state = engine.get_state()["chain"]
    mo_json = export_mo_preset(name, state)
    return JSONResponse(
        content=json.loads(mo_json),
        headers={"Content-Disposition": f'attachment; filename="{name[:16]}.mo"'}
    )


# ---------------------------------------------------------------------------
# Neural DSP Quad Cortex Scene Architecture Endpoints
# ---------------------------------------------------------------------------
def _midi_select_scene(idx: int):
    with ENGINE_STATE_LOCK:
        cortex_mgr.set_active_scene(idx, chain=engine.chain)


def _midi_handle_action(action: str, val: int):
    with ENGINE_STATE_LOCK:
        ch = engine.chain
        if action == "toggle_gate":
            ch.noise_gate.enabled = not ch.noise_gate.enabled
        elif action == "toggle_screamer":
            ch.screamer.enabled = not ch.screamer.enabled
        elif action == "toggle_amp":
            ch.amp.enabled = not ch.amp.enabled
        elif action == "toggle_cab":
            ch.cab.enabled = not ch.cab.enabled
        elif action == "toggle_mod":
            ch.mod.enabled = not ch.mod.enabled
        elif action == "toggle_delay":
            ch.delay.enabled = not ch.delay.enabled
        elif action == "toggle_reverb":
            ch.reverb.enabled = not ch.reverb.enabled
        elif action == "quick_clean":
            apply_quick_scene("clean")
        elif action == "quick_rhythm":
            apply_quick_scene("rhythm")
        elif action == "quick_lead":
            apply_quick_scene("lead")
        elif action == "toggle_ab":
            toggle_ab_snapshot()


_midi_listener = MidiSceneListener(_midi_select_scene, on_action=_midi_handle_action)

_CURRENT_QUICK_SCENE = "rhythm"
_AB_SNAPSHOT_A = None
_AB_ACTIVE = "B"


def apply_quick_scene(name: str) -> str:
    global _CURRENT_QUICK_SCENE
    name = str(name).strip().lower()
    ch = engine.chain
    if name == "clean":
        ch.noise_gate.enabled = True
        ch.screamer.enabled = False
        ch.amp.gain = 0.28
        ch.amp.bass = 0.50
        ch.amp.mid = 0.55
        ch.amp.treble = 0.65
        ch.amp.presence = 0.70
        ch.delay.enabled = False
        ch.reverb.enabled = True
        ch.reverb.mix = 0.25
        _CURRENT_QUICK_SCENE = "clean"
    elif name == "rhythm":
        ch.noise_gate.enabled = True
        ch.screamer.enabled = True
        ch.screamer.drive = 0.35
        ch.screamer.tone = 0.60
        ch.screamer.level = 0.75
        ch.amp.gain = 0.68
        ch.amp.bass = 0.55
        ch.amp.mid = 0.50
        ch.amp.treble = 0.60
        ch.amp.presence = 0.65
        ch.delay.enabled = False
        ch.reverb.enabled = True
        ch.reverb.mix = 0.15
        _CURRENT_QUICK_SCENE = "rhythm"
    elif name == "lead":
        ch.noise_gate.enabled = True
        ch.screamer.enabled = True
        ch.screamer.drive = 0.65
        ch.screamer.tone = 0.65
        ch.screamer.level = 0.85
        ch.amp.gain = 0.82
        ch.amp.bass = 0.55
        ch.amp.mid = 0.62
        ch.amp.treble = 0.65
        ch.amp.presence = 0.72
        ch.delay.enabled = True
        ch.delay.mix = 0.30
        ch.delay.feedback = 0.38
        ch.reverb.enabled = True
        ch.reverb.mix = 0.32
        _CURRENT_QUICK_SCENE = "lead"
    return _CURRENT_QUICK_SCENE


def apply_ab_state(st: dict):
    chain_data = st.get("chain", {})
    from engine import param_access
    for block_name, values in chain_data.items():
        if isinstance(values, dict):
            try:
                param_access.apply_settings(engine.chain, block_name, values)
            except Exception:
                pass


def store_ab_snapshot():
    global _AB_SNAPSHOT_A
    _AB_SNAPSHOT_A = engine.get_state()
    return True


def toggle_ab_snapshot() -> str:
    global _AB_ACTIVE, _AB_SNAPSHOT_A
    if _AB_SNAPSHOT_A is None:
        store_ab_snapshot()
        _AB_ACTIVE = "A"
        return _AB_ACTIVE
    if _AB_ACTIVE == "B":
        apply_ab_state(_AB_SNAPSHOT_A)
        _AB_ACTIVE = "A"
    else:
        _AB_ACTIVE = "B"
    return _AB_ACTIVE


@app.on_event("startup")
def _start_midi():
    _midi_listener.start()


@app.on_event("shutdown")
def _stop_midi():
    _midi_listener.stop()


@app.get("/api/cortex/scenes")
def get_cortex_scenes():
    """Returns the 8 scenes (A to H), active scene, and color palette."""
    return cortex_mgr.get_state()


@app.post("/api/cortex/scene/select")
def select_cortex_scene(data: dict):
    """Seamlessly switch between Scene A through H with zero audio glitch."""
    idx = int(data.get("index", 0))
    with ENGINE_STATE_LOCK:
        active = cortex_mgr.set_active_scene(idx, chain=engine.chain)
    return {"success": True, "active_scene": active, "state": engine.get_state(), "cortex": cortex_mgr.get_state()}


@app.post("/api/cortex/scene/update")
def update_cortex_scene(data: dict):
    """Update label, color, block bypasses, or parameter overrides for a specific scene."""
    idx = int(data.get("index", 0))
    label = data.get("label")
    color = data.get("color")
    bypasses = data.get("bypasses")
    param_overrides = data.get("param_overrides")
    with ENGINE_STATE_LOCK:
        updated = cortex_mgr.update_scene(
            idx,
            label=label,
            color_hex=color,
            bypasses=bypasses,
            param_overrides=param_overrides,
            chain=engine.chain
        )
    return {"success": True, "scene": updated, "cortex": cortex_mgr.get_state()}


@app.get("/api/cortex/presets")
def get_cortex_presets():
    """Returns all factory and multi-scene Cortex presets."""
    return {"presets": cortex_mgr.get_presets()}


# ---------------------------------------------------------------------------
# Modular Reorderable Signal Chain Endpoints (AmpForge Paradigm)
# ---------------------------------------------------------------------------
@app.get("/api/chain/order")
def get_chain_order():
    """Returns the user-facing block order of the current signal chain."""
    return {
        "order": engine.chain.get_stage_order(),
        "device_mode": getattr(engine.chain, "device_mode", "generic"),
    }


@app.post("/api/chain/reorder")
def reorder_chain(data: dict):
    """Reorder blocks dynamically or move a single block left/right."""
    with ENGINE_STATE_LOCK:
        if "order" in data and isinstance(data["order"], list):
            success = engine.chain.set_custom_order(data["order"])
        elif "block" in data and "direction" in data:
            engine.chain.move_block(data["block"], data["direction"])
            success = True
        else:
            success = False
    return {
        "success": success,
        "order": engine.chain.get_stage_order(),
        "state": engine.get_state(),
    }


# ---------------------------------------------------------------------------
# Clean, Rhythm, Lead 3-Scene Quick Switcher Endpoints
# ---------------------------------------------------------------------------
@app.post("/api/scenes/quick")
def set_quick_scene_endpoint(data: dict):
    """One-click transition to Clean, Rhythm, or Lead voicing."""
    scene = str(data.get("scene", "rhythm")).lower()
    with ENGINE_STATE_LOCK:
        active = apply_quick_scene(scene)
    return {
        "success": True,
        "active_scene": active,
        "state": engine.get_state(),
    }


# ---------------------------------------------------------------------------
# Instant A/B Rig Comparison Endpoints
# ---------------------------------------------------------------------------
@app.get("/api/ab/state")
def get_ab_state_endpoint():
    """Returns whether snapshot A is stored and which slot is active."""
    return {
        "has_a": _AB_SNAPSHOT_A is not None,
        "active": _AB_ACTIVE,
    }


@app.post("/api/ab/store")
def store_ab_endpoint():
    """Store current rig settings into snapshot A."""
    with ENGINE_STATE_LOCK:
        store_ab_snapshot()
    return {"success": True, "active": "A", "has_a": True}


@app.post("/api/ab/toggle")
def toggle_ab_endpoint():
    """Toggle between Rig snapshot A and live Rig B."""
    with ENGINE_STATE_LOCK:
        active = toggle_ab_snapshot()
    return {"success": True, "active": active, "state": engine.get_state()}


# ---------------------------------------------------------------------------
# MIDI Learn & Footswitch Mapping Endpoints
# ---------------------------------------------------------------------------
@app.get("/api/midi/status")
def get_midi_status():
    """Returns connected winmm MIDI device count, active mappings, and learn state."""
    return {
        "connected_inputs": len(_midi_listener._handles) if hasattr(_midi_listener, "_handles") else 0,
        "mappings": getattr(_midi_listener, "mappings", {}),
        "learning": getattr(_midi_listener, "learn_target", None) is not None,
        "learn_target": getattr(_midi_listener, "learn_target", None),
        "last_learned": getattr(_midi_listener, "last_learned", None),
    }


@app.post("/api/midi/learn")
def start_midi_learn(data: dict):
    """Arm or cancel MIDI learn for a specific target action (e.g. toggle_screamer, quick_lead)."""
    target = data.get("target") or data.get("action")
    if not target:
        if hasattr(_midi_listener, "cancel_learn"):
            _midi_listener.cancel_learn()
        return {"success": True, "learn_target": None}
    _midi_listener.start_learn(target)
    return {"success": True, "learn_target": target}


@app.post("/api/midi/clear")
def clear_midi_mapping(data: dict):
    """Remove a specific MIDI mapping key."""
    key = data.get("key")
    if key and key in _midi_listener.mappings:
        del _midi_listener.mappings[key]
        _midi_listener.save_mappings()
    return {"success": True, "mappings": _midi_listener.mappings}


@app.post("/api/cortex/preset/load")
def load_cortex_preset_endpoint(data: dict):
    """Loads a multi-scene Cortex preset and activates its default scene."""
    preset_id = data.get("id") or data.get("preset_id")
    target = next((p for p in cortex_mgr.get_presets() if p["id"] == preset_id or p["name"] == preset_id), None)
    if not target and "index" in data:
        idx = int(data["index"])
        presets = cortex_mgr.get_presets()
        if 0 <= idx < len(presets):
            target = presets[idx]
    if not target:
        raise HTTPException(status_code=404, detail="Cortex preset not found")

    with ENGINE_STATE_LOCK:
        engine.chain.nam = None
        cortex_state = cortex_mgr.load_preset(target, chain=engine.chain)
    return {"success": True, "cortex": cortex_state, "state": engine.get_state()}


@app.get("/api/cortex/export")
def export_cortex_preset(name: str = "Cortex Preset"):
    """Export current scenes and workstation chain state into a Cortex-compatible multi-scene JSON format."""
    state = engine.get_state()["chain"]
    doc = {
        "id": f"cortex_{name.lower().replace(' ', '_')}",
        "name": name,
        "author": "NAM Workstation",
        "category": "Custom Multi-Scene",
        "default_scene": cortex_mgr.active_scene_index,
        "base_settings": state,
        "scenes": cortex_mgr.get_scenes(),
    }
    return JSONResponse(
        content=doc,
        headers={"Content-Disposition": f'attachment; filename="{name[:20]}.cortex.json"'}
    )


@app.post("/api/cortex/import")
async def import_cortex_preset_file(file: UploadFile = File(...)):
    """Upload, save, and load a Quad Cortex multi-scene preset file (.cortex.json)."""
    content = await file.read()
    try:
        doc = json.loads(content.decode("utf-8"))
        if not isinstance(doc, dict) or "name" not in doc or "scenes" not in doc:
            raise ValueError("Cortex preset must contain 'name' and 'scenes'")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid .cortex.json format: {e}")

    safe_name = re.sub(r"[^\w\-. ]", "_", doc.get("name") or "custom_cortex").strip()
    save_path = config.CUSTOM_CORTEX_DIR / f"{safe_name}.cortex.json"
    try:
        save_path.write_bytes(content)
    except Exception as e:
        logger.warning(f"Could not persist uploaded cortex preset: {e}")

    with ENGINE_STATE_LOCK:
        engine.chain.nam = None
        cortex_state = cortex_mgr.load_preset(doc, chain=engine.chain)
    return {"success": True, "cortex": cortex_state, "state": engine.get_state()}


@app.post("/api/kemper/import")
async def import_kemper_file(file: UploadFile = File(...)):
    """Upload a Kemper .rigpack or .kipr file, saving to custom_rigs and loading immediately."""
    filename = file.filename or "uploaded.kipr"
    content = await file.read()
    safe_name = re.sub(r"[^\w\-. ]", "_", filename).strip()
    save_path = config.CUSTOM_RIGS_DIR / safe_name
    save_path.write_bytes(content)

    if filename.lower().endswith(".kipr"):
        info = read_single_kipr(str(save_path))
        if not info:
            raise HTTPException(status_code=400, detail="Failed to decode .kipr SysEx data")
        
        # Load into engine
        chain = engine.chain
        with ENGINE_STATE_LOCK:
            chain.nam = None
            params = info.get("params") or {}
            for field, value in params.items():
                if hasattr(chain.amp, field):
                    setattr(chain.amp, field, value)
        return {
            "success": True,
            "type": "kipr",
            "name": info["name"],
            "author": info["author"],
            "amp": info["amp"],
            "state": engine.get_state(),
        }
    elif filename.lower().endswith(".rigpack"):
        return {
            "success": True,
            "type": "rigpack",
            "filename": safe_name,
            "message": "RigPack imported successfully into library.",
        }
    else:
        raise HTTPException(status_code=400, detail="Expected .rigpack or .kipr file")


@app.post("/api/preset/import")
async def universal_preset_import(file: UploadFile = File(...)):
    """
    Universal importer that automatically detects file extension:
    .mo          -> MOOER GE150 preset
    .rigpack     -> KEMPER RigPack
    .kipr        -> KEMPER Rig profile
    .cortex.json -> Quad Cortex multi-scene preset
    .nam         -> Neural Amp Modeler model
    .wav         -> Cabinet Impulse Response
    """
    filename = (file.filename or "").lower()
    if filename.endswith(".mo"):
        return await import_mooer_preset_file(file)
    elif filename.endswith(".cortex.json") or (filename.endswith(".json") and "cortex" in filename):
        return await import_cortex_preset_file(file)
    elif filename.endswith(".rigpack") or filename.endswith(".kipr"):
        return await import_kemper_file(file)
    elif filename.endswith((".nam", ".namb", ".t3kpreset")):
        return await upload_nam_model(file)
    elif filename.endswith(".wav"):
        return await load_custom_ir(file)
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format: {file.filename}. Supported: .mo, .rigpack, .kipr, .cortex.json, .nam, .wav"
        )


# ---------------------------------------------------------------------------
# Kemper Rig Morphing & Studio EQ Endpoints
# ---------------------------------------------------------------------------
@app.get("/api/morph")
def get_morph_state():
    """Returns current morph position, Slot A, and Slot B parameters."""
    return morph_mgr.get_state()


@app.post("/api/morph/set")
def set_morph_position(data: dict):
    """Sets continuous morph position (0.0 Heel to 1.0 Toe)."""
    try:
        pos = float(data.get("pos", data.get("position", 0.0)))
        with ENGINE_STATE_LOCK:
            st = morph_mgr.set_morph(pos, chain=engine.chain)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"success": True, "morph": st, "state": engine.get_state()}


@app.post("/api/morph/capture")
def capture_morph_slot(data: dict):
    """Captures live chain state into Slot A or Slot B."""
    slot = str(data.get("slot", "A"))
    try:
        with ENGINE_STATE_LOCK:
            st = morph_mgr.capture_slot(slot, chain=engine.chain)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"success": True, "morph": st}


@app.delete("/api/morph/{slot}")
def clear_morph_slot(slot: str):
    """Clear a saved A/B snapshot without changing the live audio chain."""
    try:
        with ENGINE_STATE_LOCK:
            st = morph_mgr.clear_slot(slot)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"success": True, "morph": st}


@app.get("/api/eq/curve")
def get_eq_curve():
    """Returns composite 64-point frequency response curve for display."""
    curve = engine.chain.eq.get_curve_points() if hasattr(engine.chain.eq, "get_curve_points") else []
    return {"curve": curve}

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
            samples, source_rate, config.SAMPLE_RATE, config.ir_max_samples(config.SAMPLE_RATE)
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


@app.get("/api/cab/ir-preview")
def get_cab_ir_preview():
    """Return a compact, read-only view of the currently loaded cabinet IR."""
    cab = engine.chain.cab
    samples = getattr(cab, "ir_data", None)
    if samples is None or len(samples) == 0:
        return {"available": False, "name": getattr(cab, "ir_name", "")}

    import numpy as np
    values = np.asarray(samples, dtype=np.float32).reshape(-1)
    # Peak-envelope decimation: bounded payload and useful transient shape.
    bins = 96
    edges = np.linspace(0, len(values), bins + 1, dtype=np.int64)
    envelope = [float(np.max(np.abs(values[edges[i]:max(edges[i] + 1, edges[i + 1])])))
                for i in range(bins)]
    peak = max(envelope) or 1.0
    waveform = [round(value / peak, 4) for value in envelope]
    rate = int(getattr(cab, "sample_rate", config.SAMPLE_RATE))
    return {
        "available": True,
        "name": str(getattr(cab, "ir_name", "Cabinet IR")),
        "sample_rate": rate,
        "samples": int(len(values)),
        "duration_ms": round(len(values) * 1000 / rate, 2) if rate else None,
        "waveform": waveform,
    }


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
                chain.set_device_mode(mode_for_source("tone3000"))
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
        data, sr, config.SAMPLE_RATE, config.ir_max_samples(config.SAMPLE_RATE)
    )

    # Commit only once decoding and validation have fully succeeded.
    with _CAB_IR_LOCK:
        engine.chain.cab.set_ir_data(prepared, display_name)
        engine.chain.cab.enabled = True

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
        text = content.decode("utf-8-sig") if (content[:4] not in (b"BMAN", b"NAMB") and content[:5] != b"T3KHS" and not name.lower().endswith(".t3kpreset")) else ""
    except UnicodeDecodeError as exc:
        raise ValueError(binary_hint) from exc
    if content[:4] in (b"BMAN", b"NAMB"):
        model_dict = nam.parse_namb_binary(content)
        net = nam.SlimmableWaveNet(model_dict, build=quality)
        return nam.NamChain([{"title": re.sub(r"\.(nam|namb|json)$", "", name, flags=re.IGNORECASE), "gear_type": model_dict.get("metadata", {}).get("gear_type", "amp"), "net": net}])
    if content[:5] == b"T3KHS" or name.lower().endswith(".t3kpreset"):
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".t3kpreset", delete=False) as tmp:
            tmp.write(content)
            tmp_path = tmp.name
        try:
            chain_obj = get_nam_chain(tmp_path, quality if quality in ("lite", "full") else "lite")
            if chain_obj is None:
                raise ValueError("No NAM A2 model blocks found in .t3kpreset")
            return chain_obj
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
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
    if not filename.lower().endswith((".nam", ".namb", ".json", ".t3kpreset")):
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
        engine.chain.set_device_mode(mode_for_source("nam"))
        engine.chain.cab.enabled = getattr(getattr(engine, "hd_dsp", None), "force_nam_ir", False) or not new_chain.includes_cab
    try:
        custom_nam_dir = config.PROJECT_ROOT / "custom_nam"
        custom_nam_dir.mkdir(parents=True, exist_ok=True)
        (custom_nam_dir / filename).write_bytes(raw_bytes)
    except OSError:
        pass

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
        engine.chain.set_device_mode("generic")
    return {"success": True, "state": engine.get_state()}

# ------------------------------------------------------------------
@app.get("/api/nam-a2/catalog")
def get_nam_a2_and_ir_catalog():
    """
    Returns the complete catalog of NAM A2 models (Factory T3K A2 + Custom .nam/.namb)
    and Cabinet IRs (24-Bit 44.1kHz Studio IRs + Real T3K WAV IRs + Custom .wav IRs + Classic Cabs).
    """
    from engine.world_class_dsp import STUDIO_24BIT_IRS

    nam_models = []
    for p in list_tone3000_presets():
        if p.get("has_nam"):
            nam_models.append({
                "id": p["id"],
                "title": f"{p.get('amp_name') or p['name']} (NAM A2)",
                "preset_name": p["name"],
                "source": "TONE3000 A2",
                "architecture": "A2 (Slimmable Lite 3ch / Full 8ch)",
                "has_real_ir": bool(p.get("has_real_ir")),
                "cab_name": p.get("cab_name"),
            })
    custom_nam_dir = config.PROJECT_ROOT / "custom_nam"
    if custom_nam_dir.exists():
        for f in sorted(custom_nam_dir.iterdir()):
            if f.is_file() and f.suffix.lower() in (".nam", ".namb", ".json", ".t3kpreset"):
                nam_models.append({
                    "id": f"custom_nam::{f.name}",
                    "title": f"{f.stem} (Custom {f.suffix.upper()})",
                    "preset_name": f.stem,
                    "source": "Custom Upload",
                    "architecture": "A2 Binary (.namb)" if f.suffix.lower() == ".namb" else "NAM A2 / WaveNet",
                    "has_real_ir": False,
                    "cab_name": None,
                })

    ir_list = []
    for ir_title in STUDIO_24BIT_IRS:
        ir_list.append({
            "id": f"studio24::{ir_title}",
            "name": ir_title,
            "type": "24-Bit / 44.1kHz Studio IR",
            "bit_depth": 24,
            "sample_rate": int(getattr(engine, "sample_rate", 44100)),
        })
    for classic in ("Celestion V30 4x12", "Marshall 1960A Greenback", "Mesa Rectifier 4x12 Slant", "Fender Twin 2x12 Jensen"):
        ir_list.append({
            "id": f"classic::{classic}",
            "name": classic,
            "type": "Built-in Cab Model",
            "bit_depth": 24,
            "sample_rate": int(getattr(engine, "sample_rate", 48000)),
        })
    for p in list_tone3000_presets():
        if p.get("has_real_ir"):
            ir_list.append({
                "id": f"t3k_ir::{p['id']}",
                "name": f"{p.get('cab_name') or p['name']} (Real T3K IR)",
                "type": "Recorder-Measured WAV IR",
                "bit_depth": 24,
                "sample_rate": int(p.get("ir_sample_rate") or 48000),
            })
    if config.CUSTOM_IR_DIR.exists():
        for f in sorted(config.CUSTOM_IR_DIR.iterdir()):
            if f.is_file() and f.suffix.lower() == ".wav":
                ir_list.append({
                    "id": f"custom_ir::{f.name}",
                    "name": f.name,
                    "type": "Custom WAV IR",
                    "bit_depth": 24,
                    "sample_rate": int(getattr(engine, "sample_rate", 44100)),
                })

    return {
        "nam_a2_models": nam_models,
        "studio_24bit_irs": list(STUDIO_24BIT_IRS),
        "ir_cabinets": ir_list,
        "active_nam": engine.chain.nam.describe() if engine.chain.nam is not None else None,
        "active_ir": getattr(engine.chain.cab, "ir_name", ""),
        "cab_enabled": bool(engine.chain.cab.enabled),
        "sample_rate": int(engine.sample_rate),
        "bit_depth": int(getattr(getattr(engine, "hd_dsp", None), "bit_depth", 24)),
        "nam_quality": _NAM_QUALITY,
    }


@app.post("/api/nam-a2/load-pair")
def load_nam_a2_and_ir_pair(data: dict):
    """
    Loads a NAM A2 model (from T3K A2 factory or custom_nam/) AND pairs it with a
    Cabinet IR (24-Bit 44.1kHz Studio IR, T3K Real WAV IR, Custom WAV IR, or Classic Cab).
    """
    from engine.world_class_dsp import synthesize_studio_24bit_ir

    global _NAM_QUALITY
    data = data or {}
    nam_id = str(data.get("nam_id") or data.get("nam_model") or "").strip()
    ir_id = str(data.get("ir_id") or data.get("ir_name") or "").strip()
    quality = str(data.get("quality") or _NAM_QUALITY).lower()
    if quality not in ("lite", "full"):
        quality = "lite"
    _NAM_QUALITY = quality

    input_gain_db = float(data.get("input_gain_db", getattr(engine.chain.nam, "input_gain_db", 0.0) if engine.chain.nam else 0.0))
    loaded_nam_info = None
    loaded_ir_name = None

    with ENGINE_STATE_LOCK:
        if nam_id and nam_id != "__keep__":
            if nam_id == "__dsp__":
                engine.chain.nam = None
                engine.chain.set_device_mode("generic")
            elif nam_id.startswith("custom_nam::"):
                fname = os.path.basename(nam_id.split("::", 1)[1])
                fpath = config.PROJECT_ROOT / "custom_nam" / fname
                if not fpath.is_file():
                    raise HTTPException(status_code=404, detail=f"Custom NAM file not found: {fname}")
                new_chain = _build_nam_chain(fpath.read_bytes(), fname, quality)
                new_chain.set_input_gain_db(input_gain_db)
                engine.chain.nam = new_chain
                engine.chain.set_device_mode(mode_for_source("nam"))
                loaded_nam_info = new_chain.describe()
            else:
                presets = list_tone3000_presets()
                target = next((p for p in presets if p["id"] == nam_id or p["file_name"] == nam_id), None)
                if not target:
                    raise HTTPException(status_code=404, detail=f"NAM A2 model not found: {nam_id}")
                new_chain = get_nam_chain(target["file_path"], quality, input_gain_db=input_gain_db)
                if not new_chain:
                    raise HTTPException(status_code=400, detail="Selected preset has no NAM A2 block")
                engine.chain.nam = new_chain
                engine.chain.set_device_mode(mode_for_source("tone3000"))
                loaded_nam_info = new_chain.describe()
                if not ir_id and target.get("has_real_ir"):
                    ir_info = _install_real_t3k_ir(target)
                    if ir_info:
                        loaded_ir_name = ir_info["ir_name"]

        if ir_id and ir_id != "__keep__":
            if ir_id.startswith("studio24::"):
                title = ir_id.split("::", 1)[1]
                ir_samples = synthesize_studio_24bit_ir(title, sample_rate=int(engine.sample_rate))
                with _CAB_IR_LOCK:
                    engine.chain.cab.set_ir_data(ir_samples, title)
                loaded_ir_name = title
            elif ir_id.startswith("classic::"):
                title = ir_id.split("::", 1)[1]
                with _CAB_IR_LOCK:
                    engine.chain.cab.select_cab(title)
                loaded_ir_name = title
            elif ir_id.startswith("t3k_ir::"):
                pid = ir_id.split("::", 1)[1]
                presets = list_tone3000_presets()
                target = next((p for p in presets if p["id"] == pid), None)
                if not target:
                    raise HTTPException(status_code=404, detail=f"T3K IR preset not found: {pid}")
                ir_info = _install_real_t3k_ir(target)
                if ir_info:
                    loaded_ir_name = ir_info["ir_name"]
            elif ir_id.startswith("custom_ir::"):
                fname = os.path.basename(ir_id.split("::", 1)[1])
                fpath = config.CUSTOM_IR_DIR / fname
                if not fpath.is_file():
                    raise HTTPException(status_code=404, detail=f"Custom IR file not found: {fname}")
                name_out, _, _, _ = _decode_and_install_ir(fpath.read_bytes(), fname)
                loaded_ir_name = name_out
            else:
                if any(k in ir_id.lower() for k in ("24-bit", "ozzy", "neural archetype", "basketweave")):
                    ir_samples = synthesize_studio_24bit_ir(ir_id, sample_rate=int(engine.sample_rate))
                    with _CAB_IR_LOCK:
                        engine.chain.cab.set_ir_data(ir_samples, ir_id)
                elif (config.CUSTOM_IR_DIR / os.path.basename(ir_id)).is_file():
                    fpath = config.CUSTOM_IR_DIR / os.path.basename(ir_id)
                    name_out, _, _, _ = _decode_and_install_ir(fpath.read_bytes(), fpath.name)
                    loaded_ir_name = name_out
                else:
                    with _CAB_IR_LOCK:
                        engine.chain.cab.select_cab(ir_id)
                loaded_ir_name = ir_id

            engine.chain.cab.enabled = True

        if "cab_enabled" in data or "enable_cab" in data:
            engine.chain.cab.enabled = bool(data.get("cab_enabled", data.get("enable_cab", True)))
        elif loaded_nam_info is not None and not (ir_id and ir_id != "__keep__"):
            # A capture that already contains the cabinet must not go through a second IR.
            force = getattr(getattr(engine, "hd_dsp", None), "force_nam_ir", False)
            engine.chain.cab.enabled = force or not engine.chain.nam.includes_cab

    return {
        "success": True,
        "loaded_nam": loaded_nam_info or (engine.chain.nam.describe() if engine.chain.nam else None),
        "loaded_ir": loaded_ir_name or getattr(engine.chain.cab, "ir_name", ""),
        "quality": _NAM_QUALITY,
        "state": engine.get_state(),
    }


@app.post("/api/audio/24bit-44k")
def activate_24bit_44100_studio_mode(data: dict = None):
    """
    One-click switch to 24-Bit / 44.1 kHz (44,100 Hz) Natural Dynamic Studio Mode
    (or custom sample_rate / bit_depth) with Ozzy/Neural Touch Sensitivity.
    """
    data = data or {}
    default_sr = int(getattr(engine, "sample_rate", 48000) or 48000)
    target_sr = int(data.get("sample_rate", default_sr))
    if target_sr not in (44100, 48000, 88200, 96000):
        target_sr = default_sr
    target_bits = int(data.get("bit_depth", 24))
    if target_bits not in (24, 32):
        target_bits = 24

    with ENGINE_STATE_LOCK:
        engine.apply_sample_rate(target_sr)
        if getattr(engine, "hd_dsp", None) is not None:
            engine.hd_dsp.update_settings({
                "enabled": True,
                "bit_depth": target_bits,
                "touch_sensitivity": float(data.get("touch_sensitivity", 0.88)),
                "anti_squash": float(data.get("anti_squash", 0.78)),
                "ozzy_doubler": bool(data.get("ozzy_doubler", engine.hd_dsp.ozzy_doubler)),
            })
        cur_ir = str(getattr(engine.chain.cab, "ir_name", ""))
        if any(k in cur_ir.lower() for k in ("24-bit", "ozzy", "neural archetype", "basketweave")):
            from engine.world_class_dsp import synthesize_studio_24bit_ir
            with _CAB_IR_LOCK:
                engine.chain.cab.set_ir_data(synthesize_studio_24bit_ir(cur_ir, sample_rate=target_sr), cur_ir)

    if engine.is_running:
        engine.start(
            input_id=engine.input_device,
            output_id=engine.output_device,
            sample_rate=engine.sample_rate,
            block_size=engine.block_size,
        )
    persist_audio_path()
    return {
        "success": True,
        "sample_rate": engine.sample_rate,
        "bit_depth": target_bits,
        "hd_audio": engine.hd_dsp.get_status() if getattr(engine, "hd_dsp", None) else None,
        "state": engine.get_state(),
    }

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
        engine.chain.set_device_mode(mode_for_source("tone3000"))
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


_SERVER_CALLBACK_CACHE: dict[str, tuple[float, HTMLResponse]] = {}
_SERVER_CALLBACK_LOCK = threading.RLock()
_SERVER_CALLBACK_IN_FLIGHT: dict[str, threading.Event] = {}


@app.get("/api/t3k/callback", response_class=HTMLResponse)
def t3k_callback(request: Request):
    query = {k: v for k, v in request.query_params.items()}
    code = query.get("code")
    state = query.get("state")
    cache_key = str(code).strip() if code else (str(state).strip() if state else None)

    # Prevent duplicate callback invocations from consuming single-use authorization code twice
    if cache_key:
        with _SERVER_CALLBACK_LOCK:
            now = time.time()
            for k in list(_SERVER_CALLBACK_CACHE.keys()):
                if _SERVER_CALLBACK_CACHE[k][0] < now - 900:
                    _SERVER_CALLBACK_CACHE.pop(k, None)

            if cache_key in _SERVER_CALLBACK_CACHE:
                logger.info("Serving cached callback HTML response for key: %s", cache_key)
                return _SERVER_CALLBACK_CACHE[cache_key][1]

            in_flight = _SERVER_CALLBACK_IN_FLIGHT.get(cache_key)

        if in_flight is not None:
            in_flight.wait(timeout=30)
            with _SERVER_CALLBACK_LOCK:
                if cache_key in _SERVER_CALLBACK_CACHE:
                    return _SERVER_CALLBACK_CACHE[cache_key][1]

    event = threading.Event()
    if cache_key:
        with _SERVER_CALLBACK_LOCK:
            _SERVER_CALLBACK_IN_FLIGHT[cache_key] = event

    try:
        try:
            result = t3k.handle_callback(query)
        except t3k.T3KError as exc:
            upstream_detail = getattr(exc, "response_text", None) or getattr(exc, "details", None)
            if upstream_detail:
                logger.warning("TONE3000 callback rejected: %s (upstream: %s)", exc, upstream_detail)
            else:
                logger.warning("TONE3000 callback rejected: %s", exc)
            return HTMLResponse(_t3k_result_page(False, "เชื่อมต่อไม่สำเร็จ", str(exc)), status_code=400)

        if result["canceled"] and not result["tone_id"]:
            _T3K_STATE["cancel_seq"] += 1
            resp = HTMLResponse(_t3k_result_page(
                True, "ยกเลิกแล้ว", "ยังไม่ได้เลือกเสียง — เปิด TONE3000 แล้วเลือกใหม่ได้ทุกเมื่อ"))
            if cache_key:
                with _SERVER_CALLBACK_LOCK:
                    _SERVER_CALLBACK_CACHE[cache_key] = (time.time(), resp)
            return resp

        if not result["tone_id"]:
            return HTMLResponse(_t3k_result_page(
                False, "ไม่พบเสียง", "TONE3000 ไม่ได้ส่ง tone_id กลับมา"), status_code=400)

        try:
            info = _install_t3k_tone(result["tone_id"])
        except t3k.T3KError as exc:
            upstream_detail = getattr(exc, "response_text", None) or getattr(exc, "details", None)
            if upstream_detail:
                logger.warning("TONE3000 download failed: %s (upstream: %s)", exc, upstream_detail)
            else:
                logger.warning("TONE3000 download failed: %s", exc)
            return HTMLResponse(_t3k_result_page(False, "โหลดเสียงไม่สำเร็จ", str(exc)), status_code=502)
        except ValueError as exc:
            return HTMLResponse(_t3k_result_page(False, "โหลดเสียงไม่สำเร็จ", str(exc)), status_code=400)

        resp = HTMLResponse(_t3k_result_page(
            True, "โหลดเสียงเรียบร้อย",
            "เสียงถูกติดตั้งเข้า NAM AMP ในแท็บที่เปิดแอปอยู่แล้ว", info))
        if cache_key:
            with _SERVER_CALLBACK_LOCK:
                _SERVER_CALLBACK_CACHE[cache_key] = (time.time(), resp)
        return resp
    finally:
        if cache_key:
            event.set()
            with _SERVER_CALLBACK_LOCK:
                _SERVER_CALLBACK_IN_FLIGHT.pop(cache_key, None)


# Serve frontend
if os.path.exists(WEB_DIR):
    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

@app.get("/")
def index():
    return FileResponse(
        os.path.join(WEB_DIR, "index.html"),
        headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0", "Pragma": "no-cache"},
    )


@app.middleware("http")
async def _disable_static_cache(request: Request, call_next):
    resp = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/static/"):
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        resp.headers["Pragma"] = "no-cache"
    return resp

@app.get("/manus-routes.json")
def manus_routes():
    """Expose the page route inventory without falling back to the SPA shell."""
    return FileResponse(os.path.join(WEB_DIR, "manus-routes.json"), media_type="application/json")

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
