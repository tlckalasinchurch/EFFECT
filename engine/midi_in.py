"""
MIDI CC scene switching for the Cortex scene manager.

Listens on every MIDI input device through Windows winmm (ctypes, no extra
dependency). Quad Cortex convention: CC 43 with value 0-7 selects scene A-H.
"""

import ctypes
import logging
import sys
from typing import Callable, List, Optional

logger = logging.getLogger(__name__)

SCENE_CC = 43
SCENE_COUNT = 8

_MIM_DATA = 0x3C3
_CALLBACK_FUNCTION = 0x30000


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
    """Opens all MIDI inputs and calls on_scene(index) from the winmm thread."""

    def __init__(self, on_scene: Callable[[int], None], channel: Optional[int] = None):
        self._on_scene = on_scene
        self._channel = channel
        self._handles: List[ctypes.c_void_p] = []
        self._winmm = None
        # winmm keeps this pointer; it must outlive every open handle.
        self._proto = ctypes.WINFUNCTYPE(
            None, ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_size_t
        )
        self._callback = self._proto(self._on_midi)

    def _on_midi(self, _h, msg, _inst, p1, _p2):
        if msg != _MIM_DATA:
            return
        scene = scene_from_message(p1 & 0xFF, (p1 >> 8) & 0xFF, (p1 >> 16) & 0xFF, self._channel)
        if scene is None:
            return
        try:
            self._on_scene(scene)
        except Exception:
            logger.exception("MIDI scene switch failed")

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
        logger.info("MIDI scene control: %d input(s), CC %d = scene A-H", len(self._handles), SCENE_CC)
        return len(self._handles)

    def stop(self) -> None:
        for handle in self._handles:
            self._winmm.midiInStop(handle)
            self._winmm.midiInClose(handle)
        self._handles = []
