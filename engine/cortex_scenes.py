"""
Neural DSP Quad Cortex Scene Architecture & Manager.
Implements instant, zero-glitch 8-Scene switching (Scenes A to H),
parameter overrides, block bypasses, and Cortex multi-scene presets.
"""

from typing import List, Dict, Any, Optional
import copy
import math
import logging

from engine.cortex_models import (
    SCENE_COLORS,
    DEFAULT_SCENE_LABELS,
    SceneDefinition,
    FACTORY_CORTEX_PRESETS,
)

logger = logging.getLogger(__name__)

BLOCK_ATTRS = {
    "gate": "noise_gate", "screamer": "screamer", "amp": "amp", "cab": "cab", "eq": "eq",
    "mod": "mod", "delay": "delay", "reverb": "reverb", "pitch": "pitch_shifter",
}
# Short UI/preset names -> the DSP attribute that actually holds the value.
PARAM_ALIASES = {("gate", "threshold"): "threshold_db", ("delay", "time"): "time_sec",
                 ("reverb", "type"): "reverb_type"}
# Overrides that go through a setter instead of a plain attribute.
SPECIAL_PARAMS = {("eq", "data"), ("pitch", "semitones")}


class CortexSceneManager:
    """
    Manages 8 Scenes (A through H) for the guitar workstation.
    Handles seamless scene changes, parameter overriding, block bypassing,
    and multi-scene presets.
    """

    def __init__(self):
        self.active_scene_index: int = 0
        self.current_preset_name: str = "British Lead 100"
        self.current_preset_id: str = "cortex_british_lead_100"
        self.scenes: List[SceneDefinition] = []
        # (block, attr) -> value before the active scene touched it / value the scene set
        self._base: Dict[tuple, Any] = {}
        self._applied: Dict[tuple, Any] = {}
        self._init_default_scenes()

    def _init_default_scenes(self):
        """Initializes 8 blank/default scenes (A to H)."""
        self.scenes = []
        for i in range(8):
            color = SCENE_COLORS[i]["hex"]
            label = DEFAULT_SCENE_LABELS[i]
            self.scenes.append(
                SceneDefinition(
                    index=i,
                    label=label,
                    color_hex=color,
                    bypasses={
                        "gate": True,
                        "screamer": i in [1, 2, 3],
                        "amp": True,
                        "cab": True,
                        "eq": True,
                        "mod": i in [4, 5],
                        "delay": i in [3, 4],
                        "reverb": True,
                        "pitch": i == 5,
                    },
                    param_overrides={},
                )
            )

    def get_scenes(self) -> List[Dict[str, Any]]:
        """Returns the list of 8 scenes with their metadata and states."""
        return [s.to_dict() for s in self.scenes]

    def get_active_scene(self) -> Dict[str, Any]:
        """Returns the currently active scene dictionary."""
        idx = max(0, min(self.active_scene_index, len(self.scenes) - 1))
        return self.scenes[idx].to_dict()

    def set_active_scene(self, scene_index: int, chain=None) -> Dict[str, Any]:
        """
        Switches the active scene (0 to 7 -> A to H).
        Immediately applies bypass states and parameter overrides to the DSP signal chain.
        """
        if not (0 <= scene_index < len(self.scenes)):
            raise ValueError(f"Invalid scene index: {scene_index}. Must be 0-7.")

        self.active_scene_index = scene_index
        scene = self.scenes[scene_index]

        if chain is not None:
            self._apply_scene_to_chain(scene, chain)

        return scene.to_dict()

    @staticmethod
    def _block(chain, name):
        attr = BLOCK_ATTRS.get(name)
        return getattr(chain, attr, None) if attr else None

    @staticmethod
    def resolve_param(chain, block_name, param):
        """Return (block, attribute) for a scene override key, or None if unmappable."""
        block = CortexSceneManager._block(chain, block_name)
        if block is None:
            return None
        attr = PARAM_ALIASES.get((block_name, param), param)
        if (block_name, attr) in SPECIAL_PARAMS or hasattr(block, attr):
            return block, attr
        return None

    @staticmethod
    def _get(block_name, block, attr):
        if (block_name, attr) == ("pitch", "semitones"):
            return block.target_semitones
        if (block_name, attr) == ("eq", "data"):
            return list(block.gains)
        return getattr(block, attr)

    @staticmethod
    def _set(block_name, block, attr, val):
        if (block_name, attr) == ("pitch", "semitones"):
            block.set_semitones(float(val))
        elif (block_name, attr) == ("eq", "data"):
            block.set_bands(val)
        else:
            cur = getattr(block, attr)
            if isinstance(val, float) and not math.isfinite(val):
                raise ValueError(f"non-finite value {val!r}")
            if isinstance(cur, bool):
                val = bool(val)
            elif isinstance(cur, int):
                val = int(val)
            elif isinstance(cur, float):
                val = float(val)
            setattr(block, attr, val)

    def _revert_scene(self, chain):
        """Undo the previous scene: restore each value it changed, unless something
        else (a knob, a preset load) has moved it since."""
        for (block_name, attr), applied in self._applied.items():
            res = self.resolve_param(chain, block_name, attr)
            if res is None or (block_name, attr) not in self._base:
                continue
            block, attr = res
            if self._get(block_name, block, attr) == applied:
                self._set(block_name, block, attr, self._base[(block_name, attr)])
        self._applied.clear()
        self._base.clear()

    def _apply_scene_to_chain(self, scene: SceneDefinition, chain):
        """Reverts the previous scene, then applies this scene's block states and
        parameter overrides to the live DSP GuitarSignalChain."""
        self._revert_scene(chain)

        changes = [(name, "enabled", val) for name, val in (scene.bypasses or {}).items()]
        for block_name, params in (scene.param_overrides or {}).items():
            changes.extend((block_name, param, val) for param, val in params.items())

        for block_name, param, val in changes:
            res = self.resolve_param(chain, block_name, param)
            if res is None:
                logger.warning("Scene override %s.%s has no matching DSP attribute", block_name, param)
                continue
            block, attr = res
            key = (block_name, attr)
            try:
                if key not in self._base:
                    self._base[key] = self._get(block_name, block, attr)
                self._set(block_name, block, attr, val)
                self._applied[key] = self._get(block_name, block, attr)
            except Exception as e:
                logger.warning("Failed setting %s.%s = %s: %s", block_name, param, val, e)

    def update_scene(
        self,
        scene_index: int,
        label: Optional[str] = None,
        color_hex: Optional[str] = None,
        bypasses: Optional[Dict[str, bool]] = None,
        param_overrides: Optional[Dict[str, Dict[str, float]]] = None,
        chain=None,
    ) -> Dict[str, Any]:
        """Updates scene parameters and optionally re-applies if it's the active scene."""
        if not (0 <= scene_index < len(self.scenes)):
            raise ValueError(f"Invalid scene index: {scene_index}")

        scene = self.scenes[scene_index]
        if label is not None:
            scene.label = str(label)
        if color_hex is not None:
            scene.color_hex = str(color_hex)
        if bypasses is not None:
            scene.bypasses.update(bypasses)
        if param_overrides is not None:
            scene.param_overrides.update(param_overrides)

        if scene_index == self.active_scene_index and chain is not None:
            self._apply_scene_to_chain(scene, chain)

        return scene.to_dict()

    def load_preset(self, preset_data: Dict[str, Any], chain=None) -> Dict[str, Any]:
        """
        Loads a Cortex multi-scene preset dictionary.
        Applies base settings, updates scenes A-H, and switches to the default scene.
        """
        self.current_preset_name = preset_data.get("name", "Custom Cortex Preset")
        self.current_preset_id = preset_data.get("id", "cortex_custom")

        # Load scenes
        raw_scenes = preset_data.get("scenes", [])
        self.scenes = []
        for i in range(8):
            if i < len(raw_scenes):
                self.scenes.append(SceneDefinition.from_dict(raw_scenes[i]))
            else:
                self.scenes.append(
                    SceneDefinition(
                        index=i,
                        label=DEFAULT_SCENE_LABELS[i],
                        color_hex=SCENE_COLORS[i]["hex"],
                        bypasses={},
                        param_overrides={},
                    )
                )

        # A new preset replaces the base the old scene was layered on.
        self._base.clear()
        self._applied.clear()

        # Apply base settings to chain if provided
        base = preset_data.get("base_settings", {})
        if chain is not None and base:
            self._apply_base_settings(base, chain)

        # Switch to default scene
        default_scene = int(preset_data.get("default_scene", 0))
        self.set_active_scene(default_scene, chain=chain)

        return self.get_state()

    def _apply_base_settings(self, base: Dict[str, Any], chain):
        """Applies base chain parameters before scene overrides."""
        if "gate" in base and hasattr(chain, "noise_gate"):
            chain.noise_gate.enabled = base["gate"].get("enabled", True)
            if "threshold" in base["gate"]:
                chain.noise_gate.threshold_db = float(base["gate"]["threshold"])

        if "screamer" in base and hasattr(chain, "screamer"):
            chain.screamer.enabled = base["screamer"].get("enabled", False)
            if "drive" in base["screamer"]:
                chain.screamer.drive = float(base["screamer"]["drive"])
            if "tone" in base["screamer"]:
                chain.screamer.tone = float(base["screamer"]["tone"])
            if "level" in base["screamer"]:
                chain.screamer.level = float(base["screamer"]["level"])

        if "amp" in base and hasattr(chain, "amp"):
            chain.amp.enabled = base["amp"].get("enabled", True)
            for k in ["gain", "bass", "mid", "treble", "presence", "master"]:
                if k in base["amp"]:
                    setattr(chain.amp, k, float(base["amp"][k]))
            if "model" in base["amp"]:
                chain.amp.model = str(base["amp"]["model"])

        if "eq" in base and hasattr(chain, "eq"):
            chain.eq.enabled = base["eq"].get("enabled", True)
            if "data" in base["eq"]:
                chain.eq.set_bands(base["eq"]["data"], model_id=base["eq"].get("model_id", 0))

        if "cab" in base and hasattr(chain, "cab"):
            chain.cab.enabled = base["cab"].get("enabled", True)
            if hasattr(chain.cab, "set_tube_and_mic"):
                chain.cab.set_tube_and_mic(
                    tube=base["cab"].get("tube"),
                    mic=base["cab"].get("mic"),
                    center=base["cab"].get("center"),
                    distance=base["cab"].get("distance"),
                )
            if "ir_name" in base["cab"] and hasattr(chain.cab, "select_cab"):
                chain.cab.select_cab(base["cab"]["ir_name"])

        if "mod" in base and hasattr(chain, "mod"):
            chain.mod.enabled = base["mod"].get("enabled", False)
            for k in ["rate", "mix", "depth", "tone"]:
                if k in base["mod"]:
                    setattr(chain.mod, k, float(base["mod"][k]))
            if "model_id" in base["mod"]:
                chain.mod.model_id = int(base["mod"]["model_id"])

        if "delay" in base and hasattr(chain, "delay"):
            chain.delay.enabled = base["delay"].get("enabled", False)
            if "time" in base["delay"]:
                chain.delay.time_sec = float(base["delay"]["time"])
            if "feedback" in base["delay"]:
                chain.delay.feedback = float(base["delay"]["feedback"])
            if "mix" in base["delay"]:
                chain.delay.mix = float(base["delay"]["mix"])

        if "reverb" in base and hasattr(chain, "reverb"):
            chain.reverb.enabled = base["reverb"].get("enabled", True)
            if "decay" in base["reverb"]:
                chain.reverb.decay = float(base["reverb"]["decay"])
            if "mix" in base["reverb"]:
                chain.reverb.mix = float(base["reverb"]["mix"])
            if "tone" in base["reverb"]:
                chain.reverb.tone = float(base["reverb"]["tone"])

    def get_presets(self) -> List[Dict[str, Any]]:
        """Returns all available Cortex factory presets + custom downloaded presets."""
        presets = list(FACTORY_CORTEX_PRESETS)
        try:
            import config
            import glob
            import json
            import os
            custom_dir = str(getattr(config, "CUSTOM_CORTEX_DIR", ""))
            if custom_dir and os.path.isdir(custom_dir):
                for p in sorted(glob.glob(os.path.join(custom_dir, "*.cortex.json"))):
                    try:
                        with open(p, "r", encoding="utf-8") as f:
                            doc = json.load(f)
                        if isinstance(doc, dict) and "name" in doc and "scenes" in doc:
                            doc["_file_path"] = p
                            presets.append(doc)
                    except Exception as e:
                        logger.warning(f"Error loading custom cortex preset {p}: {e}")
        except Exception as e:
            logger.warning(f"Failed to scan custom_cortex: {e}")
        return presets

    def get_state(self) -> Dict[str, Any]:
        """Returns the complete scene manager state."""
        return {
            "active_scene_index": self.active_scene_index,
            "active_badge": chr(65 + self.active_scene_index),
            "preset_name": self.current_preset_name,
            "preset_id": self.current_preset_id,
            "scenes": self.get_scenes(),
            "palette": SCENE_COLORS,
        }
