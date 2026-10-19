# KEMPER Rig Manager — Library & Rig Browsing Feature Specification

> **Method:** REA static analysis (shipped-artifact authority). No source code, no runtime observation.
> **Target:** `C:\Program Files\Kemper Amps\Rig Manager\Rig Manager.dll`
> **SHA-256:** `4fb18a851e0e400d3529d90bf4b560bf8cfa713ea94a3debfc97933f9b23fa59`
> **Size:** 9,190,968 bytes · **MVID:** `56ca1111-0c54-43c0-95fc-e739c73debd1`
> **Analysed:** 2026-10-19 · REA 6.5.0 (`rea-dotnet-static`)

## Evidence index

| Evidence ID | Operation |
|---|---|
| `ev_98bf1c081cb1377c1116af9a7d502b64cb7ce496bd8414bfc79b8f11ba13fa4a` | `inspect_managed_artifact` (artifact summary) |
| `ev_94a862e7763243e00971f0006aea9dff3560a39a3444e79b0350ca5678400b89` | `inspect_managed_artifact` (complete, retained) |
| `ev_5fa705a54c307951738dcf6da94e7144f236dedfe5b2ea0334284c011c4cf837` | `inspect_managed_members` (assembly members) |
| `ev_6d233bbbfa8413f99e6e21a50f5c83f745ea115db6c65bcde0530e533eaf71d4` | `inspect_managed_members` (complete, retained) |
| `ev_762cae89bdf032a9d2bd248da7331ad8589cafee9b41cfad57bbbe062bafa29b` | `inspect_managed_members` (FormSearch, summary) |
| `ev_64d06b526343a2b77c47957ae55980c4182f6ec612ebae00175bba4c776b22dc` | `inspect_sqlite_database` (`Ace Skunk Anansie.rigpack`) |

---

## 1. Application classification

**VERIFIED** — `ev_98bf1c08…`

| Property | Value |
|---|---|
| Container | PE32+ (PE32+) |
| Machine | `0x8664` (x86-64) |
| CLI runtime | v2.5 |
| Classification | **managed**, container `pe` |
| Runtime family | `mixed-clr-native` |
| Implementation | `cpp-cli-mixed` (C++/CLI) |
| `COMIMAGE_FLAGS_ILONLY` | **clear** |
| Strong name | absent (`strong_name_rva = 0`) |
| ReadyToRun | false |

Metadata status: **complete**. Table rows: `TypeDef` 2784, `MethodDef` 4097, `Field` 7060, `MemberRef` 1231, `CustomAttribute` 3882, `ImplMap` 106, `FieldRVA` 4194, `ManifestResource` 76, `ModuleRef` 2.

**Consequence for this spec:** the browsing workflow is implemented in mixed C++/CLI. The managed half exposes structure, names, signatures and IL; the native half is **not** decompilable with the providers available on this host.

**UNKNOWN** — no C++/CLI decompilation was performed. Ghidra (`not_configured`), Hopper (`unsupported_host` on win32) and IDA (`not_configured`) are all unavailable, so native bodies inside this DLL were not examined.

---

## 2. Screen structure

**VERIFIED** — TypeDef inventory from `ev_6d233bb…`, namespace `ProfilerControlCenter` (31 types).

| Type | Role | Confidence |
|---|---|---|
| `ProfilerControlCenter.FormMain` | Main application window | VERIFIED (type exists) |
| `ProfilerControlCenter.FormSearch` | Search / filter dialog | VERIFIED |
| `ProfilerControlCenter.FormCreateRigPack` | Rig-pack authoring | VERIFIED |
| `ProfilerControlCenter.FormPreferences` | Preferences | VERIFIED |
| `ProfilerControlCenter.FormSplash` / `FormProgress` / `FormUpdate` / `FormWhatsNew` / `FormAbout` | Lifecycle & auxiliary windows | VERIFIED |
| `ProfilerControlCenter.RigInspector` | Rig detail inspector | VERIFIED |
| `ProfilerControlCenter.PerformanceInspector` | Performance-mode inspector | VERIFIED |
| `ProfilerControlCenter.Inspector` | Base inspector type | VERIFIED |
| `ProfilerControlCenter.Globals` | Global state | VERIFIED |

Framework layer — namespace `Access` (285 types), sub-namespaces observed: `Access.Windows` (`Window`, `PlatformHandle`, `MessageBoxFrame`, `Properties`), `Access.Forms` (`TabContainer`), `Access.LogicEngine`, `Access.Data`, `Access.Drawing`, `Access.IO`, `Access.XML`, `Access.System`, `Access.Potmaps`, `Access.Time`, `Access.Threading`, `Access.Dialogs`, `Access.ProfMidiLegacy`, `Access.MIDI`.

**INFERRED** — a four-pane layout (library tree / rig list / inspector / editor) organised around `TabContainer`. Based on the coexistence of `FormMain`, the three `*Inspector` types and `RigEditor` namespace types. **Not** observed at runtime; no screenshot or UI capture was made.

**INFERRED** — the application does **not** run a local audio DSP path and acts as a librarian/control surface. Based on: `KemperControlLibrary.dll`, `connectivity.dll`, `kmidi` (14 types) and `Access.ProfMidiLegacy` / `Access.MIDI`. Corroborated by the user's own `PROJECT_HANDOFF.md` §2.1, which is **not** REA evidence.

---

## 3. Search

**VERIFIED** — `ProfilerControlCenter.FormSearch`, token `0x0200058a`: 25 fields, 21 methods, 36 `#US` literals.

### 3.1 Control inventory

| Field | Kind | Meaning |
|---|---|---|
| `labelSearchIn` | label | Search-field selector label |
| `labelAnd` | label | conjunctive-join label |
| `labelTypes` | label | profile-type filter label |
| `labelDisplayResults` | label | results-area label |
| `labelRevisionError` | label | validation-error label |
| `labelTypeError` | label | validation-error label |
| `mList1` | value list (`class:333`) | search-field / scope selector |
| `mList2` | value list (`class:333`) | match-mode selector |
| `mWordOptions` | value list (`class:333`) | **word-matching mode** |
| `mCaseOptions` | value list (`class:333`) | **case-sensitivity mode** |
| `mPanelRevision` | panel (`class:193`) | revision constraint panel |
| `mPanelType` | panel (`class:193`) | profile-type filter panel |
| `mCheckClassic` | check (`class:337`) | include Classic profiles |
| `mCheck20` | check (`class:337`) | include "2.0" profiles |
| `mCheckGeneric` | check (`class:337`) | include Generic profiles |
| `mCheckLiquid` | check (`class:337`) | include Liquid profiles |
| `mCollection` | `valuetype:5940*` | backing data collection |
| `mCollectionView` | `valuetype:5944*` | **filtered view over the collection** |
| `mDBIndexFromListIndex` | `valuetype:5272*` | **list-index → database-index mapping** |
| `mSearchOptions` | `valuetype:6004*` | compiled search options |
| `mPointArray` | `valuetype:201[]` | UI geometry |
| `mFormParent` | `class:185` | owner window |
| `mApp` | `valuetype:5924*` | application context |
| `components` | `class:501` | framework component container |

### 3.2 Exact UI strings (VERIFIED — `#US` literals)

Dialog title: `Search`

Labels: `Search in:` · `and` · `Profile types included in search:` · `Display Results...`

Validation message: `You must select at least one option`

Font: `Segoe UI`

Profile-type filters: `Classic` · `2.0` · `Generic` · `Liquid`

Match modes (`mWordOptions`, 4 entries):
- `Containing the search string`
- `Exactly matching the search string`
- `Starting with the search string`
- `Ending with the search string`

Case modes (`mCaseOptions`, 2 entries):
- `Case sensitive`
- `Case insensitive`

Tag scopes: `All Tags` · `All Visible Tags` · `- Select -`

### 3.3 Behaviour

**VERIFIED** — `FormSearch` declares a `SearchUpdated` event (`token 0x02000589`, `SearchUpdatedEventHandler`) with `add_SearchUpdated` / `remove_SearchUpdated` / `raise_SearchUpdated`. `raise_SearchUpdated` (`0x06000f02`, IL size 17, 8 instructions) loads the backing delegate field and invokes it behind a null check.

**VERIFIED** — `.ctor` (`0x06000eff`, IL size 340, 140 instructions, fat header, one `finally` region) performs 6 `ldstr` operations against `mWordOptions` and `mCaseOptions`, each followed by a list-append call.

**INFERRED** — the search is a **two-term conjunctive query** over a configurable set of fields, because `labelSearchIn` and `labelAnd` are separate labels and `mList1`/`mList2` are separate lists.

**INFERRED** — filtering is applied by **swapping the active view**, not by mutating `mCollection`, because both `mCollection` and `mCollectionView` exist as distinct fields and `mDBIndexFromListIndex` exists to translate a filtered view index back to a database index.

**UNKNOWN** — the exact field set offered in `mList1`, the tag taxonomy behind `All Tags` / `All Visible Tags`, the ordering of results, and the debounce interval between input and `raise_SearchUpdated`. These require either native decompilation or runtime observation.

---

## 4. Selection & navigation

**VERIFIED** — types present: `ProfilerControlCenter.CollectionAction`, `ProfilerControlCenter.DragSourceType`, `ProfilerControlCenter.EditorType`, `ProfilerControlCenter.EditorAction`, `ProfilerControlCenter.DialogNotifier`, `ProfilerControlCenter.NotifierProxy`.

**VERIFIED** — `RigEditor.ControllerKey`, `RigEditor.EditorConfiguration`, `RigEditor.AudioProviderCallbacks`, `RigEditor.ProfilingRawData`, `RigEditor.NotifyId`, `RigEditor.EditorNotifyId`.

**VERIFIED** — event plumbing under `Access.System`: `Event`, `EventType`, `KeyboardEvent`, `WheelEvent`, `MouseWheelEvent`, `EncoderEvent`, `AbsolutePotEvent`, `EndlessPotEvent`. `Access.Windows.PlatformHandle` and `Access.Windows.Window` provide the windowing layer.

**INFERRED** — selection state is carried by a controller-key model (`ControllerKey` + `CollectionAction` + `DragSourceType`), supporting drag-and-drop reorganisation of collections. Drag support in the UI is implied by `DragSourceType` existing as a named concept.

**INFERRED** — pointer input is abstracted: `AbsolutePotEvent` and `EndlessPotEvent` indicate rotary/relative encoder support alongside `MouseWheelEvent`.

**UNKNOWN** — the concrete gesture bindings, whether collection reordering is persisted, and the selection model (single vs multi). No runtime capture was performed.

---

## 5. Data model (rig packs)

**VERIFIED** — `ev_64d06b52…`, `Ace Skunk Anansie.rigpack`, 729,088 bytes, SQLite 3.53.4, UTF-8, schema completeness **complete**.

| Table | Columns |
|---|---|
| `packs` | `id INTEGER`, `name TEXT`, `copyright TEXT`, `author TEXT`, `releasedate TEXT`, `guid TEXT`, `updateguid TEXT`, `minversion TEXT`, `signature2 BLOB` |
| `rigs` | `id INTEGER`, `packs_id INTEGER`, `name TEXT`, `author TEXT`, `createdate TEXT`, `comment TEXT`, `rig_id INTEGER` |
| `rigdata` | `id INTEGER`, `rig BLOB` |
| `texts` | `id INTEGER`, `packs_id INTEGER`, `lang TEXT`, `short TEXT`, `long TEXT` |
| `properties` | `id INTEGER`, `packs_id INTEGER`, `key TEXT`, `val TEXT` |
| `images` | `id INTEGER`, `packs_id INTEGER`, `sequence INTEGER`, `image BLOB`, `locator INTEGER`, `description TEXT` |
| `packupdates` | `id INTEGER`, `packguid TEXT`, `oldguid TEXT` |
| `sqlite_sequence` | `name`, `seq` |

Indexes: one `sqlite_autoindex_*` per table. No views, no triggers.

**VERIFIED** — 35 `.rigpack` files present under `Rig Packs\`.

### 5.1 Metadata exposed per rig

**VERIFIED** — from the `rigs` schema: **name**, **author**, **comment**, **createdate**, plus foreign keys `packs_id` and `rig_id`.

**INFERRED** — per-pack provenance from `packs`: name, copyright holder, author, release date, GUID, update GUID, minimum-version floor, and a `signature2` integrity blob. `updateguid`/`oldguid` in `packupdates` indicate an **incremental pack-update chain** (delta packs reference a superseded GUID).

**VERIFIED** — `images.sequence` + `images.locator` + `images.description` indicate **ordered, captioned artwork per pack**; `texts.lang` indicates **localised short/long descriptions per pack**.

**VERIFIED** — `rigdata.rig` is an opaque `BLOB` holding the actual rig parameter payload. The Rig Manager ships **no DSP evaluation** in this container; it marshals state to the hardware.

**UNKNOWN** — the internal encoding of `rigdata.rig` (SysEx framing vs a proprietary serialisation) and the semantics of `signature2`. Byte-level decoding was out of scope for this pass and was not performed.

---

## 6. Loading behaviour

**VERIFIED** — `FormSearch` holds `mCollection`, `mCollectionView` and `mSearchOptions` pointers and a `mDBIndexFromListIndex` mapping table; `raise_SearchUpdated` fires on change.

**INFERRED** — the pipeline is: **load pack → build `mCollection` → derive `mCollectionView` → apply `mSearchOptions` → project into the results list → map selection back through `mDBIndexFromListIndex`**. Each stage is a distinct object, which is why selection survives filtering.

**UNKNOWN** — whether loading is synchronous, whether packs are memory-mapped, thread affinity, and any progress/cancellation behaviour. `FormProgress` and `ProgressProxy<>` exist and `collection.progress.notification.status.*` strings were observed assembly-wide, so **a** progress mechanism exists, but its binding to pack loading is not established.

---

## 7. Tool limitations

1. **No native decompilation.** Ghidra not configured (`GHIDRA_INSTALL_DIR` unset), Hopper unsupported on `win32`, IDA adapter not configured. For a C++/CLI assembly this bounds conclusions to the managed surface.
2. **No CLR resolution.** The assembly was never loaded; dependencies, generics and forwarded types are unresolved.
3. **Metadata tokens are build-local.** Tokens cited above are meaningful only with this SHA-256 and MVID.
4. **No runtime observation.** Screen transitions, gesture bindings, result ordering and timing are unverified. `capture_electron_scenario` / browser lanes do not apply — this is a WinForms app, not Electron or a web page.
5. **One pack inspected.** Schema was read from `Ace Skunk Anansie.rigpack` only; other packs were not opened. Row content was not sampled.
6. **`user_strings` are per-type.** The 36 literals reported are the ones loaded by `ldstr` inside `FormSearch` bodies only.

---

## 8. Summary of confidence

| # | Finding | Class |
|---|---|---|
| 1 | .NET mixed-clr-native C++/CLI, x64 | **VERIFIED** |
| 2 | `FormSearch` has 4 match modes, 2 case modes, 4 profile-type filters | **VERIFIED** |
| 3 | Exact UI strings listed in §3.2 | **VERIFIED** |
| 4 | `SearchUpdated` event exists and is raised | **VERIFIED** |
| 5 | Rig packs are SQLite with 8 tables as specified | **VERIFIED** |
| 6 | Rig metadata = name, author, comment, createdate | **VERIFIED** |
| 7 | 35 packs installed | **VERIFIED** |
| 8 | Filtering via a separate view object, not by mutating the collection | **INFERRED** |
| 9 | Two-term conjunctive search | **INFERRED** |
| 10 | Four-pane layout | **INFERRED** |
| 11 | Collection drag-and-drop reorganisation | **INFERRED** |
| 12 | Pack update delta chain via `updateguid`/`oldguid` | **INFERRED** |
| 13 | No local DSP evaluation | **INFERRED** |
| 14 | Search field set in `mList1` | **UNKNOWN** |
| 15 | Tag taxonomy | **UNKNOWN** |
| 16 | Result ordering & debounce | **UNKNOWN** |
| 17 | Selection model (single vs multi) | **UNKNOWN** |
| 18 | `rigdata.rig` binary encoding | **UNKNOWN** |
| 19 | Load threading / progress binding | **UNKNOWN** |