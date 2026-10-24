import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
import numpy as np

PASS = "[OK] "
FAIL = "[!!] "
results = []

def check(label, fn):
    try:
        msg = fn()
        results.append((PASS, label, msg or ""))
    except Exception as e:
        results.append((FAIL, label, str(e)))

# ── 1. Imports ────────────────────────────────────────────────────────────────
def test_imports():
    from engine.audio import AudioEngine
    from engine.dsp import GuitarSignalChain
    from engine.presets import get_all_presets
    from engine.kemper_importer import list_installed_kemper_packs
    return "All engine modules imported"

check("Import: engine modules", test_imports)

def test_server_import():
    from server import app
    return "FastAPI app: " + app.title

check("Import: server (FastAPI)", test_server_import)

# ── 2. DSP Signal Chain ───────────────────────────────────────────────────────
def test_dsp_chain():
    from engine.dsp import GuitarSignalChain
    chain = GuitarSignalChain(48000)
    block = np.random.randn(256).astype(np.float32) * 0.1
    out = chain.process(block)
    assert out.shape == (256,), "Wrong shape: " + str(out.shape)
    assert not np.any(np.isnan(out)), "NaN in output"
    assert np.max(np.abs(out)) <= 1.0, "Brickwall limiter failed"
    return "shape=(256,) range=[" + str(round(float(out.min()),3)) + "," + str(round(float(out.max()),3)) + "]"

check("DSP: signal chain (256-sample block)", test_dsp_chain)

def test_dsp_silence():
    from engine.dsp import GuitarSignalChain
    chain = GuitarSignalChain(48000)
    out = chain.process(np.zeros(256, dtype=np.float32))
    assert not np.any(np.isnan(out)), "NaN on silence"
    return "Silence -> no NaN, max=" + str(round(float(np.max(np.abs(out))), 6))

check("DSP: silence input (no NaN)", test_dsp_silence)

def test_dsp_all_effects():
    from engine.dsp import GuitarSignalChain
    chain = GuitarSignalChain(48000)
    chain.screamer.enabled = True
    chain.delay.enabled = True
    chain.reverb.enabled = True
    block = np.random.randn(512).astype(np.float32) * 0.3
    out = chain.process(block)
    assert not np.any(np.isnan(out)), "NaN with all effects"
    return "Gate+OD+Amp+Cab+Delay+Reverb all enabled"

check("DSP: all effects enabled (no NaN)", test_dsp_all_effects)

def test_lowcut_zi():
    from scipy import signal as sg
    b, a = sg.butter(2, 80.0 / (48000 * 0.5), btype="high")
    zi = np.zeros(max(len(a), len(b)) - 1)
    audio = np.random.randn(256).astype(np.float32)
    out, zi_new = sg.lfilter(b, a, audio, zi=zi)
    assert zi_new.shape == (2,), "zi shape wrong: " + str(zi_new.shape)
    return "butter(2) zi shape=(2,) correct"

check("DSP: lowcut filter zi shape", test_lowcut_zi)

# ── 3. Audio Engine ───────────────────────────────────────────────────────────
def test_audio_detect():
    import sounddevice as sd
    from engine.audio import AudioEngine
    ae = AudioEngine()
    ux1_list = []
    for i, d in enumerate(sd.query_devices()):
        if "UX1" in d["name"] or "Line 6" in d["name"]:
            ux1_list.append(str(i) + ":" + d["name"][:20])
    return "in=" + str(ae.input_device) + " out=" + str(ae.output_device) + " | UX1:" + str(ux1_list)

check("Audio: UX1 auto-detection", test_audio_detect)

def test_audio_callback():
    from engine.audio import AudioEngine
    ae = AudioEngine()
    indata = np.random.randn(256, 1).astype(np.float32) * 0.1
    outdata = np.zeros((256, 2), dtype=np.float32)
    class FakeTime: pass
    ae._audio_callback(indata, outdata, 256, FakeTime(), None)
    assert not np.any(np.isnan(outdata)), "NaN in outdata"
    assert not np.all(outdata == 0), "outdata still zero"
    return "Stereo fill OK, max=" + str(round(float(np.max(np.abs(outdata))), 4))

check("Audio: callback stereo fill", test_audio_callback)

def test_tuner():
    from engine.audio import AudioEngine, freq_to_note
    ae = AudioEngine()
    sr = 48000
    t = np.arange(2048) / float(sr)
    sine = np.sin(2.0 * np.pi * 110.0 * t).astype(np.float32)
    freq = ae._estimate_pitch(sine)
    note = freq_to_note(freq)
    return "A2 sine -> " + str(round(freq, 1)) + " Hz -> " + note["note"] + str(note["octave"])

check("Audio: tuner pitch detection (A2=110Hz)", test_tuner)

# ── 4. Presets ────────────────────────────────────────────────────────────────
def test_presets():
    from engine.presets import get_all_presets
    presets = get_all_presets()
    assert len(presets) >= 5, "Expected >=5, got " + str(len(presets))
    for p in presets:
        for k in ["id", "name", "category", "author", "settings"]:
            assert k in p, "Missing key " + k
        for s in ["gate", "screamer", "amp", "cab", "delay", "reverb"]:
            assert s in p["settings"], "Missing section " + s
    names = [p["name"] for p in presets]
    return str(len(presets)) + " presets: " + ", ".join(names)

check("Presets: factory presets + structure", test_presets)

# ── 5. Kemper Importer ────────────────────────────────────────────────────────
def test_kemper():
    from engine.kemper_importer import list_installed_kemper_packs
    packs = list_installed_kemper_packs()
    return str(len(packs)) + " Kemper packs found"

check("Kemper: pack discovery", test_kemper)

# ── 5.1 TONE3000 Importer ─────────────────────────────────────────────────────
def test_tone3000():
    from engine.tone3000_importer import list_tone3000_presets
    presets = list_tone3000_presets()
    assert len(presets) == 8, "Expected 8 presets, got " + str(len(presets))
    return str(len(presets)) + " TONE3000 factory neural presets discovered"

check("TONE3000: neural presets discovery", test_tone3000)

# ── 6. Server Routes ──────────────────────────────────────────────────────────
def test_routes():
    from server import app
    routes = [r.path for r in app.routes if hasattr(r, "path") and r.path.startswith("/api")]
    return str(len(routes)) + " API routes: " + ", ".join(routes)

check("Server: API routes registered", test_routes)

# ── 7. pywebview ──────────────────────────────────────────────────────────────
def test_webview():
    import webview
    assert callable(webview.create_window), "create_window missing"
    assert callable(webview.start), "start missing"
    return "pywebview OK (create_window + start available)"

check("UI: pywebview module", test_webview)

# ── Print Report ──────────────────────────────────────────────────────────────
print()
print("=" * 62)
print("  กดจนหลอนTone Workstation -- AUDIT REPORT")
print("=" * 62)
passed = [r for r in results if r[0] == PASS]
failed = [r for r in results if r[0] == FAIL]
for status, label, detail in results:
    print(status + label)
    if detail:
        print("       -> " + detail)

print()
summary = "  Result: " + str(len(passed)) + "/" + str(len(results)) + " passed"
if failed:
    print(summary + " | " + str(len(failed)) + " FAILED:")
    for _, label, detail in failed:
        print("    * " + label)
        if detail:
            print("      " + detail)
    sys.exit(1)
else:
    print(summary + " -- ALL CLEAR!")
    print("  App is READY TO LAUNCH.")
    sys.exit(0)
print("=" * 62)
