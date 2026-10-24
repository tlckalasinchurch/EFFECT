"""Which hardware a chain is voicing, and the block order that goes with it.

Only two modes exist:

* ``generic`` -- built-in rigs, preserving the legacy order exactly.
* ``nam`` -- a TONE3000 capture in the amp slot, with the same stage order.

GE150, Quad Cortex and Kemper modes were removed on 2026-10-24. Their DSP was
an order change plus a hand-tuned voicing, not the hardware's processing, and
the owner judged the result unusable -- "the others don't work". Adding a mode
back means building and listening to its sound first, not just listing it here.

A stage name is one of the keys ``GuitarSignalChain.process`` understands:

* ``gate`` / ``pitch`` / ``tap`` / ``screamer`` / ``eq`` / ``cab`` / ``mod``
  / ``delay`` / ``reverb`` -- the block of the same name;
* ``amp`` -- the amp slot, which runs the installed NAM chain when there is one
  and ``AmpHead`` otherwise (only one is ever audible);
* ``tap`` -- copy the signal for the parallel mixer (no output of its own);
* ``parallel`` -- blend the tap back in when ``parallel_enabled`` is set.

``tap`` and ``parallel`` are markers, not blocks; a mode that leaves them out
ignores the parallel controls, which is why both modes below keep them.
"""

from typing import Tuple

DEFAULT_MODE = "generic"

#: Every mode the chain accepts.
DEVICE_MODES: Tuple[str, ...] = ("generic", "nam")

#: Stage vocabulary; kept in sync with ``GuitarSignalChain.process``.
STAGES: Tuple[str, ...] = (
    "gate", "pitch", "tap", "screamer", "amp", "eq", "cab", "parallel",
    "mod", "delay", "reverb",
)

#: The generic order: what every chain used before device modes existed.
GENERIC_ORDER: Tuple[str, ...] = (
    "gate", "pitch", "tap", "screamer", "amp", "eq", "cab", "parallel",
    "mod", "delay", "reverb",
)

BLOCK_ORDERS: dict = {
    # Bit-identical to the fixed path; pinned by tests/golden/dsp_chain_*.json.
    "generic": GENERIC_ORDER,
    # A TONE3000 capture replaces the amp block; nothing else moves yet.
    "nam": GENERIC_ORDER,
}

#: Only an explicit TONE3000/NAM load selects the NAM mode.
SOURCE_MODES: dict = {"tone3000": "nam", "t3k": "nam", "nam": "nam"}


def _validate() -> None:
    seen = set()
    for mode, order in BLOCK_ORDERS.items():
        if mode not in DEVICE_MODES:
            raise ValueError(f"{mode}: not in DEVICE_MODES")
        if len(set(order)) != len(order):
            raise ValueError(f"{mode}: duplicate stage in {order}")
        unknown = set(order) - set(STAGES)
        if unknown:
            raise ValueError(f"{mode}: unknown stages {sorted(unknown)}")
        for required in ("gate", "pitch", "amp"):
            if required not in order:
                raise ValueError(f"{mode}: missing required stage {required!r}")
        seen.add(mode)
    missing = set(DEVICE_MODES) - seen
    if missing:
        raise ValueError(f"no block order for {sorted(missing)}")


_validate()


def block_order(mode: str) -> Tuple[str, ...]:
    """Return the stage order for ``mode``; unknown modes raise ``ValueError``.

    The setter on the chain calls this before storing anything, so a typo from
    the API cannot leave a chain in a half-switched state.
    """
    try:
        return BLOCK_ORDERS[mode]
    except (KeyError, TypeError):
        raise ValueError(
            f"unknown device mode {mode!r}; expected one of {', '.join(DEVICE_MODES)}"
        ) from None


def mode_for_source(source: str) -> str:
    """Map a preset source to a mode. Only TONE3000/NAM has one; the rest is generic."""
    if not source:
        return DEFAULT_MODE
    return SOURCE_MODES.get(str(source).strip().lower().replace("-", "_"), DEFAULT_MODE)
