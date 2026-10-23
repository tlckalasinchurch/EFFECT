"""Prove engine/params.py matches the layers that still declare parameters.

Phase 2B routes the two write paths (server.update_parameter and
apply_mooer_preset) through the registry; the read side and the other four
declarations still carry their own copies. These tests read the real sources --
server.py, engine/audio.py, engine/cortex_scenes.py, engine/morph.py,
engine/mooer_preset.py and web/app.js -- and assert that what they use resolves
to the same attribute the registry claims. They are the guard against the
registry becoming a seventh copy.

A failure here means one of the two sides drifted: either add the parameter to
the registry, or fix the call site. Do not weaken the assertion.
"""

import ast
import re
import unittest
from pathlib import Path

from engine import params
from engine.dsp import GuitarSignalChain
from engine.morph import MorphController
from engine.cortex_scenes import BLOCK_ATTRS, PARAM_ALIASES

ROOT = Path(__file__).parents[1]
SRC = {
    name: (ROOT / name).read_text(encoding="utf-8")
    for name in ("server.py", "engine/audio.py", "web/app.js")
}


# ---------------------------------------------------------------------------
# Extractors: read the *actual* source, never a second copy of the mapping
# ---------------------------------------------------------------------------

def server_handler_body():
    """The AST body of server.update_parameter."""
    tree = ast.parse(SRC["server.py"])
    return next(n for n in ast.walk(tree)
                if isinstance(n, ast.FunctionDef) and n.name == "update_parameter").body


def state_chain_blocks():
    """{block: set(param)} from the 'chain' dict literal in AudioEngine.get_state."""
    tree = ast.parse(SRC["engine/audio.py"])
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        for key, value in zip(node.keys, node.values):
            if isinstance(key, ast.Constant) and key.value == "chain" and isinstance(value, ast.Dict):
                out = {}
                for block_key, block_value in zip(value.keys, value.values):
                    if isinstance(block_key, ast.Constant) and isinstance(block_value, ast.Dict):
                        out[block_key.value] = {
                            k.value for k in block_value.keys
                            if isinstance(k, ast.Constant) and isinstance(k.value, str)
                        }
                if out:
                    return out
    raise AssertionError("could not find the chain state literal in engine/audio.py")


def mooer_settings_pairs():
    """{(block, param)} in the settings dict ``mo_to_workstation_preset`` builds.

    The chain no longer walks this dict key by key -- ``apply_mooer_preset``
    hands each block to ``engine.param_access`` -- so the producer is what has to
    stay resolvable against the registry.
    """
    tree = ast.parse((ROOT / "engine" / "mooer_preset.py").read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "mo_to_workstation_preset")
    literal = next(
        node for node in ast.walk(fn)
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict)
        and any(isinstance(t, ast.Name) and t.id == "settings" for t in node.targets)
    )
    pairs = set()
    for block, value in zip(literal.value.keys, literal.value.values):
        if isinstance(block, ast.Constant) and isinstance(value, ast.Dict):
            for key in value.keys:
                if isinstance(key, ast.Constant):
                    pairs.add((block.value, key.value))
    # Fields added after the literal, e.g. settings["cab"]["ir_name"] = ...
    for node in ast.walk(fn):
        if (isinstance(node, ast.Subscript) and isinstance(node.value, ast.Subscript)
                and ast.unparse(node.value.value) == "settings"
                and isinstance(node.value.slice, ast.Constant)
                and isinstance(node.slice, ast.Constant)):
            pairs.add((node.value.slice.value, node.slice.value))
    return pairs


#: Fields a MOOER export carries that this engine deliberately maps itself: the
#: model ids and display names pick a GE150 model, which the DSP amp does not
#: emulate, so apply_mooer_preset keeps the user's amp model.
MOOER_IGNORED = {
    ("screamer", "model_id"),
    ("amp", "model_id"),
    ("amp", "model_name"),
    ("cab", "model_id"),
    ("cab", "cab_name"),
}


KNOB_RE = re.compile(
    r"K\('[^']*',\s*'[^']*',\s*[^,]+,\s*[^,]+,\s*[^,]+,\s*'[^']*',\s*[^,]+,\s*'([^']+)',\s*'([^']+)'"
)


def ui_knob_pairs():
    """{(section, param)} from KNOB_SETS in web/app.js."""
    return set(KNOB_RE.findall(SRC["web/app.js"]))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class RegistryShapeTests(unittest.TestCase):
    def test_names_are_unique_and_aliases_do_not_shadow(self):
        names = [m.name for m in params.MODULES]
        self.assertEqual(len(names), len(set(names)))
        for alias, target in params.ALIASES.items():
            self.assertNotIn(alias, names, f"alias {alias!r} shadows a module name")
            self.assertIn(target, names)

    def test_graph_order_lists_only_graph_modules(self):
        self.assertEqual(len(params.PROCESS_ORDER), len(set(params.PROCESS_ORDER)))
        for name in params.PROCESS_ORDER:
            self.assertTrue(params.module(name).in_graph, f"{name} is not a graph module")
        # 'nam' occupies the 'amp' slot instead of adding a stage of its own.
        graph = {m.name for m in params.MODULES if m.in_graph}
        self.assertEqual(graph, set(params.PROCESS_ORDER) | {"nam"})

    def test_param_keys_are_unique_within_a_module(self):
        for mod in params.MODULES:
            keys = [p.key for p in mod.params]
            self.assertEqual(len(keys), len(set(keys)), f"duplicate key in {mod.name}")

    def test_defaults_sit_inside_their_declared_range(self):
        for mod in params.MODULES:
            for p in mod.params:
                if p.minimum is None or p.read_only or not isinstance(p.default, (int, float)):
                    continue
                self.assertGreaterEqual(p.default, p.minimum, f"{mod.name}.{p.key}")
                if p.maximum is not None:
                    self.assertLessEqual(p.default, p.maximum, f"{mod.name}.{p.key}")


class RegistryMatchesEngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.chain = GuitarSignalChain(sample_rate=48000)

    def test_defaults_equal_a_fresh_signal_chain(self):
        """The strongest drift guard: the registry must describe the real object."""
        for mod in params.MODULES:
            target = self.chain if mod.attr is None else getattr(self.chain, mod.attr, None)
            if target is None:
                continue  # nam is not installed on a fresh chain
            for p in mod.params:
                if p.read_only or p.owner == "server" or p.attr.startswith("get_"):
                    continue
                with self.subTest(module=mod.name, param=p.key):
                    actual = getattr(target, p.attr)
                    if isinstance(p.default, tuple):
                        self.assertEqual(list(actual), list(p.default))
                    else:
                        self.assertEqual(actual, p.default)

    def test_setters_exist_and_are_callable(self):
        for mod in params.MODULES:
            for p in mod.params:
                if not p.setter or mod.attr is None:
                    continue
                target = getattr(self.chain, mod.attr, None)
                if target is None:
                    continue  # nam
                self.assertTrue(hasattr(target, p.setter), f"{mod.name}.{p.key} -> {p.setter}")
                self.assertTrue(callable(getattr(target, p.setter)))

    def test_update_parameter_has_no_hardcoded_chain_writes(self):
        """The handler must delegate; a hardcoded `chain.x.y = val` may not grow back.

        Phase 2B replaced the if/elif tree with one call into engine.param_access,
        so the old assertion -- every branch targets the registry attribute -- is
        now a property of the accessor (tests/test_param_access.py) and of the
        recorded endpoint behaviour (tests/test_registry_wiring.py). What is left
        to guard here is the shape: no per-parameter attribute writes in server.py.
        """
        direct = []
        for node in ast.walk(ast.Module(body=server_handler_body(), type_ignores=[])):
            if isinstance(node, ast.Assign):
                direct += [ast.unparse(t) for t in node.targets if ast.unparse(t).startswith("chain.")]
            elif isinstance(node, ast.Call):
                name = ast.unparse(node.func)
                if name.startswith("chain."):
                    direct.append(name)
        self.assertEqual(direct, [], "update_parameter writes the chain directly again")

    def test_every_settable_parameter_passes_the_handler_guard(self):
        from server import _is_known_parameter

        for mod in params.MODULES:
            if mod.name == "nam":
                continue  # installed per-preset; the handler guards on chain.nam
            for p in mod.params:
                if p.read_only or p.owner == "server":
                    continue
                with self.subTest(module=mod.name, param=p.key):
                    self.assertTrue(_is_known_parameter(mod.name, p.key))
                    for alias in p.aliases:
                        self.assertTrue(_is_known_parameter(mod.name, alias))
        self.assertTrue(_is_known_parameter("drive", "drive"), "section alias")
        self.assertTrue(_is_known_parameter("eq", "band0"), "index-addressed parameter")
        self.assertFalse(_is_known_parameter("gate", "not_a_parameter"))
        self.assertFalse(_is_known_parameter("not_a_block", "gain"))


class RegistryMatchesOtherLayersTests(unittest.TestCase):
    def test_state_shape_matches_registry(self):
        """Bidirectional: get_state emits nothing undeclared, and drops nothing."""
        blocks = state_chain_blocks()
        for block, emitted in blocks.items():
            mod = params.module(block)
            declared = set()
            for p in mod.params:
                declared.add(p.state_key or p.key)
                if p.read_attr:
                    declared.add(p.read_attr)
            for key in emitted:
                with self.subTest(block=block, state_key=key, direction="emitted"):
                    self.assertIn(key, declared, f"{block}.{key} is emitted but not registered")
            for key in declared:
                with self.subTest(block=block, state_key=key, direction="declared"):
                    self.assertIn(key, emitted, f"{block}.{key} is registered but never emitted")
        for block in blocks:
            self.assertIn(block, params.BY_NAME)

    def test_cortex_block_attrs_match_registry(self):
        for name, attr in BLOCK_ATTRS.items():
            with self.subTest(block=name):
                self.assertEqual(params.module(name).attr, attr)

    def test_cortex_param_aliases_match_registry(self):
        for (block, alias), attr in PARAM_ALIASES.items():
            with self.subTest(block=block, alias=alias):
                self.assertEqual(params.module(block).param(alias).attr, attr)

    def test_morph_flat_keys_resolve(self):
        keys = set(MorphController.DEFAULTS["slot_a"]) | set(MorphController.DEFAULTS["slot_b"])
        for flat in keys:
            block, _, param = flat.partition("_")
            with self.subTest(key=flat):
                self.assertTrue(params.module(block).param(param), f"{flat} does not resolve")

    def test_mooer_preset_settings_resolve(self):
        pairs = mooer_settings_pairs()
        self.assertGreater(len(pairs), 10, "extractor found too few mooer parameters")
        self.assertTrue(MOOER_IGNORED <= pairs, "the ignore list has gone stale")
        for block, param in pairs - MOOER_IGNORED:
            with self.subTest(block=block, param=param):
                params.resolve(block, param)  # raises if either side drifted

    def test_ui_knobs_resolve(self):
        pairs = ui_knob_pairs()
        self.assertGreater(len(pairs), 20, "extractor found too few knobs")
        for section, param in pairs:
            with self.subTest(section=section, param=param):
                params.resolve(section, param)


if __name__ == "__main__":
    unittest.main()
