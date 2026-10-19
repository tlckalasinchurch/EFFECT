from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
import os
import logging

import config
from setup_logging import get_logger

from engine.audio import AudioEngine
from engine.presets import get_all_presets, save_preset
from engine.kemper_importer import list_installed_kemper_packs, read_rigs_from_pack
from engine.tone3000_importer import list_tone3000_presets

# Setup logger
logger = get_logger(__name__)

app = FastAPI(title="กดจนหลอนTone")
engine = AudioEngine()

WEB_DIR = config.WEB_DIR

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
        elif p == "ir_name": chain.cab.ir_name = str(val)
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
    chain.cab.ir_name = s["cab"].get("ir_name", "Celestion V30 4x12")
    
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
        chain.cab.ir_name = "Fender Twin 2x12 Jensen"
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
        chain.cab.ir_name = "Marshall 1960A Greenback"
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
        chain.cab.ir_name = "Mesa Rectifier 4x12 Slant"
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
        chain.cab.ir_name = "Celestion V30 4x12"
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
def get_kemper_rigs(pack_path: str):
    return {"rigs": read_rigs_from_pack(pack_path)}

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
        chain.cab.ir_name = "Fender Twin 2x12 Jensen"
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
        chain.cab.ir_name = "Mesa Rectifier 4x12 Slant"
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
        chain.cab.ir_name = "Marshall 1960A Greenback"
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
        chain.cab.ir_name = "Marshall 1960A Greenback"
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
        chain.cab.ir_name = "Celestion V30 4x12"
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
        chain.cab.ir_name = "Mesa Rectifier 4x12 Slant"
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
        chain.cab.ir_name = "Celestion V30 4x12"
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
        chain.cab.ir_name = "Marshall 1960A Greenback"
        chain.delay.enabled = False
        chain.reverb.enabled = True
        chain.reverb.decay = 0.35
        chain.reverb.mix = 0.20

    return {
        "success": True,
        "preset": target,
        "state": engine.get_state()
    }

# Serve frontend
if os.path.exists(WEB_DIR):
    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

@app.get("/")
def index():
    return FileResponse(os.path.join(WEB_DIR, "index.html"))

if __name__ == "__main__":
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=False)
