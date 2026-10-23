"""
MOOER GE150 Complete Catalog & Model Specification
Cloned from the reverse-engineered GE150 firmware/application resource specification.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

# ---------------------------------------------------------------------------
# 1. FX / COMP (8 models)
# ---------------------------------------------------------------------------
FX_MODELS = [
    {"id": 1, "name": "01:CRY WAH", "params": ["Q", "POSITION", "PEAK", "LEVEL"]},
    {"id": 2, "name": "02:535 WAH", "params": ["Q", "POSITION", "PEAK", "LEVEL"]},
    {"id": 3, "name": "03:AUTO WAH", "params": ["RATE", "RANGE", "PEAK", "LEVEL"]},
    {"id": 4, "name": "04:TALK WAH AH", "params": ["RATE", "RANGE", "PEAK", "LEVEL"]},
    {"id": 5, "name": "05:TALK WAH OH", "params": ["RATE", "RANGE", "PEAK", "LEVEL"]},
    {"id": 6, "name": "06:TOUCH WAH", "params": ["ATTACK", "SENS", "PEAK", "LEVEL"]},
    {"id": 7, "name": "07:YELLOW COMP", "params": ["ATTACK", "THRES", "RATIO", "LEVEL"]},
    {"id": 8, "name": "08:BLUE COMP", "params": ["ATTACK", "THRES", "RATIO", "LEVEL"]},
]

# ---------------------------------------------------------------------------
# 2. DS / OD (20 models)
# ---------------------------------------------------------------------------
DS_MODELS = [
    {"id": 1, "name": "01:TUBE DR", "type": "Overdrive", "params": ["VOLUME", "TONE", "GAIN"]},
    {"id": 2, "name": "02:808", "type": "Overdrive", "params": ["VOLUME", "TONE", "GAIN"]},
    {"id": 3, "name": "03:PURE BOOST", "type": "Boost", "params": ["VOLUME", "TONE", "GAIN"]},
    {"id": 4, "name": "04:FLEX BOOST", "type": "Boost", "params": ["VOLUME", "TONE", "GAIN"]},
    {"id": 5, "name": "05:DDRIVE", "type": "Overdrive", "params": ["VOLUME", "TONE", "GAIN"]},
    {"id": 6, "name": "06:BLACK RAT", "type": "Distortion", "params": ["VOLUME", "TONE", "GAIN"]},
    {"id": 7, "name": "07:GREY FAZE", "type": "Fuzz", "params": ["VOLUME", "TONE", "GAIN"]},
    {"id": 8, "name": "08:MUFFY", "type": "Fuzz", "params": ["VOLUME", "TONE", "GAIN"]},
    {"id": 9, "name": "09:MTL ZONE", "type": "High Gain", "params": ["VOLUME", "TONE", "GAIN"]},
    {"id": 10, "name": "10:MTL MASTER", "type": "High Gain", "params": ["VOLUME", "TONE", "GAIN"]},
    {"id": 11, "name": "11:OBSESSIVE DIST", "type": "Distortion", "params": ["VOLUME", "TONE", "GAIN"]},
    {"id": 12, "name": "12:JIMMY OD", "type": "Overdrive", "params": ["VOLUME", "TONE", "GAIN"]},
    {"id": 13, "name": "13:FULL DRV", "type": "Overdrive", "params": ["VOLUME", "TONE", "GAIN"]},
    {"id": 14, "name": "14:SHRED", "type": "High Gain", "params": ["VOLUME", "TONE", "GAIN"]},
    {"id": 15, "name": "15:BEEBEE PRE", "type": "Overdrive", "params": ["VOLUME", "TONE", "GAIN"]},
    {"id": 16, "name": "16:BEEBEE +", "type": "Overdrive", "params": ["VOLUME", "TONE", "GAIN"]},
    {"id": 17, "name": "17:RIET", "type": "Distortion", "params": ["VOLUME", "TONE", "GAIN"]},
    {"id": 18, "name": "18:TIGHT DS", "type": "Distortion", "params": ["VOLUME", "TONE", "GAIN"]},
    {"id": 19, "name": "19:FULL DS", "type": "Distortion", "params": ["VOLUME", "TONE", "GAIN"]},
    {"id": 20, "name": "20:GOLD CLON", "type": "Overdrive", "params": ["VOLUME", "TONE", "GAIN"]},
]

# ---------------------------------------------------------------------------
# 3. AMP (55 Factory Models + 10 User Slots)
# Standard controls: GAIN, BASS, MID, TREBLE, PRES, MST (0-100)
# ---------------------------------------------------------------------------
AMP_PARAMS = ["GAIN", "BASS", "MID", "TREBLE", "PRES", "MST"]

AMP_MODELS = [
    {"id": 1, "name": "01:65 US DX", "category": "Fender Clean", "params": AMP_PARAMS},
    {"id": 2, "name": "02:65 US TW", "category": "Fender Twin", "params": AMP_PARAMS},
    {"id": 3, "name": "03:59 US BASS", "category": "Fender Bassman", "params": AMP_PARAMS},
    {"id": 4, "name": "04:US SONIC", "category": "Fender Super Sonic", "params": AMP_PARAMS},
    {"id": 5, "name": "05:US BLUES CL", "category": "Blues Clean", "params": AMP_PARAMS},
    {"id": 6, "name": "06:US BLUES OD", "category": "Blues Overdrive", "params": AMP_PARAMS},
    {"id": 7, "name": "07:J800", "category": "Marshall JCM800", "params": AMP_PARAMS},
    {"id": 8, "name": "08:J900", "category": "Marshall JCM900", "params": AMP_PARAMS},
    {"id": 9, "name": "09:PLX100", "category": "Marshall Plexi 100W", "params": AMP_PARAMS},
    {"id": 10, "name": "10:E650 CL", "category": "ENGL Ritchie Blackmore Clean", "params": AMP_PARAMS},
    {"id": 11, "name": "11:E650 DS", "category": "ENGL Ritchie Blackmore Lead", "params": AMP_PARAMS},
    {"id": 12, "name": "12:POWER BELL CL", "category": "ENGL Powerball Clean", "params": AMP_PARAMS},
    {"id": 13, "name": "13:POWER BELL DS", "category": "ENGL Powerball Lead", "params": AMP_PARAMS},
    {"id": 14, "name": "14:BLACKNIGHT CL", "category": "ENGL Fireball Clean", "params": AMP_PARAMS},
    {"id": 15, "name": "15:BLACKNIGHT DS", "category": "ENGL Fireball Lead", "params": AMP_PARAMS},
    {"id": 16, "name": "16:MARKIII CL", "category": "Mesa Boogie Mark III Clean", "params": AMP_PARAMS},
    {"id": 17, "name": "17:MARKIII DS", "category": "Mesa Boogie Mark III Lead", "params": AMP_PARAMS},
    {"id": 18, "name": "18:MARKV CL", "category": "Mesa Boogie Mark V Clean", "params": AMP_PARAMS},
    {"id": 19, "name": "19:MARKV DS", "category": "Mesa Boogie Mark V Lead", "params": AMP_PARAMS},
    {"id": 20, "name": "20:TRI REC CL", "category": "Mesa Boogie Triple Rectifier Clean", "params": AMP_PARAMS},
    {"id": 21, "name": "21:TRI REC DS", "category": "Mesa Boogie Triple Rectifier Lead", "params": AMP_PARAMS},
    {"id": 22, "name": "22:ROCK VRB CL", "category": "Orange Rockerverb Clean", "params": AMP_PARAMS},
    {"id": 23, "name": "23:ROCK VRB DS", "category": "Orange Rockerverb Lead", "params": AMP_PARAMS},
    {"id": 24, "name": "24:CITRUS 30", "category": "Orange AD30", "params": AMP_PARAMS},
    {"id": 25, "name": "25:CITRUS 50", "category": "Orange OR50", "params": AMP_PARAMS},
    {"id": 26, "name": "26:SLOW 100 CR", "category": "Soldano SLO100 Crunch", "params": AMP_PARAMS},
    {"id": 27, "name": "27:SLOW 100 DS", "category": "Soldano SLO100 Lead", "params": AMP_PARAMS},
    {"id": 28, "name": "28:DR.ZEE 18 JR", "category": "Dr. Z Maz 18 Jr", "params": AMP_PARAMS},
    {"id": 29, "name": "29:DR.ZEE RECK", "category": "Dr. Z Wreck", "params": AMP_PARAMS},
    {"id": 30, "name": "30:JET 100H CL", "category": "Jet City JCA100H Clean", "params": AMP_PARAMS},
    {"id": 31, "name": "31:JET 100H OD", "category": "Jet City JCA100H Overdrive", "params": AMP_PARAMS},
    {"id": 32, "name": "32:JAZZ 120", "category": "Roland JC-120 Jazz Chorus", "params": AMP_PARAMS},
    {"id": 33, "name": "33:UK30 CL", "category": "Vox AC30 Top Boost Clean", "params": AMP_PARAMS},
    {"id": 34, "name": "34:UK30 OD", "category": "Vox AC30 Top Boost Overdrive", "params": AMP_PARAMS},
    {"id": 35, "name": "35:HWT 103", "category": "Hiwatt Custom 100 DR103", "params": AMP_PARAMS},
    {"id": 36, "name": "36:PV 5050 CL", "category": "Peavey 5150 Rhythm / Clean", "params": AMP_PARAMS},
    {"id": 37, "name": "37:PV 5050 DS", "category": "Peavey 5150 Lead", "params": AMP_PARAMS},
    {"id": 38, "name": "38:REGAL TONE CL", "category": "Dumble Overdrive Special Clean", "params": AMP_PARAMS},
    {"id": 39, "name": "39:REGAL TONE OD1", "category": "Dumble Overdrive Special OD1", "params": AMP_PARAMS},
    {"id": 40, "name": "40:REGAL TONE OD2", "category": "Dumble Overdrive Special OD2", "params": AMP_PARAMS},
    {"id": 41, "name": "41:CAROL CL", "category": "Two-Rock Custom Reverb Clean", "params": AMP_PARAMS},
    {"id": 42, "name": "42:CAROL OD", "category": "Two-Rock Custom Reverb Lead", "params": AMP_PARAMS},
    {"id": 43, "name": "43:CARDEFF", "category": "Matchless Chieftain", "params": AMP_PARAMS},
    {"id": 44, "name": "44:EV 5050 CL", "category": "EVH 5150 III Clean", "params": AMP_PARAMS},
    {"id": 45, "name": "45:EV 5050 DS", "category": "EVH 5150 III Lead", "params": AMP_PARAMS},
    {"id": 46, "name": "46:HT CLUB CL", "category": "Blackstar HT Club Clean", "params": AMP_PARAMS},
    {"id": 47, "name": "47:HT CLUB DS", "category": "Blackstar HT Club Overdrive", "params": AMP_PARAMS},
    {"id": 48, "name": "48:HUGEN CL", "category": "Diezel VH4 Clean", "params": AMP_PARAMS},
    {"id": 49, "name": "49:HUGEN OD", "category": "Diezel VH4 Crunch", "params": AMP_PARAMS},
    {"id": 50, "name": "50:HUGEN DS", "category": "Diezel VH4 Lead", "params": AMP_PARAMS},
    {"id": 51, "name": "51:KOCHE OD", "category": "Koch Powertone OD", "params": AMP_PARAMS},
    {"id": 52, "name": "52:KOCHE DS", "category": "Koch Powertone Ultra Gain", "params": AMP_PARAMS},
    {"id": 53, "name": "53:ACOUSTIC 1", "category": "Acoustic Simulator Dred", "params": AMP_PARAMS},
    {"id": 54, "name": "54:ACOUSTIC 2", "category": "Acoustic Simulator Jumbo", "params": AMP_PARAMS},
    {"id": 55, "name": "55:ACOUSTIC 3", "category": "Acoustic Simulator Piezo", "params": AMP_PARAMS},
]
# User Amp Slots (56-65) for custom Tone Capture / .amp files
for u in range(56, 66):
    AMP_MODELS.append({
        "id": u,
        "name": f"{u:02d}:USER AMP {u-55}",
        "category": "User Non-Linear Capture (*.amp)",
        "params": AMP_PARAMS,
        "user_slot": True,
    })

# ---------------------------------------------------------------------------
# 4. CAB (26 Factory Cabs + 10 User IR Slots)
# Parameters: TUBE, MIC, CENTER, DISTANCE
# ---------------------------------------------------------------------------
CAB_TUBES = ["OFF", "EL34", "EL84", "6L6", "6V6"]
CAB_MICS = ["SM57", "U47", "U87", "NT1", "MD421", "MD441", "MXL2001", "MXL2003", "C3000", "C4000B"]

CAB_MODELS = [
    {"id": 1, "name": "01:US DLX 112", "type": "1x12", "desc": "Fender Deluxe Reverb"},
    {"id": 2, "name": "02:US TWN 212", "type": "2x12", "desc": "Fender Twin Reverb"},
    {"id": 3, "name": "03:US BASS 410", "type": "4x10", "desc": "Fender Bassman"},
    {"id": 4, "name": "04:SONIC 112", "type": "1x12", "desc": "Fender Super Sonic"},
    {"id": 5, "name": "05:BLUES 112", "type": "1x12", "desc": "Fender Blues Deluxe"},
    {"id": 6, "name": "06:1960 412", "type": "4x12", "desc": "Marshall 1960A Celestion G12T-75"},
    {"id": 7, "name": "07:EAGLE P412", "type": "4x12", "desc": "ENGL Pro 4x12 Vintage 30"},
    {"id": 8, "name": "08:EAGLE S412", "type": "4x12", "desc": "ENGL Standard 4x12"},
    {"id": 9, "name": "09:MARK 112", "type": "1x12", "desc": "Mesa Boogie Mark C90"},
    {"id": 10, "name": "10:REC 412", "type": "4x12", "desc": "Mesa Boogie Rectifier 4x12 Slant"},
    {"id": 11, "name": "11:CITRUS 412", "type": "4x12", "desc": "Orange PPC412 Vintage 30"},
    {"id": 12, "name": "12:CITRUS 212", "type": "2x12", "desc": "Orange PPC212"},
    {"id": 13, "name": "13:SLOW 412", "type": "4x12", "desc": "Soldano SLO 4x12 Eminence"},
    {"id": 14, "name": "14:DR.ZEE 112", "type": "1x12", "desc": "Dr. Z 1x12 Open Back"},
    {"id": 15, "name": "15:DR.ZEE 212", "type": "2x12", "desc": "Dr. Z 2x12 Best of Both"},
    {"id": 16, "name": "16:JAZZ 212", "type": "2x12", "desc": "Roland JC-120 Aluminum Cone"},
    {"id": 17, "name": "17:UK 212", "type": "2x12", "desc": "Vox AC30 Celestion Alnico Blue"},
    {"id": 18, "name": "18:HWT 412", "type": "4x12", "desc": "Hiwatt SE4123 Fane"},
    {"id": 19, "name": "19:PV 5050 412", "type": "4x12", "desc": "Peavey 5150 Sheffield 1200"},
    {"id": 20, "name": "20:REGAL TONE 110", "type": "1x10", "desc": "Dumble Open Back 1x10"},
    {"id": 21, "name": "21:TWO STONES 212", "type": "2x12", "desc": "Two-Rock 2x12 Signature"},
    {"id": 22, "name": "22:CARDEFF 112", "type": "1x12", "desc": "Matchless 1x12 Custom"},
    {"id": 23, "name": "23:EV 5050 412", "type": "4x12", "desc": "EVH 5150 III Celestion G12EVH"},
    {"id": 24, "name": "24:HT 412", "type": "4x12", "desc": "Blackstar HTV-412 Celestion"},
    {"id": 25, "name": "25:GAS STATION 412", "type": "4x12", "desc": "Diezel 4x12 Rear Loaded"},
    {"id": 26, "name": "26:ACOUSTIC112", "type": "1x12", "desc": "Flat Acoustic Full-Range"},
]
# User IR Slots (27-36)
for u in range(27, 37):
    CAB_MODELS.append({
        "id": u,
        "name": f"{u:02d}:USER IR {u-26}",
        "type": "Custom",
        "desc": "User Cabinet Impulse Response (*.wav)",
        "user_slot": True,
    })

# ---------------------------------------------------------------------------
# 5. NS GATE (3 models)
# ---------------------------------------------------------------------------
NS_MODELS = [
    {"id": 1, "name": "01:NOISE KILLER", "params": ["THRES"]},
    {"id": 2, "name": "02:INTEL REDUCER", "params": ["SENS"]},
    {"id": 3, "name": "03:NOISE GATE", "params": ["ATTACK", "RELEASE", "THRES"]},
]

# ---------------------------------------------------------------------------
# 6. EQ (4 models)
# ---------------------------------------------------------------------------
EQ_MODELS = [
    {"id": 1, "name": "01:MOOER G", "type": "graphic_5", "bands": ["100Hz", "250Hz", "630Hz", "1.6KHz", "4KHz"], "range_db": [-16, 16]},
    {"id": 2, "name": "02:MOOER HM", "type": "graphic_5", "bands": ["80Hz", "240Hz", "750Hz", "2.2KHz", "6.6KHz"], "range_db": [-16, 16]},
    {"id": 3, "name": "03:MOOER G-6", "type": "graphic_6", "bands": ["100Hz", "200Hz", "400Hz", "800Hz", "1.6KHz", "3.2KHz"], "range_db": [-16, 16]},
    {"id": 4, "name": "04:CUSTOM EQ", "type": "parametric_3", "bands": ["GAIN1", "FREQ1", "GAIN2", "FREQ2", "GAIN3", "FREQ3"], "freq_range": [0, 18000], "gain_range": [-16, 16]},
]

# ---------------------------------------------------------------------------
# 7. MOD (19 models)
# ---------------------------------------------------------------------------
MOD_MODELS = [
    {"id": 1, "name": "01:PHASER", "params": ["RATE", "LEVEL", "DEPTH"]},
    {"id": 2, "name": "02:STEP PHASER", "params": ["RATE", "LEVEL", "DEPTH"]},
    {"id": 3, "name": "03:FAT PHASER", "params": ["RATE", "LEVEL", "DEPTH"]},
    {"id": 4, "name": "04:FLANGER", "params": ["RATE", "MIX", "FEEDBACK"]},
    {"id": 5, "name": "05:JET-FLANGER", "params": ["RATE", "MIX", "FEEDBACK"]},
    {"id": 6, "name": "06:TREMOLO", "params": ["RATE", "MIX", "TONE"]},
    {"id": 7, "name": "07:STUTTER", "params": ["RATE", "MIX", "TONE"]},
    {"id": 8, "name": "08:VIBRATO", "params": ["RATE", "DEPTH", "TONE"]},
    {"id": 9, "name": "09:PITCH SHIFT", "params": ["PITCH", "MIX", "TONE"], "pitch_range": [-12.0, 12.0]},
    {"id": 10, "name": "10:DETUNE", "params": ["PITCH", "MIX", "TONE"], "pitch_range": [-20.0, 20.0]},
    {"id": 11, "name": "11:ROTARY", "params": ["RATE", "MIX", "TONE"]},
    {"id": 12, "name": "12:ANA-CHORUS", "params": ["RATE", "MIX", "TONE", "DEPTH"]},
    {"id": 13, "name": "13:TRI-CHORUS", "params": ["RATE", "MIX", "TONE", "DEPTH"]},
    {"id": 14, "name": "14:RING MOD", "params": ["RATE", "MIX", "TONE"]},
    {"id": 15, "name": "15:Q-FILTER", "params": ["RATE", "MIX", "Q"]},
    {"id": 16, "name": "16:HIGH PASS", "params": ["RATE", "MIX", "RANGE"]},
    {"id": 17, "name": "17:LOW PASS", "params": ["RATE", "MIX", "RANGE"]},
    {"id": 18, "name": "18:SLOW GEAR", "params": ["RISE", "LEVEL"]},
    {"id": 19, "name": "19:LOFI", "params": ["SAMPLE", "MIX", "BIT"]},
]

# ---------------------------------------------------------------------------
# 8. DELAY (9 models)
# ---------------------------------------------------------------------------
DELAY_SUBDIVISIONS = ["OFF", "1/4", "1/4T", "1/4D", "1/8", "1/8T", "1/8D", "1/16", "1/16T", "1/16D"]

DELAY_MODELS = [
    {"id": 1, "name": "01:DIGITAL", "params": ["LEVEL", "FEEDBACK", "TIME", "SUB-D"], "time_range_ms": [40, 2500]},
    {"id": 2, "name": "02:ANALOG", "params": ["LEVEL", "FEEDBACK", "TIME", "SUB-D"], "time_range_ms": [40, 2500]},
    {"id": 3, "name": "03:REAL", "params": ["LEVEL", "FEEDBACK", "TIME", "SUB-D"], "time_range_ms": [40, 2500]},
    {"id": 4, "name": "04:TAPE", "params": ["LEVEL", "FEEDBACK", "TIME", "SUB-D"], "time_range_ms": [40, 2500]},
    {"id": 5, "name": "05:MOD", "params": ["LEVEL", "FEEDBACK", "TIME", "SUB-D"], "time_range_ms": [40, 2500]},
    {"id": 6, "name": "06:REVERSE", "params": ["LEVEL", "FEEDBACK", "TIME", "SUB-D"], "time_range_ms": [40, 2500]},
    {"id": 7, "name": "07:PINGPONG", "params": ["LEVEL", "FEEDBACK", "TIME", "SUB-D"], "time_range_ms": [40, 2500]},
    {"id": 8, "name": "08:DYNAMIC", "params": ["LEVEL", "FEEDBACK", "TIME", "SUB-D", "THRES"], "time_range_ms": [40, 2500]},
    {"id": 9, "name": "09:DUAL DELAY", "params": ["LEVEL", "FEEDBACK", "TIME A", "SUB A", "TIME B", "SUB B"], "time_range_ms": [40, 2500]},
]

# ---------------------------------------------------------------------------
# 9. REVERB (7 models)
# ---------------------------------------------------------------------------
REVERB_MODELS = [
    {"id": 1, "name": "01:ROOM", "params": ["PRE DELAY", "LEVEL", "DECAY", "TONE"], "predelay_range_ms": [0, 500]},
    {"id": 2, "name": "02:HALL", "params": ["PRE DELAY", "LEVEL", "DECAY", "TONE"], "predelay_range_ms": [0, 500]},
    {"id": 3, "name": "03:CHURCH", "params": ["PRE DELAY", "LEVEL", "DECAY", "TONE"], "predelay_range_ms": [0, 500]},
    {"id": 4, "name": "04:PLATE", "params": ["PRE DELAY", "LEVEL", "DECAY", "TONE"], "predelay_range_ms": [0, 500]},
    {"id": 5, "name": "05:SPRING", "params": ["PRE DELAY", "LEVEL", "DECAY", "TONE"], "predelay_range_ms": [0, 500]},
    {"id": 6, "name": "06:MOD", "params": ["PRE DELAY", "LEVEL", "DECAY", "TONE"], "predelay_range_ms": [0, 500]},
    {"id": 7, "name": "07:CAVE", "params": ["PRE DELAY", "LEVEL", "DECAY", "TONE"], "predelay_range_ms": [0, 500]},
]

# Complete dictionary of all 9 modules for fast lookup
MODULE_CATALOG = {
    "FX": FX_MODELS,
    "DS": DS_MODELS,
    "AMP": AMP_MODELS,
    "CAB": CAB_MODELS,
    "NS": NS_MODELS,
    "EQ": EQ_MODELS,
    "MOD": MOD_MODELS,
    "DLY": DELAY_MODELS,
    "REV": REVERB_MODELS,
}
