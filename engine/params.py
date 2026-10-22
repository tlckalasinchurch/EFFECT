"""Single source of truth for signal-chain modules and their parameters.

This module is **data only**: importing it has no side effects, allocates no DSP
and reads no files. It exists because the same parameter set is currently
declared in six places that have already drifted apart:

    1. server.py  /api/parameter          (section + param -> attribute write)
    2. engine/audio.py get_state()["chain"] (what a preset stores)
    3. engine/cortex_scenes.py BLOCK_ATTRS / PARAM_ALIASES
    4. engine/morph.py DEFAULTS           (flat amp_gain, delay_mix, ...)
    5. engine/dsp.py apply_mooer_preset   (nested settings dict)
    6. web/app.js BLOCKS + KNOB_SETS

Phase 2A adds it next to those tables without rewiring any call site, so the
mapping can be proven correct against the running code first
(tests/test_param_registry.py). Wiring the call sites to read from here is a
later phase; see docs/SIGNAL_CHAIN_READINESS.md.

Two rules for editing:

* ``name`` is the canonical block name used by the API, presets and the UI.
  ``attr`` is the attribute that holds it on ``GuitarSignalChain``; ``None``
  means the parameters live on the chain itself (master, input, parallel).
* ``key`` is what the API/preset calls the parameter. ``attr`` on a Param is
  the DSP attribute, which differs for historical reasons (threshold ->
  threshold_db, time -> time_sec, type -> reverb_type, glide -> glide_pct).
"""

from dataclasses import dataclass, field
from typing import Any, Optional, Tuple


KINDS = ("float", "bool", "int", "str", "list")


@dataclass(frozen=True)
class Param:
    key: str                      # API / preset / UI parameter name
    attr: str                     # attribute on the DSP object
    kind: str                     # one of KINDS
    default: Any                  # value on a freshly constructed GuitarSignalChain
    setter: Optional[str] = None   # method to call instead of a plain assignment
    read_attr: Optional[str] = None  # attribute to read when it differs from `attr`
    # What get_state()['chain'] calls this value, when it disagrees with `key`
    # (get_state emits a mix of canonical names and raw attribute names).
    state_key: Optional[str] = None
    # Set when the API addresses a list element as e.g. band0, band1, ...
    index_template: Optional[str] = None
    # "block" on a DSP object, "chain" on GuitarSignalChain, "server" when the
    # value is not on the DSP at all (nam.quality lives on the server module).
    owner: str = "block"
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    choices: Tuple[str, ...] = ()
    aliases: Tuple[str, ...] = ()   # accepted on input, never emitted
    ui: bool = True                 # exposed as a knob in web/app.js
    read_only: bool = False         # emitted by get_state() but not settable

    def __post_init__(self):
        if self.kind not in KINDS:
            raise ValueError(f"{self.key}: unknown kind {self.kind!r}")
        if self.owner not in ("block", "chain", "server"):
            raise ValueError(f"{self.key}: unknown owner {self.owner!r}")
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError(f"{self.key}: minimum > maximum")


@dataclass(frozen=True)
class Module:
    name: str                     # canonical block name
    attr: Optional[str]           # GuitarSignalChain attribute, None = on the chain
    params: Tuple[Param, ...]
    aliases: Tuple[str, ...] = ()
    in_graph: bool = True         # part of the ordered processing graph

    def param(self, key: str) -> Param:
        for p in self.params:
            if p.key == key or key in p.aliases:
                return p
            if p.index_template:
                prefix = p.index_template.split("{")[0]
                if key.startswith(prefix) and key[len(prefix):].isdigit():
                    return p
        raise KeyError(f"{self.name} has no parameter {key!r}")


def _p(key, attr, kind, default, **kw):
    return Param(key=key, attr=attr, kind=kind, default=default, **kw)


# ---------------------------------------------------------------------------
# Chain-level modules (not in the ordered graph)
# ---------------------------------------------------------------------------

INPUT = Module(
    name="input", attr=None, in_graph=False,
    params=(_p("trim", "input_trim_db", "float", 0.0, owner="chain",
              state_key="trim_db", minimum=-24.0, maximum=24.0),),
)

MASTER = Module(
    name="master", attr=None, in_graph=False, aliases=("output",),
    params=(_p("volume", "master_volume", "float", 1.0, owner="chain",
              minimum=0.0, maximum=2.0),),
)

PARALLEL = Module(
    name="parallel", attr=None, in_graph=False,
    params=(
        _p("enabled", "parallel_enabled", "bool", False, owner="chain"),
        _p("blend", "parallel_blend", "float", 0.3, owner="chain", minimum=0.0, maximum=1.0),
    ),
)


# ---------------------------------------------------------------------------
# The ordered processing graph, in the order GuitarSignalChain.process applies it
# ---------------------------------------------------------------------------

GATE = Module(
    name="gate", attr="noise_gate",
    params=(
        _p("enabled", "enabled", "bool", True),
        _p("threshold", "threshold_db", "float", -55.0, minimum=-80.0, maximum=-20.0),
        # set_timing() recomputes both time constants, so a release change must
        # also pass the current attack.
        _p("release", "release_ms", "float", 50.0, setter="set_timing",
           state_key="release_ms", minimum=10.0, maximum=500.0),
        _p("hold", "hold_ms", "float", 50.0, state_key="hold_ms", minimum=0.0, maximum=200.0),
        _p("range", "range_db", "float", -60.0, state_key="range_db", minimum=-90.0, maximum=-20.0),
    ),
)

PITCH = Module(
    name="pitch", attr="pitch_shifter",
    params=(
        _p("enabled", "enabled", "bool", False),
        # The knob sets the target; the audible value glides toward it.
        _p("semitones", "semitones", "float", 0.0, setter="set_semitones",
           read_attr="target_semitones", minimum=-24.0, maximum=24.0),
        _p("glide", "glide_pct", "float", 0.0, setter="set_glide", minimum=0.0, maximum=100.0),
        _p("cents", "cents", "float", 0.0, minimum=-100.0, maximum=100.0),
        _p("mix", "mix", "float", 1.0, minimum=0.0, maximum=1.0),
    ),
)

SCREAMER = Module(
    name="screamer", attr="screamer", aliases=("drive",),
    params=(
        _p("enabled", "enabled", "bool", False),
        _p("drive", "drive", "float", 0.4, minimum=0.0, maximum=1.0),
        # Biquad coefficients are rebuilt from `tone`; the filter state is reset.
        _p("tone", "tone", "float", 0.6, setter="_update_filter", minimum=0.0, maximum=1.0),
        _p("level", "level", "float", 0.7, minimum=0.0, maximum=1.0),
    ),
)

AMP = Module(
    name="amp", attr="amp",
    params=(
        _p("enabled", "enabled", "bool", True),
        _p("gain", "gain", "float", 0.65, minimum=0.0, maximum=1.0),
        _p("bass", "bass", "float", 0.55, minimum=0.0, maximum=1.0),
        _p("mid", "mid", "float", 0.5, minimum=0.0, maximum=1.0),
        _p("treble", "treble", "float", 0.6, minimum=0.0, maximum=1.0),
        _p("presence", "presence", "float", 0.6, minimum=0.0, maximum=1.0),
        _p("master", "master", "float", 0.7, minimum=0.0, maximum=1.0),
        _p("model", "model", "str", "5150", aliases=("tone_stack",)),
        _p("bright", "bright", "bool", False),
    ),
)

# Occupies the same graph slot as AMP; GuitarSignalChain uses one or the other.
NAM = Module(
    name="nam", attr="nam",
    params=(
        _p("enabled", "enabled", "bool", True),
        _p("input_gain", "input_gain_db", "float", 0.0,
           setter="set_input_gain_db", minimum=-24.0, maximum=24.0),
        # Build quality of the next model load; held by server.py, not the DSP.
        _p("quality", "_NAM_QUALITY", "str", "lite", owner="server",
           choices=("lite", "full"), ui=False),
    ),
)

EQ = Module(
    name="eq", attr="eq",
    params=(
        _p("enabled", "enabled", "bool", False),
        _p("model_id", "model_id", "int", 1, setter="set_model", minimum=1, maximum=5),
        # List of band gains; the server edits one index and re-designs filters.
        # "data" is the name the MOOER/Cortex importers use for this list.
        _p("bands", "gains", "list", (0.0,) * 6, setter="set_bands", ui=False,
           aliases=("data",), index_template="band{index}"),
        _p("curve", "get_curve_points", "float", (), read_only=True, ui=False),
    ),
)

CAB = Module(
    name="cab", attr="cab",
    params=(
        _p("enabled", "enabled", "bool", True),
        _p("level", "level", "float", 1.0, minimum=0.0, maximum=2.0),
        _p("ir_name", "ir_name", "str", "Celestion V30 4x12", setter="select_cab"),
        _p("lowcut", "lowcut_hz", "float", 20.0, setter="set_cutoffs", minimum=10.0, maximum=20000.0),
        _p("highcut", "highcut_hz", "float", 20000.0, setter="set_cutoffs", minimum=10.0, maximum=20000.0),
        _p("mix", "mix", "float", 1.0, minimum=0.0, maximum=1.0),
        _p("tube", "tube", "str", "OFF", setter="set_tube_and_mic"),
        _p("mic", "mic", "str", "SM57", setter="set_tube_and_mic"),
        _p("center", "center", "float", 50.0, setter="set_tube_and_mic", minimum=0.0, maximum=100.0),
        _p("distance", "distance", "float", 20.0, setter="set_tube_and_mic", minimum=0.0, maximum=100.0),
    ),
)

MOD = Module(
    name="mod", attr="mod", aliases=("modulation",),
    params=(
        _p("enabled", "enabled", "bool", False),
        _p("model_id", "model_id", "int", 12, minimum=1, maximum=19),
        _p("rate", "rate", "float", 0.5, minimum=0.0, maximum=1.0),
        _p("mix", "mix", "float", 0.5, minimum=0.0, maximum=1.0),
        _p("tone", "tone", "float", 0.5, minimum=0.0, maximum=1.0),
        _p("depth", "depth", "float", 0.5, minimum=0.0, maximum=1.0),
    ),
)

DELAY = Module(
    name="delay", attr="delay",
    params=(
        _p("enabled", "enabled", "bool", False),
        _p("time", "time_sec", "float", 0.36, minimum=0.01, maximum=2.0),
        _p("feedback", "feedback", "float", 0.35, minimum=0.0, maximum=0.95),
        _p("mix", "mix", "float", 0.25, minimum=0.0, maximum=1.0),
        _p("ducking", "ducking", "bool", False),
        _p("duck_depth", "duck_depth", "float", 0.6, minimum=0.0, maximum=1.0),
    ),
)

REVERB = Module(
    name="reverb", attr="reverb",
    params=(
        _p("enabled", "enabled", "bool", False),
        _p("decay", "decay", "float", 0.5, minimum=0.0, maximum=1.0),
        _p("mix", "mix", "float", 0.2, minimum=0.0, maximum=1.0),
        _p("tone", "tone", "float", 0.5, minimum=0.0, maximum=1.0),
        _p("type", "reverb_type", "str", "plate",
           choices=("room", "hall", "plate", "cathedral", "spring")),
        _p("ducking", "ducking", "bool", False),
        _p("duck_depth", "duck_depth", "float", 0.5, minimum=0.0, maximum=1.0),
    ),
)


# ---------------------------------------------------------------------------
# Indexes
# ---------------------------------------------------------------------------

#: Engine processing order. AMP and NAM share one slot (only one is installed).
PROCESS_ORDER: Tuple[str, ...] = ("gate", "pitch", "screamer", "amp", "eq", "cab", "mod", "delay", "reverb")

#: Every module, chain-level ones included, in processing order then the rest.
MODULES: Tuple[Module, ...] = (
    GATE, PITCH, SCREAMER, AMP, NAM, EQ, CAB, MOD, DELAY, REVERB,
    INPUT, MASTER, PARALLEL,
)

BY_NAME = {m.name: m for m in MODULES}

#: alias -> canonical name, for names other layers use (UI block ids, labels).
ALIASES = {a: m.name for m in MODULES for a in m.aliases}


def module(name: str) -> Module:
    """Look a module up by canonical name or alias."""
    return BY_NAME.get(ALIASES.get(name, name)) or _missing(name)


def _missing(name: str) -> Module:
    raise KeyError(f"unknown module {name!r}")


def find(name: str):
    """Resolve ``name`` or return None instead of raising."""
    try:
        return module(name)
    except KeyError:
        return None


def resolve(section: str, param: str):
    """Map an API-style (section, param) pair to (Module, Param)."""
    mod = module(section)
    return mod, mod.param(param)


def defaults(chain_name: str) -> dict:
    """The default parameter dict of one module, as a fresh chain would have it."""
    return {p.key: p.default for p in module(chain_name).params if not p.read_only}
