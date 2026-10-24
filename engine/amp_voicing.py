"""Per-amp voicing for the standard AmpHead path.

Until now ``AmpHead.model`` was stored but never read by the standard DSP path,
so every amp model -- all 55 MOOER GE150 amps included -- ran the same preamp.
A voicing changes the character of that preamp the way the real amp families
differ: how much gain is on tap, how tight the low end is, the pre-clipping
bias, and fixed mid/high shaping that the knobs do not cover.

These are family-level approximations chosen from published descriptions of
the amps; they are not measurements or reproductions of the originals.

Names that are not recognised (the legacy '5150', 'Plexi', 'Twin', ...) resolve
to ``None`` so those presets keep their existing sound exactly.
"""

# gain_scale: pre-gain = 1 + gain**gain_exp * gain_scale.  The legacy preamp uses 60 / 2.2.
# eq: fixed shaping applied after the clipping stages, (freq_hz, gain_db, q).
_DEFAULTS = dict(lowcut_hz=80.0, gain_scale=60.0, gain_exp=2.2, bias=0.15, stage2=1.8, eq=(), bright=0.35)


def _v(**kw):
    out = dict(_DEFAULTS)
    out.update(kw)
    out["eq"] = tuple(out["eq"])
    return out


# Ordered: the first rule whose keywords all appear in the lower-cased model name wins.
_RULES = (
    (("acoustic",), _v(lowcut_hz=70.0, gain_scale=1.5, gain_exp=1.5, bias=0.0, stage2=0.9,
                       eq=((250, -3.0, 0.9), (5000, 3.0, 0.8)))),
    (("jc-120",), _v(lowcut_hz=60.0, gain_scale=2.5, gain_exp=1.6, bias=0.0, stage2=0.9,
                     eq=((400, -2.0, 0.9), (3500, 2.5, 0.8)), bright=0.2)),
    (("fender", "clean"), _v(lowcut_hz=65.0, gain_scale=6.0, gain_exp=1.8, bias=0.04, stage2=1.0,
                             eq=((500, -3.0, 0.8), (3000, 1.5, 0.8)), bright=0.25)),
    (("fender", "twin"), _v(lowcut_hz=65.0, gain_scale=7.0, gain_exp=1.8, bias=0.04, stage2=1.0,
                            eq=((500, -3.5, 0.8), (3500, 2.0, 0.8)), bright=0.25)),
    (("fender", "bassman"), _v(lowcut_hz=60.0, gain_scale=14.0, gain_exp=2.0, bias=0.08, stage2=1.2,
                               eq=((120, 2.0, 0.8), (500, -2.0, 0.8)), bright=0.2)),
    (("fender",), _v(lowcut_hz=70.0, gain_scale=12.0, gain_exp=2.0, bias=0.06, stage2=1.1,
                     eq=((500, -2.0, 0.8), (3000, 1.5, 0.8)), bright=0.25)),
    (("blues", "clean"), _v(lowcut_hz=70.0, gain_scale=7.0, gain_exp=1.8, bias=0.05, stage2=1.0,
                            eq=((400, 1.5, 0.8),), bright=0.2)),
    (("blues",), _v(lowcut_hz=75.0, gain_scale=22.0, gain_exp=2.0, bias=0.1, stage2=1.4,
                    eq=((700, 2.0, 0.9),), bright=0.2)),
    (("vox",), _v(lowcut_hz=85.0, gain_scale=14.0, gain_exp=1.9, bias=0.1, stage2=1.3,
                  eq=((200, -2.0, 0.8), (2200, 3.5, 0.9)), bright=0.3)),
    (("hiwatt",), _v(lowcut_hz=75.0, gain_scale=18.0, gain_exp=2.0, bias=0.05, stage2=1.2,
                     eq=((100, 1.5, 0.8), (3000, 1.0, 0.8)), bright=0.25)),
    (("plexi",), _v(lowcut_hz=85.0, gain_scale=34.0, gain_exp=2.1, bias=0.1, stage2=1.6,
                    eq=((700, 2.5, 0.9), (4500, 1.0, 0.8)), bright=0.35)),
    (("jcm800",), _v(lowcut_hz=95.0, gain_scale=45.0, gain_exp=2.1, bias=0.12, stage2=1.7,
                     eq=((650, 3.0, 0.9), (2500, 1.5, 0.9)), bright=0.35)),
    (("jcm900",), _v(lowcut_hz=95.0, gain_scale=50.0, gain_exp=2.1, bias=0.12, stage2=1.7,
                     eq=((700, 2.0, 0.9), (3000, 1.5, 0.9)), bright=0.35)),
    (("marshall",), _v(lowcut_hz=90.0, gain_scale=40.0, gain_exp=2.1, bias=0.12, stage2=1.7,
                       eq=((650, 2.5, 0.9),), bright=0.35)),
    (("orange", "clean"), _v(lowcut_hz=75.0, gain_scale=8.0, gain_exp=1.8, bias=0.06, stage2=1.0,
                             eq=((500, 2.5, 0.8), (4000, -1.5, 0.8)), bright=0.15)),
    (("orange",), _v(lowcut_hz=85.0, gain_scale=38.0, gain_exp=2.1, bias=0.12, stage2=1.6,
                     eq=((500, 3.0, 0.8), (4500, -2.5, 0.8)), bright=0.2)),
    (("dumble",), _v(lowcut_hz=70.0, gain_scale=16.0, gain_exp=1.9, bias=0.12, stage2=1.4,
                     eq=((700, 2.5, 0.8), (3000, 1.5, 0.8)), bright=0.15)),
    (("two-rock",), _v(lowcut_hz=70.0, gain_scale=12.0, gain_exp=1.9, bias=0.06, stage2=1.2,
                       eq=((500, -1.5, 0.8), (3500, 2.0, 0.8)), bright=0.3)),
    (("matchless",), _v(lowcut_hz=80.0, gain_scale=24.0, gain_exp=2.0, bias=0.1, stage2=1.4,
                        eq=((2000, 2.5, 0.9),), bright=0.3)),
    (("dr. z",), _v(lowcut_hz=80.0, gain_scale=28.0, gain_exp=2.0, bias=0.1, stage2=1.5,
                    eq=((600, 2.0, 0.8),), bright=0.25)),
    (("jet city",), _v(lowcut_hz=95.0, gain_scale=26.0, gain_exp=2.1, bias=0.1, stage2=1.5,
                       eq=((800, 2.0, 0.9), (3500, 1.0, 0.9)), bright=0.3)),
    (("blackstar",), _v(lowcut_hz=90.0, gain_scale=36.0, gain_exp=2.1, bias=0.12, stage2=1.6,
                        eq=((1500, 2.0, 0.9),), bright=0.3)),
    (("mesa", "clean"), _v(lowcut_hz=80.0, gain_scale=8.0, gain_exp=1.9, bias=0.06, stage2=1.1,
                           eq=((700, -1.5, 0.8), (3500, 1.5, 0.8)), bright=0.25)),
    (("mesa",), _v(lowcut_hz=105.0, gain_scale=62.0, gain_exp=2.2, bias=0.15, stage2=1.9,
                   eq=((120, 3.0, 0.8), (700, -4.0, 0.9), (2800, 2.0, 0.9)), bright=0.3)),
    (("engl", "clean"), _v(lowcut_hz=85.0, gain_scale=8.0, gain_exp=1.9, bias=0.06, stage2=1.1,
                           eq=((600, -1.0, 0.8), (3000, 1.5, 0.8)), bright=0.25)),
    (("engl",), _v(lowcut_hz=110.0, gain_scale=65.0, gain_exp=2.2, bias=0.15, stage2=1.9,
                   eq=((1500, 2.5, 0.9), (600, -1.5, 0.9)), bright=0.3)),
    (("diezel", "clean"), _v(lowcut_hz=85.0, gain_scale=8.0, gain_exp=1.9, bias=0.06, stage2=1.1,
                             eq=((1800, 1.5, 0.8),), bright=0.25)),
    (("diezel",), _v(lowcut_hz=115.0, gain_scale=70.0, gain_exp=2.2, bias=0.16, stage2=2.0,
                     eq=((90, 2.0, 0.8), (1800, 2.5, 0.9)), bright=0.3)),
    (("koch",), _v(lowcut_hz=110.0, gain_scale=62.0, gain_exp=2.2, bias=0.15, stage2=1.9,
                   eq=((1200, 2.0, 0.9),), bright=0.3)),
    (("soldano",), _v(lowcut_hz=100.0, gain_scale=60.0, gain_exp=2.2, bias=0.14, stage2=1.9,
                      eq=((1000, 2.5, 0.9), (3500, 1.5, 0.9)), bright=0.3)),
    (("evh",), _v(lowcut_hz=110.0, gain_scale=68.0, gain_exp=2.2, bias=0.16, stage2=2.0,
                  eq=((120, 2.0, 0.8), (2200, 2.0, 0.9)), bright=0.3)),
    (("peavey",), _v(lowcut_hz=110.0, gain_scale=66.0, gain_exp=2.2, bias=0.16, stage2=2.0,
                     eq=((2200, 2.0, 0.9),), bright=0.3)),
)

_CACHE = {}

# Names the built-in presets and tests already use.  They keep the legacy preamp
# so existing presets sound the way they were tuned (and the golden sweep holds).
_LEGACY_NAMES = frozenset({"5150", "plexi", "twin", "clean", "ozzy_neural", "j800", ""})


def resolve_amp_voicing(model):
    """Voicing dict for a model/category name, or None to keep the legacy sound."""
    key = str(model or "")
    if key in _CACHE:
        return _CACHE[key]
    name = key.lower()
    result = None
    if name not in _LEGACY_NAMES:
        for words, voicing in _RULES:
            if all(w in name for w in words):
                result = voicing
                break
    # Clean channels of a lead-oriented family: a low-gain variant of the matched voicing.
    if result is not None and ("clean" in name or name.endswith(" cl")) and result["gain_scale"] > 20.0:
        result = dict(result, gain_scale=8.0, gain_exp=1.9, bias=0.06, stage2=1.1)
    _CACHE[key] = result
    return result
