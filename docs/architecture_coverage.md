# Architecture coverage matrix

**Audit of 2026-10-05, branch design-v0.** Every numbered item of `ARCHITECTURE.md` against the code (`src/pegasus_core`, `scripts/`, `data/`), the evidence (`docs/evaluation/`, `DECISIONS.md`) and the stores in `pegasus_home/`, never against `STATUS.md` alone. It is a map to be checked, not a decision record: re-run the audit when a status changes, or delete the row's gap when it closes.

**Status:** `BM` built and measured (the evaluation is cited; "not recovered" is still measured) · `BU` built, unmeasured · `P` partial (the gap says what is missing) · `NB` not built · `SS` superseded (by the ADR cited). **Evidence:** `E:slug` is `docs/evaluation/*-slug.md`. **§13** says whether `ARCHITECTURE.md` §13 records the departure; "no" is a silent one.

**Found while auditing:** `ARCHITECTURE.md` lost §8.4 (admission, minimum effects, calibrated δ and θ0) and §8.5 (mechanical overlap) in commit 4c0397a (ADR-0015 rewrote §8.3). Thirty-two citations in `ARCHITECTURE.md`, eleven modules and one script, plus three ADRs and four evaluation entries, still point to them (`git show 4c0397a^:ARCHITECTURE.md`, lines 521-558, has the text). `check_docs.py` does not check section references.

## Revision 2 (2026-10-06, ADR-0023)

The rows below audit the v1 text; their section numbers still hold, because revision 2 inserted sections instead of renumbering. What the revision changes:

**New items** (all `NB` when the revision landed; statuses as of 2026-10-06's end):

| § | item |
|---|---|
| 5.3 | exact Newton on the assembled arrowhead Hessian: **BM** (`solver.StructuredNewton`, E:2026-10-06-solver-v1) |
| 5.3, 4.3 | BYM2: **P**. Its coordinates for the strengths' step were measured and not adopted (ARCHITECTURE §5.4); the parametrisation waits on the PC priors |
| 5.4 | the strengths by LAML: **BM** (safeguarded Newton on log τ, probes 8/16; E:2026-10-06-solver-v1) |
| 5.5 | selected inversion and exact draws: **P**. The draws are exact (`laplace.Posterior`, one triangular solve); traces are by Hutchinson probes, with no selected inversion |
| 5.8 | the benchmark (`bench`, O1) and the time budgets: **BM** (`scripts/bench.py`, held out; IX 32 s, XX 107 s; docs/plans/2026-10-06-optimization.md) |
| 7.0 | departure models per estimand, with Bayesian FDR |
| 7.5 | relation models: distributed lag, shared component, endemic–epidemic; negative controls |
| 8.4 | IHW weights and minimum detectable effects |
| 8.6 | conserved-level fields as standard; rule versions on stored verdicts; the coding-regime term: **P** since 2026-10-06 (`Registry.conserved`, fields across blocks; E:2026-10-06-icd-structure). Rule versions on verdicts built 2026-10-06 (`explain.RULES`, `triage --stale`; BU until the re-triage reads them). Not built: the lenses' reading beside each lead, the coding-regime term |
| 10.3 | the designed grid of planted signals |
| 10.6 | simulation-based calibration: **BU** (`scripts/sbc.py`; VII and XIII running) |
| 3.3, 4.2 | the ICD ontology consumed (subcategory leaves, list effects, structural zeros, relations for the conserved levels): **P** since 2026-10-06 (ADR-0024: the nested tree, profiles by block with geography by group, structural zeros by sex and absolute age, underlying-cause eligibility; E:2026-10-06-icd-structure). Not built: list effects θ_L, relations; subcategory leaves declined by the author. Built since: list fields and conserved levels across blocks, chapter XX's axis fields |
| 3.4, 4.1, 4.2, 7.0 | race as an axis of G, the recording model, the race terms, race disparities |

**Superseded (`SS` by ADR-0023):**
- the gate (§10.5);
- admission by exclusion (§8.4; ADR-0022 amended);
- `tools.SURVEY_PLAN` as a limit on what runs;
- E_w as an inference (it stays a screen);
- the Fellner–Schall fixed point and the autodiff Newton–CG as the end state of §5.3–5.4 (v0, replaced in O1).

**Built on 2026-10-06, `BU` until O2 measures them:**
- the horseshoe tree prior (`prior="horseshoe"`): **BM** since 2026-10-06. Held out under ADR-0024, SIM I, SIM XVII and SIH IX are equal to the Gaussian's to 2·10⁻⁵ per event, at 15–40 % more time; the Gaussian stays the default (E:2026-10-06-solver-v1, O2);
- the low-rank interaction ψωτ: **BM** since 2026-10-06. On SIM IX it gains 0.0153 per death up to rank 4; on SIH X, 0.0012 at rank 1, after which it loses. The rank is chosen per block and defaults to 0 (same entry);
- `surprise.lift`;
- `pairs.within(prewhiten=)`, which failed the microcephaly positive at the state grain (a screen).

**The gaps, re-ranked by the overhaul (ARCHITECTURE §12):**
1. **The solver (O1).** Every measurement waits on it.
2. **Validation that characterises (O5)**, because the v0 constants were tuned on the documented events.
3. **Departure models (O6).**
4. **Relation models (O7).**
5. **Recording as measurement (O8)**, including the 14,813 leads reopened on 2026-10-06.
6. **Breadth (O9)**: the old gaps 6 and 10.
7. **The top model (O10)**: the old gap 5.

The old gaps 1–3 (κ and SUS, race, the low-rank term) are measurement work inside O2. The low-rank term, κ and SUS are measured (ADR-0025: κ and SUS stay opt-in, with no held-out gain); race is not yet. The old gap 4 (the horseshoe) is built and measured. The ten-gap table below is the 2026-10-05 ranking, kept for its reasons.

## Counts

| status | items |
|---|---|
| BM built and measured | 116 |
| BU built, unmeasured | 12 |
| P partial | 46 |
| NB not built | 41 |
| SS superseded | 1 |
| total | 216 |

## The ten most consequential gaps (ranked)

| # | gap | ARCH | why it ranks here | §13 |
|---|---|---|---|---|
| 1 | **Completeness κ and the SUS-dependent population are built as opt-in exposure modifiers (ADR-0020, 2026-10-05); their refits are not read.** (Original gap: no completeness term κ and no SUS-dependent population variant.) Every block is per resident of POPSVS; SIH and SIA are not rates of the people they serve. pegasus_data ships `system-completeness-1/2` (SIM, SINASC × UF × 2000-2023) and `sus-dependent-1` (2021-22 only) | 4.1, 3.1 | SIH rates are per resident, not per SUS-dependent person, and SIH geography is two utilization factors (50 % of the variance, ADR-0018); whether the missing exposure explains part of the first is untested (ADR-0018 ties it weakly to SUS beds). Completeness was tried only as an explanation of the 57 replicated SIM claims and explained none (`E:replicated-claims-read`), never as a term. `sus-dependent-1` covers 2021-22; the fits cover 2010-2023 | no |
| 2 | **Race groups are built as race-stratified blocks (ADR-0020), unmeasured.** (Original gap: race is not in the groups g.) No recorded-race confusion Σ C(k\|j) μ; groups are sex × age band only. pegasus_data has `race_confusion_infant`, `race_confusion_women` (ADR-0143, 0149) and the account's race dimension (account-3+). PegaSUS only measured the bridge (`E:race-bridge-infant`) | 4.1, 3.1 | The author asked for it by name; race is the one stratum whose raw rates invert the ordering (2022 infant mortality per 1,000, Preta: 5.5 raw, 15.8 bridged, 15.1 truth; STATUS race-bridge row). No lens or pair can see a racial disparity | no |
| 3 | **The low-rank place × time interaction ψωτ is not built.** Patterns across blocks (CP-APR) are a stand-in that never reached the survey | 4.2, 4.3, 7.4 | The only model term for a shared place-time factor; without it SIH relations are patched in Z (ADR-0018) and the dependency map is read net of factors by hand | yes (4.2) |
| 4 | **The horseshoe on tree levels is not built:** iid Gaussian per level, per block | 4.3 | Tree pooling is the model's main device for sparse categories; the shrinkage is not the one declared and pooling per chapter was never measured (`P` row 5.4) | yes (4.3) |
| 5 | **No top model, no two-level fit, no model-choice loop.** Blocks are fitted independently; nothing shares hyperpriors or offsets; held-out choice is a script run on chapter IX twice (graph, then profile) | 5.4 | The profile=category fit on IX scores 2.143 deviance per event held out against 2.218 for the default (profile=group): 3.4 % better, in `data/logs/heldout_ix.log` only, in no evaluation, with OQ-3 still open and the default unchanged | **no** |
| 6 | **Marks: one type, one field.** Only the log-normal mark and only SINASC `PESO`. SIH length of stay, cost, ICU days, death in hospital (declared `model: mark` in pegasus_data), SINASC gestational weeks, Apgar, prenatal visits: not fitted. No case-mix, no institution effect on a mark, no count / ordinal / beta-binomial mark | 4.4 | The P2 principle (events *and marks* are modelled) holds for one field. The lenses that would catch an institution's practice (stay, cost) have no input | no (only the missing positive, 10.1) |
| 7 | **The institution layer stops at a first stage:** facility steps and an opt-in supply term for SIH annual; no E_i pair, no crossed place × facility effects in the likelihood, no SIM `CODESTAB` lattice, SIH leads only for chapter X | 4.5, 7.5 | 34 % of chapter X signals were one hospital's coding (ADR-0014/0016); the 15 strongest left are sole-provider hospitals the rule cannot tell from the place. Surveys of the other SIH chapters are running detached in separate ledgers (`E:sih-full-readout`, not yet in the register); chapter XV fails calibration by a dispersion that does not fall with place size | yes (4.5) |
| 8 | **Replication has found almost nothing, and the reserve is unspent:** 333 of 7,496 SIM leads R1, none R2/R3, no SIM signal corroborated; SIH leads (25,732) all R0; the SIM.DO 2024 reserve held for the author | 8.3 | The pipeline can state no confirmed lead. Corroboration needs independent systems: SIA/APAC is declared in pegasus_data (ADR-0147) and never read | no (open question 7) |
| 9 | **The admission rule is now the power-curve rule (ADR-0022, 2026-10-05); θ0 below 1.2 and the map under invariant 8 are still to be read.** Admission: lens power for a rate ratio planted over a macro-region and window, outbreak, space-time and spatial cluster at 2.0 (they never reach 0.5 at 1.5), change point at 1.5; pairs by E_b power at ρ = 0.3; a field miscalibrated at B1 (map) or at its tier (E_w) is excluded from pair scans in code. Open: the θ0 calibration (queued), the map re-run, the survey counts below, trend and group power at the reference | 8.4, 11.4 | Every survey count in this document predates the rule and is measured with the former 1,000 events / 5 %; P5 and P7 lose the admission constant | yes (8.4, 11.4 rows) |
| 10 | **Coverage of the data is narrow and stale in places.** Fitted: SIM 19 chapters, SIH 20 chapters (production survey: X; the rest running detached), SINASC 3, SINAN DENG and LEPT. Never read: SIA (APAC AQ/AR/AN/ATD, PA), CIHA, CNES-ST events, 54 of 58 SINAN agravos, REGIC and the care-flow graph, the climate field in the gateway (read only by `data/p2` scripts), the SIH-SIM link. `SIM.DO` chapter XVII had no fit under the current exposure key (the `hybrid` default of `3e5c9fb`); refitted 2026-10-06 (φ 8.67, 147,531 deaths), `Session.fields("XVII")` loads 10 fields | 3.1, 12 | The "all the data it reads through pegasus_data" of §1 is four systems and two infections | no |

Also silent in §13 and ranked below these: the imports of `pegasus_data` outside `gateway` (config, corroborate, facility, fields; invariant 1); no survey-per-data-update trigger (§9.3); no `Session.compare`/`subset_scan`/`cohort`/`records`; the `RECORDING` flag is not served; the population-scaled iid part of BYM2; list effects and graph mixtures; scan across fields (§7.3); the observation lens.

---

## §1 Purpose and principles

| item | status | evidence | gap |
|---|---|---|---|
| fit one hierarchical model of "normal Brazil" from all the data read through pegasus_data | P | 107 stored fits, 45 distinct full-period (see Data coverage) | four systems; no SIA, CIHA, CNES events, most SINAN; no completeness, race |
| read leads from it (7.1-7.3 departures, 7.4 structure, 7.5-7.6 relations) | BM | `E:harness-gate`, `E:lens-positives`, `E:dependency-map` | 7.3 and the 7.4 structure are not read (see §7) |
| serve to people and agents (§9) | P | `E:mcp-tools`, ADR-0008 | built and paused by the author; no UI; no agent runtime (OQ-4) |
| phase 4 prospective surveillance | NB | ADR-0004, `E:surveillance-lags` | feasibility only |
| P1 expectation first | BM | `E:harness-gate`: false leads on NB surrogates ≤ q | none |
| P2 events and marks modelled, not column correlations | P | counts: all blocks; mark: PESO only | marks (see 4.4) |
| P3 every cell carries its information | BM | w in `surprise.py`, pair weights `E:pairs-gate` | none |
| P4 estimands declared | P | E_b, E_b\|Z, E_w ledgered apart; two trend references | E_i and across-system estimands not built (7.5) |
| P5 test against a minimum relevant effect | BM | ADR-0005 (δ_E), `E:harness-gate` (θ0), `E:lens-positives` | θ0 = 1.2 provisional for three lenses; group disparity not calibratable |
| P6 structure priors on levels, never on relations | BU | no relation prior exists in the code | no check beyond reading the code |
| P7 every strength learned or measured | P | τ's by Fellner-Schall; δ by negatives | KS .03, `FAC_K` 3, `FAC_SHARE` 70 %, `NEW_CATEGORY_ALARM` 5, θ0 1.2 remain set constants |
| P8 observed stays observed; modelled typed with uncertainty | P | `E:exposure` (accounts 2-6 carry σ), ADR-0010 | default is POPSVS (no uncertainty); κ, race, SUS-dependent not read |
| P9 nothing trusted before the harness | P | `E:harness-gate`: outbreak, space-time, E_b pass | change point has a positive at BP only; trend (neighbours), group disparity fail; marks, E_w, E_i without positives; SIH survey leads exist |
| P10 no dense object larger than the population tensor | BM | `E:fit-throughput`, `E:survey-throughput` | none |

## §2 Repositories and boundary

| item | status | evidence | gap |
|---|---|---|---|
| rule 1: every input through `gateway`, the only importer | BM | `gateway.py` is the only module importing `pegasus_data` (checked by `grep`); `config.py`, `corroborate.py`, `facility.py`, `fields.py` reach it through `gateway.package_version`, `package_dir`, `nothing_published`, `roles`, `event_type`, `raw_event_counts`, `raw_field` | fixed 2026-10-05 (was four direct importers) |
| rule 2: meaning and data belong in pegasus_data, requested by handoff | BU | `docs/handoffs/`, `data/handoffs/` | enforced by practice only |
| rule 3: never write into pegasus_data's home | BU | `config.population_root` reads only | none observed |
| pegasus_view presents leads later | NB | | no export of leads to the frontend |

## §3 Objects

| item | status | evidence | gap |
|---|---|---|---|
| role (entity.property, kind, model role) | P | strata, institution, when read by `gateway`, `facility` | the `mark` role is not read: `PESO` is named by the caller (`source="mark"`), SIH and 19 other SINASC marks are never listed |
| event type | BM | SIM.DO, SIH-RD, SINASC-DN, SINAN-DENG/LEPT/CHIK/ZIKA | SIA, CIHA, CNES events unread |
| structure: tree | BM | ICD10 through `code_structure` | single vintage; no validity windows or crosswalks |
| structure: list | P | `code_list_counts` (SINASC CODANOMAL) | no membership lists in the model (see 4.2) |
| structure: SIGTAP (SIH `PROC_REA`) | NB | | the procedure classifier of SIH is unread |
| structure: ordinal, cyclic | BM | `structures.random_walk` | none |
| graph | P | contiguity (border length), contiguity01, distanceH, knnK in `graphs.py` | care-flow, REGIC, health-region graphs and mixtures unused |
| population: POPSVS and accounts | BM | `E:exposure`, `E:census-coverage`, ADR-0010 | POPSVS default; the account loses to it except at age 0 (`hybrid`) |
| population: SUS-dependent variant | BU | `gateway.sus_share` (`sus-dependent-2`, 2021-23) | unmeasured, see 4.1 row |
| population: completeness by system, place, year | P | `gateway.completeness` (`system-completeness-2`, UF × year) | read as a modifier, opt-in; no municipal completeness exists |
| aggregates: sparse counts, mark accumulators | P | `gateway.event_counts`, `mark_moments` (own DuckDB SQL) | pegasus_data's `logmoments` aggregate not used |
| records and linked persons | P | `scans/cohort.py`; links used in `data/cohort_infant.py`, `data/agent_race/` | no API: `cohort()` and `records()` of §9.3 absent |
| lattice cell (u, t, g) | BM | `monolith.BlockData` | none |
| institution cell (f, t) with catchment exposure | P | `facility.institution_lattice`, `E:institutions` | SIH annual only |
| field (id, kind, law, exposure, signature, provenance) | P | `fields.Field` | only counts are registry fields; no exposure, provenance members; mark fields live outside it |
| block, monolith (versioned), tier, surprise | BM | `store`, `surprise.py` | none |
| scan, test, hypothesis; ledger entry | BM | `control.Ledger`: 29,313 tests registered before running | 73 registered tests have no result |
| lead | P | `leads.py`; 33,228 leads | only `residual` and `subset` kinds exist in the register (7 kinds declared) |

## §4 The monolith: model

| item | status | evidence | gap |
|---|---|---|---|
| 4.1 NegBin with block dispersion φ_b | BM | `E:chapter-ix-first-fit` (φ 5.98), ADR-0006 | none |
| 4.1 κ_{s,u,t} completeness of the system | P | `gateway.completeness`, `popsvs+kappa` (ADR-0020); `E:exposure-41` refit-free: IX NLL -0.12 %, residual slope 2.3 | opt-in; refits `popsvs+kappa` queued; SIH, SINAN have none | yes (4.1) |
| 4.1 N^(v): all residents | BM | `E:exposure` | none |
| 4.1 N^(v): SUS-dependent for SIH, SIA | BU | `gateway.sus_share`, `popsvs+sus` (ADR-0020) | 2021-23 only (earlier: frozen share with measured σ); SIH IX fit queued; ANS TabNet 2008-2020 needed in pegasus_data | yes (4.1) |
| 4.1 exposure variance of N | BM | `Monolith.exposure_variance`; ADR-0010 (double counts φ, off by default) | §13 row open |
| 4.1 race in groups, μ^rec = Σ_j C(k\|j) μ_j | BU | `race=` blocks, `+confusion`, `declared_ratios` (ADR-0020) | race-stratified, not an axis of G; fits and the ratio check against the linked truth not run | yes (4.1) |
| 4.2 θ_e along the tree path | P | `th_grp`, `th_cat` | two levels (ICD block, category); no deeper path |
| 4.2 list terms θ_L | NB | | not in §13 |
| 4.2 g_e(u) carried to ℓ_g | P | `s_all, v_all, s_grp, v_grp, v_cat` | §13 row 4.2 (v_cat added) |
| 4.2 h_e(t) | P | `h_all`, `h_grp` | history to the block level only |
| 4.2 profile node p(e), f_p(a,s) | P | `f_all`, `f_grp`; OQ-3 open | profile=category held out 2.143 against 2.218 per event (IX), unrecorded (gap 5) |
| 4.2 low-rank interaction Σψωτ | NB | none in `monolith.py` | §13 row 4.2/5.4 |
| 4.2 context not in the default predictor | BM | `E:dependency-map`, `E:cnes-supply-pairs` use context only in Z | none |
| 4.3 tree: horseshoe, one σ per level per top branch | NB | iid Gaussian per level | §13 row 4.3 |
| 4.3 list prior | NB | | not in §13 |
| 4.3 ordinal RW2/RW1, sum-to-zero | BM | `E:chapter-ix-first-fit` | none |
| 4.3 cyclic RW2 | BM | `E:dengue-monthly` (B2s KS 0.011) | none |
| 4.3 graph: BYM2, learned ρ | P | BYM, ρ from the two τ's (`spatial_share` in each manifest) | §13 row 4.3 |
| 4.3 graph mixture, graph and ρ reported per field | P | one graph per block; held out on IX: kNN6 2.21759, contiguity 2.21785 (`E:sinasc-lenses-optimiser`) | mixture NB; ρ per block not per field; choice measured on one chapter |
| 4.3 identifiability: sum-to-zero, centred siblings | BM | `monolith._centre` | interaction orthogonalisation moot (no interaction) |
| 4.3 unequal places: border-length weights, 1 km corner floor | BM | `graphs.py` | none |
| 4.3 unequal places: population-scaled iid precision | NB | `structures.iid` is unweighted | not in §13 |
| 4.4 positive continuous mark, log-normal on log-moments | BM | `MarkModel`, `E:harness-gate` (PESO, δ 1.5 %) | one field only |
| 4.4 count-valued, bounded-score, binary-share marks | NB | | not in §13 |
| 4.4 marks of SIH (stay, cost, ICU days, death in hospital) | NB | pegasus_data declares them (`model: mark`) | gap 6 |
| 4.4 marks of SINASC other than PESO | NB | 19 further SINASC marks declared | |
| 4.4 case-mix and institution effect on the location | NB | | not in §13 |
| 4.5 supply term (opt-in) | BM | `E:institutions` (11 % of the facility class, 6.5 % of signals) | annual only; sole providers stay unreadable |
| 4.5 institution lattice, facility steps | BM | `E:institutions` (1,744 steps in 5,666 facilities; null 0.0002) | SIH annual; SIM `CODESTAB` has the cube, no lattice |
| 4.5 facility effect inside the likelihood, crossed effects | NB | | §13 row 4.5 |

## §5 Estimation and computation

| item | status | evidence | gap |
|---|---|---|---|
| 5.1 factorised penalised Poisson QL, cost O(nnz + nodes·UTG + E·UT·R) | BM | `E:fit-throughput`, `E:chapter-ix-first-fit` | R = 0 (no interaction) |
| 5.2 dispersion by exact ML with μ fixed | BM | `E:chapter-ix-first-fit` | none |
| 5.2 place-year component for miscalibrated fields | BM | `E:dispersion-by-region`, ADR-0006 | none |
| 5.2 block φ one value per block | BM | ADR-0006 (region φ gains 0.009 nats on dengue only) | none |
| 5.2 dispersion that depends on place size | NB | `E:sih-full-readout` §2: SIH chapter XV z sd 1.16 (small places) to 0.73 (large); B1 KS .067 | one φ per block over-states large places; the readout points to §13, which has no such row |
| 5.3 truncated Newton-CG, Fellner-Schall | BM | `E:sinasc-lenses-optimiser`, `E:fit-throughput` | §13: Poisson-Fisher diagonal, not the full Hessian |
| 5.3 warm starts "on every data update" | P | `Monolith.warm_start` (`E:fit-throughput`) | no update trigger (§9.3) |
| 5.3 Laplace by perturbation draws | BM | `E:laplace-uncertainty` | off by default; OQ-2 |
| 5.3 check against exact MCMC or INLA | NB | OQ-2 "measuring" | §13 row 5.3 |
| 5.3 posterior predictive moment matching | BM | `E:laplace-uncertainty`, `E:bp-level` | none |
| 5.4 top model of all chapters with shared terms | NB | no code | **not in §13** (gap 5) |
| 5.4 block models in parallel, top-level offset | P | `scripts/fit_blocks.py`, detached jobs | no shared offset or hyperpriors |
| 5.4 model choice by held-out deviance: rank, graph, pooling | P | `monolith.heldout`, `scripts/measure_heldout.py`; IX graph in `E:sinasc-lenses-optimiser` | rank n/a; pooling per chapter never measured; no loop selects anything |
| 5.5 stack, GPU, numba | BM | ADR-0003, `E:fit-throughput` | none |
| 5.5 numerics: seeded draws | BM | `surprise.randomised_pit` | the fit is float64 throughout (document says float32 on GPU) |
| 5.5 memory, survey threads | BM | `E:survey-throughput` | none |
| 5.5 budgets: all blocks of four systems under an hour | P | cold SIM XVI 10 years 932 s; SIH X monthly 2,488 s | no all-blocks timing |

## §6 Tiers, calibration, surprise

| item | status | evidence | gap |
|---|---|---|---|
| B0 national terms, re-levelled to each year's total | BM | `E:chapter-ix-first-fit`, `surprise.py` re-level | none |
| B1 | BM | `E:dispersion-by-region` (30 of 33 calibrated) | dengue Southeast KS .081 (OQ-6) |
| B2 place intercept and slope, exact 2×2 Newton | BM | `E:chapter-ix-first-fit` | none |
| B2s season | BM | `E:dengue-monthly`, `E:sih-readout` (Sul July peak) | monthly blocks: SIH X, SINAN DENG/LEPT only |
| BP prospective, mixture predictive | BM | ADR-0009, `E:bp-level` | worst-region KS still above .05 (OQ-6) |
| BPA alarm baseline | BM | ADR-0012, `E:bp-baseline-history` | false-alarm rate is phase 4 |
| tiers computed from one fit | BM | `surprise.Expectations` | none |
| interaction never part of a tier | BU | n/a (no interaction) | moot until built |
| surveillance lenses read BP | BM | `E:lens-positives` (COVID) | |
| unseen category has no expectation | BM | ADR-0011 | |
| 6.2 randomised PIT, KS ≤ .03 / .05 | BM | `E:dispersion-by-region` | none |
| 6.2 φ_extra hierarchy (field, macro-region, state) | BM | ADR-0006 | none |
| 6.2 flagged field excluded from pairs and maps | NB | `CALIBRATION` flag exists in `surprise.py` | `maps`, `pairs`, `map_inputs` never read it (invariant 8) |
| 6.3 z, w, zero-cell closed form | BM | `surprise.py` | none |
| 6.3 flags: denominator, calibration, small support | P | `DENOMINATOR`, `CALIBRATION`, `NO_INFORMATION`, `NEW_CATEGORY` | `RECORDING` ("not yet served"); no small-support flag |
| 6.3 virtual cube, cached for scanned fields | BM | `Expectations.surprise(cache=)` | none |

## §7 Scans

| item | status | evidence | gap |
|---|---|---|---|
| 7.1 spatial cluster (B0) | P | `E:harness-gate` (84/250 false at θ0 1.2; θ0 1.5 pooled 0.04), `E:positive-chagas-schistosomiasis` | fails the family rule (2.0 would lose Chagas); outside the default survey; 6 ledger tests |
| 7.1 outbreak | BM | `E:harness-gate`, `E:positive-leptospirosis-rs`, `E:dengue-monthly` | |
| 7.1 change point | BM | `E:lens-positives` (COVID at BP, recall 1.00) | positive recovered at BP only; São Paulo 2018, Roraima births not recovered |
| 7.1 space-time cluster | BM | `E:harness-gate`, `E:sinasc-lenses-optimiser` (microcephaly) | |
| 7.1 group disparity | P | `E:lens-positives`: weighted recall 0.048 and 0.003, spatial negatives reject sd < 1.0 | fails its gate; runs only `--ungated`; 6,991 leads exist from earlier runs |
| 7.1 trend divergence: national course at region and state | BM | `E:lens-positives` (recall 0.66, Jaccard 0.77) | |
| 7.1 trend divergence: neighbours; national at municipality | BM | `E:lens-positives` (not recovered; time-shift negatives 5/30) | not run by default; 3,355 SIM neighbour leads have no spatial test (OQ-7c) |
| 7.1 observation lens on recording-practice fields | NB | `scans/lenses.py` docstring only | 0 `observation` leads; no ill-defined-share or coding-practice field has been scanned |
| 7.1 scales and per-scale BH at q/(number of scales) | BM | `scans/scales.py`, `E:lens-positives` | |
| 7.1 SURVEY_PLAN and `--ungated` | BM | `tools.SURVEY_PLAN` | `spatial_cluster` is in the plan as passing but not in the default `lens_names` |
| 7.2 expectation-based score, marks Gaussian, LTSS | BM | `scans/subset.py`, `E:harness-gate` | |
| 7.2 free dimensions, alternation | BM | `Scanner._alternate` | groups never enter a scan as a dimension (§13) |
| 7.2 null by NB replicates with Gumbel tail; recursion | BM | `subset.null`, `subset.scan` | |
| 7.3 subset scan across fields (field as a dimension) | NB | | not in §13 |
| 7.4 interaction-factor patterns (ψ, ω, τ) | NB | no interaction | see 4.2 |
| 7.4 non-negative tensor factorisation across blocks | P | `scans/patterns.py`; once in `E:utilization` (agrees with the two factors) | not in the survey; no `pattern` or `structural` lead in the register; stability built, not run |
| 7.5 E_b between places | BM | `E:pairs-gate`, `E:eb-census-positives`, ADR-0005 | smooth-field power low |
| 7.5 E_b\|Z | BM | `E:pairs-gate`, `E:cnes-supply-pairs` | |
| 7.5 E_w lag ℓ | P | `E:positive-arbovirus-microcephaly`: ρ 0.12, none admitted; cold → respiratory ρ −0.04 < δ 0.1 | no E_w positive recovered; 914 tests |
| 7.5 E_i between institutions | NB | facility steps only (`E:institutions`) | no pair on the institution lattice |
| 7.5 across systems (E_w on the log ratio) | NB | | not in §13 |
| 7.5 minimum-effect test, Gram computation, √(w_X w_Y) weights | BM | `E:pairs-gate` | |
| 7.5 Dutilleul modified t | SS | ADR-0005 (size 0.076, liberal): MSR on the normalised graph | |
| 7.5 rank (Spearman) versions | BU | `statistics(rank=True)` | never reported |
| 7.5 HSIC with CKA floor | NB | | not in §13 |
| 7.6 pair-test dependency map, two layers, TreeBH | BM | `E:dependency-map`, ADR-0013 | one map, 65 fields, SIM/SIH/SINASC 2015-19 + contexts; no SIA or APAC field |
| 7.6 utilization factors in Z | BM | `E:utilization`, ADR-0018 | model-side fix is gap 3 |
| 7.6 sparse + low-rank graphical model, StARS | NB | ADR-0013 | §13 row 7.6 |
| 7.7 explaining away, absorbed share | BM | `E:cnes-supply-pairs` (15 leads, 108 tests) | used once |
| 7.7 decomposition (Shapley, four components) | BU | `Session.decompose`, `explain.decompose` | no evaluation entry, no run on a lead |
| 7.7 triage classes | BM | `E:lead-triage` (4,045 system / 2,015 signal / 746 / 690) | "signal" is unexplained, not confirmed |
| 7.7 facility class | BM | ADR-0014, `E:lead-triage` | |
| 7.8 cohort scans (Poisson, δ_RR 1.2, BH) | BU | `scans/cohort.py`; 90 ledger tests on the SINASC-2021 infant cohort | no evaluation entry; δ_RR uncalibrated |

## §8 Error control, replication, admission

| item | status | evidence | gap |
|---|---|---|---|
| 8.1 families | BM | `control.Ledger.family` | |
| 8.2 BH, BY | BM | `control.bh` | |
| 8.2 Benjamini-Bogomolov across families | BM | `tools.Session.survey` | |
| 8.2 TreeBH | BM | `maps.dependency_map` | Simes aggregation (§13) |
| 8.2 LOND | BU | `control.LOND`, `control.Reserve` | the stream has never run on a real claim |
| 8.2 agents: exploratory logged, claims through `confirm` | P | `mcp_server.confirm_claim` | MCP paused (ADR-0008); no agent runtime |
| 8.3 later years (`temporal`) | BM | `E:replication-independent-units` (size ≤ 0.014, power 0.9-1.0) | cannot see departures the fit absorbs (0.05-0.18) |
| 8.3 other places (`spatial`, ADR-0019) | BM | `E:artefact-aware-replication`, `E:replicated-claims-read` | clusters untested; trend (neighbours) leads have no spatial test |
| 8.3 another system (`corroborated`) | BM | `E:replication-independent-units` (scattered null 0.061) | no SIM signal corroborated; SIA/APAC would add a system |
| 8.3 evidence grades (tested, bound, consistent) | BM | `explain.GRADES`, ADR-0019 | |
| 8.3 event split for sizes | BM | `E:replication` | |
| 8.3 reserved period SIM.DO 2024 | BU | `control.RESERVED_PERIODS`, `ReservedPeriod` guard | never opened; three `confirm`-family rows are declarations, not spends |
| 8.3 tiers R0..R3 | BM | `E:replication-independent-units` (333 of 7,496 R1; 0 R2/R3) | SIH register untiered beyond R0 (25,732) |
| 8.4 admission rule and minimum effects | P | `fields.admission` (power curves, `admission_curves.json`), `lenses.py` θ0, `pairs.MIN_EFFECT` | section restored; power-curve admission applied (ADR-0022); θ0 1.2 provisional until the calibration below 1.2 is read |
| 8.5 mechanical overlap | BM | `fields.overlap`, `gateway.field_overlap`, `maps` | **section lost**; the 0.05 rule stated in 7.6 and 11.4 |

## §9 Leads, the ledger, use

| item | status | evidence | gap |
|---|---|---|---|
| 9.1 lead object, rank | BM | `leads.py`; `E:sim-survey-readout` | |
| 9.1 kinds: relation, pattern, cohort, observation, structural | NB | 33,228 leads are residual (30,332) and subset (2,896) | pairs live in `pegasus_home/maps`, not the register |
| 9.2 append-only ledger, written before execution | BM | 29,313 pending, 29,240 results | 73 without result |
| 9.3 survey per data update (refit, surprises, scans, lead update) | NB | `Session.survey` is run by hand | no trigger, no scheduler, no incremental lead update |
| API `leads`, `lead`, `fields`, `field`, `expected`, `surprise`, `scan`, `explain_away`, `confirm`, replication calls | BM | `tools.py`, `cli.py` | |
| API `compare`, `subset_scan` | NB | `dependency_map` and `scans.subset` are separate entry points | not a `Session` method |
| API `decompose` | BU | `Session.decompose` | |
| API `cohort`, `records` | NB | `scans/cohort.py` is script-driven | |
| tools over MCP | BM | `E:mcp-tools`, ADR-0008 | built and paused |
| agents (LLM loop) | NB | OQ-4 | |

## §10 Validation harness

| item | status | evidence | gap |
|---|---|---|---|
| 10.1 microcephaly and anomalies, space-time B2 | BM | `E:sinasc-lenses-optimiser` | |
| 10.1 arbovirus → microcephaly E_w | P | `E:positive-arbovirus-microcephaly` (Q02 25×; lag 6-7 on totals) | E_w at region grain not recovered |
| 10.1 COVID-19 excess deaths, BP | BM | `E:lens-positives` | |
| 10.1 dengue epidemics, BP | BM | `E:dengue-monthly`, `E:bp-baseline-history` | |
| 10.1 dengue seasonality, B2s | BM | `E:dengue-monthly` | |
| 10.1 leptospirosis RS 2024 | BM | `E:positive-leptospirosis-rs` (95.7 % of the excess) | Jaccard criterion fails as written |
| 10.1 Chagas, schistosomiasis, B0 | P | `E:positive-chagas-schistosomiasis` | Jaccard fails; the lens fails its family rule |
| 10.1 infant mortality ↔ income, sanitation | BM | `E:eb-census-positives`, `E:pairs-gate` (5 of 12 admitted) | low power on smooth fields |
| 10.1 diarrhoea admissions ↔ sewerage | P | `E:cnes-supply-pairs` (DIA ↔ no bathroom +0.208) | not the declared sewerage pair |
| 10.1 Roemer's law | BM | `E:cnes-supply-pairs` (recovered, ρ +0.264) | |
| 10.1 ESF coverage ↔ infant mortality | BM | `E:cnes-supply-pairs` (not recovered) | |
| 10.1 sanitation survives primary-care adjustment | BM | `E:cnes-supply-pairs` (2 of 3) | |
| 10.1 winter respiratory seasonality | BM | `E:sih-readout` (Jaccard 1.00 at B2s) | |
| 10.1 winter respiratory anomalous season, BP | NB | | no year declared, no run |
| 10.1 COVID-19 enters the record, change point BP | BM | `E:lens-positives` | |
| 10.1 homicide divergence across UF borders | BM | `E:lens-positives` (not recovered) | |
| 10.1 homicide from the national course | BM | `E:lens-positives` (recovered at region, state) | |
| 10.1 women's and young men's share of homicide | BM | `E:lens-positives` (fails the gate) | |
| 10.1 marks and E_w each recover a positive | NB | §13 row 10.1 | no citable mark shift; E_w weak |
| 10.2 negatives: Moran spectral randomisation, series shift | BM | ADR-0005, `E:harness-gate` | |
| 10.3 planted signals, power curves | BM | `E:harness-gate` | |
| 10.4 null surrogates, false-lead rate | BM | `E:harness-gate` (worst 2/350) | |
| 10.5 gate | P | `tools.gate_status`, the lead's `gate` field ("passed" on 11,817 leads) | applied as a flag, not a block |

## §11 Code

| item | status | evidence | gap |
|---|---|---|---|
| 11.1 every module exists; names enforced | BM | `scripts/check_docs.py` | |
| 11.1 dependency direction downward | P | | `fields`, `facility`, `corroborate`, `config` reach pegasus_data directly; `scans/subset_old.py` is untracked beside `subset.py` (in flight) |
| 11.2 Python first, Arrow at boundaries | BM | | `control`, `leads` read their own Parquet |
| 11.3 homes and artefact layout | BM | `pegasus_home/` | ten ledger and eleven register variants beside the production ones |
| 11.3 keys hash data versions; stale never served | P | §13 row 11.3 | key is the package version; the stale-key rule works (SIM XVII was not served) but leaves the block unservable until refit (XVII refitted 2026-10-06) |
| inv. 1 every input through gateway | BM | | the four direct importers now go through `gateway` (§2 rule 1) |
| inv. 2 no statistic without expectation and weight | BM | | |
| inv. 3 context never in a default tier | BM | | |
| inv. 4 taxonomic structure never in a relation prior | BU | | |
| inv. 5 every test in the ledger before it runs | BM | 29,313 pending rows | |
| inv. 6 nulls preserve dependence, no Monte-Carlo floor | P | | B0 spatial cluster and group disparity nulls fail (§13 row 8.4); corroboration floor fixed |
| inv. 7 tested against the minimum effect | BM | | |
| inv. 8 miscalibrated field never in a pair scan | NB | | not enforced (6.2) |
| inv. 9 overlap above 0.05 never tested | BM | `maps.testable` | |
| inv. 10 no array above the population tensor | BM | | |
| inv. 11 modelled input carries its model version | BM | `gateway.population_key` | |
| inv. 12 every draw seeded | BM | | |
| 11.5 verification by the harness on real data | BM | | |

## §12 Phases and gates

| item | status | evidence | gap |
|---|---|---|---|
| phase 0: harness, gateway, store, ledger | BM | `E:harness-gate` | |
| phase 1: fields, monolith, surprise, lenses, subset scans | BM | `E:chapter-ix-first-fit`, `E:lens-positives` | |
| phase 1 gate: first measurements, tree pooling and graph choice | P | graph on IX (kNN6 against contiguity) | tree pooling never measured |
| phase 1 gate: measured compute budgets | P | `E:fit-throughput`, `E:survey-throughput` | no all-blocks figure |
| phase 2: pairs, FDR across families, replication, explaining away | BM | `E:pairs-gate`, `E:replication-independent-units` | |
| phase 2: decomposition, cohort scans | BU | | no evaluation |
| phase 2: SINAN, sub-annual grain | BM | `E:dengue-monthly`, `E:positive-leptospirosis-rs` | DENG, LEPT only |
| phase 2 gate: calibrated δ and admission | P | ADR-0005, ADR-0022 | admission read from the power curves; θ0 below 1.2 not yet calibrated |
| phase 2 needs: care-flow graph | NB | pegasus_data ADR-0144 | `graphs.py` has no care-flow kind; `facility.py` rebuilds a kernel from SIH |
| phase 2 needs: linked cohorts, population account v1 | P | accounts 2-6 in `E:exposure` | linked cohorts through scripts only |
| phase 3: patterns across blocks | P | see 7.4 | |
| phase 3: dependency maps | BM | `E:dependency-map` | |
| phase 3: tools over MCP | BM | `E:mcp-tools` | paused |
| phase 3: institution lattice | P | ADR-0016 | first stage (4.5) |
| phase 3: agents | NB | OQ-4 | |
| phase 3 needs: race measurement | P | `E:race-bridge-infant` | measured, not modelled (gap 2) |
| phase 3 needs: new population sources, CNES fields | BM | `E:exposure`, `E:cnes-supply-pairs` | |
| phase 3 needs: APAC families | NB | pegasus_data ADR-0147 | never read |
| phase 4: weekly grain, nowcast, false-alarm alarms, syndromic scans | NB | ADR-0004, `E:surveillance-lags` | |
| phase 4 gate: benchmark against InfoDengue | NB | | |

## §13 Departures (all 17 rows open)

Each row is a recorded departure; none has closed. The departures **not** recorded there are the `no` and "not in §13" cells above.

| § | departure | status of the closing work |
|---|---|---|
| 4.3 | horseshoe → iid per level | NB |
| 4.3 | BYM2 → BYM | P (ρ reported) |
| 4.2 | geography carried to ℓ_g → ICAR+iid per group, iid per category | P |
| 4.2, 5.4 | low-rank interaction not built | NB |
| 5.2 | dispersion by place group → hierarchy φ_extra | BM (ADR-0006) |
| 5.3 | Laplace layer off by default | BM |
| 5.3 | Fellner-Schall block-diagonal, full-Hessian update outside the fit | P |
| 6.1 | B2s and BP at the monthly grain | BM |
| 10.1 | marks and E_w without a recovered positive | NB |
| 7.2 | groups not a free dimension | P |
| 8.2 | TreeBH with Simes aggregation | P |
| 11.3 | keys carry the package version | P |
| 3.1, 4.1 | default population has no uncertainty | P |
| 2.1 | gateway parses dates and DF residence codes | P (pegasus_data now derives them) |
| 8.4, 10.2 | θ0 1.5 for the spatial cluster; single-field negatives MSR of residuals | P |
| 7.6 | pairwise map, not a graphical model | P |
| 4.5 | facility term after the fit, not inside | P |

## Data coverage

**Fitted blocks.** `pegasus_home/monolith`: 107 manifests, **45 distinct full-period production fits** (2010-2023, contiguity, municipality grain, 5,570 places); the others are train windows, exposure and graph variants.

| system | event | blocks fitted | grain | years | notes |
|---|---|---|---|---|---|
| SIM.DO | death | 19 ICD chapters: I-XVIII, XX | annual × sex × 18 bands | 2010-2023 | XIX, XXI, XXII absent (SIM codes COVID as B34.2). Chapter XVII refitted under the `hybrid` exposure 2026-10-06 |
| SIH-RD | hospitalisation | 20 chapters: I-XIX, XXI | annual | 2010-2023 | X also monthly 2010-2023; XI monthly 2010-2016 only; XX absent |
| SINASC-DN | birth | all births; PESO (mark); XVII (`CODANOMAL` list) | annual | 2010-2023 | XVII also monthly 2010-2014 |
| SINAN-DENG | probable_case | one field | monthly | 2010-2023 | |
| SINAN-LEPT | case, notification | one field each | monthly | 2010-2023 | |

| use | datasets / products | how PegaSUS reads it |
|---|---|---|
| modelled | the four systems above | the monolith |
| context only (place effects, Z, explanations) | Census 2022 (SIDRA: sanitation, literacy, urban, income, race), GDP, ANS plan links, INEP enrolments, CNES December stocks (35 fields, 2008-2023; 6 used in the map), S2iD | `gateway.context_field`, `map_inputs`, `corroborate`, `facility` |
| independent evidence (replication tier 3) | S2iD, SINAN (CHIK, DENG), SIH | `corroborate.RULES` |
| population | POPSVS, `population-account-2` to `-6`, `hybrid` | `gateway.population` |
| linkage | SIM-SINASC infant links (race bridge, infant cohort) | `data/` scripts and `scans/cohort.py` |
| held by pegasus_data, never read | SIA-PA, SIA APAC (AQ, AR, AN, ATD), CIHA, CNES-ST events; SINAN other than DENG, LEPT, CHIK, ZIKA (54 of 58 aggregates); climate (INMET; read by `data/p2` scripts for E_w only); REGIC and care-flow graphs (`care_flows`, ADR-0144); SIH-SIM, deliveries-SIH, CIHA-SIM links; `system-completeness`; `sus-dependent`; `race_confusion_infant/women`; the SIDRA store (98 tables, 200 M rows) beyond Census 2022; SIGTAP procedures | |
| **systems asked about** | SIM yes; SINASC yes; SIH yes (annual, one survey chapter); SIA/APAC no; SINAN 4 of 58 families (DENG, LEPT fitted; CHIK, ZIKA as evidence); CNES as context; SIDRA as context; ANS as one context; INEP as one context; S2iD as evidence; population account yes (default POPSVS); race bridges measured only; completeness no; care flows no; linkage in scripts | |

## Scan coverage

**Admission rule** (the table below was counted under the former rule, at least 1,000 events and events in 5 % of the units; since ADR-0022 `fields.admission` reads the power curves, outbreak at 920, change point 11,300, space-time 6,700 and spatial cluster 1,200 events in the median region's locus, so these counts overstate the nodes the lenses now scan; recount with `scripts/measure_admission.py coverage`; descent only into admissible children). Nodes are the block's tree nodes down to the 3-character category.

Counted with `Session.fields(block)` on 2010-2023 on the audit day (`nodes` = chapter, ICD blocks and 3-character categories of the tree; XVII of SIM could not be loaded, see gap 10).

| system | blocks | tree nodes | admitted | in the production ledger | note |
|---|---|---|---|---|---|
| SIM.DO | 18 loadable of 19 | 1,921 | 690 (36 %) | 690 (100 %); XVII refitted 2026-10-06: 10 fields (36 under the earlier fit), not in the counts | VII admits 0 (340 deaths), VIII 3, XV 13, XII 14, V 19 of 90 nodes |
| SIH-RD | 20 | 1,919 | 1,529 (80 %) | 69 (chapter X 67, chapter I 2) | the remaining 1,460 are in the detached surveys (`ledger_base1/2/3`, `ledger_supply`) |
| SINASC-DN | 1 field (births); PESO; XVII by `CODANOMAL` | n/a | n/a | harness repeats only | no tree descent: the event type has no primary classifier |
| SINAN-DENG, SINAN-LEPT | one field each | n/a | n/a | 34 and 5 tests | |

The admission rule keeps 36 % of SIM nodes against 80 % of SIH nodes: the 3-character causes of death are rarer than those of admission, so the SIM survey sees the common causes and the rare ones (chapters VII, VIII, XII, XV) are outside every lens.

**Default survey** (`tools.SURVEY_PLAN`, `Session.survey`, `lens_names` default): four lens × tier × scale combinations run; the others need `--ungated`.

| lens | tier | scales | status in the default survey |
|---|---|---|---|
| outbreak | B2 | municipality | runs |
| change point | B2 | municipality | runs |
| space-time | B1 | municipality | runs |
| trend divergence, national course | B2 | region, state (BH at q/2) | runs |
| trend divergence, neighbours | B2 | municipality, region, state | ungated only |
| trend divergence, national | B2 | municipality | ungated only |
| group disparity | B0 | municipality, region, state | ungated only |
| spatial cluster | B0 | municipality | in the plan, outside `lens_names`: does not run |
| prospective (`prospective=t0`) | BPA outbreak; BP change point, space-time | municipality | runs on request; ledger shows 34 BP/BPA tests (dengue, leptospirosis) |

**Ledger** (`pegasus_home/ledger`): 58,553 rows = 29,313 registered tests (pending) + 29,240 results, 801 distinct fields.

| family | tests | fields | note |
|---|---|---|---|
| outbreak | 1,702 | | |
| space-time | 1,632 | | |
| group disparity | 1,482 | | ungated |
| trend divergence | 1,444 | | |
| change point | 1,090 | | |
| spatial cluster | 6 | | |
| E_b (map marginal and others) | 10,655 | | one map, 2015-19, 65 fields |
| E_b\|Z (map conditional) | 10,295 | | |
| E_w | 914 | | dengue, cold (climate) → respiratory, microcephaly |
| cohort | 90 | | SINASC 2021 infant deaths and sensitivity |
| declared hypotheses | 3 | | Rio Doce, Brumadinho, Y35 |
| **by system, lens tests** | SIM 5,588 · SIH-RD 644 · SINASC 1,085 · SINAN-DENG 34 · SINAN-LEPT 5 | SIM 728 · SIH 69 · others 4 | SIH: chapter X (67 fields) and 2 in chapter I only; the other SIH chapters run in `ledger_base1/2/3`, `ledger_supply` |

Other ledgers (separate runs, not in the 58,553): side-A survey 5,264 SIM tests, train-≤2019 1,124 SIM, SIH base survey 740 (ledger_base1, base2; running), institution variants 1,340 (inst, inst2, inst_base, two volume/utilisation) and supply 372; 8,840 tests in all.

**Register** (`pegasus_home/leads`): 33,228 distinct leads in 102,049 versioned rows. SIM 7,496 (17 chapters; most in XVIII 2,599, XX 1,291, IX 897, X 818, I 592) from 467 fields; SIH-RD 25,732, all chapter X, from 67 fields. By lens: SIH trend 18,575, group disparity 5,928, outbreak 615, space-time 607, change point 7; SIM trend 3,355, space-time 2,289, group disparity 1,063, outbreak 761, change point 28. Replication: R0 32,895, R1 333, none R2/R3 in the register. Triage: signal 11,472, system 11,000, noise 3,657, substitution 2,778, unclassified 4,321. Gate: 11,817 leads `passed`, none `failed`. **Corrected 2026-10-06:** 14,813 of these leads were `explained` (system 11,000, substitution 2,778, signal 890, noise 145) by a triage that predates graded explanations; none carried a tested verdict, so under ADR-0019 (only a tested explanation removes a lead) they were wrongly out of the funnel. Reopened in the register with the old verdict kept (`triage.superseded`); the graded re-triage of SIM.DO and SIH-RD is running.

**What the survey does not reach:** SIH chapters other than X (fitted; B1 calibrates 17 of 19, B2 5 of 19, `E:sih-full-readout`; their survey runs detached in `ledger_base1/2/3` and is in no production register yet); SIM chapter VII (no admissible node), VIII (3 nodes); SINASC beyond the birth total (PESO, XVII): ledger only for harness runs; SINAN DENG and LEPT: outbreak and space-time on one field each; any field of the 4-character level (codes are cut to three); marks other than PESO; observation fields; pair scans between fields of the survey (the map uses chapters, not the 726 SIM nodes).
