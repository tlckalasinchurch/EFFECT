"""
KEMPER Rig Pack reader for กดจนหลอนTone

A .rigpack file is a SQLite database. Verified schema (all 35 installed packs
share one identical table set):

    packs      id, name, copyright, author, releasedate, guid, updateguid,
               minversion, signature2 BLOB
    rigs       id, packs_id, name, author, createdate, comment, rig_id
    rigdata    id, rig BLOB
    texts      id, packs_id, lang, short, long
    properties id, packs_id, key, val
    images     id, packs_id, sequence, image BLOB, locator, description
    packupdates id, packguid, oldguid

`rigs.comment` is the instrument category ("Guitar", "Bass", "Acoustic") and is
the natural filter field for the library browser.

The `rigdata.rig` blob is a sequence of MIDI SysEx messages separated by a single
padding byte. Verified framing of one message:

    F0 <len> 00 20 33 <A1 A2 A3> <SUB> <00> <TAG> <VALUE...> F7
              ^^^^ Kemper manufacturer ID

`VALUE` is a NUL-terminated latin-1 string for text tags, and a big-endian
binary block otherwise. Tags 1-4 are the rig identity; higher tags carry amp
descriptors.

The relational columns are the source of truth for name/author/comment because
they are indexed and consistent; the SysEx payload is decoded for enrichment
only. Tag semantics beyond tag 4 are inferred from sampled content, so they are
exposed under generic keys rather than asserted as stable API.
"""

import glob
import os
import sqlite3

import config

# KEMPER_PACK_DIR is kept for backwards compatibility with existing callers.
KEMPER_PACK_DIR = str(config.KEMPER_PACK_DIR)

KEMPER_MANUFACTURER = b"\x00\x20\x33"

# Text tags whose meaning was verified against the relational columns.
# Verified: tag 1 == rigs.name, 2 == rigs.author, 3 == rigs.createdate.
TAG_RIG_NAME = 1
TAG_RIG_AUTHOR = 2
TAG_RIG_CREATED = 3
TAG_RIG_TYPE = 4

VERIFIED_TEXT_TAGS = {
    TAG_RIG_NAME: "rig_name",
    TAG_RIG_AUTHOR: "rig_author",
    TAG_RIG_CREATED: "rig_created",
    TAG_RIG_TYPE: "rig_type",
}

# Amp-descriptor tags seen in sampled blobs. Names are descriptive labels for
# this implementation, NOT a claim about KEMPER's own field naming.
AMP_TEXT_TAGS = {
    16: "amp_name", 17: "amp_maker", 18: "amp_date_a", 19: "amp_date_b",
    20: "amp_voice", 21: "amp_model", 22: "amp_variant", 23: "amp_source",
    24: "amp_mod", 25: "amp_style", 26: "amp_tag", 27: "amp_year",
    32: "cab_name", 33: "cab_maker", 34: "cab_date_a", 35: "cab_date_b",
    36: "brand", 37: "model", 38: "mic", 39: "field_a", 40: "field_b",
    41: "size_a", 42: "size_b", 43: "position", 44: "field_c", 45: "field_d",
    46: "field_e",
}

# Pack-level keys worth surfacing to the UI.
INTERESTING_PROPERTIES = (
    "type", "visibility", "rm_minversion", "rm_maxversion",
    "vendor_url", "Content", "timestamp",
)


def _pack_paths():
    directory = KEMPER_PACK_DIR
    if not os.path.isdir(directory):
        return []
    return sorted(glob.glob(os.path.join(directory, "*.rigpack")))


def _connect(path):
    # Read-only: never let an inspection write to an installed pack.
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def iter_sysex(blob):
    """Yield (address, sub, value) for each KEMPER SysEx message in `blob`."""
    if not blob:
        return
    i = 0
    n = len(blob)
    while i < n:
        start = blob.find(b"\xf0", i)
        if start == -1 or start + 2 >= n:
            return
        # F0 <len> ...: len counts the bytes after itself, F7 included. A
        # length byte >= 0x80 is two 7-bit groups (the 233/541-byte messages).
        if blob[start + 1] & 0x80:
            length = ((blob[start + 1] & 0x7F) << 7) | blob[start + 2]
            head = 3
        else:
            length = blob[start + 1]
            head = 2
        end = start + head + length
        if end > n or blob[end - 1] != 0xF7:
            return
        msg = blob[start:end]
        i = end
        # F0 <len> <3-byte mfr> <3-byte addr> <sub> ... F7
        if len(msg) < head + 10 or msg[head:head + 3] != KEMPER_MANUFACTURER:
            continue
        yield msg[head + 3:head + 6], msg[head + 6], msg[head + 7:-1]


def decode_rig_blob(blob):
    """
    Decode a rigdata.rig blob.

    Returns a dict with:
        text     {tag: string} for every NUL-terminated text value
        verified {name, author, created, rig_type} from tags 1-4
        amp      {label: string} for the amp-descriptor tags
        raw      {hex-tag: hex-value} for every tagged chunk (incl. binary)
        messages total KEMPER SysEx message count
    """
    result = {"text": {}, "verified": {}, "amp": {}, "raw": {}, "messages": 0}
    if not blob:
        return result

    for addr, sub, value in iter_sysex(blob):
        result["messages"] += 1
        # Text chunks: function 0x03 (addr[2]) with page 0x00, then the tag byte.
        if addr[2] == 0x03 and len(value) >= 2 and value[0] == 0x00:
            tag = value[1]
            text = value[2:].split(b"\x00", 1)[0].decode("latin-1", "ignore")
            result["text"][tag] = text
            if tag in VERIFIED_TEXT_TAGS:
                result["verified"][VERIFIED_TEXT_TAGS[tag]] = text
            elif tag in AMP_TEXT_TAGS:
                result["amp"][AMP_TEXT_TAGS[tag]] = text
            else:
                result["amp"].setdefault(f"tag_{tag}", text)
        else:
            # addr/sub only name the function; the first value bytes are the
            # page/param, so they are part of the key or chunks overwrite.
            key = f"{tag_hex(addr)}:{sub:02x}:{value[:5].hex()}"
            while key in result["raw"]:
                key += "+"
            result["raw"][key] = value.hex()
    return result


def tag_hex(addr):
    return "".join(f"{b:02x}" for b in addr)


# Parameter blocks are function 0x02 messages: value = <page> <param> then
# 14-bit words (two 7-bit bytes, MSB first), one per consecutive param index.
# INFERRED, not from Kemper's code: page 0x0a word 4 is amp gain and page 0x0b
# words 4-7 are bass/mid/treble/presence. Evidence: EQ words are centred on
# 8192 across all 363 factory rigs, and gain averages ~2300 on rigs named
# clean/jazz/twin vs ~8900 on metal/5150/recto/lead rigs.
PARAM_PAGE_AMP = 0x0A
PARAM_PAGE_EQ = 0x0B


def _param_words(blob, page):
    for addr, _sub, value in iter_sysex(blob):
        if addr[2] == 0x02 and len(value) >= 4 and value[0] == page and value[1] == 0:
            body = value[2:]
            return [(body[i] << 7) | body[i + 1] for i in range(0, len(body) - 1, 2)]
    return None


def decode_rig_params(blob):
    """Return {gain, bass, mid, treble, presence} as 0..1 floats, or None."""
    amp = _param_words(blob, PARAM_PAGE_AMP)
    eq = _param_words(blob, PARAM_PAGE_EQ)
    if not amp or not eq or len(amp) < 5 or len(eq) < 8:
        return None
    scale = 16383.0
    return {
        "gain": amp[4] / scale,
        "bass": eq[4] / scale,
        "mid": eq[5] / scale,
        "treble": eq[6] / scale,
        "presence": eq[7] / scale,
    }


def get_rig_params(pack_path, rig_id):
    """Params for one rig. Only installed packs are opened (path comes from the client)."""
    target = os.path.abspath(pack_path or "")
    if target not in {os.path.abspath(p) for p in _pack_paths()}:
        return None
    conn = None
    try:
        conn = _connect(target)
        row = conn.execute(
            "SELECT rd.rig FROM rigs r JOIN rigdata rd ON r.rig_id = rd.id WHERE r.id = ?",
            (rig_id,),
        ).fetchone()
        return decode_rig_params(row[0]) if row and row[0] else None
    except sqlite3.Error:
        return None
    finally:
        if conn is not None:
            conn.close()


def list_installed_kemper_packs():
    """
    Return one record per installed .rigpack.

    Failures on a single pack are collected rather than silently swallowed, so
    a corrupt file cannot hide behind an empty list.
    """
    packs = []
    for path in _pack_paths():
        record = {
            "path": path,
            "filename": os.path.basename(path),
            "pack_name": os.path.basename(path),
            "author": "Kemper",
            "rig_count": 0,
            "releasedate": None,
            "minversion": None,
            "type": None,
            "visibility": None,
            "description": None,
            "artwork": False,
            "properties": {},
            "error": None,
        }
        conn = None
        try:
            conn = _connect(path)
            conn.row_factory = sqlite3.Row

            row = conn.execute(
                "SELECT name, author, releasedate, minversion, guid FROM packs LIMIT 1"
            ).fetchone()
            if row:
                record["pack_name"] = row["name"] or record["pack_name"]
                record["author"] = row["author"] or "Kemper"
                record["releasedate"] = row["releasedate"]
                record["minversion"] = row["minversion"]

            record["rig_count"] = conn.execute(
                "SELECT COUNT(*) FROM rigs"
            ).fetchone()[0]

            props = {}
            for k, v in conn.execute("SELECT key, val FROM properties"):
                props[k] = v
            record["properties"] = props
            for key in INTERESTING_PROPERTIES:
                if key in props:
                    field = key.replace("rm_", "").replace("minversion", "minversion")
                    if field in ("minversion", "maxversion", "type", "visibility",
                                 "vendor_url", "Content", "timestamp"):
                        record[field] = props[key]

            art = conn.execute(
                "SELECT description, length(image) FROM images ORDER BY sequence LIMIT 1"
            ).fetchone()
            if art and art[1]:
                record["artwork"] = True
                record["description"] = art[0]

            long_text = conn.execute(
                "SELECT long FROM texts WHERE long IS NOT NULL AND long <> '' LIMIT 1"
            ).fetchone()
            if long_text:
                record["long_description"] = long_text[0].strip()

        except sqlite3.Error as exc:
            record["error"] = str(exc)
        finally:
            if conn is not None:
                conn.close()

        packs.append(record)
    return packs


def read_rigs_from_pack(pack_path, limit=50, decode=True):
    """
    Return rig rows for one pack.

    The relational columns provide name/author/comment/createdate; when
    `decode` is set, the SysEx payload adds amp/cab metadata and a decode
    status so callers can tell a rich row from a metadata-only one.
    """
    if not os.path.exists(pack_path):
        return []

    conn = None
    try:
        conn = _connect(pack_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT r.id, r.name, r.author, r.comment, r.createdate, rd.rig
            FROM rigs r
            LEFT JOIN rigdata rd ON r.rig_id = rd.id
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

        rigs = []
        for row in rows:
            blob = row["rig"]
            rig = {
                "id": row["id"],
                "name": row["name"],
                "author": row["author"],
                "comment": row["comment"],
                "createdate": row["createdate"],
                "category": (row["comment"] or "").strip() or None,
                "has_sysex": blob is not None,
                "pack_path": pack_path,
                "params": decode_rig_params(blob) if decode and blob else None,
                "amp": {},
                "decode": "skipped",
            }

            if decode and blob:
                info = decode_rig_blob(blob)
                verified = info["verified"]
                rig["amp"] = info["amp"]
                rig["sysex_messages"] = info["messages"]
                # Only fall back to the blob when the column is actually null.
                rig["name"] = rig["name"] or verified.get("rig_name")
                rig["author"] = rig["author"] or verified.get("rig_author")
                rig["createdate"] = rig["createdate"] or verified.get("rig_created")
                consistent = (
                    verified.get("rig_name") in (None, rig["name"])
                    and verified.get("rig_author") in (None, rig["author"])
                )
                rig["decode"] = "ok" if consistent else "mismatch"
                rig["rig_type"] = verified.get("rig_type")

            rigs.append(rig)
        return rigs
    except sqlite3.Error:
        return []
    finally:
        if conn is not None:
            conn.close()


def _fetch_rig_row(path, rig_id):
    """(id, name, author, comment, createdate, blob) from one pack, or None."""
    conn = None
    try:
        conn = _connect(path)
        return conn.execute(
            "SELECT r.id, r.name, r.author, r.comment, r.createdate, rd.rig "
            "FROM rigs r LEFT JOIN rigdata rd ON r.rig_id = rd.id WHERE r.id = ?",
            (rig_id,),
        ).fetchone()
    except sqlite3.Error:
        return None
    finally:
        if conn is not None:
            conn.close()


def get_rig_for_export(filename, rig_id):
    """Raw rig (name, author, createdate, comment, blob) from an installed pack, or None."""
    path = find_pack_path(filename)
    row = _fetch_rig_row(path, rig_id) if path else None
    if not row or not row[5]:
        return None
    _rid, name, author, comment, created, blob = row
    return {"name": name, "author": author, "createdate": created,
            "comment": comment, "blob": bytes(blob)}


def get_rig(pack_path, rig_id):
    """One rig row (same shape as read_rigs_from_pack), or None. Installed packs only."""
    target = os.path.abspath(pack_path or "")
    path = next((p for p in _pack_paths() if os.path.abspath(p) == target), None)
    if path is None:
        return None
    row = _fetch_rig_row(path, rig_id)
    if not row:
        return None
    rid, name, author, comment, created, blob = row
    info = decode_rig_blob(blob) if blob else {"amp": {}}
    return {
        "id": rid, "name": name, "author": author, "comment": comment,
        "createdate": created, "category": (comment or "").strip() or None,
        "pack": os.path.basename(path), "pack_path": path,
        "params": decode_rig_params(blob) if blob else None,
        "amp": info["amp"],
    }


def find_pack_path(filename):
    """Installed pack path for a bare filename, or None."""
    return next((p for p in _pack_paths() if os.path.basename(p) == filename), None)


def search_packs(query, category=None, limit=100, include_amp=False,
                 gain_min=None, gain_max=None):
    """
    Library search across every installed pack.

    `query` is matched case-insensitively against rig name and author.
    `category` filters on rigs.comment ("Guitar", "Bass", "Acoustic").
    With `include_amp`, the rigdata SysEx payload is decoded as well so the
    source amp (amp_name, brand, model, cab_name) also matches. That costs
    roughly one decode per rig, so it is opt-in for interactive use.

    Returns rows in pack order, which is the order the library shows them.
    """
    term = (query or "").strip().lower()
    results = []
    for pack in list_installed_kemper_packs():
        if pack["error"]:
            continue
        conn = None
        try:
            conn = _connect(pack["path"])
            sql = (
                "SELECT r.id, r.name, r.author, r.comment, r.createdate, rd.rig "
                "FROM rigs r LEFT JOIN rigdata rd ON r.rig_id = rd.id"
            )
            args = []
            if category:
                sql += " WHERE r.comment = ?"
                args.append(category)
            sql += " ORDER BY r.id"
            cursor = conn.execute(sql, args)

            for rid, name, author, comment, created, blob in cursor:
                gain_filter = gain_min is not None or gain_max is not None
                params = decode_rig_params(blob) if blob and (include_amp or gain_filter) else None
                if gain_filter:
                    g = params["gain"] if params else None
                    if g is None or (gain_min is not None and g < gain_min) \
                            or (gain_max is not None and g > gain_max):
                        continue
                if term:
                    haystack = [name or "", author or ""]
                    amp_meta = {}
                    if include_amp and blob:
                        amp_meta = decode_rig_blob(blob)["amp"]
                        haystack.extend(amp_meta.values())
                    if not any(term in (h or "").lower() for h in haystack):
                        continue
                elif include_amp and blob:
                    amp_meta = decode_rig_blob(blob)["amp"]
                else:
                    amp_meta = {}

                results.append({
                    "pack": pack["pack_name"],
                    "pack_path": pack["path"],
                    "id": rid,
                    "name": name,
                    "author": author,
                    "category": comment,
                    "createdate": created,
                    "amp": amp_meta,
                    "params": params,
                })
                if limit and len(results) >= limit:
                    return results
        except sqlite3.Error:
            continue
        finally:
            if conn is not None:
                conn.close()
    return results


def list_categories():
    """Distinct instrument categories across all packs, with counts."""
    counts = {}
    for pack in list_installed_kemper_packs():
        if pack["error"]:
            continue
        conn = None
        try:
            conn = _connect(pack["path"])
            for cat, n in conn.execute(
                "SELECT comment, COUNT(*) FROM rigs GROUP BY comment"
            ):
                key = (cat or "Uncategorised").strip() or "Uncategorised"
                counts[key] = counts.get(key, 0) + n
        except sqlite3.Error:
            continue
        finally:
            if conn is not None:
                conn.close()
    return [{"category": k, "count": v} for k, v in sorted(counts.items())]