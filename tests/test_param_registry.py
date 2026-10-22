"""Prove engine/params.py matches the six places that still declare parameters.

Phase 2A installs the registry without rewiring anything, so these tests read
the real sources -- server.py, engine/audio.py, engine/cortex_scenes.py,
engine/morph.py, engine/dsp.py and web/app.js -- and assert that every
(section, parameter) pair they use resolves to the same attribute the registry
claims. They are the guard against the registry becoming a seventh copy.

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
    for name in ("server.py", "engine/audio.py", "engine/dsp.py", "web/app.js")
}


# ---------------------------------------------------------------------------
# Extractors: read the *actual* source, never a second copy of the mapping
# ---------------------------------------------------------------------------

def _literal_params(test):
    """Parameters a `p == "x"` / `p in ("x", "y")` guard accepts, else None."""
    if isinstance(test, ast.BoolOp):
        for value in test.values:
            found = _literal_params(value)
            if found:
                return found
        return None
    if not isinstance(test, ast.Compare):
        return None
    left, op, right = test.left, test.ops[0], test.comparators[0]
    if ast.unparse(left) != "p":
        return None
    if isinstance(op, ast.Eq) and isinstance(right, ast.Constant) and isinstance(right.value, str):
        return [right.value]
    if isinstance(op, ast.In) and isinstance(right, ast.Tuple):
        return [e.value for e in right.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)]
    return None


def _action(node):
    """Describe what a statement does: ('assign', dotted target) or ('call', name)."""
    if isinstance(node, ast.Assign):
        return ("assign", [ast.unparse(t) for t in node.targets])
    if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
        return ("call", [ast.unparse(node.value.func)])
    return None


def server_parameter_map():
    """{(section, param): [(kind, target), ...]} from server.update_parameter."""
    tree = ast.parse(SRC["server.py"])
    fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "update_parameter")
    found = {}

    def record(section, param, node):
        action = _action(node)
        if action:
            found.setdefault((section, param), []).append(action)

    def walk(stmts, section):
        for st_node in stmts:
            if isinstance(st_node, ast.If):
                test = ast.unparse(st_node.test)
                if test.startswith("sec =="):
                    walk(st_node.body, ast.literal_eval(st_node.test.comparators[0]))
                else:
                    accepted = _literal_params(st_node.test)
                    if accepted is None:
                        walk(st_node.body, section)
                    else:
                        for param in accepted:
                            for inner in st_node.body:
                                record(section, param, inner)
                                if isinstance(inner, (ast.With, ast.For)):
                                    for deep in inner.body:
                                        record(section, param, deep)
                walk(st_node.orelse, section)
            elif section is not None:
                record(section, None, st_node)

    walk(fn.body, None)
    return {k: v for k, v in found.items() if k[0] is not None}


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
    """{(block, param)} read by GuitarSignalChain.apply_mooer_preset."""
    tree = ast.parse(SRC["engine/dsp.py"])
    cls = next(n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == "GuitarSignalChain")
    fn = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "apply_mooer_preset")
    pairs = set()
    for node in ast.walk(fn):
        # s["block"]["param"]
        if (isinstance(node, ast.Subscript) and isinstance(node.value, ast.Subscript)
                and ast.unparse(node.value.value) == "s"
                and isinstance(node.value.slice, ast.Constant)
                and isinstance(node.slice, ast.Constant)):
            pairs.add((node.value.slice.value, node.slice.value))
        # s["block"].get("param")
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "get" and isinstance(node.func.value, ast.Subscript)
                and isinstance(node.func.value.slice, ast.Constant) and node.args
                and isinstance(node.args[0], ast.Constant)):
            pairs.add((node.func.value.slice.value, node.args[0].value))
    return pairs


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

    def test_server_parameter_handler_targets_the_registry_attribute(self):
        mapping = server_parameter_map()
        self.assertGreater(len(mapping), 40, "extractor found too few parameters")
        for (section, param), actions in mapping.items():
            with self.subTest(section=section, param=param):
                mod = params.module(section)
                if param is None:
                    # server.py's dynamic eq band branch: chain.eq.gains[idx]
                    for kind, targets in actions:
                        for target in targets:
                            if "." not in target:
                                continue  # local helper: idx = int(p[4:])
                            self.assertTrue(
                                target.startswith(f"chain.{mod.attr}.gains")
                                or target == f"chain.{mod.attr}._design_filters",
                                f"unexpected dynamic-eq target {target}",
                            )
                    continue

                p = mod.param(param)
                if p.owner == "server":
                    self.assertEqual([t for _, ts in actions for t in ts], [p.attr])
                    continue

                prefix = f"chain.{mod.attr}." if mod.attr else "chain."
                for kind, targets in actions:
                    if kind == "assign":
                        self.assertEqual(targets, [prefix + p.attr])
                    else:
                        self.assertEqual(targets, [prefix + p.setter])
                        self.assertIsNotNone(p.setter, f"{section}.{param} is set by a method, not an attribute")

    def test_every_registry_param_is_reachable_from_the_server(self):
        mapping = server_parameter_map()
        reachable = {(s, q) for (s, q) in mapping if q}
        has_dynamic_index = any(q is None for (s, q) in mapping)
        for mod in params.MODULES:
            for p in mod.params:
                if p.read_only or mod.name == "nam":
                    continue  # nam is installed per-preset; the handler guards on chain.nam
                if p.index_template:
                    self.assertTrue(has_dynamic_index, f"{mod.name}.{p.key} needs an index template")
                    continue
                keys = {p.key, *p.aliases}
                self.assertTrue(
                    any((mod.name, k) in reachable for k in keys),
                    f"{mod.name}.{p.key} is not settable through /api/parameter",
                )


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
        for block, param in pairs:
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
