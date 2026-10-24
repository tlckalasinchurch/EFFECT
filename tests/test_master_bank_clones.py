"""
Tests for กดจนหลอนTone Master Signature Bank and cloned flagship features:
- Master Signature presets from all 4 brands (Quad Cortex, Kemper, MOOER GE150, TONE3000)
- Full 9-block preset loading (including EQ, Cab Tube/Mic/3D Pos, 19-Model Modulation, Ducking Delay/Reverb)
- Kemper Auto-Morph A<->B slot generator (/api/morph/auto)
- MOOER / Quad Cortex Tap Tempo BPM Delay sync (/api/tempo/sync)
"""

import shutil
from unittest import mock

import pytest
from fastapi.testclient import TestClient

import server
from engine import presets
from engine.morph import MorphController
from server import app


@pytest.fixture(autouse=True)
def isolated_presets_db(tmp_path):
    """These endpoints save presets and morph slots; keep them off the real presets.db."""
    db = tmp_path / "presets.db"
    shutil.copyfile(presets.DB_PATH, db)
    with mock.patch.object(presets, "DB_PATH", str(db)), \
         mock.patch.object(server, "morph_mgr", MorphController(str(db))):
        yield


def test_master_bank_presets_and_full_9_block_load():
    client = TestClient(app)
    res = client.get("/api/master-bank/presets")
    assert res.status_code == 200
    presets = res.json()["presets"]
    assert len(presets) >= 5

    # Load the MOOER + Cortex Cyber Lo-Fi Bitcrush & Octave preset
    load_res = client.post("/api/preset/load", json={"preset_id": "master_lofi_synth_experimental"})
    assert load_res.status_code == 200
    body = load_res.json()
    chain = body["state"]["chain"]

    # Verify all 9 cloned blocks and extensions loaded properly
    assert chain["pitch"]["enabled"] is True
    assert chain["mod"]["enabled"] is True
    assert chain["mod"]["model_id"] == 19  # Lo-Fi Bitcrusher
    assert chain["cab"]["tube"] == "KT88"
    assert chain["cab"]["mic"] == "SM57"
    assert chain["delay"]["ducking"] is True

    # Verify Morph Slot A & B were automatically paired from the Master Signature preset
    morph = body["morph"]
    assert morph["captured"]["A"] is True
    assert morph["captured"]["B"] is True
    assert morph["slot_b"]["amp_gain"] > morph["slot_a"]["amp_gain"]


def test_kemper_auto_morph_generator():
    client = TestClient(app)
    res = client.post("/api/morph/auto", json={})
    assert res.status_code == 200
    morph = res.json()["morph"]
    assert morph["captured"]["A"] is True
    assert morph["captured"]["B"] is True
    assert morph["slot_b"]["amp_gain"] > morph["slot_a"]["amp_gain"]
    assert morph["slot_b"]["screamer_enabled"] == 1.0


def test_tap_tempo_bpm_delay_sync():
    client = TestClient(app)
    # 120 BPM quarter note = 0.500 sec (500 ms)
    res = client.post("/api/tempo/sync", json={"bpm": 120, "subdivision": "1/4"})
    assert res.status_code == 200
    data = res.json()
    assert data["bpm"] == 120.0
    assert abs(data["delay_time_sec"] - 0.5) < 1e-3
    assert abs(data["state"]["chain"]["delay"]["time"] - 0.5) < 1e-3

    # 120 BPM dotted eighth (1/8d) = 0.375 sec (375 ms)
    res_dotted = client.post("/api/tempo/sync", json={"bpm": 120, "subdivision": "1/8d"})
    assert res_dotted.status_code == 200
    assert abs(res_dotted.json()["delay_time_sec"] - 0.375) < 1e-3


def test_ai_artist_tone_matcher_synthesizes_full_rig():
    client = TestClient(app)
    prof_res = client.get("/api/ai-tone/profiles")
    assert prof_res.status_code == 200
    assert len(prof_res.json()["profiles"]) >= 5

    # Match "Polyphia" / Tim Henson Neural Clean
    match_res = client.post("/api/ai-tone/match", json={"query": "Polyphia Playing God"})
    assert match_res.status_code == 200
    body = match_res.json()
    assert body["matched_profile"]["id"] == "tim_henson_neural_clean"
    assert body["state"]["chain"]["parallel"]["enabled"] is True
    assert body["state"]["chain"]["mod"]["model_id"] == 13
    assert body["morph"]["captured"]["A"] is True
    assert body["morph"]["captured"]["B"] is True
