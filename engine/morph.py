"""Persistent A/B parameter snapshots and continuous morph control."""

import contextlib
import json
import math
import os
import sqlite3
import threading
from typing import Any, Dict


class MorphController:
    """Own the stored A/B snapshots and apply their supported parameters."""

    DEFAULTS = {
        "slot_a": {
            "amp_gain": 0.40,
            "amp_master": 0.70,
            "screamer_drive": 0.20,
            "screamer_level": 0.70,
            "delay_mix": 0.15,
            "reverb_mix": 0.18,
            "screamer_enabled": 0.0,
            "delay_enabled": 0.0,
        },
        "slot_b": {
            "amp_gain": 0.85,
            "amp_master": 0.85,
            "screamer_drive": 0.50,
            "screamer_level": 0.85,
            "delay_mix": 0.38,
            "reverb_mix": 0.32,
            "screamer_enabled": 1.0,
            "delay_enabled": 1.0,
        },
    }

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or os.path.join(os.path.dirname(__file__), "..", "presets.db")
        self._lock = threading.RLock()
        self.morph_pos = 0.0
        self.slot_a = dict(self.DEFAULTS["slot_a"])
        self.slot_b = dict(self.DEFAULTS["slot_b"])
        self.captured = {"A": False, "B": False}
        self._captured_at = {"A": None, "B": None}
        self._init_storage()

    def _connect(self):
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        return sqlite3.connect(self.db_path, timeout=5.0)

    @contextlib.contextmanager
    def _session(self):
        """One unit of work: commit on success, roll back on error, always close.

        `with sqlite3.connect(...) as conn` only wraps the *transaction* -- it
        commits or rolls back and leaves the handle open.  CPython's statement
        cache holds a reference back to the connection, so refcounting does not
        reclaim it either, and `presets.db` stays locked on Windows.  closing()
        is what actually releases the handle.
        """
        conn = self._connect()
        with contextlib.closing(conn):
            with conn:
                yield conn

    def _init_storage(self):
        with self._session() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS morph_slots (
                    slot TEXT PRIMARY KEY CHECK (slot IN ('A', 'B')),
                    settings_json TEXT NOT NULL,
                    captured_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            for slot in ("A", "B"):
                row = conn.execute("SELECT settings_json, captured_at FROM morph_slots WHERE slot = ?", (slot,)).fetchone()
                if row:
                    try:
                        settings = json.loads(row[0])
                        self._validate_snapshot(settings)
                    except (TypeError, ValueError, json.JSONDecodeError):
                        conn.execute("DELETE FROM morph_slots WHERE slot = ?", (slot,))
                    else:
                        setattr(self, f"slot_{slot.lower()}", settings)
                        self.captured[slot] = True
                        self._captured_at[slot] = row[1]

    @staticmethod
    def _validate_snapshot(settings):
        if not isinstance(settings, dict) or set(settings) != set(MorphController.DEFAULTS["slot_a"]):
            raise ValueError("Morph snapshot does not match the supported parameter schema")
        if any(not isinstance(value, (int, float)) or not math.isfinite(value) for value in settings.values()):
            raise ValueError("Morph slot parameters must be finite numbers")

    def get_state(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "morph_pos": round(self.morph_pos, 3),
                "slot_a": dict(self.slot_a),
                "slot_b": dict(self.slot_b),
                "captured": dict(self.captured),
                "captured_at": self._captured_at.copy(),
            }

    def capture_slot(self, slot_name: str, chain) -> Dict[str, Any]:
        """Capture and persist the currently audible supported chain parameters."""
        slot = str(slot_name).strip().upper()
        if slot not in {"A", "B"}:
            raise ValueError("Morph slot must be 'A' or 'B'")
        if chain is None or not all(hasattr(chain, name) for name in ("amp", "screamer", "delay", "reverb")):
            raise ValueError("A complete signal chain is required to capture a morph slot")

        snapshot = {
            "amp_gain": float(chain.amp.gain),
            "amp_master": float(chain.amp.master),
            "screamer_drive": float(chain.screamer.drive),
            "screamer_level": float(chain.screamer.level),
            "delay_mix": float(chain.delay.mix),
            "reverb_mix": float(chain.reverb.mix),
            "screamer_enabled": 1.0 if chain.screamer.enabled else 0.0,
            "delay_enabled": 1.0 if chain.delay.enabled else 0.0,
        }
        self._validate_snapshot(snapshot)
        with self._lock:
            with self._session() as conn:
                conn.execute(
                    "INSERT INTO morph_slots(slot, settings_json, captured_at) VALUES (?, ?, CURRENT_TIMESTAMP) "
                    "ON CONFLICT(slot) DO UPDATE SET settings_json=excluded.settings_json, captured_at=excluded.captured_at",
                    (slot, json.dumps(snapshot, allow_nan=False, sort_keys=True)),
                )
                row = conn.execute("SELECT captured_at FROM morph_slots WHERE slot = ?", (slot,)).fetchone()
            setattr(self, f"slot_{slot.lower()}", snapshot)
            self.captured[slot] = True
            self._captured_at[slot] = row[0] if row else None
            return self.get_state()

    def clear_slot(self, slot_name: str) -> Dict[str, Any]:
        """Clear a saved slot and report it as empty."""
        slot = str(slot_name).strip().upper()
        if slot not in {"A", "B"}:
            raise ValueError("Morph slot must be 'A' or 'B'")
        with self._lock:
            with self._session() as conn:
                conn.execute("DELETE FROM morph_slots WHERE slot = ?", (slot,))
            setattr(self, f"slot_{slot.lower()}", dict(self.DEFAULTS[f"slot_{slot.lower()}"]))
            self.captured[slot] = False
            self._captured_at[slot] = None
            return self.get_state()

    def set_morph(self, pos: float, chain=None) -> Dict[str, Any]:
        """Set a bounded morph position and apply linear parameter interpolation."""
        pos = float(pos)
        if not math.isfinite(pos):
            raise ValueError("Morph position must be a finite number")
        with self._lock:
            self.morph_pos = max(0.0, min(1.0, pos))
            t = self.morph_pos
            if chain is not None:
                a, b = self.slot_a, self.slot_b
                if hasattr(chain, "amp"):
                    chain.amp.gain = (1 - t) * a["amp_gain"] + t * b["amp_gain"]
                    chain.amp.master = (1 - t) * a["amp_master"] + t * b["amp_master"]
                if hasattr(chain, "screamer"):
                    chain.screamer.drive = (1 - t) * a["screamer_drive"] + t * b["screamer_drive"]
                    chain.screamer.level = (1 - t) * a["screamer_level"] + t * b["screamer_level"]
                    chain.screamer.enabled = ((1 - t) * a["screamer_enabled"] + t * b["screamer_enabled"]) >= 0.5
                if hasattr(chain, "delay"):
                    chain.delay.mix = (1 - t) * a["delay_mix"] + t * b["delay_mix"]
                    chain.delay.enabled = ((1 - t) * a["delay_enabled"] + t * b["delay_enabled"]) >= 0.5
                if hasattr(chain, "reverb"):
                    chain.reverb.mix = (1 - t) * a["reverb_mix"] + t * b["reverb_mix"]
            return self.get_state()
