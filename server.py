from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel
import os
import re
import logging
import threading

import config
from setup_logging import get_logger

from engine.audio import AudioEngine
from engine.presets import get_all_presets, save_preset
from engine.kemper_importer import (
    list_installed_kemper_packs,
    read_rigs_from_pack,
    search_packs,
    list_categories,
)
from engine.tone3000_importer import list_tone3000_presets

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
    in_id = data.get("input_id") if data else None
    out_id = data.get("output_id") if data else None
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
    if sec == "gate":
        if p == "enabled": chain.noise_gate.enabled = bool(val)
        elif p == "threshold": chain.noise_gate.threshold_db = float(val)
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
        elif p == "model": chain.amp.model = str(val)
    elif sec == "cab":
        if p == "enabled": chain.cab.enabled = bool(val)
        elif p == "ir_name":
            # Previously this only renamed the cabinet. Selecting a cab must
            # actually install that cabinet's IR or the tone never changes.
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
        
    s = target["settings"]
    chain = engine.chain
    
    # Apply gate
    chain.noise_gate.enabled = s["gate"].get("enabled", True)
    chain.noise_gate.threshold_db = s["gate"].get("threshold", -55.0)
    
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
    
    # Apply delay
    chain.delay.enabled = s["delay"].get("enabled", False)
    chain.delay.time_sec = s["delay"].get("time", 0.35)
    chain.delay.feedback = s["delay"].get("feedback", 0.35)
    chain.delay.mix = s["delay"].get("mix", 0.25)
    
    # Apply reverb
    chain.reverb.enabled = s["reverb"].get("enabled", False)
    chain.reverb.decay = s["reverb"].get("decay", 0.5)
    chain.reverb.mix = s["reverb"].get("mix", 0.2)
    
    return {"success": True, "loaded_preset": target, "state": engine.get_state()}

@app.post("/api/preset/save")
def create_preset(req: PresetSave):
    curr_state = engine.get_state()["chain"]
    save_preset(req.id, req.name, req.category, req.author, curr_state)
    return {"success": True, "message": "Preset saved"}

class KemperRigLoad(BaseModel):
    name: str
    author: str = "Kemper"

@app.get("/api/kemper/categories")
def kemper_categories():
    """Distinct instrument categories (Guitar / Bass / Acoustic) with counts."""
    return {"categories": list_categories()}

@app.get("/api/kemper/search")
def kemper_search(q: str = "", category: str | None = None, limit: int = 100,
                  include_amp: bool = False):
    """
    Search every installed rig pack.

    `include_amp` also decodes each rig's SysEx payload so the source amp,
    brand, model and cabinet name match the query. That costs one decode per
    rig, so it is opt-in.
    """
    limit = max(1, min(int(limit), 2000))
    hits = search_packs(q, category=category, limit=limit, include_amp=include_amp)
    return {"query": q, "category": category, "count": len(hits), "results": hits}

@app.post("/api/kemper/load")
def load_kemper_rig(req: KemperRigLoad):
    name_lower = req.name.lower()
    chain = engine.chain

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

    return {
        "success": True,
        "name": req.name,
        "author": req.author,
        "category": category,
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

class Tone3000Load(BaseModel):
    id: str

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
    cid = target["id"]

    if cid == "t3k_ampeg_bass_drive":
        chain.amp.model = "Clean"
        chain.amp.gain = 0.35
        chain.amp.bass = 0.75
        chain.amp.mid = 0.50
        chain.amp.treble = 0.45
        chain.amp.presence = 0.40
        chain.amp.master = 0.85
        chain.screamer.enabled = False
        chain.cab.enabled = True
        chain.cab.select_cab("Fender Twin 2x12 Jensen")
        chain.delay.enabled = False
        chain.reverb.enabled = False
    elif cid == "t3k_bogner_fullstack":
        chain.amp.model = "5150"
        chain.amp.gain = 0.78
        chain.amp.bass = 0.55
        chain.amp.mid = 0.52
        chain.amp.treble = 0.65
        chain.amp.presence = 0.60
        chain.amp.master = 0.72
        chain.screamer.enabled = True
        chain.screamer.drive = 0.25
        chain.screamer.tone = 0.65
        chain.screamer.level = 0.80
        chain.cab.enabled = True
        chain.cab.select_cab("Mesa Rectifier 4x12 Slant")
        chain.delay.enabled = False
        chain.reverb.enabled = True
        chain.reverb.decay = 0.25
        chain.reverb.mix = 0.15
    elif cid == "t3k_dumble_spread":
        chain.amp.model = "Plexi"
        chain.amp.gain = 0.52
        chain.amp.bass = 0.55
        chain.amp.mid = 0.62
        chain.amp.treble = 0.60
        chain.amp.presence = 0.55
        chain.amp.master = 0.78
        chain.screamer.enabled = True
        chain.screamer.drive = 0.30
        chain.screamer.tone = 0.55
        chain.screamer.level = 0.75
        chain.cab.enabled = True
        chain.cab.select_cab("Marshall 1960A Greenback")
        chain.delay.enabled = False
        chain.reverb.enabled = True
        chain.reverb.decay = 0.45
        chain.reverb.mix = 0.22
    elif cid == "t3k_marshall_bluesbreaker":
        chain.amp.model = "Plexi"
        chain.amp.gain = 0.55
        chain.amp.bass = 0.60
        chain.amp.mid = 0.58
        chain.amp.treble = 0.55
        chain.amp.presence = 0.50
        chain.amp.master = 0.80
        chain.screamer.enabled = False
        chain.cab.enabled = True
        chain.cab.select_cab("Marshall 1960A Greenback")
        chain.delay.enabled = False
        chain.reverb.enabled = True
        chain.reverb.decay = 0.35
        chain.reverb.mix = 0.18
    elif cid == "t3k_matchless_crunch":
        chain.amp.model = "Plexi"
        chain.amp.gain = 0.50
        chain.amp.bass = 0.50
        chain.amp.mid = 0.65
        chain.amp.treble = 0.68
        chain.amp.presence = 0.60
        chain.amp.master = 0.75
        chain.screamer.enabled = True
        chain.screamer.drive = 0.20
        chain.screamer.tone = 0.60
        chain.screamer.level = 0.70
        chain.cab.enabled = True
        chain.cab.select_cab("Celestion V30 4x12")
        chain.delay.enabled = False
        chain.reverb.enabled = True
        chain.reverb.decay = 0.30
        chain.reverb.mix = 0.15
    elif cid == "t3k_mesa_pitch_shift":
        chain.amp.model = "5150"
        chain.amp.gain = 0.82
        chain.amp.bass = 0.62
        chain.amp.mid = 0.48
        chain.amp.treble = 0.65
        chain.amp.presence = 0.65
        chain.amp.master = 0.70
        chain.screamer.enabled = True
        chain.screamer.drive = 0.30
        chain.screamer.tone = 0.70
        chain.screamer.level = 0.85
        chain.cab.enabled = True
        chain.cab.select_cab("Mesa Rectifier 4x12 Slant")
        chain.delay.enabled = True
        chain.delay.time_sec = 0.32
        chain.delay.feedback = 0.30
        chain.delay.mix = 0.22
        chain.reverb.enabled = True
        chain.reverb.decay = 0.40
        chain.reverb.mix = 0.20
    elif cid == "t3k_stereo_crunch_verb":
        chain.amp.model = "Plexi"
        chain.amp.gain = 0.48
        chain.amp.bass = 0.50
        chain.amp.mid = 0.55
        chain.amp.treble = 0.65
        chain.amp.presence = 0.65
        chain.amp.master = 0.75
        chain.screamer.enabled = True
        chain.screamer.drive = 0.35
        chain.screamer.tone = 0.65
        chain.screamer.level = 0.75
        chain.cab.enabled = True
        chain.cab.select_cab("Celestion V30 4x12")
        chain.delay.enabled = True
        chain.delay.time_sec = 0.45
        chain.delay.feedback = 0.45
        chain.delay.mix = 0.35
        chain.reverb.enabled = True
        chain.reverb.decay = 0.75
        chain.reverb.mix = 0.40
    elif cid == "t3k_stereo_fuzz":
        chain.amp.model = "5150"
        chain.amp.gain = 0.85
        chain.amp.bass = 0.65
        chain.amp.mid = 0.50
        chain.amp.treble = 0.60
        chain.amp.presence = 0.55
        chain.amp.master = 0.70
        chain.screamer.enabled = True
        chain.screamer.drive = 0.85
        chain.screamer.tone = 0.50
        chain.screamer.level = 0.85
        chain.cab.enabled = True
        chain.cab.select_cab("Marshall 1960A Greenback")
        chain.delay.enabled = False
        chain.reverb.enabled = True
        chain.reverb.decay = 0.35
        chain.reverb.mix = 0.20

    return {
        "success": True,
        "preset": target,
        "state": engine.get_state()
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

# Serve frontend
if os.path.exists(WEB_DIR):
    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

@app.get("/")
def index():
    return FileResponse(os.path.join(WEB_DIR, "index.html"))

if __name__ == "__main__":
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=False)
