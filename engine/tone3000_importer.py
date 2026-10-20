"""
TONE3000 .t3kpreset importer - real chain-block decoder.

A .t3kpreset is a binary "T3KHS / T3KPreset" container. The body carries
tagged frames, and the parts this app cares about are the ChainBlock entries:

    ChainBlock <NUL> <frame> id <frame>... <NUL> type <NUL> <SP> <len> <typestr> <NUL> ...

Each block carries its source tone's TONE3000 JSON (title / makes / gear) and,
for blocks of type "ir", the actual impulse response embedded inside a
ModelCache as a standard RIFF/WAVE blob. "nam" blocks are neural amp captures
whose toneJson describes the captured gear.

Reverse-engineered from the installed factory presets. Nothing here writes to
the vendor files; they are only ever read.

Framing helper: the container separates keys/values with NUL (byte value 0)
and a byte 0x01 string-type marker, built at runtime via bytes([..]) to keep
this source plain ASCII.
"""

import os
import re
import glob
import io
import struct
import warnings

from scipy.io import wavfile

TONE3000_FACTORY_DIR = r"C:\ProgramData\TONE3000\Presets\Factory"

NUL = bytes([0])
SP1 = bytes([0, 1])            # NUL + string-type marker
CHAINBLOCK_MARKER = b"ChainBlock" + NUL

# Fallback DSP character for presets whose names we already tuned by ear.
# This stays as a safety net; the real gear names now come from the files.
_STYLE_MAP = {
    "Ampeg Bass Drive": ("Bass / Clean", "SansAmp Bass Driver DI", "Ampeg 8x10 SVT", 0.35),
    "Bogner Fullstack": ("High Gain", "Bogner Ecstasy 101B", "Bogner 4x12 V30", 0.75),
    "Dumble Spread": ("Crunch / Boutique", "Dumble Overdrive Special", "Dumble 2x12 Open", 0.50),
    "Marshall Bluesbreaker": ("Vintage Crunch", "1966 JTM45 Bluesbreaker", "Marshall 1960A Greenback", 0.55),
    "Matchless Crunch": ("Class-A Crunch", "Matchless Brave 30", "Matchless 2x12 Custom", 0.50),
    "Mesa Pitch Shift": ("High Gain Lead", "Mesa Boogie Dual Rectifier", "Mesa Rectifier 4x12 Slant", 0.80),
    "Stereo Crunch Verb": ("Ambient Crunch", "JHS Morning Glory + Amp", "Celestion V30 4x12", 0.45),
    "Stereo Fuzz": ("Fuzz / Psychedelic", "Magnatone M10A 1966 + Fuzz", "Vintage 1x12 Oxford", 0.85),
}

# An ir block whose source gear is a reverb/delay/other capture is never a
# speaker cabinet.
_NON_CAB_GEARS = {"space", "reverb", "delay", "echo", "outboard", "mic", "amp"}


def _read_preset_bytes(path):
    return open(path, "rb").read()


def _frame_value(region, start, key, win=200):
    """Read a tagged frame value: value runs from 2 bytes after the marker."""
    tag = NUL + key.encode() + SP1
    i = region.find(tag, start, start + win)
    if i < 0:
        return None
    raw = region[i + len(tag) + 2:]
    end = raw.find(NUL)
    if end <= 0:
        return None
    return raw[:end].decode("utf-8", "ignore")


def _riff_waves(region):
    """Decode every decodable RIFF/WAVE blob in `region` as (rate, samples)."""
    out = []
    for m in re.finditer(b"RIFF", region):
        o = m.start()
        if o + 12 > len(region):
            continue
        try:
            size = struct.unpack("<I", region[o + 4:o + 8])[0]
            if region[o + 8:o + 12] != b"WAVE" or size <= 0 or size > 10_000_000:
                continue
            blob = region[o:o + 8 + size]
            with warnings.catch_warnings():
                # scipy.io.wavfile emits WavFileWarning for auxiliary DAW/BWF metadata chunks
                # (e.g. bext, cart, minf, regn, umid, _PMX, id3). The PCM audio in 'data' is valid.
                warnings.filterwarnings("ignore", category=wavfile.WavFileWarning)
                sr, data = wavfile.read(io.BytesIO(blob))
            out.append((sr, data))
        except Exception:
            continue
    return out


def _parse_blocks(data):
    """Split the container at ChainBlock markers and decode each block."""
    marks = [m.start() for m in re.finditer(CHAINBLOCK_MARKER, data)]
    blocks = []
    for i, pos in enumerate(marks):
        end = marks[i + 1] if i + 1 < len(marks) else len(data)
        block_type = _frame_value(data, pos, "type") or "?"
        if len(block_type) > 12:
            continue  # footer/descriptor mentions, not a real block
        region = data[pos:end]

        title_m = re.search(rb'"title": "([^"]+)"', region)
        gear_m = re.search(rb'"gear": "([A-Za-z0-9_]+)"', region)
        makes = [m.decode("utf-8", "ignore")
                 for m in re.findall(rb'"name": "([^"]{4,70})"', region)][:6]

        block = {
            "type": block_type,
            "title": title_m.group(1).decode("utf-8", "ignore") if title_m else None,
            "gear": gear_m.group(1).decode() if gear_m else None,
            "makes": makes,
            "wav_count": 0,
            "ir_sample_rate": None,
            "ir_samples": None,
        }
        if block_type == "ir":
            wavs = _riff_waves(region)
            block["wav_count"] = len(wavs)
            if wavs:
                # When several blobs sit in one region, the shortest one is
                # the speaker response; long captures are room/reverb tails.
                short = min(wavs, key=lambda w: len(w[1]))
                block["_ir"] = short
                block["ir_sample_rate"] = short[0]
                block["ir_samples"] = len(short[1])
        blocks.append(block)
    return blocks


# Parsing reads ~2 MB files and listing + loading both hit it, so memoise on
# (path, mtime, size).
_PARSE_CACHE = {}


def _cached_parse(path, data):
    try:
        stat = os.stat(path)
        key = (path, stat.st_mtime_ns, stat.st_size)
    except OSError:
        key = (path, 0, len(data))
    hit = _PARSE_CACHE.get(key)
    if hit is None:
        hit = _parse_blocks(data)
        _PARSE_CACHE[key] = hit
    return hit


def _chosen_amp_block(blocks):
    for b in blocks:
        if b["type"] == "nam" and b["title"]:
            return b
    return None


def _chosen_cab_block(blocks):
    """
    First ir block whose source gear is a cabinet AND which embeds a WAVE.

    Presets such as Marshall Bluesbreaker embed only a reverb/room IR
    (gear "reverb") and Stereo Crunch Verb's ir blocks are delay/reverb
    captures; those are not speakers and must fall back to the synthetic cab
    instead of masquerading as one.
    """
    for b in blocks:
        if b["type"] != "ir" or "_ir" not in b:
            continue
        gear = (b["gear"] or "cab").lower()
        if gear in _NON_CAB_GEARS:
            continue
        return b
    return None


def _clean(name):
    'Collapse whitespace and strip non-ASCII glyphs (pack titles ship emoji/mojibake).'
    extra = str(name or "").encode("ascii", "ignore").decode("ascii")
    return " ".join(extra.split())[:64] if extra else None


def _header_name(data):
    """Decode the display name from the T3KPresetHeader section."""
    tag = NUL + b"name" + NUL + bytes([17, 5])   # observed: len-mark then text
    i = data.find(tag, 0, 1024)
    if i >= 0:
        raw = data[i + len(tag):]
        end = raw.find(NUL)
        if end > 0:
            return raw[:end].decode("utf-8", "ignore")
    return None


def list_tone3000_presets():
    if not os.path.exists(TONE3000_FACTORY_DIR):
        return []

    presets = []
    for filepath in glob.glob(os.path.join(TONE3000_FACTORY_DIR, "*.t3kpreset")):
        try:
            fname = os.path.basename(filepath)
            data = _read_preset_bytes(filepath)

            # The product name comes from the filename, exactly as the
            # TONE3000 app lists it ("Ampeg Bass Drive", ...).
            clean_name = fname.replace(".t3kpreset", "")
            preset_name = _clean(clean_name)
            category, fallback_amp, fallback_cab, gain_val = _STYLE_MAP.get(
                clean_name, ("Modern Amp", preset_name, "Celestion V30 4x12", 0.6)
            )

            blocks = _cached_parse(filepath, data)
            amp_block = _chosen_amp_block(blocks)
            cab_block = _chosen_cab_block(blocks)
            chain = [
                {"type": b["type"], "title": _clean(b["title"]), "gear": b["gear"]}
                for b in blocks if b["type"] in ("nam", "ir") and b["title"]
            ]

            # Real gear names decoded from the preset take priority; the
            # curated guess remains only as an offline fallback.
            amp_name = _clean(amp_block["title"]) if amp_block else fallback_amp

            cab_name = fallback_cab
            mic_name = None
            if cab_block:
                cab_name = _clean(cab_block["title"])
                if cab_block["makes"]:
                    known_mics = ("shure sm57", "shure sm58", "sennheiser md 421", "senheiser md 421",
                                  "coles 4038", "alnico blue")
                    mic_name = next((mk for mk in cab_block["makes"]
                                     if mk.lower() in known_mics), None)

            presets.append({
                # Stable identifiers used by the server and the UI.
                "id": "t3k_" + clean_name.lower().replace(" ", "_"),
                "name": preset_name,
                "file_name": fname,
                "file_path": filepath,
                "author": "TONE3000 Factory",
                "category": category,
                "gain": gain_val,

                # Real decoded data.
                "amp_name": amp_name,
                "cab_name": cab_name or fallback_cab,
                "cab_fallback": fallback_cab,
                "ir_mic": _clean(mic_name),
                "chain": chain,
                "has_nam": any(b["type"] == "nam" for b in blocks),
                "has_real_ir": cab_block is not None,
                "ir_samples": cab_block["ir_samples"] if cab_block else None,
                "ir_sample_rate": cab_block["ir_sample_rate"] if cab_block else None,
                "ir_duration_ms": (round(cab_block["ir_samples"] * 1000 / cab_block["ir_sample_rate"])
                                   if cab_block else None),
                "file_size_kb": len(data) // 1024,
            })
        except Exception:
            continue

    # The old dict kept 'amp_model'/'cab_model' as the visible columns; keep
    # those keys so the UI, audit and older callers stay compatible.
    for p in presets:
        p.setdefault("amp_model", p["amp_name"] or "NAM Capture")
        p.setdefault("cab_model", p["cab_name"] or "Celestion V30 4x12")
    return presets


def get_real_cab_ir(file_path):
    """
    Return the embedded cabinet IR of a preset.

    Returns (sample_rate, samples, title) or None when the preset carries no
    decodable speaker IR (nam-only chains, reverb-only IRs, ...).
    The vendor file is read through the same cached parse used for listing.
    """
    try:
        data = _read_preset_bytes(file_path)
        blocks = _cached_parse(file_path, data)
        block = _chosen_cab_block(blocks)
        if not block or "_ir" not in block:
            return None
        sr, samples = block["_ir"]
        title = (block["title"] or "TONE3000 Cab IR").strip()
        return int(sr), samples, title
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Embedded NAM models
#
# Every "nam" ChainBlock carries its neural model as JSON (NAM v0.7.0): either
# one SlimmableContainer holding a small and a full WaveNet, or the two WaveNets
# on their own. Reverse-engineered from the factory presets; read-only.
# ---------------------------------------------------------------------------
_NAM_JSON_START = re.compile(rb'\{"version":"[0-9.]+","metadata"')
_NAM_MODEL_CACHE = {}


def _json_object_at(buf, start):
    """Bytes of the JSON object that opens at buf[start], or None (brace matching)."""
    depth, in_str, esc = 0, False, False
    for i in range(start, len(buf)):
        c = buf[i]
        if in_str:
            if esc:
                esc = False
            elif c == 0x5C:
                esc = True
            elif c == 0x22:
                in_str = False
        elif c == 0x22:
            in_str = True
        elif c == 0x7B:
            depth += 1
        elif c == 0x7D:
            depth -= 1
            if depth == 0:
                return buf[start:i + 1]
    return None


def _nam_container(models):
    """One slimmable container per block: prefer the shipped one, else pair the plain WaveNets."""
    for m in models:
        if m.get("architecture") == "SlimmableContainer":
            return m
    plain = sorted((m for m in models if m.get("architecture") == "WaveNet"),
                   key=lambda m: len(m["weights"]))
    if not plain:
        return None
    subs = [{"max_value": 0.5 if i < len(plain) - 1 else 1.0, "model": m} for i, m in enumerate(plain)]
    return {"architecture": "SlimmableContainer", "metadata": {}, "config": {"submodels": subs}}


def _nam_blocks(path):
    """[(title, gear_type, container_json)] for each NAM block, in chain order."""
    import json
    stat = os.stat(path)
    key = (path, stat.st_mtime_ns, stat.st_size)
    hit = _NAM_MODEL_CACHE.get(key)
    if hit is not None:
        return hit
    data = _read_preset_bytes(path)
    marks = [m.start() for m in re.finditer(CHAINBLOCK_MARKER, data)]
    out = []
    for i, pos in enumerate(marks):
        if (_frame_value(data, pos, "type") or "?") != "nam":
            continue
        region = data[pos:marks[i + 1] if i + 1 < len(marks) else len(data)]
        models = []
        for m in _NAM_JSON_START.finditer(region):
            raw = _json_object_at(region, m.start())
            if raw:
                try:
                    models.append(json.loads(raw))
                except ValueError:
                    continue
        container = _nam_container(models)
        if container is None:
            continue
        title_m = re.search(rb'"title": "([^"]+)"', region)
        title = title_m.group(1).decode("utf-8", "ignore") if title_m else container["metadata"].get("name", "NAM")
        out.append((title, container["metadata"].get("gear_type"), container))
    _NAM_MODEL_CACHE[key] = out
    return out


def get_nam_chain(file_path, quality="lite", input_gain_db=0.0):
    """
    Build the preset's NAM stages as an engine.nam.NamChain, or None when the
    preset has no NAM block. quality: "lite" (3 channels, cheap) or "full" (8).
    """
    from engine.nam import NamChain, SlimmableWaveNet
    if quality not in ("lite", "full"):
        raise ValueError("quality must be 'lite' or 'full'")
    stages = [
        {"title": title, "gear_type": gear, "net": SlimmableWaveNet(container, build=quality)}
        for title, gear, container in _nam_blocks(file_path)
    ]
    return NamChain(stages, input_gain_db=input_gain_db) if stages else None
