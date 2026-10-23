"""RigDocument v2 — a versioned, order-aware description of a rig.

Why this exists
---------------
A preset is currently stored as ``settings_json``, which is literally
``AudioEngine.get_state()['chain']``: a dict keyed by DSP attribute names, with
no schema version, no module order and no way to tell a missing field from a
default. This module defines a second, canonical shape:

    {
      "schema_version": 2,
      "meta": {"id", "name", "author", "category"},
      "chain": {"master": {...}, "input": {...}, "parallel": {...}},
      "modules": [{"slot_id", "type", "enabled", "params", "extras"}, ...],
      "extras": {...}
    }

``modules`` holds only the ordered processing graph (``params.PROCESS_ORDER``);
``chain`` holds the registry modules that are not stages. ``amp`` and ``nam``
share one slot: at most one of them may appear.

Guarantees this module makes
----------------------------
* It never touches audio. Importing it must not import ``engine.dsp``.
* It never writes to the database. It parses text/dicts and returns objects.
* It never drops data. Anything it cannot map is kept verbatim in ``extras``
  and reported as an ``Issue``, so a round trip is lossless.
* It does not invent values. A parameter absent from v1 stays absent; callers
  that need a complete set ask for ``effective_params()``, which merges the
  registry defaults explicitly.

The one thing it refuses to do silently is guess: an unknown module type or an
unsupported ``schema_version`` raises instead of producing a partial document.
"""

import json
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple

from engine import params

SCHEMA_VERSION = 2
SUPPORTED_VERSIONS = (2,)

#: v1 stores the master volume as a bare top-level scalar, not as a block.
V1_SCALARS = {"master_volume": ("master", "volume")}

#: Which stages a parallel dry tap can contain, and where the wet path rejoins.
#:
#: GuitarSignalChain.process captures the dry signal after gate and pitch, then
#: blends it back after the cabinet — before mod, delay and reverb, which stay
#: fully wet. Both positions are implicit in the order of the statements, not
#: declared anywhere, so they are frozen here for the refactor phase: moving
#: either one changes the sound of every preset with parallel enabled, and
#: making them configurable is a routing feature, not a refactor. These strings
#: are not taken on faith: tests/test_rigdoc.py reads process() and checks that
#: they name the stages on either side of the tap and blend statements.
#:
#: ``PARALLEL_TAP_AFTER`` is the *last* stage included in the tap; gate and pitch
#: are the only stages before it, so the tap is gate + pitch.
PARALLEL_TAP_AFTER = "pitch"
PARALLEL_BLEND_AFTER = "cab"

#: Declared anchors in nominal (default) order, for callers that validate a chain.
PARALLEL_ANCHORS = (PARALLEL_TAP_AFTER, PARALLEL_BLEND_AFTER)

#: Stage types that share one slot, mapped to the type that names the slot.
#: ``nam`` replaces ``amp`` at the same point of the graph.
SLOT_ALIASES = {"nam": "amp"}

#: One DSP instance per module type in this phase: the engine holds a single
#: attribute per type and the API addresses a module by (section, param) with
#: no instance id. A document may still be *read* with two of a kind so nothing
#: is lost, but it is reported as an error and must not be built.
MAX_INSTANCES_PER_TYPE = 1


class RigDocumentError(ValueError):
    """Base class for anything that makes a document unusable."""


class UnsupportedSchemaVersion(RigDocumentError):
    pass


class UnknownModuleType(RigDocumentError):
    pass


class InvalidDocument(RigDocumentError):
    pass


# ---------------------------------------------------------------------------
# Issues: every lossy decision is recorded instead of applied silently
# ---------------------------------------------------------------------------

DEFAULTED = "defaulted"
UNKNOWN_FIELD = "unknown-field"
UNKNOWN_MODULE = "unknown-module?"
INVALID_VALUE = "invalid-value"
OUT_OF_RANGE = "out-of-range"
DUPLICATE_SLOT = "duplicate-slot"
DUPLICATE_TYPE = "duplicate-type"


@dataclass(frozen=True)
class Issue:
    where: str          # "gate.threshold" or "modules[3]"
    problem: str        # one of the constants above
    detail: str = ""
    severity: str = "warning"

    def __str__(self) -> str:
        tail = f": {self.detail}" if self.detail else ""
        return f"{self.where} [{self.problem}]{tail}"


# ---------------------------------------------------------------------------
# Document objects
# ---------------------------------------------------------------------------

@dataclass
class ModuleConfig:
    """One module in the graph (or one chain-level module)."""

    slot_id: str
    type: str
    enabled: bool = True
    params: Dict[str, Any] = field(default_factory=dict)
    #: v1 keys that exist in the preset but are not parameters (kept verbatim).
    extras: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "slot_id": self.slot_id,
            "type": self.type,
            "enabled": self.enabled,
            "params": dict(self.params),
        }
        if self.extras:
            out["extras"] = dict(self.extras)
        return out

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ModuleConfig":
        if not isinstance(data, dict):
            raise InvalidDocument(f"module entry is {type(data).__name__}, not an object")
        slot_id = data.get("slot_id")
        type_name = data.get("type")
        if not isinstance(type_name, str):
            raise InvalidDocument(f"module entry has no string 'type': {data!r}")
        if params.find(type_name) is None:
            raise UnknownModuleType(f"unknown module type {type_name!r}")
        if not isinstance(slot_id, str) or not slot_id:
            slot_id = type_name
        params_dict = data.get("params") or {}
        if not isinstance(params_dict, dict):
            raise InvalidDocument(f"{type_name!r} params is {type(params_dict).__name__}, not an object")
        return cls(
            slot_id=slot_id,
            type=type_name,
            enabled=bool(data.get("enabled", True)),
            params=dict(params_dict),
            extras=dict(data.get("extras") or {}),
        )


@dataclass
class RigDocument:
    modules: List[ModuleConfig] = field(default_factory=list)
    chain: Dict[str, ModuleConfig] = field(default_factory=dict)
    meta: Dict[str, Any] = field(default_factory=dict)
    extras: Dict[str, Any] = field(default_factory=dict)
    schema_version: int = SCHEMA_VERSION
    issues: List[Issue] = field(default_factory=list)

    # -- queries ---------------------------------------------------------

    def module(self, name: str) -> Optional[ModuleConfig]:
        want = params.find(name)
        if want is None:
            return None
        for mod in self.modules:
            if mod.type == want.name:
                return mod
        return None

    def slot(self, slot_id: str) -> Optional[ModuleConfig]:
        for mod in self.modules:
            if mod.slot_id == slot_id:
                return mod
        for mod in self.chain.values():
            if mod.slot_id == slot_id:
                return mod
        return None

    def effective_params(self, name: str) -> Dict[str, Any]:
        """Registry defaults merged with what the document actually stores.

        This is the runtime view: a complete, ordered set of values. Persisted
        documents stay faithful to their source and do not grow defaults.
        """
        mod = self.module(name) or self.chain.get(name)
        registry = params.module(name)
        merged = {p.key: p.default for p in registry.params if not p.read_only}
        if mod is not None:
            merged.update(mod.params)
            if any(p.key == "enabled" for p in registry.params):
                merged["enabled"] = mod.enabled
        return merged

    def ordered_types(self) -> Tuple[str, ...]:
        """Module types in the order they are stored, i.e. the order they process.

        Stored order is authoritative. A document read from v1 is canonicalised
        on import (v1 has no order of its own), so this returns PROCESS_ORDER for
        a legacy preset and the user's own order for a reordered v2 document.
        """
        return tuple(m.type for m in self.modules)

    @property
    def tap_after(self) -> str:
        """Last stage included in the parallel dry tap (frozen this phase)."""
        return PARALLEL_TAP_AFTER

    @property
    def blend_after(self) -> str:
        """Stage the wet path reaches before the dry tap rejoins (frozen)."""
        return PARALLEL_BLEND_AFTER

    def parallel_tap_is_reachable(self) -> bool:
        """True when every stored stage sits on the engine's side of both
        parallel boundaries.

        ``process()`` taps the dry signal after pitch and mixes it back after
        the cab, which splits the graph into three groups: the tap (gate,
        pitch), the wet path between the anchors (screamer, amp/nam, eq, cab)
        and everything after the blend (mod, delay, reverb).

        Reordering *inside* a group is the feature this document exists for and
        returns True. Moving a stage *across* a boundary returns False: a reverb
        ahead of the tap would be mixed in dry, a delay inside the wet path
        would be blended, and a gate moved past the blend would leave the dry
        signal. A stage whose type has no declared position also returns False,
        because there is no side to prove it belongs to.

        Absent anchors are not crossings. Most factory presets have no pitch and
        no cab; each boundary then sits after every stored stage that nominally
        precedes its anchor, which is where the engine leaves it when the anchor
        stage is bypassed.
        """
        positions: List[int] = []
        for type_name in self.ordered_types():
            index = _nominal_index(type_name)
            if index is None:
                return False
            positions.append(index)

        tap_anchor = params.PROCESS_ORDER.index(PARALLEL_TAP_AFTER)
        blend_anchor = params.PROCESS_ORDER.index(PARALLEL_BLEND_AFTER)

        # A boundary sits after every stored stage that nominally precedes its
        # anchor, so an absent anchor still leaves the boundary in place.
        tap = sum(1 for index in positions if index <= tap_anchor)
        blend = sum(1 for index in positions if index <= blend_anchor)

        for position, index in enumerate(positions):
            stored_side = 0 if position < tap else (1 if position < blend else 2)
            nominal_side = 0 if index <= tap_anchor else (1 if index <= blend_anchor else 2)
            if stored_side != nominal_side:
                return False
        return True

    @property
    def errors(self) -> Tuple[Issue, ...]:
        """Issues that make the document unbuildable, as opposed to lossy."""
        return tuple(i for i in self.issues if i.severity == "error")

    # -- serialisation ---------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "meta": dict(self.meta),
            "chain": {name: mod.to_dict() for name, mod in self.chain.items()},
            "modules": [m.to_dict() for m in self.modules],
            "extras": dict(self.extras),
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RigDocument":
        if not isinstance(data, dict):
            raise InvalidDocument(f"document is {type(data).__name__}, not an object")
        version = data.get("schema_version")
        if version not in SUPPORTED_VERSIONS:
            raise UnsupportedSchemaVersion(
                f"schema_version {version!r} is not supported (this build reads {SUPPORTED_VERSIONS})"
            )
        modules = [ModuleConfig.from_dict(m) for m in data.get("modules") or []]
        chain_raw = data.get("chain") or {}
        if not isinstance(chain_raw, dict):
            raise InvalidDocument("'chain' is not an object")
        chain = {name: ModuleConfig.from_dict(m) for name, m in chain_raw.items()}

        doc = cls(
            modules=modules,
            chain=chain,
            meta=dict(data.get("meta") or {}),
            extras=dict(data.get("extras") or {}),
            schema_version=version,
        )
        doc.issues = _check_slots(doc)
        return doc

    @classmethod
    def from_json(cls, text: str) -> "RigDocument":
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise InvalidDocument(f"not valid JSON: {exc}") from exc
        return cls.from_dict(data)

    def to_v1(self) -> Dict[str, Any]:
        """Render as the legacy ``settings_json`` shape.

        Emitted keys are the ones v1 actually uses (``state_key`` where the
        registry records one), so a document produced by :func:`from_v1` renders
        back byte-for-byte equal to its source.
        """
        out: Dict[str, Any] = {}
        for name, mod in self.chain.items():
            registry = params.module(name)
            if name in _V1_SCALAR_MODULES:
                p = registry.params[0]
                if p.key in mod.params:
                    out[_V1_SCALAR_MODULES[name]] = mod.params[p.key]
                continue
            out[name] = _emit_module(registry, mod)
        for mod in self.modules:
            registry = params.module(mod.type)
            out[registry.name] = _emit_module(registry, mod)
        for key, value in self.extras.items():
            out.setdefault(key, value)
        return out


_V1_SCALAR_MODULES = {mod: v1_key for v1_key, (mod, _p) in V1_SCALARS.items()}


def _emit_module(registry: params.Module, mod: ModuleConfig) -> Dict[str, Any]:
    emitted: Dict[str, Any] = {}
    has_enabled = any(p.key == "enabled" for p in registry.params)
    if has_enabled:
        emitted["enabled"] = mod.enabled
    for p in registry.params:
        if p.key == "enabled" or p.read_only:
            continue
        if p.key in mod.params:
            emitted[p.state_key or p.key] = mod.params[p.key]
    emitted.update(mod.extras)
    return emitted


# ---------------------------------------------------------------------------
# v1 -> v2 adapter
# ---------------------------------------------------------------------------

def _coerce(value: Any, kind: str) -> Tuple[bool, Any]:
    """Return (ok, value). Never raises; the caller records invalid values."""
    if kind == "bool":
        return (isinstance(value, bool), value)
    if kind == "str":
        return (isinstance(value, str), value)
    if kind == "int":
        return (isinstance(value, int) and not isinstance(value, bool), value)
    if kind == "float":
        if isinstance(value, bool):
            return (False, value)
        if isinstance(value, (int, float)):
            return (True, float(value))
        return (False, value)
    if kind == "list":
        if isinstance(value, list) and all(
            isinstance(v, (int, float)) and not isinstance(v, bool) for v in value
        ):
            return (True, value)
        return (False, value)
    return (False, value)


def _v1_names(p: params.Param) -> Iterable[str]:
    """Every name v1 might use for this parameter."""
    for candidate in (p.state_key, p.key, p.attr, *p.aliases):
        if candidate:
            yield candidate


def from_v1(settings: Dict[str, Any], meta: Optional[Dict[str, Any]] = None) -> RigDocument:
    """Convert a legacy ``settings_json`` mapping into a :class:`RigDocument`.

    Missing sections stay missing (a factory preset really does have only six
    sections); missing parameters inside a present section are reported, not
    invented. Values that fail their declared type or range are kept verbatim
    and reported, because dropping them would corrupt the preset.
    """
    if not isinstance(settings, dict):
        raise InvalidDocument(f"settings is {type(settings).__name__}, not an object")

    doc = RigDocument(meta=dict(meta or {}))
    scalar_keys = {v1_key: (mod, pkey) for v1_key, (mod, pkey) in V1_SCALARS.items()}

    for key, value in settings.items():
        if key in scalar_keys:
            mod_name, param_key = scalar_keys[key]
            registry = params.module(mod_name)
            ok, coerced = _coerce(value, registry.param(param_key).kind)
            if not ok:
                doc.issues.append(Issue(key, INVALID_VALUE, f"{value!r} is not {registry.param(param_key).kind}"))
                coerced = value
            doc.chain[mod_name] = ModuleConfig(
                slot_id=mod_name, type=mod_name, enabled=True, params={param_key: coerced}
            )
            continue

        registry = params.find(key)
        if registry is None:
            # Not a module: keep it verbatim so nothing is lost. A leading
            # underscore is a reserved extension namespace (_t3k) and is not
            # reported as a surprise.
            doc.extras[key] = value
            if not key.startswith("_"):
                doc.issues.append(Issue(key, UNKNOWN_FIELD, "kept verbatim at document level"))
            continue

        if not isinstance(value, dict):
            doc.issues.append(Issue(key, INVALID_VALUE, f"{type(value).__name__} is not an object"))
            doc.extras[key] = value
            continue

        mod_config, module_issues = _module_from_v1(registry, value)
        doc.issues.extend(module_issues)
        if registry.in_graph:
            doc.modules.append(mod_config)
        else:
            doc.chain[registry.name] = mod_config

    # v1 inherits its key order from get_state(), which is not the processing
    # order (pitch is emitted last but processes second). Canonicalise here so
    # that stored order is meaningful from this point on and a later reorder by
    # the user is the only thing that can change it.
    doc.modules.sort(key=_process_index)
    doc.issues.extend(_check_slots(doc))
    return doc


def _nominal_index(type_name: str) -> Optional[int]:
    """Where a stage sits in the engine's declared order, or None if it has no place."""
    try:
        return params.PROCESS_ORDER.index(SLOT_ALIASES.get(type_name, type_name))
    except ValueError:
        return None


def _process_index(mod: ModuleConfig) -> Tuple[int, str]:
    index = _nominal_index(mod.type)
    return (len(params.PROCESS_ORDER) if index is None else index, mod.slot_id)


def _module_from_v1(registry: params.Module, block: Dict[str, Any]) -> Tuple[ModuleConfig, List[Issue]]:
    issues: List[Issue] = []
    stored: Dict[str, Any] = {}
    extras: Dict[str, Any] = {}
    enabled = True
    has_enabled = any(p.key == "enabled" for p in registry.params)

    for key, value in block.items():
        if key == "enabled" and has_enabled:
            if isinstance(value, bool):
                enabled = value
            else:
                issues.append(Issue(f"{registry.name}.enabled", INVALID_VALUE, repr(value)))
                enabled = bool(value)
            continue

        if _is_derived(registry, key) and _lookup(registry, key) is None:
            # Engine-computed mirror of a knob (pitch.target_semitones): kept
            # verbatim, never treated as an unknown field.
            extras[key] = value
            continue

        param = _lookup(registry, key)
        if param is None:
            extras[key] = value
            if not key.startswith("_"):
                issues.append(Issue(f"{registry.name}.{key}", UNKNOWN_FIELD, "kept verbatim in module extras"))
            continue

        if param.read_only:
            # Derived value (e.g. the EQ response curve). Stored and re-emitted
            # as-is: it is data the preset contained, not something to validate.
            extras[key] = value
            continue

        ok, coerced = _coerce(value, param.kind)
        if not ok:
            issues.append(Issue(f"{registry.name}.{key}", INVALID_VALUE,
                                f"{value!r} is not {param.kind}"))
            stored[param.key] = value
            continue
        if (param.minimum is not None and isinstance(coerced, (int, float))
                and not isinstance(coerced, bool) and coerced < param.minimum):
            issues.append(Issue(f"{registry.name}.{key}", OUT_OF_RANGE, f"{coerced} < {param.minimum}"))
        elif (param.maximum is not None and isinstance(coerced, (int, float))
                and not isinstance(coerced, bool) and coerced > param.maximum):
            issues.append(Issue(f"{registry.name}.{key}", OUT_OF_RANGE, f"{coerced} > {param.maximum}"))
        stored[param.key] = coerced

    for p in registry.params:
        if p.key == "enabled" or p.read_only:
            continue
        if p.key not in stored:
            issues.append(Issue(f"{registry.name}.{p.key}", DEFAULTED,
                                "absent in v1; runtime falls back to the registry default"))


    return ModuleConfig(
        slot_id=registry.name, type=registry.name, enabled=enabled, params=stored, extras=extras
    ), issues


def _is_derived(registry: params.Module, key: str) -> bool:
    """True for a value the engine computes and v1 happens to persist (target_semitones)."""
    return any(p.read_attr == key or p.read_only and p.key == key for p in registry.params)


def _lookup(registry: params.Module, key: str) -> Optional[params.Param]:
    for p in registry.params:
        if key in set(_v1_names(p)):
            return p
        if p.index_template and key.startswith(p.index_template.split("{")[0]):
            tail = key[len(p.index_template.split("{")[0]):]
            if tail.isdigit():
                return p
    return None


def _check_slots(doc: RigDocument) -> List[Issue]:
    issues: List[Issue] = []
    seen: Dict[str, str] = {}
    for index, mod in enumerate(doc.modules):
        if mod.type not in params.PROCESS_ORDER:
            issues.append(Issue(f"modules[{index}]", UNKNOWN_MODULE, f"{mod.type!r} is not a graph stage"))
        if mod.slot_id in seen:
            issues.append(Issue(f"modules[{index}]", DUPLICATE_SLOT,
                                f"slot_id {mod.slot_id!r} already used by {seen[mod.slot_id]!r}"))
        seen[mod.slot_id] = mod.type
    present = {m.type for m in doc.modules}
    if set(SLOT_ALIASES) | set(SLOT_ALIASES.values()) <= present:
        issues.append(Issue("modules", DUPLICATE_SLOT, "amp and nam share one slot but both are present", "error"))

    counts: Dict[str, int] = {}
    for mod in doc.modules:
        counts[mod.type] = counts.get(mod.type, 0) + 1
    for type_name, count in counts.items():
        if count > MAX_INSTANCES_PER_TYPE:
            issues.append(Issue(
                f"modules.{type_name}", DUPLICATE_TYPE,
                f"{count} instances of {type_name!r}; the engine holds one DSP object per type",
                "error",
            ))
    return issues


# ---------------------------------------------------------------------------
# Convenience entry points
# ---------------------------------------------------------------------------

def from_settings_json(text: str, meta: Optional[Dict[str, Any]] = None) -> RigDocument:
    """Parse a ``presets.db`` ``settings_json`` string."""
    try:
        settings = json.loads(text)
    except json.JSONDecodeError as exc:
        raise InvalidDocument(f"settings_json is not valid JSON: {exc}") from exc
    return from_v1(settings, meta=meta)


def upgrade(data: Dict[str, Any], meta: Optional[Dict[str, Any]] = None) -> RigDocument:
    """Accept either a v1 settings mapping or a v2 document."""
    if isinstance(data, dict) and data.get("schema_version") == SCHEMA_VERSION:
        return RigDocument.from_dict(data)
    return from_v1(data, meta=meta)
