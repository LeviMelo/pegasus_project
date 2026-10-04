# Architectural debt ledger

Localized fixes that are façades over architectural-level issues. Each entry: the **symptom(s)** we
patched, the **gap** underneath, the **redesign** direction. Maintained so we escalate a recurring patch
into a deliberate redesign (CLAUDE.md §X) instead of re-patching. Entries are hypotheses about the *right*
redesign — validate scope before building.

> Origin: surfaced during the 2026-07 national-scale (C25) campaign, when clearing a cascade of memory
> walls finally reached stages never before exercised on real national data.

---

## AD-1 · Semantic recognition by name-matching, not registry consultation

**Symptoms patched**
- `efg/executor/support.py::_with_year_lazy` produced a NULL `year` axis for SIH/SINASC (whose temporal
  columns are `admission_year`/`birth_year`, not `year`) → national panel collapsed to T=0 → LDO crash.
  Band-aided with a hardcoded `_YEAR_ALIAS_COLUMNS` tuple (commit `ef7a7fb`).
- The DuckDB zero-variance profiler routes exact-vs-approx `count(distinct)` by
  `she/zero_variance.py::classify_structural_role`, a **fuzzy substring/suffix name heuristic** (`c9ec8f7`).
- (Map, 2026-07) ~4 mutually-inconsistent temporal synonym lists — `_YEAR_ALIAS_COLUMNS`,
  `kernels.py::_YEAR_KEYS`, `align.py`, `materialize.py`; a phantom `competence_year` that matches no real
  data (CNES emits `year`); an **incomplete geography set** in `align.py`.
- **A second live latent bug of the same shape** (flagged by the map, worth confirming): `demographic_axis_maps.yaml`
  declares SINASC's `age_group` source column as `maternal_age_years`, but the SINASC normalizer emits
  `mother_age_years` → `demographic_axis.source_column("age_group","SINASC")` returns a nonexistent column
  → silent skip of demographic stratification for births.

**The gap.** The registries already carry the semantics — `config/registries/datasus/source_fields.yaml`
tags every column with `role: [time_axis_candidate | geography_axis | …]` and `axes: {time|geography|age: <local>}`;
`demographic_axis_maps.yaml` has `source_columns:` (canonical axis → per-system column) + a resolver. But
downstream consumers (the executor spine translation, panel, profiler) **re-derive** column semantics by
string-matching, which drifts from the registry and the normalizers and produces silent nulls/skips.
`disease` and `demographic` are the only domains with true concept-level abstraction; time, geography, age,
value, identifier are recognized by scattered exact/substring lists.

**Redesign.** Generalize the proven `demographic_axis` pattern to a canonical **structural-axis resolver**
(time / geography / age), *generated* from the `source_fields.yaml` `axes`/`role` metadata (single source
of truth), consulted at the one physical translation seam (`_with_year_lazy` / `_with_geo_lazy`). Then the
scattered hardcoded lists are **deleted, not synchronized**. Longer arc: one concept↔surface substrate
unifying axes + disease + demographic + ontology. See PIPELINE.md "Seam A".

**Status (2026-07).** DONE: `registries/canonical_axis.py` (resolve axis→column from `source_fields.yaml`
role/axes) built + validated; the panel-spine seam `_with_year_lazy`/`_with_geo_lazy` wired to it and
`_YEAR_ALIAS_COLUMNS` deleted (`4b5cbe7`); the SINASC maternal-age map drift corrected in place (`64f8f7b`).
REMAINING: (a) delegate `demographic_axis.source_column` (age/sex/race) onto `canonical_axis` — needs an
age precedence (years > days; subject-vs-maternal, resolved by which column the frame carries) validated
against the population tensor before adopting, since it touches hard-won stratification; (b) fold
`align.py::_canonical` and `kernels.py::_YEAR_KEYS` onto the resolver; (c) migrate the profiler's
`she/zero_variance.py::classify_structural_role` substring heuristic onto registry roles.

---

## AD-2 · Scale-blind memory — stages materialize whole datasets instead of streaming

**Symptoms patched**
- National combine eager-reconciled ~25 GB (per-UF dtype drift blocks plain streaming) → pyarrow row-group
  streaming (`ac8722d`).
- she_build zero-variance profiler eager-loaded each ~12 GB event parquet (22.7 GB spike) → out-of-core
  DuckDB (`c9ec8f7`). *[Principled re-engineering, not a band-aid — listed for the pattern.]*
- efg_build accumulates ALL field tensors + aligned vectors in RAM (21.8 GB, tripped the floor) → my
  streaming fix (`9114289`) was **partial**: it streamed one reduce but the cross-field accumulation
  remained. **RESOLVED** (see Status): the two-pass streaming redesign eliminates it entirely.
- LDO residual-HSIC scan allocated a dense ~107 GB kernel → budget guard that **COARSENS** to ≤702 cells
  (`977e8d0`) — degrades spatial resolution rather than streaming the computation.

**The gap.** Every stage was built and validated at single-state scale, implicitly assuming its working set
fits in RAM; at ~27× national scale each materialization exceeds memory. There is no *uniform*
streaming / memory-envelope execution model — only the LDO has an envelope guard — so each OOM is a
separate reactive patch, discovered one full run at a time.

**Redesign.** A memory-envelope discipline applied uniformly: (a) a canonical schema at normalize→combine so
the combine is a plain streaming union (AD-3); (b) **stream the EFG panel assembly** — build the panel index
from keys, then align + emit + free per field, instead of accumulating all fields; (c) replace LDO coarsening
with streaming / Nyström HSIC (tracked as G2 / LDO-GPU-03; the user's noted direction); (d) a central
resource-sizing policy every stage consults (AD-4).

**Status (2026-07).** (b) **DONE** — `compile_attach.attach_autonomous_efg_to_run` rewritten as a two-pass
stream: pass 1 builds the panel index from key columns alone, folding each field's cells into a running
`_union_step` (working set O(distinct cells), not O(Σ fields)); pass 2 re-reads each tensor, aligns, computes
its Q-row, and frees the vector before the next. The dead `field_tensors`/`vectors_by_field` dicts are gone;
`_build_panel_index` (all-at-once concat) deleted. **Why the map was decisive:** the LDO rebuilds its panel
matrix `X` INDEPENDENTLY from the per-field parquets via `she.panel.compile_common_panel` (already streaming),
and `support_index.parquet` has no reader repo-wide — so the *only* byte-identical invariant is
`Q_tensor.parquet`. **Measured** (500 synthetic full-panel fields × 139 250 cells): peak RSS **8.55 GB → 0.61 GB**
(14×), now flat in field count; validated byte-identical (panel + every q_row vector, tolerant of the
pre-existing ~1e-13 parallel-mean ULP noise) across 6 real compiled runs (≤153 fields). **Two findings from
measuring, not assuming** (CLAUDE.md §VIII): (i) streaming the *vectors* alone left peak at 6.6 GB — the
panel-index `pl.concat(all key-frames).unique()` was itself an O(F×cells) spike the *old* code shared; the
incremental union was the actual fix. (ii) A String `value` column (a label/categorical field) can't be
mean-aggregated: the old code's `agg(mean)` threw and silently dropped it from the index, so a dtype gate now
reproduces that exclusion (clearer warning, byte-identical result).

**(e) DONE — `_population_solver_tensor` eager read (the REAL national wall, not the LDO).** After (b) landed,
the national run still aborted at ~23 GB — but full-pipeline, subprocess-aware profiling at the *true*
operating point (§VIII/§IX) showed the wall is NOT the LDO. It is `efg/executor/kernels.py::
_population_solver_tensor` doing `pl.read_parquet(tensor_path)` — an **eager full read of the 140.7 M-row ×
17-col national population tensor** to compute a marginal denominator (`group_by(year,muni,[axis]).sum`). A
rapid 13→21 GB jump in one `read_parquet`, exposed only once efg_build stopped dying first (§IX: a bug hides
behind the upstream bug). Fixed by projecting to the 4-5 needed columns and streaming the group-by-sum
(`scan_parquet→select→group_by→agg→collect(streaming)`): **peak 21 GB → 4.8 GB** for the ~14 M-group age
marginal, byte-identical group sums (verified vs DuckDB on the real tensor; polars-streaming won a measured
bake-off 4.8 vs 6.1 GB). **Cautionary note for the record:** an isolated `run_investigate` probe had reported
the LDO completing at 16 GB and wrongly implicated `stability_select` — because it read *cached* compile
outputs and never traversed the executor's population path. Profiling the real end-to-end run corrected it;
the LDO is genuinely fine.

**(f) DONE — `_source_field_tensor` per-event projection.** With (e) fixed the run advanced further and hit
the NEXT eager materialization (§IX, bugs behind bugs): `efg/executor/kernels.py::_source_field_tensor` — the
raw-source-column kernel — was a bare per-EVENT projection (`select(keys, col).collect()`), so it materialized
the WHOLE national source (SIM/SIH ≈ 1e8 rows → ~21 GB); `.collect(streaming)` can't bound a projection with
nothing to reduce (every sibling kernel — count/sum/functional — aggregates to ~139K cells). Fixed by
reducing to panel-cell granularity with the SAME `group_by(keys).agg(mean)` the panel builder + Q-tensor
already apply downstream — byte-identical (mean-of-means over single-row groups = the cell mean), O(cells)
memory. 37 executor/panel/compile tests green.

**Pattern (the AD-2 theme, live):** the national compile is a *chain* of scale-blind eager materializations,
each hidden behind the previous — efg_build accumulation (b) → pop-solver eager read (e) → source-field
projection (f). Each was built at state scale where the working set is small and only OOMs at ~27× national;
each is found one-at-a-time by profiling the real end-to-end run to its abort (§VIII/§IX), not by unit tests.
Remaining executor kernels (RN-ratio, race-bridge, SIDRA) operate on per-cell parent tensors / per-table SIDRA
(bounded); the LDO completes at ~16 GB. Longer arc: a uniform streaming/envelope execution model so a new
stage can't reintroduce this. Remaining doc items: (c) LDO streaming-HSIC (open, not a wall) and (d) central
sizing policy; a `stability_select` worker cap is a designed scale-safety follow-up.

**(g) DONE — stale field-tensor paths → LDO T=0 (a NON-memory latent bug the fixed chain exposed).** Once
the memory walls fell, the national run completed compile with **bounded memory (peak ~14 GB, never near the
22 GB floor)** and reached `run_ldo` end-to-end for the first time — then raised `ValueError: need T>1 time
points; got T=0`. Root cause (`she/panel.py::_tensor_path`, commit `bfd4744`): V_fields records each tensor's
path as an ABSOLUTE path into the transient `{run_dir}__efg_stage_workspace` staging dir, which is pruned once
the bundle flushes tensors to `run_dir/Tables/efg_tensors/`. On a COMPLETED run that stored path is stale →
`compile_common_panel` found ZERO tensors → empty index → T=0. (An isolated probe on an OLDER run dir had
worked only because its stage workspace happened to persist — §IX: a stage's "works" status is unverified
until reached on a clean real run.) Fixed by resolving from the canonical stable location
`run_dir/Tables/efg_tensors/{field_id}.parquet` — the panel never trusts a stored absolute path. National
panel 0 → 167 791 cells (S=5625, T=42). This is an AD-3 shape (no enforced canonical form — a transient
absolute path stored as if durable), not an eager-load.

**Open (scope enforcement, AD-3/data-quality):** the resolved panel spans **T=42 (1969–2024) and S=5625** —
wider than the C25 study window (2000–2024) and Brazil's 5570 municipalities. SIDRA historical/census years and
a few non-standard muni codes leak in because the panel is the UNION of all tensor cells and does not enforce
the intent's spatiotemporal scope. It does not crash the LDO (T≫K), but may dilute the temporal structure /
admit out-of-scope cells; assess against the LDO result and enforce the intent window at the panel if it
materially distorts the determinants.

---

## AD-3 · No enforced canonical form across sources (normalization-consistency)

**Symptoms patched**
- Per-UF canonicals exhibit **dtype drift** (a column all-null in one UF, typed in another) → blocks the
  combine's plain streaming → forced the schema-unify + row-group band-aid (`ac8722d`, `7faee5f`).
- Per-system canonical column **names diverge** (`admission_year` / `birth_year` / `year`) with no
  reconciliation → AD-1.

**The gap.** Each normalizer emits its own per-source output schema, and the combine its own per-UF schema,
without enforcing a shared canonical form — dtypes, names, and the axis vocabulary. Divergence is by
*omission*, not design; it surfaces as both the dtype-drift (combine memory) and the name-divergence
(recognition) problems — two faces of "no enforced canonical form."

**Redesign.** A canonical schema contract at the normalize→combine boundary: pin per-column dtypes (kill the
null-inference drift) and align names/axes to the canonical vocabulary (AD-1). Then the combine is a plain
streaming union and the recognition drift is fixed at the source.

---

## AD-4 · Manual knobs instead of auto-determination

**Symptoms patched.** `PEGASUS_SIDRA_UF_PARALLEL` env var (`95766df`); hardcoded DuckDB `memory_limit='6GB'`;
combine concurrency `min(3, …)`; several batch sizes.

**The gap.** CLAUDE.md §V prescribes auto-determining resource/tuning parameters from the data, problem
dimensions, and environment; several fixes hardcode memory/parallelism knobs instead of sizing from
available RAM / core count / the stage's working-set estimate. `compute/resources.py` reportedly exists as a
central sizing policy but is not uniformly consulted (verify).

**Redesign.** Route memory/parallelism through the central sizing policy. Overlaps AD-2's envelope discipline.

---

## Not debt — principled changes this campaign (for honesty / contrast)

- The out-of-core DuckDB profiler core (`c9ec8f7`) — a genuine re-engineering, winner of a measured bake-off.
- Content-addressed cache key on `processed_sha256` (`75784a3`) — fixed a real nondeterminism.
- The two-tier RSS kill switch (run harness) — real machine safety; measures resident footprint, not commit
  charge (see CLAUDE.md §VII).
