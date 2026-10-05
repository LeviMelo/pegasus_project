# The first dependency map: 65 fields, 2,059 pairs per layer, 0 false edges in 40 surrogate worlds once δ_E|Z is 0.1 (2026-10-05)

**Regime.** `pegasus-core map` (5065a87, 17fc4ee; `scans/maps.py` δ_Z and the CLI entry-point order changed here), fields from `data/depmap/build_inputs.py` (store `maps`, key `map_inputs` v1): 17 SIM and 22 SIH chapters (survivors; 2015-19 events, indirectly standardised, shrunk Poisson intercepts), 7 SINASC indicators, 20 contexts; 5,570 places. SIM VII, VIII and SIH XXII left out (too few events). 2,059 pairs tested per layer, 21 excluded by overlap. Marginal δ_E 0.03, conditional δ_E|Z first 0.05 then 0.1, TreeBH (family → pair) and BY at q 0.05. Map 18 s. Negatives: `harness.map_negatives`, 20 worlds of Moran-randomised surrogates (generated on knn8, tested on contiguity), seed `map-negatives` (calibration) and `map-negatives-val` (validation, `data/depmap/validate.py`); logs `data/logs/depmap_*.log`; edges in store `maps/map_edges`; reading script `data/depmap/edges.py`.

## False-edge rate

| layer, δ | all fields surrogate | contexts kept real |
|---|---|---|
| marginal, 0.03 | TreeBH 0 and BY 0 in 20 worlds (raw p ≤ q: 12.8 per world of 2,059); smallest δ clearing every family 0.02 | no health-involving edge; the 61 admitted per world are the real context pairs |
| conditional, 0.05 | TreeBH 0.45 per world, at least one in 8 of 20 worlds (global-null FDR 0.40; BY 1 of 20); the family context × context has raw rate 0.08 at δ 0.05, the others ≤ 0.018 | other families ≤ 0.015 |
| conditional, **0.1** (calibrated) | **0 in 20 fresh worlds** (TreeBH and BY); every family ≤ 0.002 | 16 constant (the real context pairs), health families ≤ 0.002 |

So δ_E|Z is 0.1 in the map (`maps.DELTA_Z`; `pairs.MIN_EFFECT['E_b|Z']` 0.05 stays for single pair scans). With it the real map admits marginal 242 (BY 120) and conditional 116 (BY 66; 189 at 0.05): direct 85, explained 157, suppressed 31. The n_eff − dim Z against no subtraction was not compared.

## The strongest admitted edges (rank: lower 90 % bound of |ρ|, health-involving)

Admitted by family, marginal / conditional (of 210 SIH×SIH, 136 SIM×SIM, 340 SIM×context, 420 SIH×context, 140 SINASC×context, 119 SIM×SINASC tested): SIH×SIH 76/89, SIM×SIM 30/1, SIM×context 17/0, SIH×context 16/4, SINASC×context 9/1, SIM×SINASC 3/1; **SIH×SIM (357 tests) and SIH×SINASC (147) have none in either layer**.

- **SIH × SIH (the 20 strongest of both layers, ρ 0.4-0.7, direct):** I-X, XI-XIV, IX-X, X-XIV, IV-X. An artefact of a shared level, not a morbidity relation: each SIH chapter is a standardised admission rate per resident, so a place's overall hospital use (access, referral, billing, AIH volume) enters all of them; conditioning on the 19 contexts, beds included, leaves it (I-X 0.69 → 0.68). The same chapters do not covary with their SIM counterparts (IX 0.10, X 0.00, both n.s.). Not tested directly (no common-factor fit): "hospital use is one dimension", nothing about disease.
- **SIH × SUS beds (known, recovered):** X +0.28, I +0.26, XIV +0.24, IV +0.22 (conditional, n_eff 1.9-3.0k); marginal IX +0.16. Roemer's law again, as in the CNES entry (+0.264).
- **SIH × ICU beds, ANS coverage (marginal only, explained):** I-ICU beds -0.27, I-ANS coverage -0.34, IV-ICU -0.23; about 0 given the other contexts. Plausible (richer, privately covered places use SUS admission less), a confounded income/urbanity pattern, not new.
- **SIM × SIM:** IX-XI +0.48 (direct, +0.38 conditional); X-XIV, I-XII, IV-XX marginal only, explained by the contexts. IX-XI is unexplained by the contexts here; shared certification quality is the rival reading, untested.
- **SIM × SINASC:** XVI (perinatal) × Apgar5 < 7 +0.35 (direct, +0.30): known, the same neonatal care chain; the two share no events (overlap excluded). XIII × teen mother and × LBW are explained away (≤ 0.05 conditional).
- **SIM × context:** only ICU beds and nurses (II +0.30, VI +0.25, XVIII -0.21), all explained (≤ 0.09 given the rest): places with an ICU certify cancer and neurological deaths more and ill-defined deaths less (diagnostic capture, plausible, not tested). The expected **SIM I × sanitation recovery failed**: sewer +0.04, water 0.00, no bathroom +0.02, waste +0.05, income -0.11 (n_eff 360-1300, SE about 0.03-0.05), a well-powered null at chapter level (chapter I is dominated by HIV, sepsis and TB; a diarrhoeal code-level field is the next test, not run).
- **SINASC × context:** teen mother × income over 2 minimum wages -0.58 marginally (n_eff 15, not admitted: too few effective places) and -0.23 conditionally (admitted, n_eff 887): known relation, found only by the conditional layer, since the marginal layer lacks power for fields this smooth. At the old δ 0.05 teen mother × indigenous, agriculture and black/brown shares (+0.22 to +0.23, marginal +0.46 for the last) were also admitted; at 0.1 they are not.
- **Contexts:** GDP per capita × public-administration share -0.87 (n_eff 10; GVA shares are complements of private output, an accounting relation), waste collection × urbanisation +0.74, water × urbanisation, no bathroom × waste collection -0.52/-0.28: known. Physicians × nurses +0.48/+0.38 and ICU beds × physicians: shared CNES source and per-1,000 denominator, an artefact class.

Reading: the map recovers the relations it was declared for (beds, the perinatal chain, income and teen motherhood) and finds no new health relation among the top 20 of either layer; the strongest health-health edges are one hospital-use dimension. Ranking by effect size, not novelty: lower-ranked edges are unread.

## Limits

- 20 + 20 worlds resolve a per-world false-edge rate only above about 0.05 (0 in 40 all-surrogate worlds). The contexts-real run cannot test the context × context family (the dependence is true).
- The conditional layer's n_eff is 4-10 times the marginal one (residuals after 19 contexts are less spatially smooth); the surrogate calibration supports it at δ 0.1 only.
