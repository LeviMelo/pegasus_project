# `datasus` — raw DATASUS microdata → canonical event parquet

A faithful code map of `src/pegasus/datasus/` (~5.2k LOC): the data-plane boundary that **fetches** raw
DATASUS FTP microdata through an isolated R subprocess and **decodes** it into the canonical event schema
the SHE substrate admits. Two spines live here — an *R-bridge fetch* orchestration and a *vectorized
raw→canonical decode* — plus storage-GC/profiling satellites. Its output (`canonical.parquet`) is the
source artifact [`she.md`](she.md) §3 admits and [`efg.md`](efg.md) builds fields from. See
[`../MODULE_MAP.md`](../MODULE_MAP.md). Verify against live code (CLAUDE.md §IX).

> **§IX correction.** Contrary to a "normalize-only" reading, this module *does* own the fetch bridge
> (`subprocess.py`, `client_microdatasus.py`, `manifests.py`, `cache.py`, `r_scripts/`). What it does not
> own is the FTP I/O itself (that is `microdatasus`/`read.dbc` inside R) and the combine→normalize→canonical
> *driving* + cache-key computation (that is `workflows/pipeline.py::_combine_normalize_one`).

## 1. Responsibility

- **Owns — fetch bridge:** spawn/timeout/heartbeat/cache of the microdatasus R subprocess that turns a
  `(system, uf, year[, month])` request into a per-chunk raw-coded `processed.parquet`
  (`subprocess.py::fetch_datasus_chunk` :175, `client_microdatasus.py::MicrodatasusClient`,
  request manifests + availability windows `manifests.py`, `cache.py::DatasusCache`).
- **Owns — decode:** the `Cols` primitive library (`normalize/primitives.py`), the four per-system
  vectorized normalizers (`normalize/{sim,sih,sinasc,cnes}.py`), the shared in-house codebook
  (`normalize/codebook.py`), and the scalar/record correctness oracles (`decoders.py`, `icd_parser.py`,
  `normalize/records.py`).
- **Owns — satellites:** storage GC (`storage_gc.py`), column profiling / raw↔processed diff
  (`profile.py`, `schema_compare.py`), static ICD chapter/block ranges (`icd_groups.py`).
- **Does NOT:** download from FTP (microdatasus/R), drive the combine→canonical flow, admit the substrate,
  build the EFG, or *own* raw→canonical field routing semantics — those are declared in
  `registries.source_fields` and consulted via `she.source_registry` (CLAUDE.md §X).

## 2. The vectorized decode spine

**`normalize/primitives.py::Cols`** (docstrings call it `vec.Cols`) is the single source of truth for *how*
a raw DATASUS column decodes, as Polars expressions — no per-row Python. Bound to a `DataFrame`/`LazyFrame`;
raw lookups are defensive — an absent column resolves to a typed null literal, never a crash (:262-271).
Every method returns `pl.Expr` (or `(value, state)` per MSD §2.3). Primitives: `clean`/`digits`/`int_digits`
(sentinel-null + digit-run), `date`/`date_state` (multi-format DDMMYYYY/YYYYMMDD/ISO, 7-digit zero-pad
:300), `municipality(prefix, *names, crosswalk)` → `{prefix}_cod6/cod7/state` with the **UF+0000
"ignored" sentinel** nulled to missingness (:333, const :240), `sex`/`race_admin`, `categorical`/
`categorical_value`/`lookup` (codebook, §3), `nonneg_int`/`money`/`money_state`, `flag_int` (bool service
flags), `icd_norm`/`icd_state`/`icd_marker`, and the CNPJ gate `cnpj_digits` + `cnpj_from_digits` (mod-11
check digits, `_cnpj_check_ok` :551). Perf note: `cnpj_digits` must be materialized **once** as a column
before the check — polars CSE does not dedupe the ~30 per-digit slices, so an inline form re-runs the
clean+regex ~30×/CNPJ (measured 19.7s→1.2s on a 300k SIH panel, :462-469; applied in sih.py:314, cnes.py:256).

**Per-system normalizers** — each `_X_vectorized_frame(df, *, source_manifest_hash, row_offset)` is
lazy-in→lazy-out (streaming sink) / eager-in→eager-out (tests), assembling the canonical schema from `Cols`
in one `with_columns` pass; each declares only *which raw columns feed which primitive*:

- `normalize_sim_do_events(*, input_path, output_path, source_manifest_hash) -> dict` — SIM-DO mortality
  (`SIM_DO_NORMALIZED_COLUMNS`, 62 cols): IDADE age-unit decode inline via `_SIM_AGE_UNITS` with
  date-difference age provenance (sim.py:275-295), LINHAA–D cause chain + LINHAII as sorted-key JSON,
  cod6→cod7 crosswalk, categorical fields via `_SIM_CATEGORICAL`.
- `normalize_sih_rd_events(...)` — SIH-RD hospitalizations: COD_IDADE-driven age unit (`_SIH_AGE_UNITS`),
  secondary-diagnosis + cost JSON vectors, hospital/maintainer CNPJ gate, `_SIH_CATEGORICAL` (24 concepts).
- `normalize_sinasc_events(...)` — SINASC births (`SINASC_NORMALIZED_COLUMNS`): perinatal scalars
  (weight/gestation/APGAR) + count2 fields, `anomaly_flag`/`anomaly_icd`/`anomaly_positive` numerator logic.
- `normalize_cnes_st_events(...)` — CNES-ST facilities: COMPETEN year/month split, QTLEIT bed primitives +
  full capacity/flag/attribute JSON vectors, facility/maintainer CNPJ gate.

**Batched decode driver — `stream_normalize_batched(*, input_path, output_path, frame_fn,
source_manifest_hash, batch_rows=120_000) -> int`** (primitives.py:104). The decode plans cannot stream
(`with_row_index` + per-row `struct.json_encode` force the whole-frame path → a national/UF `sink_parquet`
peaks at 15-17 GB), so this pulls fixed row-batches off the parquet row groups, decodes each eagerly, and
appends via one `ParquetWriter` → **peak RAM ≈ workers × one batch**, independent of UF/national size. Decode
is size-based parallel (`ThreadPoolExecutor`, worker count memory-budgeted via `compute.resources`,
:158-166) yet **byte-identical to serial**: each batch keeps the global `row_offset` assigned in read order
and batches are written in read order, so surrogate identity (`_i`/`event_id`/`row_hash`) and row order are
unchanged (:190-217). Empty input → a schema-only canonical file (:224). `read_raw_table`/`scan_raw_table`
read CSV/TXT with `infer_schema_length=0` (all-Utf8) — schema inference is *harmful* here (it drops a
zero-padded date's leading zero, :69-86).

## 3. The codebook / categorical registry — `normalize/codebook.py`

In-house replacement for microdatasus `process_*()` categorical translation: loads
`config/registries/datasus/datasus_codebook.yaml` (concepts + per-system bindings + reference lookups,
lru-cached). One code→meaning dictionary per **concept**, shared across systems, so SEXO/RACACOR/the
Sim-Não flags are defined once. `translate(concept, code) -> (value, state)` is the record-level twin;
`categorical_exprs(concept, code_expr) -> (value_expr, state_expr)` the vectorized twin behind
`Cols.categorical` — both live here so the dictionary applies identically. State (an improvement over
microdatasus's silent 0/9→NA collapse): blank→`missing`, in-values→`valid`, unknown-sentinel→`unknown`,
else→`invalid` (:15-19). Zero-padded fixed-width DBC codes (`"00"`/`"01"`) fall back to an int-normalized
key so they don't mis-read as invalid (`_strip_leading_zeros` :78, `code_norm` :133). `concept_for(system,
col)` resolves a raw column's bound concept. Large open code→name tables (`tabCBO`/`tabNaturalidade`, mirrored
from microdatasus) load via `load_reference_table` / `lookup_expr` as `{code:name}` joins, distinct from the
small closed concept dictionaries.

## 4. The oracles + how parity is maintained

Two oracle layers back the vectorized live path:

1. **Scalar decoders (`decoders.py`)** — the single source of *decode logic*: `decode_sim_idade` (:89),
   `decode_sih_age` (:201, unit map from `composite_decoders.yaml`), `decode_physical_scalar`, `decode_count2`,
   `clamp_bool` (:299), `filter_cnpj` + `_valid_cnpj_check_digits` (:331/:359), `decode_datasus_sex`/
   `_date`/`_hour`/`_race_admin`/`_municipality_cod6`/`_facility_code`/`_integer`. Each returns a typed
   pydantic `Decoded*` with an explicit §2.3 state. `icd_parser.py::parse_icd` (:43) is the ICD authority
   (R-codes → `ill-defined`, :114).
2. **Registry-routed record path (`normalize/records.py::normalize_record`, :370)** — the SIM/SINASC record
   oracle (`normalize_sim_do_record`/`normalize_sinasc_record`, :431-436): resolves each raw column through
   `she.source_registry`, dispatches the declared decoder by name via `registries.callables`, and emits
   canonical fields (+ `__state`/`__decoder`). SIH/CNES instead have direct record oracles
   `normalize_sih_rd_record` (sih.py:134) / `normalize_cnes_st_record` (cnes.py:123) producing the *same*
   schema as their vectorized frame.

**How parity is actually enforced — and where it is not.** The committed contract test
`tests/contract/test_no_decode_duplication.py` pins parity only at the **primitive** level: each `Cols`
`(value,state)` vs its scalar oracle across the full §2.3 state space, for `{sex, race_admin, flag_int,
cnpj}` (:46-71). It also guards that the pre-consolidation flat normalizers stay deleted. **No test compares
a record oracle against its vectorized frame end-to-end** (verified: no test references
`normalize_*_record` or `_*_vectorized_frame`). The age-unit maps `_SIM_AGE_UNITS`/`_SIH_AGE_UNITS` *duplicate*
the scalar authority's constants and are only *claimed* kept in sync (sih.py:239) — so the repeated
docstring "the equivalence stress-check pins against" the record oracle overstates the live guard (CLAUDE.md
§II: green tests ≠ math correctness). **Deliberate divergences** the frames do *not* reproduce: identity/
provenance columns. The vectorized frames set `raw_json=None` and `row_hash = row_hash(manifest:_i)` (a
manifest+row-index surrogate, sih.py:370/378, cnes.py:284/288, sinasc.py:387); SIM sets both
`raw_record_hash` and `processed_record_hash` to that same surrogate (sim.py:353-357,409). The record oracles
instead emit full `raw_json` + a SHA-256 of the raw payload (sih.py:232, cnes.py:182). `completeness.py`
guards silent decode-to-null: `REQUIRED_RAW_COLUMNS` per system, warned + reported when absent (:28-65).

## 5. Seams & contracts

- **Fetch → chunk:** `MicrodatasusClient.fetch_systems` builds request manifests (`build_datasus_manifests`
  :300 — SIM/SINASC annual, SIH/CNES **per-month** chunks by default, :321; availability floors/ceilings/
  known-holes drop chunks DATASUS never published, :97-199) and runs them through `fetch_datasus_chunk`,
  which invokes `r_scripts/fetch_process_microdatasus.R --vanilla`, polling with backoff + heartbeat +
  process-tree kill (:284-302), and emits a per-chunk `processed.parquet` (raw-coded, all columns) +
  `manifest.json`. **Cache validity is keyed on the consumed `processed.parquet` + its manifest, not the
  legacy `raw.rds` sidecar** (:215), gated on an accepted bridge-contract-version set (:22-25); the
  `processed_sha256` is read from a co-located sidecar to avoid re-hashing GB-scale parquet on warm hits
  (:45-68).
- **Chunk → canonical (driven by `workflows/pipeline.py`, not here):** `_combine_normalize_one` combines a
  system's ok chunks (`pl.concat(...).sink_parquet`) then calls the `normalize_*_events` in `_NORMALIZERS`
  (pipeline.py:143). The `source_manifest_hash` handed to the normalizer is `combined_hash` —
  **content-addressed on the sorted `processed_sha256` set** (pipeline.py:259-276), NOT on volatile manifest
  bytes (the prior bug: cache never hit, re-normalized every run, orphan canonicals piled up; commit 75784a3).
  Output: `data/normalized/datasus/{system}/uf=…/years=…/{hash}/canonical.parquet`, short-circuited if present.
- **Canonical → downstream:** `canonical.parquet` is the source artifact the SHE substrate boundary admits
  (`she.md` §3, via `inspect_source_artifact`, `provenance_mode="materialized_external"`); `she` +
  `registries.source_fields` own the raw→canonical field *routing* this module's columns are keyed to.
- **Storage GC (`storage_gc.py`):** `gc_datasus_raw_sidecars` (drop `raw.rds` + microdatasus sidecar once
  `processed.parquet` exists), `gc_datasus_combined_after_canonical` (drop the combined intermediate once
  `canonical.parquet` exists) — both safe-by-construction (removed only after the consumed artifact is
  confirmed) and `dry_run=True` by default.

## 6. Known flags / debts

- **Overstated oracle claim.** The per-system frame docstrings assert the record fn is "the correctness
  oracle the equivalence stress-check pins against," but only *primitive*-level parity is tested (§4); a
  record-vs-frame equivalence test does not exist. The age-unit constant maps are duplicated, not derived.
- **`_assemble_sim_do_record` is orphaned** (sim.py:132). It projects the registry-routed record output into
  `SIM_DO_NORMALIZED_COLUMNS`, but the public `normalize_sim_do_record` routes to `records.normalize_record`
  (sim.py:458) and the live batch path is `_sim_vectorized_frame` — nothing calls it (grep: only its own def
  + docstrings + a critique doc). So the SIM/SINASC record "oracle" emits a *different* (registry-suffixed)
  shape than the frame, with no reconciler wired.
- **Silent decode-to-null on a missing raw column** is only *warned*, not raised (`completeness.py:56`); a
  genuinely dropped required column still produces an all-null canonical field (auditable via the returned
  `missing_required_columns`, but non-fatal).
- **Registry-routed record path swallows decoder failures** — `_decode_value` returns `state="invalid"` +
  a `decoder_failed:` warning on any exception (records.py:350), so a broken decoder degrades a field
  silently rather than surfacing (weaker than CLAUDE.md §V for a malformed vs absent value).
- **Deep-map status:** this page joins [`she.md`](she.md), [`ldo.md`](ldo.md), [`efg.md`](efg.md),
  [`output.md`](output.md); only `denominators/population` remains (see [`../MODULE_MAP.md`](../MODULE_MAP.md)).
