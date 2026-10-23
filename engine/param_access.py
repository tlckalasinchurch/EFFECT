"""Write parameters into a running ``GuitarSignalChain`` from ``engine/params.py``.

``engine/params.py`` declares what a parameter *is*; this module is the single
place that knows how to *apply* one. Every runtime caller routes through here,
so the rules live next to the declaration instead of being re-derived at each
call site:

* the value is coerced to ``Param.kind``;
* it is clamped to the registry range only where the API has always clamped
  (``Param.clamp``);
* ``Param.setter`` is called instead of a plain assignment, and its arguments
  are read from its own signature -- ``set_cutoffs(lowcut_hz=...)`` takes the
  attribute name, ``set_semitones(value)`` takes one positional, and
  ``set_timing(attack_ms, release_ms)`` needs the sibling attack time from the
  object;
* ``Param.assign`` decides whether the attribute is written before the setter
  runs;
* an index-addressed parameter (``band3``) edits the list and re-applies it
  through the setter, so the filters are redesigned exactly once.

This module is deliberately small and has no side effects on import: no DSP is
allocated, no files are read.
"""

import inspect
import logging
import math
from typing import Any, Iterable, Optional, Tuple

from engine import params

logger = logging.getLogger(__name__)


class ServerOwnedParameter(Exception):
    """The value is held by ``server.py``, not by the chain (``nam.quality``)."""


class ModuleNotInstalled(LookupError):
    """The block is optional and not on this chain (``nam`` before a model load)."""


def _split_index(mod: params.Module, key: str) -> Tuple[Optional[params.Param], Optional[int]]:
    for p in mod.params:
        if not p.index_template:
            continue
        prefix = p.index_template.split("{", 1)[0]
        suffix = key[len(prefix):]
        if key.startswith(prefix) and suffix.isdigit():
            return p, int(suffix)
    return None, None


def resolve(section: str, key: str) -> Tuple[params.Module, params.Param, Optional[int]]:
    """Map an API-style (section, key) pair to its module, parameter and index.

    Raises ``KeyError`` for anything the registry does not know, so a caller can
    decide whether that is a silent no-op or a client error.
    """
    mod = params.module(section)
    p, index = _split_index(mod, key)
    if p is None:
        p = mod.param(key)
    if p.owner == "server":
        raise ServerOwnedParameter(f"{mod.name}.{p.key} is held by the server, not the chain")
    return mod, p, index


def _target(chain, mod: params.Module):
    if mod.attr is None:
        return chain
    block = getattr(chain, mod.attr, None)
    if block is None:
        raise ModuleNotInstalled(f"{mod.name} is not installed on this chain")
    return block


class NonFiniteValue(ValueError):
    """NaN or infinity offered for a numeric parameter.

    Delay/reverb buffers and IIR state keep a NaN forever, so it is refused at
    the door instead of being stored.
    """


def _finite(value):
    if not math.isfinite(value):
        raise NonFiniteValue(f"non-finite value {value!r}")
    return value


def _coerce(p: params.Param, value, element: bool = False):
    """Convert an API/preset value to the declared kind.

    ``list`` parameters are numeric lists (EQ band gains); ``element=True``
    coerces one entry of that list instead of the list itself.
    """
    if p.kind == "list":
        if element:
            return _finite(float(value))
        values = list(value)
        for v in values:
            _finite(float(v))
        return values
    if p.kind == "float":
        return _finite(float(value))
    if p.kind == "bool":
        return bool(value)
    if p.kind == "int":
        return int(value)
    return str(value)


def _clamp(p: params.Param, value):
    if not p.clamp or not isinstance(value, (int, float)):
        return value
    if p.minimum is not None:
        value = max(p.minimum, value)
    if p.maximum is not None:
        value = min(p.maximum, value)
    return value


def _call_setter(target, p: params.Param, value) -> None:
    method = getattr(target, p.setter)
    signature = inspect.signature(method)
    arguments = {
        name: arg for name, arg in signature.parameters.items()
        if arg.kind not in (arg.VAR_POSITIONAL, arg.VAR_KEYWORD)
    }
    if p.attr in arguments:
        # set_cutoffs(lowcut_hz=None, highcut_hz=None), set_tube_and_mic(...),
        # set_bands(gains, ...), set_model(model_id). Optional siblings keep
        # their current value; a required one has to be read from the object,
        # which is how set_timing(attack_ms, release_ms) gets its attack time.
        kwargs = {p.attr: value}
        for name, argument in arguments.items():
            if name != p.attr and argument.default is inspect.Parameter.empty:
                kwargs[name] = getattr(target, name)
        method(**kwargs)
    elif not arguments:
        # _update_filter(): the value was already assigned, the call rebuilds
        # the derived state.
        method()
    else:
        # select_cab(cab_name), set_semitones(value), set_glide(pct): the only
        # argument is the value, under a name that differs from the attribute.
        method(value)


def set(chain, section: str, key: str, value, *, lock=None, hook=True) -> Any:
    """Write one parameter and return the value that was stored.

    ``lock`` is for writes that must be serialised against another entry point
    in the caller (the cabinet IR swap shares its lock with the upload
    endpoints).

    ``hook=False`` assigns the attribute without calling the setter. It exists
    for one caller only: the GE150 import has always stored ``screamer.tone``
    without rebuilding its biquad, so a loaded preset keeps whatever tone
    filter the chain already had. That is a bug (docs/SIGNAL_CHAIN_READINESS.md
    section 10), but this module reproduces it rather than fixing it behind the
    refactor's back -- no recorded golden can see a filter coefficient.
    """
    mod, p, index = resolve(section, key)
    target = _target(chain, mod)
    if index is None:
        value = _clamp(p, _coerce(p, value))
    else:
        value = _coerce(p, value, element=True)

    if lock is None:
        return _apply(target, p, index, value, hook)
    with lock:
        return _apply(target, p, index, value, hook)


def _apply(target, p: params.Param, index: Optional[int], value, hook: bool):
    if index is not None:
        values = list(getattr(target, p.attr))
        while len(values) <= index:
            values.append(0.0)
        values[index] = value
        value = values
    if p.assign:
        setattr(target, p.attr, value)
    if hook and p.setter:
        _call_setter(target, p, value)
    return value


def apply_settings(chain, section: str, values: dict, *, skip: Iterable[str] = ()) -> list:
    """Apply every known key in ``values`` to one block, in registry order.

    ``values`` may be a foreign format (a MOOER export, a stored preset): keys
    the registry does not know are ignored, and ``None`` means "this source
    does not carry the value", which leaves the chain untouched -- the same
    thing the DSP setters do with a ``None`` argument.

    ``skip`` names parameters the caller deliberately withholds.
    """
    mod = params.module(section)
    skipped = frozenset(skip)
    applied = []
    for p in mod.params:
        # An index-addressed parameter is still applied as a whole list here;
        # only the individual ``band3`` form belongs to the API.
        if p.read_only or p.owner == "server" or p.key in skipped:
            continue
        source_key = next((k for k in (p.key, *p.aliases) if k in values), None)
        if source_key is None or values[source_key] is None:
            continue
        try:
            set(chain, section, p.key, values[source_key])
        except NonFiniteValue:
            # A foreign file must not abort half-way through the block.
            logger.warning("Ignored non-finite %s.%s from a loaded preset", section, p.key)
            continue
        applied.append(p.key)
    return applied
