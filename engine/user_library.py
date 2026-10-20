"""
Per-user favourites and tags for Kemper rigs.

The installed .rigpack files are read-only, so user data lives in its own JSON
file. A rig is identified by `<pack filename>::<rig id>` because every pack
numbers its rigs from 1.
"""

import json
import os
import re
import threading

import config

_LOCK = threading.Lock()
_KEY_RE = re.compile(r"^[^:\\/]{1,200}::\d{1,9}$")
MAX_TAGS = 20
MAX_TAG_LEN = 32


def rig_key(pack_path, rig_id):
    return f"{os.path.basename(pack_path)}::{int(rig_id)}"


def _load():
    try:
        with open(config.USER_LIBRARY_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save(data):
    # Write-then-replace so a crash cannot leave a half-written library.
    tmp = f"{config.USER_LIBRARY_PATH}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, config.USER_LIBRARY_PATH)


def _check_key(key):
    if not isinstance(key, str) or not _KEY_RE.match(key):
        raise ValueError("invalid rig key")


def get_all():
    with _LOCK:
        return _load()


def set_favourite(key, value):
    _check_key(key)
    with _LOCK:
        data = _load()
        entry = data.setdefault(key, {"favourite": False, "tags": []})
        entry["favourite"] = bool(value)
        if not entry["favourite"] and not entry["tags"]:
            del data[key]
        _save(data)
        return data.get(key, {"favourite": False, "tags": []})


def set_tags(key, tags):
    _check_key(key)
    if not isinstance(tags, list):
        raise ValueError("tags must be a list")
    clean = []
    for t in tags:
        t = str(t).strip().lower()[:MAX_TAG_LEN]
        if t and t not in clean:
            clean.append(t)
    if len(clean) > MAX_TAGS:
        raise ValueError(f"at most {MAX_TAGS} tags per rig")
    with _LOCK:
        data = _load()
        entry = data.setdefault(key, {"favourite": False, "tags": []})
        entry["tags"] = clean
        if not entry["favourite"] and not clean:
            del data[key]
        _save(data)
        return data.get(key, {"favourite": False, "tags": []})
