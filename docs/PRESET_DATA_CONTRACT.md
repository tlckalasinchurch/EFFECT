# Preset Data Contract — `presets.db`

| | |
|---|---|
| Dataset | SQLite file `presets.db`, table `presets` |
| Producer | `engine/presets.py` (`save_preset`, `init_db`), the importers and the API |
| Consumers | `AudioEngine`, `server.py` `/api/presets`, the pedalboard UI |
| Enforcement | [`tests/test_preset_contract.py`](../tests/test_preset_contract.py) for the table; [`tests/test_rigdoc.py`](../tests/test_rigdoc.py) for what `settings_json` contains |
| Read policy | Validation opens the file with `mode=ro`; no check may write to it |

## Schema

```sql
CREATE TABLE presets (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT,
    author TEXT,
    settings_json TEXT NOT NULL
);
```

| Column | Type | Null | Meaning |
|---|---|---|---|
| `id` | TEXT | no\* | Stable identity, `[A-Za-z0-9_.-]+`. Imported presets carry their source id (`t3k_88775`); a rename must not change it. |
| `name` | TEXT | no | Human label shown in the UI. Duplicates are allowed; `id` is the identity. |
| `category` | TEXT | yes (schema) | Free-text grouping used by the browser (`Metal / Lead`, `Amp + Cab`, …). |
| `author` | TEXT | yes (schema) | Attribution; importer name for imported presets. |
| `settings_json` | TEXT | no | UTF-8 JSON **object** in the legacy `settings_json` shape, consumed by `engine.rigdoc.from_v1`. |

`category` and `author` are nullable in the schema for backward compatibility,
but every row in the shipped file carries both — the contract treats an empty
label as a defect, not as "unknown".

\* SQLite does **not** add `NOT NULL` to a `TEXT PRIMARY KEY`, so the schema
only makes `id` unique, not non-null. The contract therefore enforces it on the
data (`id` must be a non-empty string in every row). Making the schema say
`id TEXT PRIMARY KEY NOT NULL` requires rebuilding the table; that is a
migration, not a contract change, and is deliberately left out of this pass.

## Quality dimensions

| Dimension | Rule | Enforced by |
|---|---|---|
| Completeness | `id`, `name`, `category`, `author` non-empty after trimming; `settings_json` present | `test_preset_contract.py` |
| Uniqueness | `id` is unique and is the only primary key | `test_preset_contract.py` |
| Validity | `settings_json` is stored as TEXT and decodes to a JSON object | `test_preset_contract.py` |
| Consistency | Every preset converts to `RigDocument` v2 and renders back byte-identically to its stored value | `test_rigdoc.py::RealPresetAuditTests` |
| Type & range | No `INVALID_VALUE` or `OUT_OF_RANGE` issue for any stored parameter; only `DEFAULTED` is expected, because factory presets omit parameters on purpose | `test_rigdoc.py::test_stored_presets_report_only_defaulted_issues` |
| Accuracy | Not testable here: nobody has compared the rendered sound with the hardware. | — |
| Timeliness | Not applicable: this is a locally editable library, not an ingested feed, so there is no freshness SLA. | — |

## Deliberately out of scope

* Cross-table checks with `morph_slots`; that table has its own lifecycle.
* Duplicate display names: two authors may ship the same preset name.
* Audio quality of a preset. The contract proves the row is well-formed and
  loadable, never that it sounds good.

## Changing the contract

* Adding or renaming a column is a contract change: update this file, the
  `CREATE TABLE` in `engine/presets.py`, and the column list in
  `tests/test_preset_contract.py` in the same commit.
* Adding a key inside `settings_json` must stay round-trip safe. Unknown keys are
  preserved in `extras` by `rigdoc` rather than dropped; a new *parameter* should
  be declared in `engine/params.py` so type and range validation see it.
