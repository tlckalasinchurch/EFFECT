"""
Write a collection of KEMPER rigs as a .rigpack.

The table layout is copied from the installed packs (all 35 share it) and the
rig blobs are copied byte-for-byte, so what we write decodes with
kemper_importer exactly like the original.

NOT verified: whether KEMPER's own Rig Manager accepts the file. Official
packs carry a 20-byte `packs.signature2`; this writer leaves it NULL because
the signing scheme is unknown.
"""

import os
import re
import secrets
import sqlite3
import time

SCHEMA = (
    'CREATE TABLE `packupdates` (  `id`    INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT UNIQUE,  `packguid`      TEXT NOT NULL,  `oldguid`       TEXT NOT NULL  )',
    'CREATE TABLE `texts` (  `id`    INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT UNIQUE,  `packs_id`      INTEGER NOT NULL,  `lang`  TEXT,  `short` TEXT,  `long`  TEXT  )',
    'CREATE TABLE `properties` (  `id`    INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT UNIQUE,  `packs_id`      INTEGER NOT NULL,  `key`  TEXT,  `val`  TEXT  )',
    'CREATE TABLE `images` (  `id`    INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT UNIQUE,  `packs_id`      INTEGER NOT NULL,  `sequence`      INTEGER,  `image` BLOB,  `locator`       INTEGER,  `description`   TEXT  )',
    'CREATE TABLE `packs` (  `id`    INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT UNIQUE,  `name`  TEXT NOT NULL,  `copyright`     TEXT NOT NULL,  `author`        TEXT NOT NULL,  `releasedate`   TEXT NOT NULL,  `guid`  TEXT NOT NULL,  `updateguid`    TEXT NOT NULL,  `minversion`    TEXT NOT NULL,  `signature2`    BLOB  )',
    'CREATE TABLE `rigs` (  `id`    INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT UNIQUE,  `packs_id`      INTEGER NOT NULL,  `name`  TEXT,  `author`        TEXT,  `createdate`    TEXT,  `comment`       TEXT,  `rig_id`        INTEGER NOT NULL  )',
    'CREATE TABLE `rigdata` (  `id`    INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT UNIQUE,  `rig`   BLOB  )',
)


def _guid():
    # Same shape as the installed packs: 8_8_16 upper-case hex.
    return f"{secrets.token_hex(4)}_{secrets.token_hex(4)}_{secrets.token_hex(8)}".upper()


def safe_filename(name):
    stem = re.sub(r"[^\w \-.()]", "", name or "", flags=re.UNICODE).strip(" .")[:80]
    return stem or "My Rigs"


def export_rigpack(rigs, out_dir, name, author="Hack-effect"):
    """
    rigs: list of {name, author, createdate, comment, blob}. Returns the path.
    Never overwrites: a name clash gets a timestamp suffix.
    """
    if not rigs:
        raise ValueError("no rigs to export")
    os.makedirs(out_dir, exist_ok=True)
    stem = safe_filename(name)
    path = os.path.join(out_dir, f"{stem}.rigpack")
    if os.path.exists(path):
        path = os.path.join(out_dir, f"{stem} {time.strftime('%Y%m%d-%H%M%S')}.rigpack")
    tmp = f"{path}.part"
    if os.path.exists(tmp):
        os.remove(tmp)

    now = time.localtime()
    conn = sqlite3.connect(tmp)
    try:
        for stmt in SCHEMA:
            conn.execute(stmt)
        conn.execute("PRAGMA user_version = 1")
        conn.execute(
            "INSERT INTO packs (name, copyright, author, releasedate, guid, updateguid, minversion) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (name, f"© {now.tm_year} {author}", author,
             time.strftime("%Y%m%d%H%M%S", now), _guid(), _guid(), "5.0"),
        )
        for rig in rigs:
            cur = conn.execute("INSERT INTO rigdata (rig) VALUES (?)", (rig["blob"],))
            conn.execute(
                "INSERT INTO rigs (packs_id, name, author, createdate, comment, rig_id) "
                "VALUES (1, ?, ?, ?, ?, ?)",
                (rig["name"], rig["author"], rig["createdate"], rig["comment"], cur.lastrowid),
            )
        for key, val in (("Content", "Rigs"), ("type", "user"), ("visibility", "65535"),
                         ("rm_minversion", "3.0"), ("rm_maxversion", ""),
                         ("tool", "Hack-effect rigpack_export"),
                         ("timestamp", time.strftime("%Y-%m-%d %H:%M:%S", now))):
            conn.execute("INSERT INTO properties (packs_id, key, val) VALUES (1, ?, ?)", (key, val))
        conn.commit()
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("exported pack failed integrity_check")
    except Exception:
        conn.close()
        os.remove(tmp)
        raise
    conn.close()
    os.replace(tmp, path)
    return path
