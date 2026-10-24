"""
กดจนหลอนTone — AI Artist Tone Matcher & Multi-Brand Rig Synthesizer.

Inspired by:
- Positive Grid Bias FX / Spark AI Tone Cloud
- Neural DSP Archetype Artist Suites (Petrucci, Plini, Gojira, Henson, Rabea)
- Kemper Profiler Rig Exchange & Morphing
- MOOER GE150 9-Block Chain & Tone Capture

Given any artist name, song title, or natural-language tone description (in Thai or English),
synthesizes a complete 9-block signal chain, pairs a Real Studio Cabinet IR + 3D Mic position,
builds 8 Quad Cortex performance scenes (A-H), and configures Kemper Morph Slot A <-> Slot B.
"""

from typing import Any, Dict, List, Optional


ARTIST_TONE_PROFILES: List[Dict[str, Any]] = [
    {
        "id": "tim_henson_neural_clean",
        "title": "Polyphia · Tim Henson 'Playing God' Neural Clean & Comp",
        "artist": "Tim Henson (Polyphia)",
        "brand_dna": "Neural DSP Archetype: Tim Henson + Quad Cortex",
        "keywords": ["polyphia", "tim henson", "playing god", "goat", "math rock", "acoustic", "clean", "ใส", "เด้ง", "เกา"],
        "bpm": 138,
        "voicing": "clean",
        "summary": "เสียงคลีนใสประกายไฮไฟแบบマルチแบนด์ ผสม Tri-Chorus บางๆ และ Parallel Direct Path ให้หัวโน้ตชัดทุกการเกานิ้ว",
        "parallel": {"enabled": True, "blend": 0.42},
        "morph_a": {
            "amp_gain": 0.24, "amp_master": 0.82,
            "screamer_drive": 0.12, "screamer_level": 0.72,
            "delay_mix": 0.18, "reverb_mix": 0.26,
            "screamer_enabled": 0.0, "delay_enabled": 1.0,
        },
        "morph_b": {
            "amp_gain": 0.52, "amp_master": 0.86,
            "screamer_drive": 0.42, "screamer_level": 0.82,
            "delay_mix": 0.34, "reverb_mix": 0.38,
            "screamer_enabled": 1.0, "delay_enabled": 1.0,
        },
        "settings": {
            "gate": {"enabled": True, "threshold": -58.0, "release_ms": 40.0, "hold_ms": 30.0, "range_db": -60.0},
            "pitch": {"enabled": False, "semitones": 0.0, "glide": 0.0, "cents": 0.0, "mix": 1.0},
            "screamer": {"enabled": False, "drive": 0.18, "tone": 0.72, "level": 0.78},
            "amp": {"enabled": True, "gain": 0.26, "bass": 0.48, "mid": 0.52, "treble": 0.76, "presence": 0.74, "master": 0.84, "model": "Twin", "bright": True},
            "eq": {"enabled": True, "model_id": 5, "bands": [65.0, 1.5, -1.5, 3.2, 4.5, 18500.0]},
            "cab": {"enabled": True, "ir_name": "Fender Twin 2x12 Jensen", "lowcut": 60.0, "highcut": 18500.0, "mix": 1.0, "level": 1.05, "tube": "6L6", "mic": "U87", "center": 62.0, "distance": 22.0},
            "mod": {"enabled": True, "model_id": 13, "rate": 0.28, "mix": 0.32, "tone": 0.70, "depth": 0.45},
            "delay": {"enabled": True, "time": 0.326, "feedback": 0.34, "mix": 0.22, "ducking": True, "duck_depth": 0.60},
            "reverb": {"enabled": True, "decay": 0.58, "mix": 0.28, "tone": 0.68, "type": "plate", "ducking": True, "duck_depth": 0.50},
        },
    },
    {
        "id": "petrucci_majesty_lead",
        "title": "Dream Theater · John Petrucci 'Majesty' Liquid Solo & Crunch",
        "artist": "John Petrucci (Dream Theater)",
        "brand_dna": "Neural DSP Archetype: Petrucci + Kemper Morph",
        "keywords": ["petrucci", "dream theater", "majesty", "mesa", "jp2c", "mark iv", "solo", "lead", "โซโล่", "ลีด", "หวาน"],
        "bpm": 126,
        "voicing": "highgain",
        "summary": "โทนハイเกนเนื้อแน่นพุ่งติดนิ้วสไตล์แอมป์ตระกูล Mark/Rectifier พ่วง Tri-Chorus และ Ducking Delay หางยาวแต่ไม่กวนหัวโน้ต",
        "parallel": {"enabled": False, "blend": 0.25},
        "morph_a": {
            "amp_gain": 0.66, "amp_master": 0.76,
            "screamer_drive": 0.15, "screamer_level": 0.82,
            "delay_mix": 0.0, "reverb_mix": 0.14,
            "screamer_enabled": 1.0, "delay_enabled": 0.0,
        },
        "morph_b": {
            "amp_gain": 0.86, "amp_master": 0.88,
            "screamer_drive": 0.32, "screamer_level": 0.90,
            "delay_mix": 0.38, "reverb_mix": 0.32,
            "screamer_enabled": 1.0, "delay_enabled": 1.0,
        },
        "settings": {
            "gate": {"enabled": True, "threshold": -50.0, "release_ms": 35.0, "hold_ms": 30.0, "range_db": -70.0},
            "pitch": {"enabled": False, "semitones": 0.0, "glide": 0.0, "cents": 0.0, "mix": 1.0},
            "screamer": {"enabled": True, "drive": 0.22, "tone": 0.68, "level": 0.85},
            "amp": {"enabled": True, "gain": 0.78, "bass": 0.45, "mid": 0.58, "treble": 0.68, "presence": 0.65, "master": 0.80, "model": "5150", "bright": True},
            "eq": {"enabled": True, "model_id": 2, "bands": [4.5, 1.5, -3.5, 2.5, 4.0, 0.0]},
            "cab": {"enabled": True, "ir_name": "Mesa Rectifier 4x12 Slant", "lowcut": 80.0, "highcut": 13800.0, "mix": 1.0, "level": 1.08, "tube": "6L6", "mic": "SM57", "center": 42.0, "distance": 14.0},
            "mod": {"enabled": True, "model_id": 13, "rate": 0.30, "mix": 0.24, "tone": 0.60, "depth": 0.42},
            "delay": {"enabled": True, "time": 0.357, "feedback": 0.40, "mix": 0.34, "ducking": True, "duck_depth": 0.68},
            "reverb": {"enabled": True, "decay": 0.62, "mix": 0.26, "tone": 0.60, "type": "hall", "ducking": True, "duck_depth": 0.55},
        },
    },
    {
        "id": "gojira_modern_djent_chug",
        "title": "Gojira / Modern Djent · Razor-Tight 5150 Chug & Pitch Shift",
        "artist": "Joe Duplantier (Gojira) / Modern Metal",
        "brand_dna": "Neural DSP Archetype: Gojira + MOOER HM EQ",
        "keywords": ["gojira", "djent", "metal", "chug", "5150", "drop", "heavy", "เมทัล", "โหด", "ตึ้บ", "อุดสาย"],
        "bpm": 145,
        "voicing": "highgain",
        "summary": "เกตตัดฉับไวระดับมิลลิวินาที อัดหน้าแอมป์ 5150 ด้วย Tube Screamer Drive ต่ำ Level สูง ผ่านตู้ V30 + หลอด KT88 หัวโน้ตคมกริบ",
        "parallel": {"enabled": False, "blend": 0.20},
        "morph_a": {
            "amp_gain": 0.72, "amp_master": 0.74,
            "screamer_drive": 0.10, "screamer_level": 0.88,
            "delay_mix": 0.0, "reverb_mix": 0.08,
            "screamer_enabled": 1.0, "delay_enabled": 0.0,
        },
        "morph_b": {
            "amp_gain": 0.90, "amp_master": 0.84,
            "screamer_drive": 0.28, "screamer_level": 0.94,
            "delay_mix": 0.28, "reverb_mix": 0.22,
            "screamer_enabled": 1.0, "delay_enabled": 1.0,
        },
        "settings": {
            "gate": {"enabled": True, "threshold": -44.0, "release_ms": 22.0, "hold_ms": 18.0, "range_db": -80.0},
            "pitch": {"enabled": False, "semitones": -2.0, "glide": 0.0, "cents": 0.0, "mix": 1.0},
            "screamer": {"enabled": True, "drive": 0.12, "tone": 0.74, "level": 0.90},
            "amp": {"enabled": True, "gain": 0.76, "bass": 0.52, "mid": 0.44, "treble": 0.70, "presence": 0.72, "master": 0.75, "model": "5150", "bright": True},
            "eq": {"enabled": True, "model_id": 5, "bands": [95.0, 2.5, -2.0, 3.8, 2.5, 12000.0]},
            "cab": {"enabled": True, "ir_name": "Mesa Rectifier 4x12 Slant", "lowcut": 90.0, "highcut": 12500.0, "mix": 1.0, "level": 1.12, "tube": "KT88", "mic": "MD421", "center": 32.0, "distance": 10.0},
            "mod": {"enabled": False, "model_id": 4, "rate": 0.25, "mix": 0.20, "tone": 0.50, "depth": 0.35},
            "delay": {"enabled": False, "time": 0.31, "feedback": 0.30, "mix": 0.20, "ducking": True, "duck_depth": 0.65},
            "reverb": {"enabled": True, "decay": 0.28, "mix": 0.10, "tone": 0.52, "type": "room", "ducking": True, "duck_depth": 0.50},
        },
    },
    {
        "id": "john_mayer_dumble_blues",
        "title": "John Mayer · 'Slow Dancing' Dumble & Two-Rock Edge of Breakup",
        "artist": "John Mayer / SRV",
        "brand_dna": "Kemper Boutique Profile + MOOER 808 Overdrive",
        "keywords": ["mayer", "john mayer", "srv", "blues", "dumble", "strat", "slow dancing", "บลูส์", "อุ่น", "แตกปลาย"],
        "bpm": 98,
        "voicing": "vintage",
        "summary": "โทน Edge-of-Breakup ที่ตอบสนองน้ำหนักมือ เมื่อดีดเบาจะใสอุ่น พอดีดแรงเสียงจะแตกหวานแบบแอมป์หลอด 6V6/6L6 คู่กับ Spring Reverb",
        "parallel": {"enabled": True, "blend": 0.25},
        "morph_a": {
            "amp_gain": 0.32, "amp_master": 0.78,
            "screamer_drive": 0.25, "screamer_level": 0.72,
            "delay_mix": 0.14, "reverb_mix": 0.26,
            "screamer_enabled": 0.0, "delay_enabled": 0.0,
        },
        "morph_b": {
            "amp_gain": 0.58, "amp_master": 0.85,
            "screamer_drive": 0.58, "screamer_level": 0.82,
            "delay_mix": 0.28, "reverb_mix": 0.34,
            "screamer_enabled": 1.0, "delay_enabled": 1.0,
        },
        "settings": {
            "gate": {"enabled": True, "threshold": -62.0, "release_ms": 70.0, "hold_ms": 50.0, "range_db": -55.0},
            "pitch": {"enabled": False, "semitones": 0.0, "glide": 0.0, "cents": 0.0, "mix": 1.0},
            "screamer": {"enabled": True, "drive": 0.42, "tone": 0.58, "level": 0.76},
            "amp": {"enabled": True, "gain": 0.42, "bass": 0.58, "mid": 0.62, "treble": 0.62, "presence": 0.56, "master": 0.80, "model": "Plexi", "bright": False},
            "eq": {"enabled": True, "model_id": 1, "bands": [1.5, 2.2, 2.8, 1.2, 0.8, 0.0]},
            "cab": {"enabled": True, "ir_name": "Fender Twin 2x12 Jensen", "lowcut": 55.0, "highcut": 15500.0, "mix": 1.0, "level": 1.04, "tube": "6V6", "mic": "R121", "center": 52.0, "distance": 26.0},
            "mod": {"enabled": False, "model_id": 6, "rate": 0.42, "mix": 0.30, "tone": 0.55, "depth": 0.45},
            "delay": {"enabled": True, "time": 0.306, "feedback": 0.24, "mix": 0.18, "ducking": False, "duck_depth": 0.50},
            "reverb": {"enabled": True, "decay": 0.55, "mix": 0.28, "tone": 0.56, "type": "spring", "ducking": False, "duck_depth": 0.45},
        },
    },
    {
        "id": "ambient_shoegaze_cloud",
        "title": "Post-Rock / Shoegaze · Cathedral Cloud & Pitch Shimmer",
        "artist": "Explosions in the Sky / Loathe / Ambient",
        "brand_dna": "Quad Cortex Cloud Engine + MOOER Mod & Pitch",
        "keywords": ["ambient", "shoegaze", "shimmer", "cloud", "post rock", "loathe", "ลอย", "หลอน", "อวกาศ", "กว้าง"],
        "bpm": 90,
        "voicing": "clean",
        "summary": "ม่านเสียงลอยฟุ้งระดับภาพยนตร์ ผสม Pitch +12st Octave บางๆ เข้ากับ Ana-Chorus, Ducking Delay และ Cathedral Reverb หางยาวพิเศษ",
        "parallel": {"enabled": True, "blend": 0.38},
        "morph_a": {
            "amp_gain": 0.28, "amp_master": 0.78,
            "screamer_drive": 0.20, "screamer_level": 0.70,
            "delay_mix": 0.38, "reverb_mix": 0.46,
            "screamer_enabled": 0.0, "delay_enabled": 1.0,
        },
        "morph_b": {
            "amp_gain": 0.72, "amp_master": 0.86,
            "screamer_drive": 0.65, "screamer_level": 0.84,
            "delay_mix": 0.55, "reverb_mix": 0.65,
            "screamer_enabled": 1.0, "delay_enabled": 1.0,
        },
        "settings": {
            "gate": {"enabled": False, "threshold": -65.0, "release_ms": 90.0, "hold_ms": 60.0, "range_db": -50.0},
            "pitch": {"enabled": True, "semitones": 12.0, "glide": 25.0, "cents": 8.0, "mix": 0.28},
            "screamer": {"enabled": False, "drive": 0.35, "tone": 0.60, "level": 0.75},
            "amp": {"enabled": True, "gain": 0.32, "bass": 0.50, "mid": 0.50, "treble": 0.68, "presence": 0.68, "master": 0.78, "model": "Twin", "bright": True},
            "eq": {"enabled": True, "model_id": 5, "bands": [50.0, 2.0, -1.0, 2.0, 4.0, 17500.0]},
            "cab": {"enabled": True, "ir_name": "Marshall 1960A Greenback", "lowcut": 50.0, "highcut": 17500.0, "mix": 1.0, "level": 1.02, "tube": "EL34", "mic": "U87", "center": 58.0, "distance": 35.0},
            "mod": {"enabled": True, "model_id": 12, "rate": 0.26, "mix": 0.46, "tone": 0.65, "depth": 0.68},
            "delay": {"enabled": True, "time": 0.50, "feedback": 0.62, "mix": 0.44, "ducking": True, "duck_depth": 0.55},
            "reverb": {"enabled": True, "decay": 0.88, "mix": 0.52, "tone": 0.72, "type": "cathedral", "ducking": True, "duck_depth": 0.48},
        },
    },
    {
        "id": "ozzy_neural_24bit",
        "title": "Ozzy × Neural 24-Bit · 'Crazy Train / Bark at the Moon' Oversized British Stack (44.1 kHz)",
        "artist": "Ozzy Osbourne (Randy Rhoads / Zakk Wylde) × Neural DSP",
        "brand_dna": "Neural DSP 24-Bit 44.1kHz Archetype + Hot-Rodded JCM800 + Stereo Doubler",
        "keywords": ["ozzy", "โอไซด์", "ออซซี่", "นูลอ", "neural", "zakk", "randy", "crazy train", "bark", "oversized", "24bit", "44.1"],
        "bpm": 138,
        "voicing": "highgain",
        "summary": "โทนสไตล์ โอไซด์ × นูลอ (Ozzy × Neural DSP) 24-bit 44.1 kHz ตอบสนองไดนามิกเป็นธรรมชาติตามน้ำหนักปิ๊ก พร้อม Stereo Micro-Pitch Doubler และตู้ Oversized 4x12",
        "parallel": {"enabled": False, "blend": 0.25},
        "morph_a": {
            "amp_gain": 0.52, "amp_master": 0.76,
            "screamer_drive": 0.16, "screamer_level": 0.78,
            "delay_mix": 0.12, "reverb_mix": 0.18,
            "screamer_enabled": 1.0, "delay_enabled": 0.0,
        },
        "morph_b": {
            "amp_gain": 0.84, "amp_master": 0.86,
            "screamer_drive": 0.42, "screamer_level": 0.90,
            "delay_mix": 0.34, "reverb_mix": 0.30,
            "screamer_enabled": 1.0, "delay_enabled": 1.0,
        },
        "settings": {
            "gate": {"enabled": True, "threshold": -52.0, "release_ms": 35.0, "hold_ms": 28.0, "range_db": -70.0},
            "pitch": {"enabled": False, "semitones": 0.0, "glide": 0.0, "cents": 0.0, "mix": 1.0},
            "screamer": {"enabled": True, "drive": 0.28, "tone": 0.68, "level": 0.84},
            "amp": {"enabled": True, "gain": 0.72, "bass": 0.54, "mid": 0.66, "treble": 0.68, "presence": 0.66, "master": 0.78, "model": "Ozzy_Neural", "bright": True},
            "eq": {"enabled": True, "model_id": 5, "bands": [80.0, 1.5, 2.8, 3.2, 2.0, 14500.0]},
            "cab": {"enabled": True, "ir_name": "Marshall 1960A Greenback", "lowcut": 75.0, "highcut": 14800.0, "mix": 1.0, "level": 1.08, "tube": "EL34", "mic": "SM57", "center": 44.0, "distance": 16.0},
            "mod": {"enabled": True, "model_id": 12, "rate": 0.28, "mix": 0.26, "tone": 0.62, "depth": 0.38},
            "delay": {"enabled": True, "time": 0.326, "feedback": 0.34, "mix": 0.24, "ducking": True, "duck_depth": 0.62},
            "reverb": {"enabled": True, "decay": 0.48, "mix": 0.22, "tone": 0.58, "type": "plate", "ducking": True, "duck_depth": 0.50},
        },
    },
]


def match_artist_tone(query: str) -> Optional[Dict[str, Any]]:
    """
    Matches a query or profile ID to the best profile in ARTIST_TONE_PROFILES by
    keyword overlap. Returns None when nothing matches, so the caller can say so
    instead of loading an unrelated tone.
    """
    q = (query or "").strip().lower()
    if not q:
        return ARTIST_TONE_PROFILES[0]

    # Exact ID match first
    for prof in ARTIST_TONE_PROFILES:
        if prof["id"] == q:
            return prof

    # Score keyword matches
    best_prof = ARTIST_TONE_PROFILES[0]
    best_score = -1
    for prof in ARTIST_TONE_PROFILES:
        score = 0
        if q in prof["title"].lower() or q in prof["artist"].lower():
            score += 10
        for kw in prof["keywords"]:
            if kw in q:
                score += 4
        if score > best_score:
            best_score = score
            best_prof = prof

    return best_prof if best_score > 0 else None
