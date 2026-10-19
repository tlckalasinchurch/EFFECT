import json
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "presets.db")

DEFAULT_PRESETS = [
    {
        "id": "5150_metal",
        "name": "5150 High Gain Metal",
        "category": "Metal / Lead",
        "author": "กดจนหลอนTone",
        "settings": {
            "gate": {"enabled": True, "threshold": -50.0},
            "screamer": {"enabled": True, "drive": 0.2, "tone": 0.7, "level": 0.8},
            "amp": {"enabled": True, "gain": 0.75, "bass": 0.55, "mid": 0.45, "treble": 0.65, "presence": 0.65, "master": 0.7, "model": "5150"},
            "cab": {"enabled": True, "ir_name": "Mesa Rectifier 4x12 Slant"},
            "delay": {"enabled": False, "time": 0.35, "feedback": 0.3, "mix": 0.2},
            "reverb": {"enabled": True, "decay": 0.3, "mix": 0.15}
        }
    },
    {
        "id": "plexi_crunch",
        "name": "Plexi 70s British Crunch",
        "category": "Classic Rock",
        "author": "กดจนหลอนTone",
        "settings": {
            "gate": {"enabled": False, "threshold": -60.0},
            "screamer": {"enabled": False, "drive": 0.4, "tone": 0.5, "level": 0.6},
            "amp": {"enabled": True, "gain": 0.55, "bass": 0.6, "mid": 0.65, "treble": 0.6, "presence": 0.5, "master": 0.8, "model": "Plexi"},
            "cab": {"enabled": True, "ir_name": "Marshall 1960A Greenback"},
            "delay": {"enabled": False, "time": 0.28, "feedback": 0.25, "mix": 0.2},
            "reverb": {"enabled": True, "decay": 0.4, "mix": 0.2}
        }
    },
    {
        "id": "twin_clean",
        "name": "Fender Twin Sparkling Clean",
        "category": "Clean / Jazz",
        "author": "กดจนหลอนTone",
        "settings": {
            "gate": {"enabled": False, "threshold": -60.0},
            "screamer": {"enabled": False, "drive": 0.1, "tone": 0.5, "level": 0.5},
            "amp": {"enabled": True, "gain": 0.25, "bass": 0.5, "mid": 0.45, "treble": 0.7, "presence": 0.6, "master": 0.8, "model": "Twin"},
            "cab": {"enabled": True, "ir_name": "Fender Twin 2x12 Jensen"},
            "delay": {"enabled": False, "time": 0.38, "feedback": 0.3, "mix": 0.25},
            "reverb": {"enabled": True, "decay": 0.65, "mix": 0.35}
        }
    },
    {
        "id": "texas_blues",
        "name": "Texas Blues Solo Lead",
        "category": "Blues / Rock",
        "author": "กดจนหลอนTone",
        "settings": {
            "gate": {"enabled": True, "threshold": -58.0},
            "screamer": {"enabled": True, "drive": 0.65, "tone": 0.6, "level": 0.75},
            "amp": {"enabled": True, "gain": 0.5, "bass": 0.55, "mid": 0.6, "treble": 0.65, "presence": 0.55, "master": 0.75, "model": "Plexi"},
            "cab": {"enabled": True, "ir_name": "Celestion V30 4x12"},
            "delay": {"enabled": True, "time": 0.34, "feedback": 0.35, "mix": 0.28},
            "reverb": {"enabled": True, "decay": 0.5, "mix": 0.22}
        }
    },
    {
        "id": "ambient_dream",
        "name": "Ambient Chime & Clouds",
        "category": "Ambient",
        "author": "กดจนหลอนTone",
        "settings": {
            "gate": {"enabled": False, "threshold": -60.0},
            "screamer": {"enabled": False, "drive": 0.1, "tone": 0.5, "level": 0.5},
            "amp": {"enabled": True, "gain": 0.3, "bass": 0.45, "mid": 0.5, "treble": 0.65, "presence": 0.7, "master": 0.75, "model": "Twin"},
            "cab": {"enabled": True, "ir_name": "Celestion V30 4x12"},
            "delay": {"enabled": True, "time": 0.45, "feedback": 0.55, "mix": 0.45},
            "reverb": {"enabled": True, "decay": 0.85, "mix": 0.5}
        }
    }
]

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS presets (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            category TEXT,
            author TEXT,
            settings_json TEXT NOT NULL
        )
    """)
    # Insert default presets if empty
    c.execute("SELECT COUNT(*) FROM presets")
    if c.fetchone()[0] == 0:
        for p in DEFAULT_PRESETS:
            c.execute(
                "INSERT INTO presets (id, name, category, author, settings_json) VALUES (?, ?, ?, ?, ?)",
                (p["id"], p["name"], p["category"], p["author"], json.dumps(p["settings"]))
            )
        conn.commit()
    conn.close()

def get_all_presets():
    init_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, name, category, author, settings_json FROM presets")
    presets = []
    for row in c.fetchall():
        presets.append({
            "id": row[0],
            "name": row[1],
            "category": row[2],
            "author": row[3],
            "settings": json.loads(row[4])
        })
    conn.close()
    return presets

def save_preset(preset_id, name, category, author, settings):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT OR REPLACE INTO presets (id, name, category, author, settings_json) VALUES (?, ?, ?, ?, ?)",
        (preset_id, name, category, author, json.dumps(settings))
    )
    conn.commit()
    conn.close()
