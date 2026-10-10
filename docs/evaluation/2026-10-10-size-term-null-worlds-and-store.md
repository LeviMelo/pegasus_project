# The size term refused, B3's null worlds read, and the store given eviction (2026-10-10)

Regime: branch `design-v0` at eca6ff3, with the B4 trial on branch `b4-size` (22ab14c); PegaSUS's root
`C:/Users/Galaxy/pegasus_core_data`, store `pegasus_home`; CPU fits.

## B4: a size term in the expectation (work plan B4, OPEN_QUESTIONS 13)

`scripts/measure_heldout.py` fits on 2010–2021 and scores 2022–2023 (contiguity graph, group profile). The exposure is
`popsvs+size:β`, POPSVS × (place population / the year's median place)^β. Runner: `data/probes/b4_heldout.sh`, log
`data/probes/b4_heldout.log`.

| block | β 0 | β 0.005 | β 0.01 |
|---|---|---|---|
| SIM IX, deviance per death (787,737 deaths) | 2.203987 | 2.203991 | 2.203997 |
| births, deviance per birth (5,099,320 births) | 0.069739 | 0.069745 | 0.069752 |

- **The fit worsens monotonically in β on both blocks.** The NB log-likelihood of the non-empty cells falls with it:
  - SIM IX: −988,245 at β 0, −988,263 at 0.005, −988,282 at 0.01.
  - Births: −246,809, −246,820, −246,832.
- **The term is refused.** The size gradient of OPEN_QUESTIONS 13 stays inside the noise, and the place effects
  already carry what a size term could. Branch `b4-size` is not merged.
- **A defect in the first run.** The worktree's script imported the main checkout's installed package, which has no
  size modifier, so every β > 0 run failed. The rerun put the trial's `src` first on the path.

## B3: the null-world grid on births (work plan B3)

`pegasus-core grid SINASC-DN birth '*' --kinds place --shapes spike,step --worlds 2 --null-worlds 20`, read by
`data/probes/b3_verdict.py` (`data/probes/b3_grid_sinasc_early.json`). Its code was imported before ADR-0035, so
cell_excess is the pooled version here.

| lens | null worlds with a finding (of 20) | mean findings | power over planted worlds |
|---|---|---|---|
| excess_step, step | 1 | 0.05 | 0.18, 0.15 |
| excess_trend | 2 | 0.10 | 0.13 |
| excess | 3 | 0.25 | 0.59 |
| cell_excess (pooled) | 5 | 0.35 | 0.58 |
| change_point, divergence (both), group_disparity, outbreak, space_time | 0 | 0 | 0.00–0.46 |
| excess_level | 20 | 24.1 | 0.07 |
| spatial_cluster | 20 | 12.4 | 0.01 |
| institution_step | 20 | 2,042 | 0.00 |

- **The lenses that read departures from B1 hold q, or come within the binomial noise of 20 worlds.** cell_excess
  is the exception at 5 of 20.
- **The last three rows measure the harness, not B3.**
  - A null world is drawn from the fitted B1 expectation, so it keeps every place's real level.
  - excess_level and spatial_cluster test B0, the level against national rates, and they find that level.
  - institution_step reads the facility cube, which no world simulates.
  - Judging them needs worlds drawn from their own tier.
- **The grid now draws them (OPEN_QUESTIONS 16).**
  - `grid_world(spatial=False)` draws from the fit without its place effects. A grid that reads B0 lenses adds
    `null_b0` worlds, and only those lenses read them.
  - institution_step is not judged (`GRID_NOT_JUDGED`).
  - Births, 10 `null_b0` worlds (`data/probes/oq16_null_b0.json`):
    - excess_level: 2 worlds with a finding, 0.2 findings a world (24.1 in B1 worlds);
    - group_disparity: 0 worlds;
    - spatial_cluster: all 10 worlds, 3.4 findings a world (12.4 in B1 worlds).
  - The worlds keep the field's persistent place-year frailty, which a cluster summed over the years collects. The
    cell excess's heavy tail traces to the same frailty (OPEN_QUESTIONS 12).
  - A null plan that no requested lens reads is no longer drawn.

**The classed cell excess, after ADR-0035.** Null worlds on births, the same seeds in every run (ADR-0035 amendment):

| version | null worlds | worlds with a finding | findings in worlds 0-3 |
|---|---|---|---|
| a BH per class (ADR-0035 as decided) | 11 | 7 | 2, 2, 2, 3 |
| one BH over every class | 4 | 3 | 2, 1, 1, 0 |
| one BH, each class's σ0 at least 1 (kept) | 11 | 2 | 0, 1, 1, 0 |

- **What is left belongs to the predictive.** In one world (`data/probes/cell_null_tails.py`, seed 3):
  - the z centre is calibrated: sd 1.005, σ0 0.96-1.03 per class;
  - P(z > 3) is 0.0009-0.0015 in the seven smaller classes against N(0, 1)'s 0.00135, but 0.0026, 0.0021 and 0.0044 in
    the three largest;
  - the three cells BH rejects have expectations of 451, 980 and 8,727 births.
  - The same seed, drawn as plain NB(μ, φ) without the field's correlated frailty, has Gaussian tails in every class
    (P(z > 3) 0.0009-0.0018) and no rejection.
  - So the heavy tail is the persistent place-year frailty, which dominates large places, and the per-cell predictive
    does not carry its shape.
- **Consequence for real data.** Births' findings in large places carry part of this tail. ADR-0035 had moved 308 of
  455 findings into the four largest classes. OPEN_QUESTIONS 12 holds the fix, which belongs in the model.

## The store: dead entries, and eviction

The store held 14.8 GB. Removed:
- 720 blockdata entries under superseded assembly versions (5.29 GB). The current assembly is `1:0715d0bb1ab75192`;
  entries of the last 12 hours were kept.
- 2,080 `event_counts` entries keyed before `declared` (1.97 GB). No current code computes those keys.

It holds 7.7 GB now. A read now stamps its entry. `pegasus-core gc` evicts the least recently read entries of the
caches (gateway, blockdata) to a budget; fits, results and registers are never evicted. The dry run at 4 GB would
evict 215 of 1,758 entries (0.58 GB).

**`PEGASUS_DATA_HOME` is pinned to PegaSUS's root.** A pegasus_data call that named no root had created a home beside
the working directory twice:
- `pegasus_project/pegasus_data_home` made 167 fetches between 2026-10-05 and 2026-10-09;
- the B4 worktree created a 225 MB seeded catalog.

`config` now sets the variable to `data_root()` unless it is already set.
