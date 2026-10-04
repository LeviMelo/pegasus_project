# `registries` — the typed config-registry layer (canonical semantics)

A faithful code map of `src/pegasus/registries/` (~2.5k LOC, 22 modules): the typed loader/accessor
layer over `config/registries/` (48 YAML/JSON/JSONL files + spatial parquet artifacts across 9 subdirs:
`datasus health demographic disease fields inference ontology sidra spatial`). This is the **single
place canonical semantics are DECLARED** — a source column's carrier/unit/role/axes, the DATASUS
codebook callable bindings, demographic axis crosswalks, event carriers + legal RN ratios,
population/denominator solver policy — and the read boundary consumers CONSULT instead of re-deriving by
string-matching (CLAUDE.md §X). It owns *declaration + typed loading*, **not** the transforms/decoders
themselves (those live in [`datasus.md`](datasus.md) / [`she.md`](she.md) and are merely DISPATCHED here
by name). Companion deep maps: [`she.md`](she.md) (consumes `source_fields`), [`efg.md`](efg.md) (events/
functional/topology/axis), [`denominators.md`](denominators.md) (`population` + `demographic_axis`),
[`datasus.md`](datasus.md) (owns the decoders this layer dispatches). Verify against live code (CLAUDE.md
§IX); see [`../MODULE_MAP.md`](../MODULE_MAP.md).

## 1. Responsibility

`registries` turns `config/registries/*.yaml` into frozen typed accessor objects and answers "what is the
canonical carrier/unit/role/axis/solver of *this* surface token?" It is pure read+validate: it does not
fetch, normalize, build fields, or solve. Three things it owns: (a) **typed loading** — YAML → dataclass
with a hash for provenance; (b) **the §II.1 admission rule** — one shared `is_active` test for which
registry entries count as live; (c) **executable-authority validation** — proof that every decoder/parser
*name* a registry declares resolves to a real callable, and every carrier/unit/aggregation token exists
in its vocabulary registry. The decoder/parser bodies are elsewhere; this layer only names and dispatches
them.

## 2. The loader / validator spine

REG-07's target was to collapse divergent loaders into one typed contract. **What actually landed** is a
shared *admission rule* + a typed `RegistryEntry` with a dict-compat shim — **not** a single load
function. Three load paths still coexist (§6):

- **`loader.py::load_registry_file`** (`:19`) — raw `dict` parse, `lru_cache`d by `(resolved_path, mtime)`
  (`_load_registry_file_cached`, `:10`) so edits invalidate. The low-level cache.
- **`generic.py`** — the **typed** contract: `RegistryEntry` (`:33`, frozen `id/status/description/
  warnings/payload`) with a dict-compat `.get()` (`:41`) so dict-era consumers treat a typed entry
  uniformly. `load_registry_payload` (`:77`) reads YAML *fresh* + stamps `registry_sha256` (`:91`);
  `load_entries`/`active_entries` (`:109/122`) build the `RegistryEntry` tuple; `resolve_registry_path`
  (`:61`) resolves the **first existing** of a candidate-name tuple (the closest thing to a "merge":
  `events.REGISTRY_FILES` tries `clinical_event_definitions.yaml` → `events_registry.yaml` → `events.yaml`).
- **`semantic.py`** — the legacy `list[dict]` contract: `registry_entries`/`active_entries` (`:14/20`)
  go through `loader.load_registry_file` + `generic.is_active`; plus `match_entry` (`:55`, §3).
- **`source_fields.py`** — a bespoke `SourceFieldRegistry` with its own `lru_cache` (§3).

**The unification that landed** = `is_active` (`generic.py:27`), the single §II.1 rule: `status.startswith
("active")` ∪ `{stable, planned_contract, experimental}` (`_ACTIVE_NON_PREFIX_STATUSES`, `:24`). Its
docstring records the *latent gun* it fixed — `generic` once used strict `== "active"` while `semantic`
used the graded-active union, so a naive unification to the strict form would have silently dropped
graded-active entries (`active_artifact_required`, `active_warning`); `semantic.active_entries` now imports
`generic.is_active` and MUST NOT re-inline a status test (`semantic.py:22`).

**Validation surface** — `validators.py` (loaded by `cli.py:30`, the `validate-registries` command).
`validate_registry_tree` (`:177`) checks a hardcoded `required` list of files (`:180`) exists + shape-checks
each via `validate_registry_file` (`:21`, `REQUIRED_REGISTRY_KEYS`, `:11`), then runs the **executable-
authority** cross-check `validate_registry_authority` (`:99`): every `decoder`/`parser`/`composite_decoder`/
`transform` name in `source_fields.yaml` must `resolve_callable` (`:136`); every `carrier`/`unit`/
`aggregation` token must exist in its ontology registry; a `route=Decode|Parse` must name its callable
(round-trip, `:151`); every `spatial_graphs.yaml` graph must carry `legality_class` + `provenance` + an
existing artifact (`:159`). (**Note:** there is *no* `REGISTRY_FILES` constant in `validators.py` — that
name is a per-wrapper candidate-path tuple, only in `events.py:18`.)

## 3. The key registries and what each declares

- **`source_fields.py`** (346 LOC, the largest) — the canonical **source-column semantics**.
  `load_source_field_registry` (`:200`, `lru_cache` by root+mtime, `:210`) builds a frozen
  `SourceFieldRegistry` of `SourceFieldRegistryEntry` (`:22`: `carrier/unit/aggregation/field_kind/role/
  quality_role/provenance/admissible/dashboard_safe/axes/decoder/route/parser/raw_fields`). `resolve`
  (`:82`) matches exact `(system, column)` → regex `field_patterns` → `default_unknown` fallback;
  `resolve_raw_all` (`:104`) reverse-maps a raw DATASUS column to its canonical entries. Every entry is
  cross-validated at load (`_validate_entry`, `:183`: carrier/unit/aggregation/quality/provenance all
  resolve, and `unit ∈ carrier.allowed_units`). `normalize_source_system` (`:125`) canonicalizes system
  aliases (`SIM→SIM-DO`, `SIH→SIH-RD`, `CNES→CNES-ST`). `resolve_source_field_entry` (`:273`) is the
  per-column memoized public entry.
- **`demographic_axis.py`** — the source↔canonical **axis category crosswalk** (MSD §2.12.2), from
  `demographic/demographic_axis_maps.yaml`. `map_category(axis, system, code)` (`:85`, unknown→`__unknown__`
  so it is *excluded*, never silently merged); `source_category_map` (`:66`, cached, read-only);
  `source_column` (`:75`, which normalized column carries an axis for a system); `axis_for_classification`
  (`:47`, SIDRA classification id → canonical axis, e.g. `'2'→'sex'`); `age_group_for_years` (`:121`,
  arithmetic bucketing) + `age_group_sort_key` (`:101`, guards the alphabetical `age_10<age_2` scramble
  that would break the aging loss). `DEMOGRAPHIC_AXES={sex,age_group,race}` (`:26`).
- **`events.py`** — the clinical-event **carrier + legal RN-ratio** registry (`clinical_event_definitions.
  yaml`). `primary_event_carriers` (`:150`, directly-countable carriers), `clinical_ratio_specs` (`:104`,
  each legal numerator|denominator ratio + role + output unit), `restricted_event_specs` (`:134`,
  σ-restricted derived events). Denominator-unit-by-output policy (`rate→person_years/persons`,
  `proportion→counts`) is the one epidemiological rule inline (`:24`).
- **`callables.py`** — the **decoder-dispatch-by-name** resolver (MSD-II §II.1). `resolve_callable`
  (`:60`, `lru_cache`) maps a registry name → Python callable: `_EXPLICIT` synonyms/compound decoders
  first (`:39`, e.g. `decode_sex→decode_datasus_sex`, `decode_sim_cause_chain→…records._sim_cause_chain_
  decode`), else a lazy `importlib` scan of `_MODULES` (`:31`, `datasus.decoders` + `datasus.icd_parser`)
  trying `name`/`decode_*`/`parse_*`. `resolve_callable_strict` (`:103`) is the fail-loud form.
- **`population.py`** — the **solver-selection policy** (no math). `select_population_solver` (`:141`)
  picks the first `active` `PopulationSolverSpec` (`:27`) for a mode, preferring `sparse_block_coordinate`
  when `n_cells>DENSE_NATIONAL_CELL_THRESHOLD`=10M (`:50,160`); `RETIRED_SCAFFOLD_SOLVERS` (`:57`) and a
  `scaffold`-in-status guard raise a typed `PopulationSolverUnavailableError` rather than silently
  downgrading. `assert_dense_population_tensor_allowed` (`:173`) is the scale gate.
- **Ontology quartet** (`carrier.py`/`unit.py`/`aggregation.py`/`quality.py` + `provenance.py`) —
  structurally identical thin `get_*`/`load_*_registry` wrappers over `ontology/*.yaml`, each a frozen spec
  dict `lru_cache`d by root+mtime with a `content_hash` (e.g. `CarrierSpec.allowed_units`, `carrier.py:36/68`).
  These are the vocabularies `source_fields._validate_entry` + `validate_registry_authority` check against.
- **`canonical_axis.py`** — the **axis→source-column resolver** (AD-1). `resolve_axis_column(axis, columns)`
  (`:74`) answers "which column of this frame IS the temporal/spatial axis?" by reading the `role`/`axes`
  metadata already declared in `source_fields.yaml` (`axis_columns`, `:47`; geography precedence
  residence→occurrence→…, `:42`) — the §X pattern done right (see §4/§6).
- **`race_bridge.py`** — the **Bridge_R prior selection** registry (`race_bridge_priors.yaml`).
  `resolve_race_bridge_plan` (`:236`) maps an intent `race_tensor_mode` to a `RaceBridgePlan`
  (`not_requested`/`planned`/`embedded`/`blocked`); `select_compile_race_bridge_prior` (`:198`) UF-scopes
  the prior; `load_prior` (`:43`) re-validates id/mode/axis against the artifact (`measurement.race`).
- **`functional.py`** / **`bridge.py`** / **`diagnostic_topology.py`** / **`cnes_capacity.py`** /
  **`sih_cost.py`** — thin read boundaries for their `fields/*` and `health/*` YAML. The last three (+
  `bridge`) resolve a field to its entry via `semantic.match_entry` (§6); `cnes_capacity`/`sih_cost` also
  hold hardcoded canonical **component tables** (`CAPACITY_COMPONENTS:24`, `COST_COMPONENTS:23`) that
  `she.cnes_capacity`/`she.sih_costs` import directly, and a `require_*` guard forbidding a generic
  bed/cost request that would erase vector-indexed semantics.

## 4. Canonical concept → surface representation (the §X mapping)

The load-bearing pattern (CLAUDE.md §X): one canonical concept, many source spellings, **one queryable
mapping**, consumers CONSULT rather than re-derive.

- *temporal / spatial axis*: `year`/`admission_year`/`birth_year` and `mun_residence_cod6`/
  `mun_occurrence_cod6`/… → `canonical_axis.resolve_axis_column("time"|"geography", cols)`, driven by the
  `time_axis_candidate`/`geography_axis` roles in `source_fields.yaml`.
- *demographic category*: DATASUS sex code `1`/SIDRA category → `demographic_axis.map_category`; a SIDRA
  classification id → `axis_for_classification`.
- *source column semantics*: any raw/normalized column → `source_fields.resolve*` (carrier/unit/role/axes).
- *decoder name*: a registry string → `callables.resolve_callable`.

The declared semantics live once (in YAML), and the resolver is the single consult point — so the answer
can never drift from the normalizers. Where a consumer still re-derives by a private hardcoded synonym
list instead, that is the §X anti-pattern (§6).

## 5. Seams & contracts (who consumes each registry)

- **`she.source_registry`** (`she/source_registry.py:16,232,263,299,350`) — the SHE-facing compatibility
  boundary; wraps `source_fields.resolve_source_field_entry`/`resolve_raw_*`/`load_source_field_registry`
  for the substrate admission gate (she.md §3.2).
- **`datasus.normalize.records`** (`:36`) — dispatches decoders through `callables.resolve_callable`; the
  decoder bodies are `datasus`, this layer only names them.
- **`efg`** — `dag/spine.py`+`dag/helpers.py`+`operators.py` consult `events.{primary_event_carriers,
  clinical_ratio_specs,restricted_event_specs}`, `functional.functional_field_specs`,
  `bridge.bridge_grammar_entries`, `demographic_axis.{DEMOGRAPHIC_AXES,source_column}`; `legality.py:139-151`
  consults the `diagnostic_topology`/`cnes_capacity`/`sih_cost` `*_evidence` + carrier/unit/aggregation
  registries; `executor/{kernels,support}.py` consult `demographic_axis.{map_category,source_category_map}`
  + `canonical_axis.resolve_axis_column` (`support.py:219,244`).
- **`denominators`** — `population/build/orchestrator.py:22,724` + `reconstruction/solvers.py:27` consult
  `population.select_population_solver`/`assert_dense_population_tensor_allowed`; `strata.py`/`priors.py`/
  `fields.py` consult `demographic_axis.{map_category,source_category_map,axis_for_classification,
  age_group_*}`.
- **`sidra` / `sources.sidra`** — `compendium.py:204` + `sidra_projection.py:57` consult
  `demographic_axis.{axis_for_classification,map_category}`.
- **`workflows`** — `compile.py:514`/`pipeline.py:45`/`report/race_bridge.py:50` consult
  `race_bridge.{resolve_race_bridge_plan,select_compile_race_bridge_prior}`; `output/query/denominators.py:15`
  reads `health/denominators.yaml` via `loader.load_registry_file`; `cli.py` runs
  `validators.validate_registry_tree` + `source_fields.source_field_registry_summary`.

## 6. Known flags / debts

- **Three load paths survived REG-07.** `loader.load_registry_file` (mtime-cached dict, → `semantic` +
  `output.query`), `generic.load_registry_payload` (**fresh read + sha256 every call, no `lru_cache`** on
  `load_entries`, → `events`/`functional`/`core_seed`), and `source_fields`' bespoke cached registry are
  three distinct contracts. REG-07 unified the *admission rule* (`is_active`) and added the typed
  `RegistryEntry.get()` shim, but the loaders themselves were **not** collapsed — the `generic` (typed
  tuple) vs `semantic` (`list[dict]`) split is still chosen per-wrapper. `generic`'s re-read is only
  amortized because `events`/`functional` wrap their accessors in their own `@lru_cache`.
- **§X anti-pattern — the temporal-synonym lists `canonical_axis` claims to have retired still live, and
  have already DRIFTED.** `canonical_axis.py`'s docstring (`:14`) says it REPLACES `_YEAR_KEYS`,
  `align.py::_canonical`, etc. — but `efg/executor/kernels.py:303` still hardcodes
  `_YEAR_KEYS=("year","admission_year","birth_year","competence_year")` (used by `_shift_year`, `:329`) and
  `efg/align.py:35` still hardcodes `{"year","birth_year","admission_year","annual"}`. The two lists have
  **already diverged** (`kernels` has `competence_year`, `align` has `annual`) — exactly the "same synonym
  list copied into several modules drifts apart, each divergence a silent bug" §X failure. `canonical_axis`
  was wired into `executor/support.py` only; `kernels._shift_year` and `align._canonical` should call
  `resolve_axis_column("time", cols)` and let the private lists be deleted.
- **`match_entry` resolves the health topology/capacity/cost registries by substring pattern-match.**
  `semantic.match_entry` (`:55`) scores entries by longest `field_pattern`/`id` substring found in a
  concatenated `field_text` dump of the field (`:27`). It is centralized (one resolver) and its
  longest-match specificity fixed the Slice-27A "generic pattern shadows specialized QTLEIT/QTINST" bug —
  but it is still string-matching over a stringified field, the fragility §X warns about, not a declared
  key lookup.
- **`normalize_source_system` alias map is a small hardcoded synonym list** (`source_fields.py:125`) with a
  duplicated `"SIM-DO":"SIM-DO"` key (harmless copy-paste, `:129-130`) — the §X class in miniature, though
  one place.
- **Silent-but-audited fallbacks.** `source_fields.resolve` returns the `default_unknown` spec
  (`admissible=False`, `carrier=AuditMetadata`) for any unmatched column — not raising here, but SHE then
  audits it as `unresolved_source_field` (she.md §3), so not silent downstream. `callables.resolve_callable`
  returns `None` on *any* `importlib`/`getattr` failure (bare `except`, `:76,94`) — `resolve_callable_strict`
  is the fail-loud variant; `validators` uses the `None` form deliberately to *collect* dangling-callable
  errors. `demographic_axis.map_category` → `__unknown__` for unmapped codes is intentional exclusion
  (§IV-honest), not a silent merge.
- **National solver-backend label is a policy band, not executed math** — `select_population_solver` records
  `sparse_block_coordinate_v1` on the full 135M cell count while the blocked path re-selects per-block and
  actually runs `projected_gradient_small` (fully documented in [`denominators.md`](denominators.md) §2.2/§6;
  not re-derived here).
- **Deep-map status:** this page joins [`ldo.md`](ldo.md), [`efg.md`](efg.md), [`she.md`](she.md),
  [`denominators.md`](denominators.md), `datasus`, `output` (see [`../MODULE_MAP.md`](../MODULE_MAP.md)).
