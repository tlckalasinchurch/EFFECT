import os
import sqlite3
import glob

KEMPER_PACK_DIR = r"C:\Program Files\Kemper Amps\Rig Manager\Rig Packs"

def list_installed_kemper_packs():
    if not os.path.exists(KEMPER_PACK_DIR):
        return []
    packs = []
    for f in glob.glob(os.path.join(KEMPER_PACK_DIR, "*.rigpack")):
        try:
            conn = sqlite3.connect(f)
            c = conn.cursor()
            c.execute("SELECT name, author FROM packs LIMIT 1")
            row = c.fetchone()
            pack_name = row[0] if row else os.path.basename(f)
            author = row[1] if row else "Kemper"
            c.execute("SELECT COUNT(*) FROM rigs")
            rig_count = c.fetchone()[0]
            conn.close()
            packs.append({
                "path": f,
                "filename": os.path.basename(f),
                "pack_name": pack_name,
                "author": author,
                "rig_count": rig_count
            })
        except Exception:
            pass
    return packs

def read_rigs_from_pack(pack_path, limit=50):
    if not os.path.exists(pack_path):
        return []
    conn = sqlite3.connect(pack_path)
    c = conn.cursor()
    query = """
        SELECT r.id, r.name, r.author, r.comment, rd.rig 
        FROM rigs r 
        LEFT JOIN rigdata rd ON r.rig_id = rd.id 
        LIMIT ?
    """
    c.execute(query, (limit,))
    rigs = []
    for row in c.fetchall():
        rid, name, author, comment, blob = row
        params = {}
        if blob:
            # Parse SysEx chunks
            i = 0
            while i < len(blob):
                start = blob.find(b'\xf0', i)
                if start == -1: break
                end = blob.find(b'\xf7', start)
                if end == -1: break
                chunk = blob[start:end+1]
                if len(chunk) > 10 and chunk[2:5] == b'\x00\x20\x33':
                    addr = chunk[7:10]
                    val = chunk[10:-1]
                    if addr == b'\x00\x00\x01':
                        params['rig_name'] = val.rstrip(b'\x00').decode('latin1', errors='ignore')
                    elif addr == b'\x00\x00\x02':
                        params['author'] = val.rstrip(b'\x00').decode('latin1', errors='ignore')
                i = end + 1
                
        rigs.append({
            "id": rid,
            "name": name or params.get('rig_name', 'Untitled Rig'),
            "author": author or params.get('author', 'Unknown'),
            "comment": comment or '',
            "has_sysex": blob is not None
        })
    conn.close()
    return rigs
