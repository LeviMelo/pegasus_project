# Hospital use is two factors; read net of them, 88 of 89 SIH x SIH conditional edges go and no SIH x SIM or SIH x SINASC edge appears (2026-10-05)

**Regime.** Branch design-v0, `scans/maps.py` (`factors`, `dependency_map(adjust=k)`) and `scans/utilization.py`. Fields of the first dependency map: 21 SIH chapters, 17 SIM, 7 SINASC, 20 contexts, 5,570 places, 2015-19 (`map_inputs` v1; the earlier entry said 22 SIH, corrected there). Scripts `data/utilization/{step1,step2,step3,run_map,planted,negatives_edges,split,read_map}.py`, logs `data/logs/util_*.log`. The tensor is 55.7 M surviving admissions, indirectly standardised by year x sex x band as in the map. Care-flow self-sufficiency: `pegasus_data/data/probes/care_flow/sih_rd_{2015..2019}.parquet` (residents' admissions treated in the home municipality over all of them).

## How many factors, and how much they carry

PCA of the weighted correlation matrix of the 21 SIH place effects (place weight: the geometric mean of the fields' 1/sd², as in the pair statistic). Null: 200 worlds in which each SIH field is its own Moran surrogate (ADR-0005; spectrum kept, fields independent).

| factor | eigenvalue (share of 21) | null mean / 99 % | cumulative share of the squared off-diagonal correlation | split-half congruence (N+NE+CO / SE+S) |
|---|---|---|---|---|
| 1 | 6.84 (0.33) | 3.52 / 4.07 | 0.79 | 0.99 / 0.99 |
| 2 | 3.50 (0.17) | 1.89 / 2.46 | 0.965 | 0.98 / 0.88 |
| 3 | 1.46 (0.07) | 1.48 / 1.75 | 0.973 | 0.83 / 0.78 |

**Two factors** stand above the spatially structured null, a third does not. Factor 1 loads positively on every chapter (largest IX 0.33, XI 0.31, XIV 0.30, X 0.29, VI 0.29; smallest XV 0.05, XX 0.07, VII 0.08): general hospital use per resident. Factor 2 contrasts local acute care (I -0.35, IV -0.31, X -0.24, XIV -0.21, XV -0.19) with specialty or elective admissions (XVII 0.36, VII 0.34, XVI 0.32, V 0.26, II 0.20): which kind of admission a place has.

CP-APR (`patterns.fit`, counts over place x year x chapter, the standardised expectation as offset) agrees. Deviance explained against the expectation alone: 0.30 (rank 1), 0.48 (2), 0.58 (3), 0.61 (4), 0.65 (5), 0.68 (6). Rank 1 is a place multiplier (all chapter loadings 1) and correlates 0.89 with factor 1 (weighted by expected admissions). Stability (Tucker, halves): temporal 0.95-0.98 up to rank 3; spatial 0.95/0.84 at rank 2, 0.95/0.88/0.83 at rank 3, 0.6-0.73 from rank 4. The departure component at rank 2 correlates -0.66 with factor 2 and 0.42 with factor 1. Two components are near the 0.9 stability bar, more are not. The map uses the PCA factors, k = 2.

## What the factors correlate with (E_b null of ADR-0005; marginal rho (n_eff) / given the other contexts)

| | factor 1, general use | factor 2, referral / specialty | total admission rate |
|---|---|---|---|
| SUS beds per 1,000 | +0.21 (1043) / +0.18 (2030) | -0.19 (715) / -0.31 (1389) | +0.27 / +0.24 |
| care-flow self-sufficiency | +0.17 (804) / +0.10 (1345) | -0.28 (192) / -0.45 (672) | +0.25 / +0.20 |
| treated per resident (log) | +0.14 / +0.02 | -0.26 / -0.27 | +0.20 / +0.05 |
| private plan coverage (ANS) | +0.20 (20) / -0.05 | +0.37 (37) / +0.04 | -0.04 / -0.07 |
| urban share | +0.13 (105) / 0.00 | +0.21 (121) / -0.05 | -0.01 / 0.00 |
| ICU beds, physicians, nurses, income, sanitation | +0.09 to +0.33 marginal, n_eff 10-270; within 0.12 of 0 given the rest | up to +0.38 marginal; within 0.12 given the rest | within 0.17 |

Factor 1 goes with SUS supply and with treating one's own residents at home, but weakly (about 0.2): most of a place's overall hospital use is not supply. The CNES, ANS and urbanisation correlations are those of smooth fields, whose n_eff is 10-140 (little power), and they vanish once beds are in Z. Factor 2 is the referral side: low self-sufficiency (-0.45) and few SUS beds (-0.31) go with more specialty and elective admissions and fewer local acute ones, in places whose residents are treated elsewhere.

## The map with the factors in the conditional layer

Pairs with an SIH member take factors 1-2 into Z (n_eff minus dim Z, now 21-22 columns); the marginal layer is unchanged. Regression check: k = 0 gives 242 marginal (BY 120) and 116 conditional (BY 66) as before.

| conditional layer, TreeBH admitted | k = 0 | k = 1 | k = 2 |
|---|---|---|---|
| all (BY) | 116 (66) | 29 (18) | 23 (13) |
| SIH x SIH (of 210) | 89 | 4 | **1** |
| SIH x context (of 420) | 4 | 2 | 0 |
| SIH x SIM (357), SIH x SINASC (147) | 0, 0 | 0, 0 | **0, 0** |
| other families | 23 | 23 | 22 (context x context 20 to 19: the family tree shifts) |

- **Gone:** 88 of 89 SIH x SIH and the 4 SIH x context (beds, ICU beds: Roemer's law at chapter level is carried by the general factor, not by a chapter-specific excess). The 76 marginally admitted SIH x SIH pairs had median |rho| 0.36, 0.35 given the contexts, 0.056 given the factors.
- **Remaining:** SIH I x X, +0.34 (n_eff 504; 0.68 before), direct. Infectious and respiratory admissions, both dominated by acute infections of children (gastroenteritis, pneumonia): plausible as disease.
- **Appeared:** none. No SIH x SIM and no SIH x SINASC edge is admitted once utilization is removed. The best: SIM IV x SIH IV +0.21 (n_eff 195, raw p 0.06), SIM II x SIH XV +0.20 (136, 0.12), SIH XV x teen mother +0.20 (119, 0.14; marginal +0.56), SIH XVI x low birth weight +0.16 (199, 0.19). Either there is no chapter-level, 5-year, place-level covariation between admissions and deaths or births beyond what a place's overall hospital use carries, or the power is too low (n_eff 100-600: minimum detectable |rho| about 0.18 at delta 0.1).
- **The strongest remaining SIH edges** (lower bound of |rho_c|; only the first is admitted): I-X +0.34; XV-XVI +0.32 (n 139, raw p 0.004; marginal +0.06, so suppressed by the factors: the same maternity services); XV x school enrolments per person +0.25 (n 512, p < 0.001; a fertility proxy that the national age standard misses); IX-X +0.20 (0.62 before); IV-XVII +0.19; I-XVI +0.19; XIX x black or brown share +0.20; XV x ANS coverage -0.16; X x SUS beds +0.11 and I x SUS beds +0.11 (0.28 and 0.26 before). Seven of the first twenty flipped sign against their marginal (X-XIX -0.20 from +0.30, IV-XI -0.16 from +0.44, IX-XIV -0.16 from +0.58, I-III -0.14 from +0.33, III-XI -0.15, IV-XIV -0.12, IV x income -0.11). Reading rule: a conditional rho of opposite sign to the marginal after a factor is removed is the signature of the removal (of 210 SIH x SIH, 31 rho_c are below -0.1, 26 above +0.1, 6 have raw p_c below 0.05) and is not read as a relation.

## Over-adjustment and the false-edge rate

Planted fields (`planted.py`): SIM XII, XIII and IV replaced by 0.6 x a signal + 0.8 x a Moran surrogate. With the signal the part of SIH IX, X and XIV that contexts and factors do not explain, the adjusted conditional rho is +0.52, +0.51, +0.50 (n_eff 313-687) and all three are admitted (unadjusted +0.34, +0.29, +0.19: two of three). With the signal the utilization factor 1, marginal rho 0.36-0.47 (admitted) becomes +0.06, 0.00, -0.04 (none admitted). The adjustment keeps an SIH-specific relation and removes a utilization one.

Negatives (`harness.map_negatives` stream, factors re-extracted from each world's surrogates, k = 2, delta_Z 0.1, seed `map-negatives-val`): all fields surrogate, **1 false conditional edge in 20 worlds** (SIH X x XIV, rho_c +0.30 against marginal -0.18); contexts real, **1 in 20** (SIH I x XIV, -0.38 against +0.03; the 16 context pairs are the real ones); marginal 0 in both. Raw rate at 0.1 for SIH x SIH 0.016 (0.012 with contexts real), every other family 0.000-0.023. The first map had 0 in 40; this one has 2 in 40 worlds, 0.05 per world, equal to q and what TreeBH allows under the global null. Both false edges are SIH x SIH with the sign opposite to the marginal: the induced correlation of residualising on factors that a set of independent fields still aligns with by chance. A second seed (`map-negatives`) was queued behind the shared heavy slots for 45 minutes and withdrawn: 40 worlds are one seed's.

## Limits

- The factors are principal components of the same fields they condition, so every SIH x SIH rho_c is pulled toward zero or sign-flipped by construction; the planted and negative runs bound this, they do not remove it. A leave-two-out factor per pair is not built. Power for a planted SIH-SIM relation of the real size is untested.
- Weights concentrate on large places; the small places' scores are extrapolated.
- Care-flow self-sufficiency counts residents' admissions of every kind, deaths included; import share exists for the 3,321 municipalities that treat any admission.
- Pooled 2015-19: the factors are not time-resolved (the year mode of CP-APR rank 1 is flat).
