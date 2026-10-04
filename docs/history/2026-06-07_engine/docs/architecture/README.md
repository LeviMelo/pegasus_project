# PegaSUS architecture documentation

**Purpose.** A *living* reference for how the code actually works — the data model, the pipeline
stages, each module's responsibilities and contracts, and the known architectural debts. This is
deliberately distinct from the `PEGASUS_*.md` files at the repo root, which are point-in-time
audits / critiques / roadmaps / plans. Those record *decisions and assessments*; these record the
*current mechanics* so we stop re-researching them from the code every time.

**Maintenance rule.** When you finish investigating how a module works (as opposed to skimming),
write it down here before moving on. Turn a one-time re-research into a durable page. Verify claims
against the live code (CLAUDE.md §IX) — a doc that lies is worse than none.

## Contents

- **⭐ [DISCOVERY_ENGINE_NORTH_STAR.md](DISCOVERY_ENGINE_NORTH_STAR.md)** — the governing *vision* (what PegaSUS
  is for), sitting ABOVE the mechanics docs. PegaSUS = a deterministic discovery engine that reveals leads,
  not conclusions; the three-level statistical frame + identification wall; and the three axes the system
  still lacks — **grain** (individual / linked-cohort / ecological, not ecological-only), **bias
  instrumentation** (arm, don't eradicate), and **deterministic orchestration** (fused, gatekept synthesis,
  not a finding dump). The frame to check every redesign against. Reframes `FINDING_ONTOLOGY.md` as its
  Level-1 ecological slice.
- **[FINDING_ONTOLOGY.md](FINDING_ONTOLOGY.md)** — the finding-ontology output spec (a finding = a certified
  departure from a type-appropriate null); the Level-1 ecological realization of the north star's structure axis.
- **[PIPELINE.md](PIPELINE.md)** — end-to-end data flow (intent → acquire → combine → compile → investigate
  → output), the canonical data model / panel spine, the registries, and the critical seams.
- **[MODULE_MAP.md](MODULE_MAP.md)** — the repo-wide module index: every `src/pegasus/` module's role,
  entry points, key structures, and status (medium depth; `modules/ldo.md` + `modules/efg.md` are the deep
  exemplars, the rest are the deep-map follow-up).
- **[ARCHITECTURAL_DEBT.md](ARCHITECTURAL_DEBT.md)** — localized fixes that are façades over
  architectural-level issues, each with the symptom → gap → redesign direction. The redesign backlog.
- **[LDO_RESIDUAL_ARTIFACT_HANDOFF.md](LDO_RESIDUAL_ARTIFACT_HANDOFF.md)** — open investigation: the
  residual-scan near-clique artifact in the national C25 run (companion to `modules/ldo.md` §8/§10).
- `modules/` — per-module architecture pages (below). Filled incrementally.

## Module pages

- **[modules/efg.md](modules/efg.md)** — the Entity-Field Graph: the compile-stage engine that turns
  normalized source events into typed analytical `FieldNode`s (the field/node data model + content-addressed
  identity, the operator grammar, legality/declaration/alignment, the executor & kernel math incl. the O7
  extensive/intensive gate, the Q-tensor/state/uncertainty, the measured-quantity seam to the LDO, and
  materialization/lineage/DAG spine + a wired-vs-orphaned and gaps/stale-vs-plan section). The map for
  localizing the compile-stage dataflow without re-reading the source.
- **[modules/she.md](modules/she.md)** — the Substrate Harmonization Engine: the substrate-admission boundary
  (source artifacts → zero-variance/registry gate → typed `SubstrateBundle`) and the **CommonPanel spine**
  (`compile_common_panel` — the EFG's per-field tensors assembled onto one geo×time cell index, the
  anti-silence provenance manifest, the axis-scoping that keeps the LDO working set bounded). The LDO's
  direct input.
- **[modules/ldo.md](modules/ldo.md)** — the Latent Dependency Operator: a faithful code + **mathematics**
  map of the whole estimator (margins → covariance/whitening → sparse+low-rank precision ADMM `Ω=S−L` → lags
  / detrend / multiresolution → edge readout + stability → residual HSIC scan → certification/coverage), the
  spine call-graph, the core data structures, and a consolidated flags / orphaned-code / questionable-math
  section. The math reference for localizing dataflow + numerics without re-reading the source.
- **[modules/datasus.md](modules/datasus.md)** — the DATASUS data plane: the R-bridge fetch orchestration
  (subprocess/heartbeat/cache) + the vectorized `Cols` raw→canonical decode spine, the in-house codebook, and
  the scalar/record oracles (with the measured parity-guard gaps). Raw FTP microdata → `canonical.parquet`.
- **[modules/output.md](modules/output.md)** — the run-bundle output contract + the Output Query Layer: the
  17-key bundle, `OutputBundleManager` atomic flush, `validate_output_bundle`, and the `materialize_query`
  read side — plus the measured LinkRecord-vs-seed schema duality and the validator's live no-ops.
- **[modules/denominators.md](modules/denominators.md)** — the population-denominator data plane: the
  SIDRA-anchored two-layer population-tensor build (closed-form census interpolation + the 8-term Spectral
  Projected Gradient solver), census closure (9606/6579/2093 + FAL-POP-SV), AMC carve, gravity-CTR migration
  flows, and the `population_denominator_seed` seam the LDO **excludes** from analytical outcomes (§IV).

## Per-module page template

Each `modules/<pkg>.md` should answer, tersely and truthfully:

1. **Responsibility** — one paragraph: what this module owns, what it does NOT.
2. **Inputs / outputs** — the data it consumes and produces (shapes, canonical columns, files).
3. **Key abstractions** — the 2-5 types/functions that carry the design; where the real logic lives.
4. **Contracts & invariants** — what callers may assume; what this module assumes of its inputs
   (e.g. "expects a `year` column"; "panel keyed on `(year, municipality_cod6)`").
5. **Registries / config consulted** — which `config/registries/*` files, and how.
6. **Known debts** — links into ARCHITECTURAL_DEBT.md; scale limits; ad-hoc spots.

## Priority modules to document (where re-research keeps happening)

`datasus/normalize` · `workflows/acquire` (combine) · `she` (substrate, zero_variance, panel) ·
`efg/executor` (the per-system→spine translation seam) · `efg/compile_attach` (panel/Moran bridge) ·
`efg/dag` · `ldo` (assemble → estimator) · `registries` (source_fields, demographic_axis) ·
`denominators/population`. Do these as they're touched; don't block on a big-bang pass.
