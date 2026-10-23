"""Executable checks for docs/PRESET_DATA_CONTRACT.md against presets.db.

The adapter audit in ``tests/test_rigdoc.py`` already proves that every stored
``settings_json`` converts to RigDocument v2 and renders back unchanged. This
module covers what that audit cannot see: the identity and label columns, and
that ``settings_json`` is really a JSON object stored as TEXT.

The database is opened read-only. A check that changes the file it validates is
not a check.
"""

import json
import re
import sqlite3
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
DB_PATH = ROOT / "presets.db"

COLUMNS = ("id", "name", "category", "author", "settings_json")
ID_PATTERN = re.compile(r"[A-Za-z0-9_.-]+")


class PresetContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not DB_PATH.exists():
            raise unittest.SkipTest("presets.db not present")
        cls.connection = sqlite3.connect(f"file:{DB_PATH.as_posix()}?mode=ro", uri=True)
        cls.rows = cls.connection.execute(
            "SELECT id, name, category, author, settings_json FROM presets"
        ).fetchall()

    @classmethod
    def tearDownClass(cls):
        cls.connection.close()

    def rows_by_column(self):
        return [dict(zip(COLUMNS, row)) for row in self.rows]

    def test_the_contract_columns_are_the_whole_table(self):
        info = self.connection.execute("PRAGMA table_info(presets)").fetchall()
        self.assertEqual({column[1] for column in info}, set(COLUMNS))
        # SQLite does not add NOT NULL to a TEXT PRIMARY KEY, so `id` is only a
        # key here; its nullability is checked against the rows below.
        self.assertEqual({column[1] for column in info if column[3]}, {"name", "settings_json"})
        self.assertEqual([column[1] for column in info if column[5]], ["id"],
                         "id must be the only primary key")

    def test_the_table_is_not_empty(self):
        self.assertGreater(len(self.rows), 0, "a preset library with no presets is a defect")

    def test_ids_are_unique_stable_labels(self):
        ids = [row["id"] for row in self.rows_by_column()]
        self.assertEqual([i for i in ids if not isinstance(i, str) or not ID_PATTERN.fullmatch(i)], [],
                         "ids must be non-empty and match [A-Za-z0-9_.-]+")
        self.assertEqual(len(set(ids)), len(ids), "duplicate preset id")

    def test_every_row_has_human_labels(self):
        missing = [
            (row["id"], column)
            for row in self.rows_by_column()
            for column in ("name", "category", "author")
            if not isinstance(row[column], str) or not row[column].strip()
        ]
        self.assertEqual(missing, [], f"empty labels: {missing}")

    def test_settings_json_is_a_json_object_stored_as_text(self):
        kinds = {row[0] for row in self.connection.execute(
            "SELECT DISTINCT typeof(settings_json) FROM presets"
        )}
        self.assertEqual(kinds, {"text"}, f"settings_json must be stored as TEXT, found {kinds}")

        broken = []
        for row in self.rows_by_column():
            try:
                value = json.loads(row["settings_json"])
            except json.JSONDecodeError as exc:
                broken.append((row["id"], f"not JSON: {exc}"))
                continue
            if not isinstance(value, dict):
                broken.append((row["id"], f"{type(value).__name__} is not an object"))
        self.assertEqual(broken, [], f"malformed settings_json: {broken}")


if __name__ == "__main__":
    unittest.main()
