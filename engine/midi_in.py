"""
MIDI CC scene switching & footswitch mapping for the guitar workstation.

Listens on every MIDI input device through Windows winmm (ctypes, no extra
dependency). Supports:
- Quad Cortex scene switching: CC 43 with value 0-7 selects scene A-H
- MIDI Learn & configurable footswitch actions (bypass, scenes, tap tempo, A/B)
"""

import ctypes
import json
import logging
import os
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

SCENE_CC = 43
SCENE_COUNT = 8

_MIM_DATA = 0x3C3
_CALLBACK_FUNCTION = 0x30000
MAPPINGS_FILE = Path(__file__).resolve().parent.parent / "midi_mappings.json"

DEFAULT_MAPPINGS = {
    "cc_80": "toggle_screamer",
    "cc_81": "toggle_delay",
    "cc_82": "toggle_reverb",
    "cc_64": "tap_tempo",
    "cc_48": "quick_clean",
    "cc_49": "quick_rhythm",
    "cc_50": "quick_lead",
    "cc_51": "toggle_ab",
}


def scene_from_message(status: int, data1: int, data2: int, channel: Optional[int] = None) -> Optional[int]:
    """Return the scene index a MIDI message selects, or None if it selects none.

    channel is 0-15, or None to accept any channel.
    """
    if status & 0xF0 != 0xB0 or data1 != SCENE_CC or data2 >= SCENE_COUNT:
        return None
    if channel is not None and status & 0x0F != channel:
        return None
    return data2


class MidiSceneListener:
    """Opens all MIDI inputs and dispatches scene and footswitch actions from winmm thread."""

    def __init__(self, on_scene: Callable[[int], None], channel: Optional[int] = None, on_action: Optional[Callable[[str, int], None]] = None):
        self._on_scene = on_scene
        self._on_action = on_action
        self._channel = channel
        self._handles: List[ctypes.c_void_p] = []
        self._winmm = None
        self.learn_target: Optional[str] = None
        self.last_learned: Optional[Dict[str, str]] = None
        self.mappings: Dict[str, str] = dict(DEFAULT_MAPPINGS)
        self.load_mappings()

        # winmm keeps this pointer; it must outlive every open handle.
        if sys.platform == "win32":
            self._proto = ctypes.WINFUNCTYPE(
                None, ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_size_t
            )
            self._callback = self._proto(self._on_midi)
        else:
            self._proto = None
            self._callback = None

    def load_mappings(self):
        if MAPPINGS_FILE.exists():
            try:
                with open(MAPPINGS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    self.mappings.update(data)
            except Exception:
                pass

    def save_mappings(self):
        try:
            with open(MAPPINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(self.mappings, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save MIDI mappings: {e}")

    def start_learn(self, target: str):
        self.learn_target = str(target)
        self.last_learned = None

    def cancel_learn(self):
        self.learn_target = None

    def _on_midi(self, _h, msg, _inst, p1, _p2):
        if msg != _MIM_DATA:
            return
        status = p1 & 0xFF
        data1 = (p1 >> 8) & 0xFF
        data2 = (p1 >> 16) & 0xFF

        msg_type = status & 0xF0
        ch = status & 0x0F
        if self._channel is not None and ch != self._channel:
            return

        # Determine key (e.g. cc_43 or pc_1)
        if msg_type == 0xB0:
            key = f"cc_{data1}"
        elif msg_type == 0xC0:
            key = f"pc_{data1}"
        elif msg_type == 0x90 and data2 > 0:
            key = f"note_{data1}"
        else:
            return

        # MIDI Learn handling
        if self.learn_target:
            target = self.learn_target
            self.mappings[key] = target
            self.last_learned = {"key": key, "action": target}
            self.learn_target = None
            self.save_mappings()
            logger.info("MIDI Learned: %s -> %s", key, target)
            return

        # Default Scene CC check
        scene = scene_from_message(status, data1, data2, self._channel)
        if scene is not None:
            try:
                self._on_scene(scene)
            except Exception:
                logger.exception("MIDI scene switch failed")
            return

        # Custom Footswitch Action check
        action = self.mappings.get(key)
        if action and self._on_action:
            try:
                self._on_action(action, data2)
            except Exception:
                logger.exception("MIDI action %s execution failed", action)

    def start(self) -> int:
        """Open every input device; returns how many opened (0 off Windows)."""
        if sys.platform != "win32":
            return 0
        self._winmm = ctypes.WinDLL("winmm")
        for dev in range(self._winmm.midiInGetNumDevs()):
            handle = ctypes.c_void_p()
            err = self._winmm.midiInOpen(
                ctypes.byref(handle), dev, self._callback, 0, _CALLBACK_FUNCTION
            )
            if err or self._winmm.midiInStart(handle):
                logger.warning("MIDI input %d unavailable (winmm error %d)", dev, err)
                if not err:
                    self._winmm.midiInClose(handle)
                continue
            self._handles.append(handle)
        logger.info("MIDI scene & action control: %d input(s) active", len(self._handles))
        return len(self._handles)

    def stop(self) -> None:
        for handle in self._handles:
            self._winmm.midiInStop(handle)
            self._winmm.midiInClose(handle)
        self._handles = []
