# What PegaSUS should discern — the epidemiological finding ontology

**Status: governing design (2026-07-13). Supersedes the implicit "a finding = a certified pairwise
dependency edge" model.** Written after the realization that the LDO discerns exactly ONE kind of
structure — global pairwise conditional dependence in the municipality×year covariance — while the goal
is to discern *any* epidemiologically-meaningful structure in the data over the spatiotemporal lattice.
Grounded in a live-code recon of what the engine already computes (much is computed and thrown away).

## 1. The reframing

PegaSUS compiles the DATASUS/SIDRA universe into a set of variables `{Y_v}`, each a **random field**
`Y_v(s, t)` over municipalities `s ∈ S` (~5570) and time `t ∈ T` (~26 years / months), indexed further by
a concept lattice (disease ICD hierarchy, demographic age×sex×race strata, clinical/procedure axes),
with population denominators giving rates. The scientific goal — *automating epidemiology* — is to surface
**every epidemiologically-meaningful structure** in this field-valued process.

A **finding is a certified, substantive, non-artefactual departure from a type-appropriate null.** The
engine's boring null is: each variable is *spatially homogeneous, temporally stationary, demographically
uniform, and mutually independent*. Every structured departure is a candidate finding. Today the LDO tests
only the last clause (independence), and only its global-linear-conditional form. That is a narrow slice.

The overhaul: enumerate the departures, give each a **producer** (a detector) and a **relevance test**
(a null + effect size + multiplicity control + artefact guard), and unify them under one Finding model of
which today's `LinkRecord` is a single type.

## 2. The taxonomy — organized by the question epidemiology asks

For each: the estimand, the null it departs from, and the engine's current state
(✅ computed+surfaced · ◻ computed-but-thrown-away · ○ detector-exists-but-unwired · ✗ absent).

### WHERE — spatial structure of ONE variable (unary)
- **Global clustering** — is `Y_v` spatially autocorrelated at all? Moran's I. *Null: spatial randomness.*
  ◻ computed (`geo/spatial.py::moran_i`, in the Q-tensor) but only deflates `n_eff`; never a finding.
- **Local hotspots / coldspots / spatial outliers** — *where* is `Y_v` high-surrounded-by-high (HH),
  low-by-low (LL), or a high-among-low outlier (HL/LH)? Local Moran (LISA) / Getis-Ord. *Null: conditional
  spatial randomness.* ✗→foundation: LISA is the per-node decomposition of the Moran sum (`local_moran`,
  added this cycle). **This is the user's flagged gap: a persistently localized phenomenon.**
- **Spatial gradient** — does `Y_v` vary smoothly along a spatial covariate / direction (a
  north–south, urban–rural, coastal gradient)? ✗.
- **Autocorrelation range / scale** — over what distance does the clustering extend? ○ orphaned:
  `geo/centroids.py::estimate_spatial_range` computes it (e-folding of the empirical correlogram) with
  **no caller**.

### WHEN — temporal structure of ONE variable (unary)
- **Secular trend** — monotone rise/fall over years. ◻ detrended away as a nuisance (`ldo/temporal.py`).
- **Regime shift / change-point / trend-break** — a step or slope change at time `T*`. ○ the detector
  exists (`causal/quasi.py::interrupted_time_series`, `detect_structural_break`) but is wired only as an
  edge-promotion gate — the break time becomes an *edge warning*, never a standalone finding. A variable
  with a real regime change but no certified pairwise edge produces nothing.
- **Outbreak / aberration / excess** — a transient excess over the expected baseline (the surveillance
  question). *Null: expected trend baseline (detrended, robust-MAD; the annual analogue of Farrington/
  EARS).* ✅ `ldo/temporal_findings.py::find_temporal_outbreaks` (see §7).
- **Seasonality / periodicity** — ◻ used only as a permutation-null structure for HSIC.

### WHO — demographic structure of ONE variable (unary)
- **Stratum concentration** — for a stratified family (the age×sex×race joint the EFG now emits), which
  stratum carries the burden? *Null: burden proportional to population share.* ✗ (the joint machinery
  exists; no concentration finding).
- **Disparity / gradient** — an ordered inequality across a stratum axis (e.g., mortality rising
  monotonically from branca→preta, controlling for age) — the slope/concentration index of inequality.
  *Null: no gradient.* ✗.

### HOW IT MOVES — spatiotemporal structure of ONE variable (unary)
- **Emergence** — a cluster that appears / grows over time. ✅ `find_emerging_clusters` (foundation #6).
- **Diffusion / traveling wave** — a phenomenon spreading spatially across time. ✗.
- **Space-time interaction** — is the space-time pattern more than space × time (Knox / space-time scan)?
  *Null: separable space×time.* ✅ `find_spacetime_clusters` (Kulldorff space-time permutation scan, §7).
- **Localized outbreak** — an outbreak confined to a region-and-window. ✅ `find_spacetime_clusters` (§7).

### WHAT CO-OCCURS — joint structure of TWO+ variables (bi/multivariate)
- **Global conditional dependence** — `Y_i ⟂̸ Y_j | rest` across (muni,year) cells. ✅ **today's entire
  LDO output** (`LinkRecord`: contemporaneous / lagged-directed / latent-shared / nonlinear-residual).
- **Spatial co-location** — do `Y_i` and `Y_j` cluster in the *same places* (bivariate LISA)? The user's
  "phenomena that co-occur in the same place." Distinct from global covariation. *Null: independent spatial
  fields.* ✗.
- **Temporal co-movement / lead-lag** — synchronized surges, or `Y_i` leading `Y_j` in time. ◻ partial:
  lagged edges capture linear lead-lag; co-outbreak (joint aberration) is ✗.
- **Spatiotemporal coupling / spillover** — `Y_i` in place A at `t` → `Y_j` in place B at `t+k`
  (contagion, referral flow, diffusion between variables). ✗.

### HOW IT DEPENDS ON CONTEXT — effect modification
- **Varying level / dependence** — a level or an `i→j` coupling that *varies* over place / time / stratum
  (the BYM varying-coefficient surface, with sign-flip detection). ✅ `find_effect_modifications` — now read
  from the `.spatial_field.parquet` sidecars via `read_spatial_field` and wired into `run_investigate` (§7;
  the sidecar was previously written with no reader).

### WHY — causal / driver structure
- **Orientation** — the causal rung of a directional claim (LiNGAM / collider / ITS-DiD). ✅ today
  (rungs 0–2 on edges). **Exposure–response** gradients (a dose-response between a contextual SIDRA
  exposure and an outcome) and **candidate-driver** ranking are ✗.

## 3. The unified Finding model

Replace "the output is `Hypotheses.parquet` of `LinkRecord`s" with a **`Finding`** carrying a common
envelope + a type-specific payload. `LinkRecord` becomes the `dependency` finding type (additive; the
existing Hypotheses key is preserved).

```
Finding (common envelope)
  finding_id        content hash
  finding_type      spatial_cluster | temporal_change | temporal_outbreak | stratum_concentration
                    | spatial_co_location | dependency | effect_modification | exposure_response | ...
  subjects          the variable(s) — 1 for unary, 2+ for joint
  locus             WHERE/WHEN/WHO the structure lives — {municipalities[], time_window, stratum, scale}
  effect_size       the magnitude on an interpretable scale (rate ratio, cluster elevation, break Δ,
                    disparity slope, partial correlation)
  direction         sign / class (hotspot vs coldspot, rise vs fall, excess vs deficit)
  significance      p/q vs the TYPE-APPROPRIATE null (spatial CSR, stationarity, uniformity, independence)
  persistence       stability of the structure across the orthogonal axis (a spatial cluster's fraction
                    of years; a temporal signal's spatial extent)
  certification     selected | descriptive (the same conjunction machinery, per type)
  provenance/warnings   reliability, denominator fragility, mechanical/artefact flags
  + type-specific payload (e.g. dependency → edge_type/lag_k/causal_rung; spatial_cluster → LISA/quadrant)
```

## 4. Relevance, generalized

Today "relevant" = a certified pairwise dependency (`|pcorr|≥0.05`, stability≥0.6, `n_eff≥100`, BY-FDR
q≤0.1, path-agreement≥0.66, not latent-lag, not mechanical). That machinery **generalizes per type**:
- **Null** — each type tests against its own null (spatial: conditional permutation / CSR; temporal:
  stationary bootstrap / expected baseline; demographic: multinomial-under-population-share; dependency:
  the current design-effect Fisher-z).
- **Effect-size floor** — a per-type substantive threshold (a cluster rate-ratio, a break magnitude, a
  disparity slope) so a *statistically* significant but trivial structure is descriptive, not selected.
- **Multiplicity** — dependence-aware FDR across the finding set of that type (already have BY).
- **Artefact guards** — reuse: denominator fragility (the near-zero rate floor), reliability weighting
  (Q-tensor), mechanical overlap (shared-numerator), and the small-`n_eff` power gate.
- **Persistence as evidence** — a structure that recurs across the orthogonal axis (a spatial cluster
  stable over years; a temporal signal present in many places) is stronger than a one-off.

## 5. Implementation roadmap (foundation-first, latent-capability-first)

Ordered by leverage — each surfaces capability the engine already computes or nearly computes:

1. **Spatial clusters (WHERE)** — LISA per variable × year → persistent HH/LL clusters → `spatial_cluster`
   findings. LISA is the decomposition of the existing Moran sum. **Building now** (the user's named gap).
2. **Temporal change/outbreak (WHEN)** — run the existing `quasi.py` change-point detector per variable
   (not only on edge targets) → `temporal_change` findings; add an EARS/Farrington baseline for outbreaks.
3. **Stratum concentration (WHO)** — over the joint age×sex×race pivot the EFG now emits → concentration /
   disparity-slope findings. Pure post-processing of existing variables.
4. **Spatial co-location (WHAT, same place)** — bivariate LISA over variable pairs → `spatial_co_location`.
5. **Effect modification** — promote the orphaned BYM `.spatial_field.parquet` (sign-flip, scale) to a
   first-class `effect_modification` finding with a reader.
6. **Spatiotemporal (HOW IT MOVES)** — space-time scan / Knox; the heaviest, last.

Each lands as a `Finding` in a new bundle key (`Findings.parquet`), additively — the dependency
`Hypotheses` key is unchanged. The output query layer and dashboard gain finding-type-aware views.

## 6. Status (2026-07-13) — ALL SIX FOUNDATIONS BUILT

The unified `Finding` model (`ldo/findings.py`) + all six foundations are built, tested, and wired into
`run_investigate` → additive `Findings.parquet` (the dependency `Hypotheses` key unchanged):

- ✅ **#1 spatial cluster (WHERE)** — `geo/spatial.py::local_moran` (LISA) + `ldo/spatial_findings.py`.
  Live Alagoas: municipalities with persistently poor cause-of-death documentation.
- ✅ **#2 temporal change (WHEN)** — `ldo/temporal_findings.py` (ITS structural-break + OLS trend). Live
  Alagoas: MicrocephalyBirths falling (Zika aftermath), SIH-admissions regime-shift @2015.
- ✅ **#3 stratum concentration (WHO)** — `ldo/stratum_findings.py` (disparity ratio + Kruskal–Wallis over
  the `~strat~` pivot). Synthetic-validated (real needs a stratified compile).
- ✅ **#4 spatial co-location (WHAT/same place)** — `geo/spatial.py::local_moran_bivariate` +
  `ldo/spatial_findings.py::find_spatial_colocations`. Live Alagoas: LowApgar1 co-locating with
  socioeconomic context (a social-determinant signal).
- ✅ **#5 effect modification (HOW-IT-DEPENDS-ON-CONTEXT)** — `ldo/effect_modification_findings.py` promotes
  the orphaned BYM per-locality surface (sign-flip → context-dependent coupling). Synthetic-validated.
- ✅ **#6 spatiotemporal emergence (HOW-IT-MOVES)** — `ldo/spatiotemporal_findings.py` (per-year-LISA
  hotspot-extent trend). Synthetic-validated; a full Kulldorff/Knox space-time scan is the extension.

Live end-to-end: combined `Findings.parquet` on the real Alagoas panel = **114+ findings** across spatial
clusters, temporal changes, co-locations, and emerging clusters (stratum + effect-mod need stratified/BYM
inputs). The output now answers WHERE/WHEN/WHO/same-place/context/emergence — not only "which two
variables co-vary."

## 7. Post-foundation build-out (2026-07-13)

Beyond the six foundations, the following were completed so the ontology is *usable*, not just *produced*:

- ✅ **Temporal outbreak (surveillance, within #2)** — `ldo/temporal_findings.py::find_temporal_outbreaks`:
  a transient EPIDEMIC YEAR (a spike that returns to baseline) is distinct from a permanent trend/break.
  Detrends the annual series and flags years beyond a robust (MAD) baseline — the annual, trend-aware
  analogue of an EARS/Farrington aberration baseline (weekly seasonal baselines do not fit annual panels).
  Wired into `run_investigate` (`temporal_outbreak` findings).
- ✅ **Finding-type-aware view in the output query layer** — `output/query/engine.py` `kind='finding'`:
  reads `Findings.parquet`, selects by `finding_type` (`quantity='all'`/`'*'` for every type), filters
  (e.g. `certification_status='selected'`), and enriches subject field_ids to human names. `Findings` is
  registered as an **additive-optional** bundle key (recognized first-class for the query layer, but never
  required-non-empty — a panel may honestly certify zero findings). This closes the "produced but not
  surfaced" gap: the findings the LDO discovers are now readable/exportable by type, not just written.
- ✅ **Effect-modification WIRED (foundation #5 was orphaned).** The §6 status above claimed #5 "built +
  wired"; it was not — `find_effect_modifications` had zero callers and the BYM `.spatial_field.parquet`
  sidecars it consumes had no reader, so context-dependent / sign-reversing couplings never reached the
  output despite the fit being computed every run (a CLAUDE.md §IX orphaned-but-callable, corrected). Added
  `spatial_field.read_spatial_field` + wired it into `run_investigate` over the LinkRecords carrying a
  `spatial_field_ref`. All six foundations are now genuinely in the live path.
- ✅ **Space-time interaction / localized-outbreak scan (#6 extension)** —
  `ldo/spatiotemporal_findings.py::find_spacetime_clusters`: a Kulldorff space-time PERMUTATION scan
  (contiguity-expanding spatial window × contiguous year window, Poisson GLR vs the marginal-product
  separability null, Monte-Carlo inference redistributing each municipality's total over years). Needs no
  denominator; bounded (spatial block ≥2 munis, top-`max_variables` count fields, coverage warning on the
  rest); wired into `run_investigate` gated on spatial extent (state-scale). Validated: recovers a planted
  5-muni×3-year cluster, rejects a null Poisson panel, and finds plausible localized clusters on real AL SIM.

**Remaining extensions (genuinely optional, lower value-per-effort):** a national center-capped/reduced-R
variant of the space-time scan (state-scale is wired today); a disparity slope/relative-index of inequality
for the ordinal age axis (#3 — the concentration ratio already covers the non-ordinal race/sex axes); a
dashboard front-end over the `kind='finding'` query.
