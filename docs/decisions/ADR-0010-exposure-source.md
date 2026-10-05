# ADR-0010: The gateway reads the population from a source parameter; POPSVS stays the default, population-account-2 is available with its uncertainty

**Date.** 2026-10-05. **Status.** Active.

**Evidence.** `docs/evaluation/2026-10-05-exposure.md` (`scripts/measure_exposure.py`, `data/exposure/`); pegasus_data's decision record 0148 (`population-account-2`).

## Decision

1. **`gateway.population(years, source=)`**, `config.population_source()` (env `PEGASUS_POPULATION`), `monolith.assemble(population=)`, `surprise.Expectations(population=)`: `popsvs` (default) or `account-2`. The account is read through pegasus_data's modelled tier (`read_modelled`, pinned `population-account-2`): municipal rows, 2010-2023 (earlier years are comparable areas and raise), 80 % interval read as the standard deviation of log N.
2. **The source fixes the age bands.** The account's 0-4 holds ages 0 and 1-4, which POPSVS keeps apart and the account cannot split, so the account has 17 bands against 18; the monolith takes its band count from the data. Nothing is padded or split. A control source `popsvs-5y` (POPSVS summed to the account's bands) exists to separate source from bands.
3. **Not covered is unallocated, not guessed.** 16 municipalities pooled in 5 comparable-area groups have no account row (their events, 14,369 of IX's 4,990,893, are unallocated 'municipality'); a cell with events and no population (1 IX death) is unallocated 'no population in the cell'.
4. **Cache keys** carry `population` and `population_model` for the account; POPSVS adds nothing (its keys predate the switch). Event-count keys carry a digest of the place set when it is not POPSVS's 5570.
5. **Exposure variance** (`Monolith.exposure_variance`): Var(Σ μ_g) = Σ μ_g²(e^{s²}-1) + ρ[(Σ μ_g s_g)² - Σ μ_g² s_g²] enters the predictive's variance beside the Laplace Var(η) (`predictive_phi`), in B0-B2 and BP; ρ = 0 by default; zero for POPSVS.
6. **The default stays POPSVS.** Account-2 is not better on held-out or in-sample deviance (SIM chapter IX, SINASC births), and the exposure variance does not reduce miscalibration (the block's φ already carries it).

## What it does not decide
Whether the account's lower 2023 population (-1.5 to -2 % in places under 100,000 against POPSVS) is right; the 2023 row is a projection. The band effect of 17 against 18 bands is not separated (the `popsvs-5y` fits for the full span did not finish).
