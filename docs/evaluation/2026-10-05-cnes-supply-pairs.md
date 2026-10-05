# Health supply with the CNES fields: Roemer's law passes, ESF coverage fails its sign, sanitation survives primary care, no supply step explains the SIM leads

**Regime.** Positives declared in `harness.POSITIVES` and committed alone (4281e6c) before any CNES field was read against these outcomes. Scripts `data/agent_cnes/{prep,analyse,steps,explain_run}.py` (gitignored; results `analyse.json`, `steps.json`, `explain_run.json`, logs beside them); E_b production code (`pairs.between`, MSR on the normalised contiguity graph, δ_E 0.03, δ_E|Z 0.05, ADR-0005); tests in the harness ledger (`harness:known_positive:cnes:*`). Inputs: the 35 `cnes_*` December stocks 2008–2023 (pegasus_data decision 0150) from `pegasus_core_data`, SIH-RD admissions through the gateway, POPSVS. One fix on the way: `scans.explain.explain_away` broadcast φ against the raveled μ and failed on any [U, T] input; it now broadcasts against the original shape. 2026-10-05.

## Roemer's law (declared: pass needs E_b and E_b|Z, ρ > 0, p ≤ 0.05) — **passes**

Outcome: all-cause SIH-RD admissions by residence 2015–19 (58.1 M), indirectly standardised on national sex × 5-year-age rates by year, Poisson-shrunk place effect (τ 7.7). Context: `cnes_beds_sus` per 1,000, mean of the five December rates, asinh (1,916 of 5,570 municipalities have none).

| | ρ | n_eff | p at δ |
|---|---|---|---|
| E_b (δ 0.03) | +0.264 | 1,365 | < 5e-5 |
| E_b\|log GDP pc, urban share (δ 0.05) | +0.252 | 1,766 | < 5e-5 |

Not declared, same data: without chapters XV and Z (obstetric, newborn) +0.276 / +0.263; beds in the immediate region over its population +0.238 (n_eff 241, p 5e-4) / +0.243; Spearman +0.254 / +0.242; weights floored at the prior's variance (the Poisson weights concentrate on cities, ESS 208 of 5,570) +0.293 / +0.290. Placebo with the gate's outcomes: infant mortality ρ −0.020 (p 0.64), diarrhoea deaths +0.032 (p 0.47) against the same beds field, so the beds field does not simply track every outcome's place effect.

**What it can and cannot mean.** Literature: Roemer 1961 (Hospitals 35:36–42); Delamater et al. 2013, [PLoS ONE 8:e54900](https://doi.org/10.1371/journal.pone.0054900) (Michigan ZIP codes, spatial regression, positive, standardised coefficient 0.21); a Brazilian municipal analysis of ambulatory-care-sensitive admissions ([Braz. J. Health Rev.](https://ojs.brazilianjournals.com.br/ojs/index.php/BJHR/article/view/4038), and [Braz. Appl. Sci. Rev.](https://www.brazilianjournals.com/index.php/BASR/article/download/2392/2413), both found by search and not opened: the publisher returned 403, so only their stated conclusion, more beds with more admissions, is relied on). The sign and size agree. But ρ is an association between place effects: beds are built where demand is, SIH counts only SUS admissions by residence, and residents of bedless towns are admitted in the hub (so the own-municipality bed rate overstates the hub's supply and understates the neighbours'). E_b cannot separate supply-induced admission from demand-placed supply; the catchment version being as strong says the pattern is not only the own-border artefact. It is a recovered known association, not evidence of supply-induced demand.

## Primary care (declared) — ESF coverage ↔ infant mortality **fails**; sanitation survives **passes (2 of 3)**

- **ESF coverage** (min(1, 3,450 × teams / population), mean 2018–22; median 1.0, 92% mean): crude ρ +0.151 (E_b p 0.045), given log GDP pc **+0.068, p 0.32**. Declared sign negative, observed positive: **failed, not swapped**. Coverage correlates −0.26 with log GDP pc: ESF reached small and poor municipalities, where infant mortality is higher (confounding by indication), and the cap makes most of the country 1.0. The panel designs ([Aquino et al. 2009](https://doi.org/10.2105/AJPH.2007.127480), [Rasella et al. 2013](https://doi.org/10.1016/S0140-6736(13)60715-1)) identify the effect by change within municipality; a 2018–22 cross-section cannot. Not declared: community health agents per 1,000 ρ +0.135 (p 0.065); diarrhoea deaths ↔ ESF +0.098 (p 0.060).
- **Sanitation given primary care** (Z = log GDP pc, ESF coverage, agents; ρ with Z = GDP only → full Z; δ_E|Z 0.05):

| pair | ρ | ρ | p (full Z) | admitted |
|---|---|---|---|---|
| IM ↔ no bathroom | +0.182 | +0.166 | 0.012 | yes |
| DIA ↔ no bathroom | +0.218 | +0.208 | 0.0001 | yes |
| IM ↔ water | −0.148 | −0.103 | 0.108 (0.063 with ESF alone) | no (was 0.0487) |

Signs kept 3 of 3, admitted 2 of 3: the declared criterion is met. Of the other pairs none gains admission, DIA ↔ literacy (admitted at 0.043 given GDP) falls to 0.070, and all 12 keep their sign. ρ shrinks 17–38% for sewer, water, waste and literacy (IM ↔ literacy −0.12 → −0.07), against −4 to −9% for the bathroom pairs. IM ↔ water was on the edge before (0.0487); losing it is the power cost of two more covariates, not necessarily a mediation.

## Explain-away with supply (declared rule, 18 lead rows of the 15 unexplained) — **no lead is explained**

Rule (committed): a lead is explained by supply if, at its places, the log ratio of the mean of its first two years to the two before, in any of six fields (beds, ICU beds, CT, SUS hospitals, physician registrations, ESF teams), exceeds the 99th percentile of the same ratio over municipalities (multi-place leads: 3,000 random sets of the same size). Result (`steps.json`): **1 of 108 tests fires**, ICU beds in J09 (influenza) Rio Brilhante and 14 more places, MS/PR 2016 (0 → 10 beds); about one false hit is expected from 108 at the 99th percentile, and a new ICU does not generate influenza deaths: not claimed. `Session.explain_away` (national slope of log(1+stock) on the field's deviance, share absorbed over the lead's cells) gives a maximum of **0.08** (V49 deficit in Ceará, ESF teams) and ≤ 0.06 for every event; nothing near an explanation.
- **São Borja I21** (declared positive for the rule): beds total 124 → 154 (percentile 0.966), ICU 7 → 8, CT 2 → 2, one SUS hospital throughout: **fails**. Of all 35 fields none reaches the 99th percentile (best: ICU beds 0.974, SUS beds 84 → 123 from 2016 to 2018, 0.972; physician registrations 97 → 122). The MI rise from 28–53 to 99–134 a year came with a 40% growth in SUS beds and physicians over 2016–18, common in Brazilian municipalities. The 35 fields hold no catheterisation laboratory, cardiology specialty or death-certification service: those, not the fields at hand, are the candidate drivers.
- Most of the 15 are events (dengue 2015/2017, dam collapse, floods, fire, COVID, influenza) whose mechanism is exposure, not detection; a supply step could explain only the diagnosis-dependent ones (I21, the deficits V49 and I80), and for those there is none. Two rows (A90 Cosmópolis, class `system` in the register) were included because the lead-triage table lists them.

## Not shown
Causal effect of beds or of ESF (no within-municipality design here: a 2008–23 panel with municipality effects would be the test); the subcode, certifier and cath-lab drivers of São Borja; ambulatory-care-sensitive admissions against ESF coverage (the Portaria SAS/MS 221/2008 code list was not fetched).
