# Institutions, first stage: the supply term and the facility lattice (2026-10-05)

**Question.** A third of SIH chapter X "signals" are one facility's volume or coding step (evaluation 2026-10-05, lead triage). Can the expectation absorb it, and what does an institution lattice add?
**Regime.** SIH-RD hospitalisation, chapter X, annual 2010-2023, 5,570 places, 77,980 non-empty place-year cells, 16.77 M admissions; POPSVS; fitted block of 2026-10-05 (ADR-0006 dispersion); facility cube of the lead-triage run. Code: `facility.py` (`supply_indices`, `fit_supply`, `attach_supply`, `institution_lattice`), `Monolith.supply`, `Session(supply=True)`, `Session.institutions`; scripts (gitignored) `data/inst/`; artefacts there and in `pegasus_home/leads_inst_base`, `leads_inst2`. The survey is today's plan with 50 replicates (the 22,628-lead register of the lead-triage run came from an earlier plan and is not the baseline).

## 1. Which evidence explains the place-year residuals (B1, chapter total, NB likelihood, dispersion refitted)

| index (log, exponent) | gain in log-likelihood | kappa (0.1164 before) |
|---|---|---|
| facility volume, weights = block events (0.75) | +14.4 k | 0.0745 |
| facility volume, weights = other-chapter events (1.0) | +9.9 k | 0.0857 |
| place's own other-chapter admissions (1.25) | +13.7 k | 0.0763 |
| both (0.5, 0.5), raw | +17.5 k | 0.0677 |
| both (1, 1), soft-thresholded (the shipped term) | +6.0 k | 0.0965 |

Place-year deviance fell 21-36 % in every size class with the raw indices. **The raw indices explain more because they carry the place-year noise shared across chapters** (the "hospital-use dimension" of the dependency map), which is not supply: in the 1,191 sole-provider places (>= 85 % of >= 100 events at one facility) the raw term raised the z sd from 0.959 to 1.059. The shipped term takes it out (deadband at 2 sd of counting noise) and gives 0.983.

## 2. The survey, chapter X, today's plan (4,321 leads at baseline)

| term | leads | facility | signal | system | substitution | noise |
|---|---|---|---|---|---|---|
| none | 4,321 | 507 | 974 | 1,838 | 827 | 175 |
| raw, chosen (0.5, 0.5) | 4,247 | 444 | 925 | 1,839 | 874 | 165 |
| raw, (1, 0) | 4,506 | 453 | 949 | 1,956 | 956 | 192 |
| raw, (1, 1) | 5,065 | 527 | 1,113 | 2,139 | 1,015 | 271 |
| **shipped (deadband, chosen 1, 1)** | **4,200** | **452** | **911** | 1,837 | 840 | 160 |

- Facility class -11 %, signal -6.5 %; the volume-step mechanism 295 to 242 in the raw (0.5, 0.5) run. The facility share of signal-or-facility stays 34 %. Of the 507 facility leads 421 stay facility, 82 vanish (locus match), 2 become signals; 857 of 974 signals stay.
- A fuller pass-through adds leads: the term injects noise when it is not thresholded.
- **Most facility leads are a facility's handling of a node** (J45, J15, J13, J12 ...) in single places or small sets: a chapter-level supply cannot see them.

## 3. Calibration (67 admissible fields)

B1: 67/67 calibrated both ways, mean KS 0.0140 to 0.0138, chapter 0.0227 to 0.0191. B2: 51/67 both ways, chapter 0.0398 to 0.0374 (the raw term: 53/67 and 0.0289).

## 4. Known positives where SIH carries them

- **Dengue** (chapter I, A90, A91), state-years with >= 200 observed: correlation of obs/exp before and after .9964-.9989 (302 and 41 state-years); every state-year at 2x or more stays at B2 (22 of 22, 14 of 14 at A91 B1/8 of 8 B2) and 22 of 25 at A90 B1 (the other three fall just under 2x). Outbreak lens A91 B2 84 to 85 cells.
- **COVID-era pneumonia** (J12, J18, J96, J09-J18): state-year correlations .90-.99; J12 DF 2021 4.31 to 3.41 and 2020 3.44 to 2.84 (the Federal District's hospital volumes moved), SP 2021 2.94 to 3.08, AM 2021 (J96) 1.85 to 1.69; the outbreak lens' 2020-21 cells 7 to 10 over the eight settings. Not run: the prospective BP test (a fit up to 2019 for chapter X does not exist).
- **Winter seasonality** (monthly X, Sul and Sudeste): with the annual factor on the months the profile is identical (Jaccard of months >= 1.10 against the observed 1.00, Sul peak July), KS unchanged, **but the outbreak lens's cells rose 83 to 139 (B1) and 73 to 103 (B2s)**, Jun-Aug 6 to 6. A step inside a year lands in the wrong months, so the term is off at the monthly grain.

## 5. Sole-provider places (1,191; 256 small) on the surprise scale

| subset | B1 sd of z | B1 abs z > 3 | B2 abs z > 3 | B2 abs z > 2 |
|---|---|---|---|---|
| sole, before -> after | .959 -> .983 | .89 % -> .95 % | 1.04 % -> .91 % | 4.34 % -> 4.40 % |
| sole with a volume range >= 1.6 (141) | 1.263 -> 1.267 | 2.63 % -> 2.63 % | 3.34 % -> 2.79 % | 10.89 % -> 8.76 % |
| other places (4,379) | 1.024 -> 1.020 | .91 % -> .81 % | .98 % -> .90 % | 5.42 % -> 5.57 % |

42 sole-provider facility leads stay (2 vanish); 112 of 113 sole-provider signals stay. **Sole providers do not become readable**: where hospital and place coincide, other chapters of the same people carry the same noise; only the stepped ones gain, at B2.

## 6. The lattice (chapter X; 5,666 facilities with >= 30 expected events)

- 1,744 steps (31 % of the facilities): **1,336 volume (77 %), 408 specific**. 880 start in 2010 (a facility present only early: a CNES code that left); window lengths 1-7 years.
- Of the 3,219 facility leads of the earlier register, 1,625 have a top facility that is a step (688 of their 1,785 distinct facilities); the most leads per step facility: CNES 2118629 (Governador Valadares) 16, 2272113 14, 2706741 13. Of today's 507 facility leads, 235 (46 %) sit on a node-level step; of 716 concentrated signals, 302 (42 %): the detector does not discriminate facility leads from other concentrated ones.
- **Null.** Under negative binomial counts with the facilities' own dispersion, 0 to 1 of 5,666 flagged (0.0002); at twice and four times that dispersion 1.1 % and 15 %. The observed 31 % (50 % of the smallest third of facilities, 15 % of the largest) is above all three: **the facilities' year-to-year variation is real or heavier than one dispersion, and the threshold is provisional.**
- At the node level (57 nodes) 14,102 steps in 3,880 facilities (9,295 specific): too many to be leads; no multiplicity, replication or pair yet.

## Reading

An expectation can take out what other chapters show of a facility (about a tenth of the facility class, with calibration a little better and the positives intact); it cannot take out a facility's handling of the block, and should not (a referral hospital's outbreak is real). The rest belongs on the institution lattice, which finds the steps (the 3,219 place leads name 1,785 facilities, 688 of them steps) but is not yet a calibrated lens. Next: the term inside the likelihood, crossed place x facility effects at the node level, a lattice null with the observed dispersion and a multiplicity over nodes. Decision: ADR-0016.
