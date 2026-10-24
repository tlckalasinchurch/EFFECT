"""Regression and feature verification tests for Pro NAM Desktop:
- Signal chain reordering & custom block orders
- Quick scenes (Clean, Rhythm, Lead)
- Rig A/B snapshot and toggle
- MIDI Learn mapping and dispatch
- FastAPI server endpoints
"""
import numpy as np
import pytest
from starlette.testclient import TestClient

from engine.dsp import GuitarSignalChain
from engine.device_mode import BLOCK_ORDERS
from engine.midi_in import MidiSceneListener, _MIM_DATA
from server import app, engine, _midi_handle_action, apply_quick_scene, store_ab_snapshot, toggle_ab_snapshot


def test_chain_reorder_stages():
    """Verify that GuitarSignalChain supports custom reordering of blocks."""
    chain = GuitarSignalChain()
    default_order = chain.get_stage_order()
    assert "gate" in default_order
    assert "screamer" in default_order
    assert "amp" in default_order
    assert "cab" in default_order
    assert "reverb" in default_order

    # Move screamer (drive) to left
    res = chain.move_block("screamer", "left")
    assert isinstance(res, list)
    new_order = chain.get_stage_order()
    screamer_idx = new_order.index("screamer")
    assert screamer_idx < default_order.index("screamer")

    # Set explicit custom order matching actual stages
    custom = ["eq", "gate", "pitch", "screamer", "amp", "cab", "mod", "delay", "reverb"]
    ok = chain.set_custom_order(custom)
    assert ok is True
    assert chain.get_stage_order() == custom

    # Verify audio passes cleanly through reordered chain
    audio_in = np.random.uniform(-0.1, 0.1, 256).astype(np.float32)
    audio_out = chain.process(audio_in)
    assert audio_out.shape == (256,)
    assert not np.isnan(audio_out).any()
    assert not np.isinf(audio_out).any()


def test_quick_scenes():
    """Verify Quick Scenes (Clean, Rhythm, Lead) apply deterministic parameters."""
    # Apply Lead scene
    apply_quick_scene("lead")
    assert engine.chain.screamer.enabled is True
    assert engine.chain.delay.enabled is True
    assert engine.chain.reverb.enabled is True

    # Apply Clean scene
    apply_quick_scene("clean")
    assert engine.chain.screamer.enabled is False
    assert engine.chain.delay.enabled is False
    assert engine.chain.reverb.enabled is True

    # Apply Rhythm scene
    apply_quick_scene("rhythm")
    assert engine.chain.screamer.enabled is True
    assert engine.chain.delay.enabled is False


def test_ab_rig_comparison():
    """Verify storing Snapshot A, altering live state, and toggling A/B."""
    engine.chain.reverb.enabled = False

    # Store Snapshot A
    store_ab_snapshot()

    # Modify live chain B
    engine.chain.reverb.enabled = True
    engine.chain.screamer.enabled = True

    # Toggle to A (should restore Snapshot A state)
    t1 = toggle_ab_snapshot()
    assert t1 == "A"
    assert engine.chain.reverb.enabled is False

    # Toggle to B (should switch to B slot)
    t2 = toggle_ab_snapshot()
    assert t2 == "B"


def test_midi_learn_and_action():
    """Verify MIDI Learn captures triggers and dispatches actions."""
    executed_actions = []

    def handle_action(action_name, value=None):
        executed_actions.append(action_name)

    listener = MidiSceneListener(on_scene=lambda s: None, on_action=handle_action)
    listener.start_learn("scene_lead")
    assert listener.learn_target == "scene_lead"

    # Simulate incoming CC 80: status 0xB0, data1 80, data2 127
    packed_p1 = 0xB0 | (80 << 8) | (127 << 16)
    listener._on_midi(None, _MIM_DATA, None, packed_p1, None)
    assert listener.learn_target is None
    assert listener.mappings.get("cc_80") == "scene_lead"

    # Trigger incoming CC 80 again (should fire on_action callback)
    listener._on_midi(None, _MIM_DATA, None, packed_p1, None)
    assert "scene_lead" in executed_actions


def test_api_endpoints():
    """Verify FastAPI endpoints for reordering, scenes, A/B, and MIDI."""
    client = TestClient(app)

    # 1. Chain reorder endpoints
    r = client.get("/api/chain/order")
    assert r.status_code == 200
    order_data = r.json()
    assert "order" in order_data

    r = client.post("/api/chain/reorder", json={"block": "eq", "direction": "left"})
    assert r.status_code == 200
    assert r.json()["success"] is True

    # 2. Quick scene endpoint
    r = client.post("/api/scenes/quick", json={"scene": "clean"})
    assert r.status_code == 200
    assert r.json()["active_scene"] == "clean"

    # 3. A/B Rig endpoints
    r = client.post("/api/ab/store")
    assert r.status_code == 200
    assert r.json()["has_a"] is True

    r = client.post("/api/ab/toggle")
    assert r.status_code == 200
    assert r.json()["active"] in ("A", "B")

    r = client.get("/api/ab/state")
    assert r.status_code == 200
    assert "active" in r.json()

    # 4. MIDI endpoints
    r = client.get("/api/midi/status")
    assert r.status_code == 200
    assert "mappings" in r.json()

    r = client.post("/api/midi/learn", json={"action": "scene_clean"})
    assert r.status_code == 200
    assert r.json()["learn_target"] == "scene_clean"

    r = client.post("/api/midi/learn", json={"action": None})
    assert r.status_code == 200
    assert r.json()["learn_target"] is None

    # 5. Devices & ASIO discovery
    r = client.get("/api/devices")
    assert r.status_code == 200
    d = r.json()
    assert "devices" in d
    assert "asio_drivers" in d
    assert isinstance(d["asio_drivers"], list)
