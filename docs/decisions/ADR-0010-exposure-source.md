# ADR-0010: The gateway reads the population from a source parameter; POPSVS stays the default, population-account-2 is available with its uncertainty

**Date.** 2026-10-05. **Status.** Active.

**Evidence.** `docs/evaluation/2026-10-05-exposure.md` (`scripts/measure_exposure.py`, `data/exposure/`); pegasus_data's decision record 0148 (`population-account-2`).

## Decision

1. **`gateway.population(years, source=)`**, `config.population_source()` (env `PEGASUS_POPULATION`), `monolith.assemble(population=)`, `surprise.Expectations(population=)`: `popsvs` (default), `account-2`, or (amended below) `account-3` / `account-4`. `account-2` is read through pegasus_data's modelled tier (`read_modelled`, pinned `population-account-2`): municipal rows, 2010-2023 (earlier years are comparable areas and raise), 80 % interval read as the standard deviation of log N.
2. **The source fixes the age bands.** The account's 0-4 holds ages 0 and 1-4, which POPSVS keeps apart and the account cannot split, so the account has 17 bands against 18; the monolith takes its band count from the data. Nothing is padded or split. A control source `popsvs-5y` (POPSVS summed to the account's bands) exists to separate source from bands.
3. **Not covered is unallocated, not guessed.** 16 municipalities pooled in 5 comparable-area groups have no account row (their events, 14,369 of IX's 4,990,893, are unallocated 'municipality'); a cell with events and no population (1 IX death) is unallocated 'no population in the cell'.
4. **Cache keys** carry `population` and `population_model` for the account; POPSVS adds nothing (its keys predate the switch). Event-count keys carry a digest of the place set when it is not POPSVS's 5570.
5. **Exposure variance** (`Monolith.exposure_variance`): Var(Σ μ_g) = Σ μ_g²(e^{s²}-1) + ρ[(Σ μ_g s_g)² - Σ μ_g² s_g²] enters the predictive's variance beside the Laplace Var(η) (`predictive_phi`), in B0-B2 and BP; ρ = 0 by default; zero for POPSVS.
6. **The default stays POPSVS.** Account-2 is not better on held-out or in-sample deviance (SIM chapter IX, SINASC births), and the exposure variance does not reduce miscalibration (the block's φ already carries it). Account-3/4 do not change this (amendment).

## Amendment 2026-10-05: sources `account-3` and `account-4`

7. **`account-3`** (2000-2023) and **`account-4`** (2000-2030, the forecast beyond 2023) are pegasus_data's complete tensor (`population-account-3/4`, decision record 0151: all 5,570 municipalities, single ages 0-100, race, intervals). `gateway._tensor_population` reads the race `total` and sums the single ages exactly onto POPSVS's 18 bands (age 0 apart from 1-4); the band's `s` is Σ N_a s_a / N_band, the ages' errors taken as perfectly correlated, an upper bound. Years outside the held range raise. Nothing is unallocated: the account-2 gaps (5,554 places, 17 bands) disappear. Race is available in the tensor but unused by the gateway. The keys carry source and model version.
8. **POPSVS stays the default** by the rule fixed beforehand (the default changes only if IX also favours the account): chapter IX is also slightly worse under account-3 (NLL +0.04 to +0.3 %, KS tied except BP .044 against .038), and births lose (NLL +0.4 % in B1 and BP, held-out KS .096 against .059). Numbers and the diagnosis of the births loss: evaluation 2026-10-05, exposure, "Account-3".

## Amendment 2026-10-05 (2): `account-6` and `hybrid`; newborn-exposure fields read the hybrid by default

9. **`account-6`** (1991-2030, `population-account-6`) is a selectable source and **`hybrid`** is POPSVS at every age but 0 and the account's age 0 (same 18 bands, `s` = 0 above age 0). On SIM chapter XVI (perinatal) the account's age 0 beats POPSVS on every tier, held-out BP included (31,579 against 31,596 NLL); the hybrid equals account-6 there to within one unit, so the whole gain is age 0.
10. **Per-field default.** `monolith.default_population` chooses when no source is named and `PEGASUS_POPULATION` is unset: `hybrid` for a **newborn-exposure field**, defined by its data as an event-count block of which at least half (`NEWBORN_SHARE` 0.5) of the events, over the years asked, are at age 0 (XVI: 0.994; IX: 0.001; births, whose subject is the mother: 0), `popsvs` otherwise. Code-list and mark readers keep POPSVS. `PEGASUS_POPULATION` or an explicit `population=` still overrides. The resolved source is in the data's key (`population: hybrid`, `population_model`), so a hybrid fit never shares an entry with a POPSVS one.
11. **POPSVS stays the general default** (item 6 stands; the account-6 loss on births stands).

Caveat: the age-0 reference (registered births minus infant deaths) is **not independent of the account's inputs**, the same SIM and SINASC events the field is scored on; the held-out gain is small (-0.05 %) and rests on the predictive score, not on an external truth.

## What it does not decide
Whether the account's lower 2023 population (-1.5 to -2 % in places under 100,000 against POPSVS) is right; the 2023 row is a projection. The band effect of 17 against 18 bands is not separated (the `popsvs-5y` fits for the full span did not finish), but account-3 on the 18 bands shows the loss is not the bands. Account-3's better age 0 (registered births minus infant deaths, 2015) is not independent evidence: the account is built with those events.
