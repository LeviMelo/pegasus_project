# Handoff — LDO residual-scan near-clique artifact (for GPT-5.6 "Sol")

**From:** Claude (Opus 4.8), 2026-07-11. **To:** GPT-5.6.
**Companion doc:** [`modules/ldo.md`](modules/ldo.md) — the faithful code+math map of the whole LDO module (read it first; this handoff assumes it).

> **RESOLUTION 2026-07-12 (commit `deddf68`).** GPT-5.6/Codex acted on this handoff; I then assessed +
> integrated the result. **Verdict:** the artifact was **spatial nuisance** — the residual conditions
> across variables (`Ω`) but not on the panel's municipality/time structure, so every co-located pair
> beat the null (confirmed per-mechanism on a controlled synthetic: confounder pair p **0.001→0.76**
> under the fix). Codex's fixes — two-way FE nuisance projection, spatial-block **cross-fit of Ω**,
> refuse-don't-average, normalized-HSIC effect size, corrected low-rank memory model — are sound and
> committed. **One validated caveat:** the municipality FE also **erases cross-sectional determinants**
> (p **0.001→0.87**), so the residual scan now tests a *within-municipality temporal* estimand;
> cross-sectional signal must come from the linear backbone. A cross-sectional-preserving low-rank
> confounder removal (keeps cross-sectional at k=2 in synthetics) is proposed but **not adopted**
> (k-sensitive; null-calibration unverified; risk-averse — FE can only remove, never manufacture edges).
> The rest of this handoff is the original open-question framing, retained for the record.

> **RESOLUTION — completed 2026-07-12 (the artifact is CLOSED).** `deddf68` (above) removed the *spatial*
> nuisance; four further fixes removed the remaining mechanical/degenerate contributions and the clique
> collapsed end-to-end on real data:
> - `1369193` — **normalized-HSIC (CKA) effect-size floor.** Residual edges gate at `stat ≥ floor`
>   (default 0.05); a statistically-significant but negligible-effect pair no longer certifies.
> - `5fbb582` — **degenerate complete-case sampling fix.** The scan maximized variable count, collapsing
>   `n` until singleton FE groups demeaned to a point-mass residual → CKA saturated to 1.0 for *every*
>   pair (the true source of the flat clique). Replaced with a coverage-ordered **cliff rule** (stop at
>   the first variable that collapses `n` >3×) + a degeneracy guard (`ResidualScanUnderpowered` when the
>   median unique-fraction < 0.05).
> - `56d106b` + shared-numerator guard — **mechanical-overlap typing.** Edges between a variable and its
>   own ICD-nested / shared-numerator counterpart (a count and its own rate) are demoted, not certified.
> - `7b1a943` — **population denominator/exposure seeds excluded** from the analytical outcome set (§IV):
>   they are exposures, not determinants, and were driving co-scaling CKA≈1.0.
>
> **Validated on the real SP slice (prior session):** production clique **1711 → 825 → 78–139 real edges**;
> a 43-variable cross-domain slice → 62 edges / 22 certified, all **textbook epidemiology** (infant-mortality
> cluster, birth-outcome web, socioeconomic↔fatality), 31 LiNGAM-oriented, 7 mechanical correctly demoted.
> Cross-scope (perinatal / arbovirus / mortality) all non-degenerate with distributed CKA. Full design record:
> [`LDO_DECONFOUNDING_DESIGN.md`](LDO_DECONFOUNDING_DESIGN.md) §7a–§7f.
>
> **CAVEAT — the national deliverable is stale.** `data/runs/national_c25_full_ad2/Hypotheses.parquet`
> (built 07-11 12:14) **predates every fix above** — its 9,180 `nonlinear_residual` edges (all "selected",
> **0 FDR-significant**) are the pre-fix clique. Refreshing the national output requires re-running the
> investigate/LDO stage on the existing national panel at current HEAD (a targeted LDO rerun, not a full
> recompile) — intentionally not launched autonomously (lengthy full-scale runs are deprioritized).

**What I need from you:** an independent review of the situation and — critically — of the **mathematics**. I reached a plausible diagnosis and even shipped a fix that turned out to be the wrong layer (details below). I have deliberately **stopped** rather than push a second guess. Please assess the math yourself, decide whether my reasoning holds, and identify which layer actually owns the artifact. Treat my conclusions as hypotheses, not findings.

---

## 1. Context in one paragraph

PegaSUS runs a national epidemiological inference pipeline (Brazil, DATASUS + IBGE/SIDRA, 2000–2024). The **LDO** (Latent Dependency Operator, `src/pegasus/ldo/`) is the final inference stage: it takes a `(year, municipality) × variable` panel and fits a Gaussian-graphical model — a **sparse + low-rank precision** `Ω = S − L` (LVGLASSO/ADMM) for the *linear* backbone, then a **residual HSIC scan** for *nonlinear* residual edges — and emits typed `LinkRecord`s ("determinants") into `Hypotheses.parquet`. The driving task was the national pancreatic-cancer (ICD **C25**) study. For over a day the LDO stage never completed; my job was to make it run end-to-end and then trust (or not) its output.

## 2. What was fixed to make it run (engineering — settled, committed)

Three genuine defects blocked completion; all fixed, validated, committed:

- **`f26f525` — residual-scan was memory-bandwidth-bound.** The exact-mode HSIC permutation null re-materialized a randomly-gathered `ky[np.ix_(π,π)]` n×n kernel copy per permutation → O(P·n²) random-access traffic, a 40–60 min grind (the "cores busy but idle, RAM churning, disk dead" signature). Fixed by factoring the numerically-low-rank centered RBF kernel (`k = AAᵀ`, rank ≈16 even at n=3000) and running the null as `‖Aₓᵀ A_y[π]‖²_F` — an n×r contiguous row-permute + batched matmul. **Bit-exact** (stat Δ 6e-13, p-values identical), 16–30× faster. See `ldo/hsic.py` `_low_rank_factor`, `_batched_perm_null`, `hsic_pair_stat_and_null`.
- **`953dd99` — output crash.** `write_hypotheses` → `pl.DataFrame(rows)` inferred a `float|None` column as `Null` from the first 100 all-None records, then couldn't append a later float. Fixed with an explicit polars schema from the `LinkRecord` dataclass; also JSON-encoded `causal_assumptions` (was omitted). `ldo/output.py`.
- **`a078106` — pair cap.** The residual scan's `_MAX_PAIRS` was 15k (a contention-era throttle); raised to 150k so national coverage (~61k pairs) is complete. `ldo/residual_scan.py:348`.
- (`a1356fc` — cosmetic: quieted a benign divide warning in `covariance.py:288`.)

**Result:** the national LDO now completes end-to-end in ~26 min, peak RSS 18.5 GB (well under guards — memory was never the true blocker), full residual coverage (0 pairs capped), and writes `data/runs/national_c25_full_ad2/Hypotheses.parquet` (7,483 edges) + `Coverage.json`.

## 3. The actual problem — the output is largely an artifact

The completed run reports **links=7483, selected=7372**. But characterizing `Hypotheses.parquet` (no re-fit needed) shows the discoveries do not hold up:

| edge_type | count |
|---|---|
| `nonlinear_residual` | **7,197** |
| `contemporaneous` (linear) | 279 |
| `lagged_directed` | 7 |
| `mechanical_overlap` | **0** |

Verified facts about the 7,197 nonlinear edges:

- **They form a near-clique.** Only **132 of 348** variables participate, at **median degree ≈118 of a possible 131** — ≈83% of all pairs among those 132 nodes. Not hub-dominated (top-10 nodes carry only ~8.6% of endpoints); a dense mutual-dependence blob.
- **The effect sizes are tiny.** HSIC statistic median **0.006–0.009**, 90% below 0.05, vs linear-edge `|weight|` median **0.166**, max 0.84. Yet they pass BY-FDR, so each observed HSIC **exceeds all 200 within-block permutations** — i.e. it is *systematic* (real shared structure), just negligible in magnitude.
- **113 of the 132 clique nodes are DATASUS disease-carrier variables** (SIM/SIH/SINASC × disease concepts, content-hashed 64-char IDs), +15 SIDRA context, +4 population_tensor.
- **The `mechanical_overlap` guard emitted 0 edges** — it is inert on this run. That guard (`orchestrator.py` `type_mechanical_overlap`, `§5.3`) keys on ICD-**code** overlap via `variable_meta` code-sets; it does not fire on shared *source event-volume*.

**Interpretation (mine, unverified in the last step):** this looks like one shared structure among same-source disease-**count** variables — they co-move because bigger municipalities have more of everything — inflated by multiplicity into ~7,200 pairwise "discoveries." A §IV correlated-multiplicity + effect-size problem, most likely living in the **disease-variable / denominator** layer, not the residual precision. But I have not decisively measured the residual to confirm this.

## 4. My mistake (please scrutinize it)

I initially diagnosed the clique as a **low-rank global-factor leak**: the residual scan forms the conditional residual `e_j = (P Z)_j / P_jj`, and I found it was fed the **sparse** precision `S` (`lags.py` `lag0_precision`, built from `fit.S`) instead of the **full** `Ω = S − L` that its own docstring specifies — so the low-rank `L` (which owns dense/global structure) never leaves the residual. I built a synthetic with a planted rank-1 global factor, confirmed conditioning on `Ω` strips it (block residual off-diag corr **0.72 → 0.04**, genuine sparse edge preserved 0.628 → 0.629), shipped the fix (**`bcdd0dd`**: added `lag0_precision_full = Ω`, residual scan now uses it; 21 LDO tests + a new regression test green), and re-ran national.

**It barely moved the clique** (7,197 → 7,290 nonlinear edges; same 132 vars, same tiny HSIC). So my diagnosis was **wrong-layer** (§I.c): the synthetic reproduced the *symptom* (a clique) via a mechanism (low-rank leak) that is **not** the national cause. Note the LDO *already* projects out the common temporal trend before fitting (`orchestrator.py:150`, `common_trend`), so a single low-rank factor was never the story. The `Ω` fix is still a legitimate bug fix (the residual *should* condition on the full precision per its spec — I kept it), but it does **not** explain this artifact. **Lesson I'm carrying:** a synthetic that reproduces the symptom can validate the wrong mechanism; the real quantity to measure is the *national* residual, not a proxy.

## 5. Candidate mechanisms — refined by the code-mapping (companion doc §8/§10)

After I stopped, I mapped the whole LDO faithfully ([`modules/ldo.md`](modules/ldo.md)). Mapping the residual scan (§8) sharpened my three original guesses (counts-vs-rates / mechanical-overlap / FDR) into a more precise, code-anchored set of **convergent mechanisms inside the residual-HSIC path itself**. These are for your assessment — **I did not act on them.**

- **A. No effect-size floor** (`residual_scan.py:402`): an edge is included on `q ≤ 0.1` alone; `weight` is the raw HSIC. At the tight permutation null of large effective-n, an arbitrarily tiny HSIC is "significant" — directly explaining the observed median HSIC ≈ 0.006. Significance ≠ effect size.
- **B. Ecological averaging is the LIVE national grain** (`_coarsen_residuals`, `residual_scan.py:199`): the `0.40·total-RAM` memory guard forces the national scan onto **(spatial-block × year) GROUP-AVERAGED** residuals (~hundreds of municipalities per group). Aggregation inflates cross-variable dependence (MAUP / ecological correlation); the HSIC then tests aggregate co-movement, not cell-level dependence — a near-clique among co-trending aggregates is the expected result.
- **C. The executed null does not preserve residual temporal autocorrelation.** `Ω=S−L` conditions *contemporaneously* (lag-0), so residuals retain within-block temporal structure; but the executed null is a free within-block **YEAR shuffle** (`restricted_intra_uf_spatial_swap`, `nulls.py:161`) — **NOT** the autocorrelation-preserving `spatial_block_cyclic_time_shift` the null registry *advertises* for annual panels (`residual_scan.py:302-316` documents the divergence). A free year-shuffle is anti-conservative for any pair sharing a within-block temporal trend/co-movement — the mechanism most likely to manufacture a trend-driven near-clique. **This subsumes and sharpens my "counts vs rates" guess:** counts or rates, a shared temporal trend the lag-0 conditioning does not remove will read as significant under this null.
- **D. Which dependence is even tested is chosen by 40%-of-RAM** (`residual_scan.py:100`): fine grain shuffles municipalities (spatial dependence), coarse grain shuffles years (temporal co-movement) — the grain, hence the hypothesis, is non-reproducible across machines.

Two more, code-anchored:
- **Certification discrepancy:** residual edges are marked `descriptive` when `insample_biased = n < 10·p` (`residual_scan.py:288,399`). The map reasons this *should* fire at national coarse n (~hundreds) with large p — yet the run marked all ~7,200 `nonlinear_residual` edges **`selected`**. Resolve by reading the actual coarsened `n`, kept `p`, and `certifiable` on a live run.
- **Mechanical-overlap guard is inert (0 edges)** and keys only on ICD-code Jaccard, not shared carrier/source provenance (`edges.py:409`) — verify it is wired (`code_set` populated?) and whether provenance-overlap should demote these pairs.

## 6. What I recommend you assess

- **The math of the residual scan end-to-end** (`residual_scan.py` + `hsic.py` + `nulls.py` + `fdr.py`): is the null correctly calibrated for these residuals? Is the `(n-1)²` HSIC normalization + the within-(spatial-block × temporal-bucket) permutation sound at the coarsened grain (n≈675)? Is BY-FDR the right control across ~60k dependent tests, and is it actually enforced?
- **Whether my `Ω = S − L` fix is even correct in principle** (I claim it is, per the docstring; verify the sign/formulation and that it doesn't degrade genuine recovery — `test_ldo_residual_global_factor.py`).
- **The disease-variable/denominator layer:** are these counts or rates; is the mechanical-overlap/provenance guard wired and sufficient.
- **The decisive measurement I did *not* run:** reconstruct the national residual `E` (the coarsened `(p × ~675)` matrix the HSIC actually sees) and, for the clique pairs, measure (a) their *linear* correlation in `E` (high ⇒ uncaptured linear/count structure; low ⇒ genuine-nonlinear or null miscalibration), and (b) the null distribution for a few pairs (is the observed HSIC genuinely extreme, or is the null too tight?). This single reconstruction distinguishes candidates 1/3.

## 7. How to reproduce / inspect (self-contained)

- **Output:** `data/runs/national_c25_full_ad2/Hypotheses.parquet` (7,483 × 25), `Coverage.json`.
- **Characterize the clique** (polars, no re-fit):
  ```python
  import polars as pl, re
  from collections import Counter
  df = pl.read_parquet(r"data/runs/national_c25_full_ad2/Hypotheses.parquet")
  nl = df.filter(pl.col("edge_type")=="nonlinear_residual")
  deg = Counter()
  for s,t in zip(nl["source_var"], nl["target_var"]): deg[s]+=1; deg[t]+=1
  # 132 nodes, median degree ~118, tiny HSIC (nl["weight"]); 113/132 are 64-hex disease vars
  ```
- **Re-run the national LDO** (~26 min): the probe is `scratchpad/ldo_national_memprofile.py` (points at `data/runs/national_c25_full_ad2`, calls `run_investigate(run_dir, intent=<config/intents/national_pancreatic_c25_determinants.json>, write=True)`; line-buffered log to `.codex-tmp/national_ldo_scoped3.log`). Guard at 26 GB.
- **The residual-precision synthetic** that misled me: `scratchpad/validate_residual_precision.py`. **The regression test:** `tests/synthetic/test_ldo_residual_global_factor.py`.
- **Live code entry points:** `run_investigate` (`workflows/investigate.py:334`) → `run_ldo_multiresolution` (`orchestrator.py:600`) → `run_ldo` (`orchestrator.py:97`) → residual scan at `orchestrator.py:345`.

## 8. Explicit non-goals for this handoff

I did **not** pursue candidates 1–3 or run the decisive residual reconstruction — that is yours to assess and direct. The `Ω` fix (`bcdd0dd`) is committed and kept as a correctness fix but is **not** claimed to resolve the artifact. Do not assume the 7,372 "determinants" are real; the linear `contemporaneous` edges (279) and `lagged_directed` (7) are less suspect but were not separately validated.
