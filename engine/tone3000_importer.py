import os
import glob
import re
import json

TONE3000_FACTORY_DIR = r"C:\ProgramData\TONE3000\Presets\Factory"

def list_tone3000_presets():
    if not os.path.exists(TONE3000_FACTORY_DIR):
        return []
    
    presets = []
    for filepath in glob.glob(os.path.join(TONE3000_FACTORY_DIR, "*.t3kpreset")):
        try:
            fname = os.path.basename(filepath)
            with open(filepath, "rb") as f:
                data = f.read()
            
            # Extract readable metadata from the preset binary/json chunk
            name_m = re.search(rb'\"name\":\s*\"([^\"]+)\"', data)
            preset_name = name_m.group(1).decode('utf-8', 'ignore') if name_m else fname.replace(".t3kpreset", "")
            
            # Determine amp/gear style
            clean_name = fname.replace(".t3kpreset", "")
            nam_count = data.count(b".nam")
            
            # Map known tones to amp models and styles
            style_map = {
                "Ampeg Bass Drive": ("Bass / Clean", "SansAmp Bass Driver DI", "Ampeg 8x10 SVT", 0.35),
                "Bogner Fullstack": ("High Gain", "Bogner Ecstasy 101B", "Bogner 4x12 V30", 0.75),
                "Dumble Spread": ("Crunch / Boutique", "Dumble Overdrive Special", "Dumble 2x12 Open", 0.50),
                "Marshall Bluesbreaker": ("Vintage Crunch", "1966 JTM45 Bluesbreaker", "Marshall 1960A Greenback", 0.55),
                "Matchless Crunch": ("Class-A Crunch", "Matchless Brave 30", "Matchless 2x12 Custom", 0.50),
                "Mesa Pitch Shift": ("High Gain Lead", "Mesa Boogie Dual Rectifier", "Mesa Rectifier 4x12 Slant", 0.80),
                "Stereo Crunch Verb": ("Ambient Crunch", "JHS Morning Glory + Amp", "Celestion V30 4x12", 0.45),
                "Stereo Fuzz": ("Fuzz / Psychedelic", "Magnatone M10A 1966 + Fuzz", "Vintage 1x12 Oxford", 0.85)
            }
            
            category, amp_model, cab_model, gain_val = style_map.get(
                clean_name, 
                ("Modern Amp", preset_name, "Celestion V30 4x12", 0.6)
            )

            presets.append({
                "id": f"t3k_{clean_name.lower().replace(' ', '_')}",
                "name": preset_name,
                "file_name": fname,
                "file_path": filepath,
                "author": "TONE3000 Factory",
                "category": category,
                "amp_model": amp_model,
                "cab_model": cab_model,
                "gain": gain_val,
                "has_nam": nam_count > 0,
                "file_size_kb": len(data) // 1024
            })
        except Exception:
            pass
            
    return presets
