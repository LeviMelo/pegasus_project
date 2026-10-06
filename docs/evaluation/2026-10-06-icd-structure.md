# The ICD's structure in the model: nested groups, sex structural zeros, the profile carrier; the mean's likelihood (2026-10-06)

**Regime.**
- SIM.DO, fitted 2010–2021, held out 2022–2023 (`monolith.heldout`: NB log-likelihood and deviance per held-out death).
- Contiguity graph, `scripts/bench.py`; rows in `data/bench/2026-10-06.jsonl`, logs `data/q_*.log`, `data/bench_lik_*.log`.
- PegaSUS on 8d3885c plus this change; pegasus_data dff5162 (the nested tree).
- Timings come from the sequential queue `data/queue_1006.py`, on a calm machine. Runs made in parallel earlier paged the machine at 50,000 pages/s, and their seconds are not comparable.

## The defect: every category took its carrier's sex ratio

The model has no category × sex term: a category's age–sex profile is its carrier's.

On the stored chapter II fit (profile carrier = the outermost group, so all of C00-C97 shared one profile), expected and observed deaths by sex, 2010–2023, were:

| category | expected men / women | observed men / women |
|---|---|---|
| C53 cervix | 44,820 / 39,951 | 0 / 84,774 |
| C56 ovary | 26,905 / 24,731 | 0 / 51,638 |
| C61 prostate | 111,157 / 98,184 | 209,343 / 1 |
| C50 breast | 119,767 / 110,261 | 2,672 / 227,359 |

So a sex-specific field's expectation was wrong by about half. Two different things carry the fix:
- **The sex restriction is structural** (pegasus_data `code_attributes().sex`, the CID-10 release's RESTRSEXO). A carrier whose categories differ in it is split by it. A restricted group's exposure is zero in the other sex (`BlockData.group_sex`, `Monolith._prof`). The profile centring becomes the residual of the additive group + cell fit over the allowed cells: an orthogonal projection, idempotent to 3·10⁻¹⁵, with row and column sums zero to 6·10⁻¹⁴.
- Records in the excluded sex are counted as unallocated ("sex the code excludes"): 1 in chapter II, 2010–2021.
- **Breast cancer (C50) is not restricted.** Its 99 % female share is a profile matter, carried by the finer carrier below.

## The profile carrier (OPEN_QUESTIONS 3)

pegasus_data's tree now nests groups (C53 > C51-C58 > C00-C75 > C00-C97 > II). The carrier is `profile="group"` (the outermost group, as before), `"block"` (the innermost) or `"category"`.

| block | carrier, sex zeros | carriers | held-out NB loglik / death | deviance / death | seconds | outers |
|---|---|---|---|---|---|---|
| II | group, without | 4 | −2.54725 | 3.81535 | 85 | 17 |
| II | group, with | 11 | −2.45893 | 3.58042 | 85 | 7 |
| II | block, without | 18 | −2.37895 | 3.38328 | (paged) | 5 |
| II | block, with | 23 | **−2.37752** | **3.38042** | 258 | 6 |
| XV | group = block, with | — | −8.10559 | 16.05393 | 42 | 8 |
| XV | group, without | — | −8.10250 | 16.05955 | 59 | 6 |

- On II, the sex zeros gain 0.088 per death (44 k log-likelihood units over 498,964 deaths).
- The block carrier gains as much again (0.081 per death). Its gain is the age profile as well as the sex ratio: childhood leukaemia and prostate cancer no longer share one age curve.
- XV (all female) loses 0.003 per death in NB log-likelihood and gains in deviance: no material change, and a third faster.

**Cost of the block carrier.** It multiplies the groups K, and the place system has 2 + 2(K − 1) unknowns per place. II went from 85 to 258 s.

Chapter XX by block (35 carriers) held B, its permuted copy and every group's coupling at once: 32 GB.
- B is now written straight into the factor's row order, a chunk of places at a time.
- The Newton step is unchanged: equal to the committed solver's to ≤ 3·10⁻⁹ relative on VII, the worst components being the ICAR's near-null directions.
- The dense Y = L⁻¹PB still grows as K²: XX by block remains about 7 GB.

## The mean's likelihood (OPEN_QUESTIONS 8)

The mean fitted with the negative binomial likelihood (`Monolith(likelihood="nb")`, φ re-estimated every outer), against the Poisson quasi-likelihood. Held-out NB log-likelihood per death:

| block | Poisson | NB | NB − Poisson |
|---|---|---|---|
| VII | −10.37605 | −10.39030 | −0.014 |
| XV | −8.10250 | −8.60606 | −0.504 |
| VI | −2.08180 | −2.08080 | +0.001 |
| II | −2.54725 | −2.54600 | +0.001 |

- NB gains about a thousandth of a unit per death on the large chapters and loses on the sparse ones. On XV it loses badly; why is not measured.
- It is 2–4 times slower, because every evaluation streams every cell.
- **The Poisson quasi-likelihood stays.** The NB fit stays available for a block where a later measurement favours it.
- IX's NB fit was lost to a machine sleep and is not reported.

## VII's outers are path-dependent

Refitting VII after the B change (the same Newton step to 10⁻⁹) ended at a different optimum: 16 outers against 17, φ 1.1·10⁵ against 32, held-out −10.320 against −10.376. Its strengths sit on a flat ridge where last-bit differences choose the endpoint.

## Two carriers: the profile by block, history and geography by group

`assemble(profile="block", geography="group")`:
- **The block carries** the levels and the age–sex profile.
- **The outer group carries** history, place effects and season (`BlockData.group_outer`).
- **In the solver,** the place system's reduced coordinates are the outer groups' contrasts, mapped to the blocks' rows. So its size follows the outer group: 12 against 30 unknowns per place on XIII.

**Checks.**
- With no outer group, the Newton step equals the committed solver's to ≤ 3·10⁻⁹ relative.
- With one, the gradient equals finite differences to ≤ 6·10⁻⁷ relative on every component, the tied ones included.

| block | group (sex zeros) | block | block + group geography |
|---|---|---|---|
| II | −2.45893, 85 s | −2.37752, 258 s | −2.38340, 90 s |
| XIII | −4.49440, 33 s | −4.43809, 116 s | −4.44377, 69 s |
| XX | −3.33967, 75 s | −3.21416, 2,174 s | −3.22970, 192 s |

The table gives held-out NB log-likelihood per death. The geography carrier keeps 88–93 % of the block carrier's gain at near the group carrier's cost. Most of the block's gain is therefore the profile, not per-block geography.

## Admissibility: sex, age and underlying-cause eligibility

**The source.** pegasus_data's `code_attributes` (6254ed6) adds NCHS Instruction Manual Part 11 (2023), Table G, to the release's RESTRSEXO.
- **Table G** lists the age/cause and sex/cause edits for codes valid as underlying cause, each absolute or conditional.
- **The two sex sources never contradict.** 885 codes agree, 117 are restricted by DATASUS only, and 2 (Q97, Q98) by NCHS only.
- **DATASUS publishes no age table.** The SIM critiques ("Óbito com restrição de idade") are applied in the system but are neither published nor carried in the DO files.

**The rule** (`monolith._admissible`):
- A category's admissible cells are its sex and Table G's *absolute* age limit.
- A band is excluded only when it lies wholly outside the limit. The 28-day edits fall inside POPSVS's first band and do not act.
- Conditional edits are not zeros: the obstetric 10–54 years, for instance.
- For SIM's underlying cause, codes that cannot be one are not leaves.
- Records in excluded cells are counted by reason. The counts per chapter are in `data/admissible_counts.txt`.
  - Over SIM 2010–2021's 15.9 M deaths in 19 chapters, 233 records are left out: 212 by age (199 in XVIII), 18 as not an underlying cause, 3 by sex.
  - SIM's own critiques enforce these rules at entry. The rules' effect is on the expectation, which no longer places a category's deaths in cells it cannot occur in, not on the records.
  - SIH-RD 2010–2023 (principal diagnosis) breaks them more often (`data/admissible_counts_sih.txt`): XV 332 records (men with pregnancy diagnoses), XIV 438 and II 225 by sex, IV 164 by age. Hospital records pass no critique of the kind.
- **End to end on XIV** (genitourinary; three single-sex blocks):
  - expected deaths are zero in the excluded sex: N40–N51 16,519 men and 0 women; N70–N77 and N80–N98 0 men;
  - the Laplace draws run under the new carriers: 64 draws, total 454,517 ± 852 against the MAP's 443,783.

**The start (`_initialise`) was wrong under age masks, and was corrected before any fit was read.**
- Centring the profile over whole sex rows read the masked ages' zeros as data: IV started at 2.7 times its optimum.
- On the admissible cells alone, the IPF's free scale per group drifted: A33, two admissible cells, went to −36, and its level to +240.
- Crediting only the row means to the levels lost the column part: I started at 8 times its optimum.

**Now:**
- each group's profile and course are put at mean zero, with the scale on the leaves;
- the part the centring removes is split by least squares into the group's level and the overall profile;
- the excluded ages start on the line through their nearest admissible bands.

Starts with the rules on now match those with the rules off (I: 227,124 against 213,350; IV: 1,155,821 against 1,152,722), and the fitted objective is lower with the rules on.

**A third defect showed on chapter V in the refits.**
- A small restricted group (F53, women 10–54) has margins that are mutually inconsistent once a margin with no events counts half an event.
- The IPF then has no solution, and its free scale overflowed before the gauge was fixed.
- Each group's course and profile margins are now rescaled to its leaves' total, and the gauge is fixed at every sweep.
- V now starts at 540,775 and reaches 494,625 after eight Newton steps. The starts of I, IV and IX are unchanged (227,100; 1,155,819; 2,616,540).

## The adopted configuration, held out (`data/q_final.log`)

ADR-0024's defaults (block profiles, group geography, admissibility, the corrected start), fitted one block at a time on a calm machine. The table gives held-out NB log-likelihood per death, 2022–23.

| block | group carrier, rules on | adopted (block profile, group geography) | difference per death | seconds (adopted) |
|---|---|---|---|---|
| IX | -1.63715* | -1.63487 | +0.0023 | 37 (5 outers) |
| II | -2.45893 | -2.38341 | +0.0755 | 88 (11 outers) |
| I | -6.01400 | -6.01338 | +0.0006 | 574 (10 outers) |
| IV | -2.04701 | -2.04721 | -0.0002 | 97 (9 outers) |
| XV | -8.10559 | -8.09767 | +0.0079 | 77 (10 outers) |
| XIII | -4.49440 | -4.44564 | +0.0488 | 95 (11 outers) |
| VI | -2.08184 | -2.08184 | -0.0000 | 179 (14 outers) |
| VII | -10.32000* | -10.22396 | +0.0960 | 101 (9 outers) |
| XX | -3.33967 | -3.22976 | +0.1099 | 257 (7 outers) |

- `*` marks the group carrier's earlier fit, before the admissibility rules, which leave out at most two of the block's records.
- I, IV and VI: level (within 0.0006). Block profiles cost nothing where a group's categories share their ages and sexes.
- I's held-out years span the fall of COVID-19 deaths (B34: 425,098 in 2021, 66,088 in 2022, 10,444 in 2023), which no course fitted to 2010–2021 anticipates. How much of its −6.01 per death (deviance 26.5) that accounts for is not measured.

## BYM2 coordinates for the strengths: not adopted

The strengths' Newton step was taken in (log σ², logit φ) for each place pair and mapped back exactly. Results:

| block | BYM2 | before |
|---|---|---|
| VII | −10.107, 9 outers | −10.32, 16 outers |
| VI | −2.08216, 13 outers | −2.0818, 9 outers |
| II, IX | unchanged | — |

The code was removed.

## The interaction's start on sparse blocks (a defect before today)

The low-rank interaction (ADR-0021) failed its first factorisation on XIII (66 k deaths) under every carrier, the group carrier included.

**The cause** is its start. The weighted least squares of the base fit's residual cube divides (y − μ) by μ with a unit ridge. Where μ is tiny and deaths occur, that set ω to 32 and the interaction to 438 on the log scale, and the Hessian (10²⁰⁶) is beyond any factorisation. IX (788 k deaths) never met it.

**Now** each component's scale is chosen on the model's own objective, from 0 to 1 times the least-squares start (ω carries it). The start can then only improve on the base fit.

**Also changed:** ψ is now centred within each geography carrier's active leaves (ADR-0024 item 5).

**The interaction's strengths had no step radius.** ix_os and ix_ov were clipped at ×100 only, while the base strengths have Rprop's radius. On XIII they flipped 71 ↔ 0.7 every outer, and the objective with them (281 k ↔ 290 k; `data/ix_init_fix.log`). They now share the base strengths' radius rule.

**Verification:**
- IX at rank 1 under the group carrier converged in 12 outers, held-out −1.62539 against the morning's −1.62807 (`data/ix_r1_regress.log`).
- XIII at rank 1 with both fixes (`data/ix_radius.log`): no factorisation fails. The ω strengths wander along their own s/v ridge for a dozen outers, then settle. The fit converges in 36 outers (891 s beside five other jobs), held-out −4.44605 against rank 0's −4.44564: on this sparse block the term does not pay, which is O2's question to answer across blocks.

## The strengths' stopping tolerance

The outers stop when the strengths' predicted LAML gain falls below `PEGASUS_LAML_TOL`. At 0.1 units, chapters on the BYM ridge ran 11–14 outers. At 1.0, held out on the same code (`data/laml_tol_1.log`):

| block | outers 0.1 → 1.0 | held-out NB loglik per death 0.1 → 1.0 |
|---|---|---|
| II | 11 → 7 | −2.38341 → −2.38341 |
| VI | 14 → 10 | −2.08184 → −2.08184 |
| XIII | 11 → 11 | −4.44564 → −4.44564 |

The default is now 1.0. XIII's outers end on the strengths' change, not on the gain.

## Geography by chapter: not adopted

`geography="chapter"` gives one place effect and one course per block, with each leaf's own place deviation, and a place system of 2 unknowns per place. Held out against group geography (`data/q_geo_chapter.log`):

| block | NB loglik per death, change | outers |
|---|---|---|
| II | −0.0009 | 8 |
| IX | −0.0016 | 4 (21 s against 37 s) |
| XX | −0.0116 | 6 |

XX loses about 3,500 units over 304 k deaths: transport accidents, falls and homicides do not share a geography.

Chapter I goes the other way: −4.22388 against −6.01338, in 53 s and 4 outers against 574 s. The geography carrier also carries each group's course. **Tested** (`data/heldout_by_group_I.json`, held-out 2022–23 by group):
- **Group geography.** B25-B34's own course, continued linearly from 2020–21, expects 2,548,583 deaths against 76,813 observed. That holds 97 % of the chapter's deviance; the other groups are near their observed counts (A30-A49: 66,644 against 61,105).
- **Chapter geography.** The shared course spreads the surge over every group: A00-A09 expects 103,173 against 10,671, and B25-B34 1,273,186. The total deviance is smaller only because the shock is diluted.

Chapter I's held-out figures therefore measure the history's extrapolation across a shock, not the carriers (OPEN_QUESTIONS 9). The groups' place effects carry signal, so the group stays the geography carrier. `chapter` remains an option of the same mechanism.

## The defaults on SIH (`data/q_sih_adopted.log`, `data/q_sih_group.log`)

SIH-RD fitted 2010–2021 and held out 2022–23. The adopted configuration (block profiles, pooled group geography, admissibility) is set against the group carrier:

| block | group carrier | adopted | change per admission | seconds |
|---|---|---|---|---|
| II | −1.93451 | −1.87749 | +0.057 | 70 → 57 |
| XV | −0.53066 | −0.53066 | 0 | 67 → 72 |

XV is all female, so its blocks and groups split alike.

## Small geography carriers pooled (adopted)

`geo_pool=0.01` sends the geography carriers that hold less than 1 % of the block's events to one pooled carrier. Their place effects are shrunk to nothing, and each costs two unknowns at every place. Held out against unpooled group geography (`data/q_geo_pool.log`; seconds beside other jobs):

| block | carriers | NB loglik per death, change | seconds |
|---|---|---|---|
| I | 21 → 8 | +0.47457 | 574 → 249 |
| IV | 8 → 6 | −0.00065 | 97 → 54 |
| XX | 8 → 6 | −0.00079 | 257 → 214 |

- **The default is now `GEO_POOL = 0.01`.** The data key names it only where pooling happens.
- **The losses on IV and XX** are about 200 units each.
- **I's gain** is the same extrapolation artefact (above) and does not count for or against pooling. The decision rests on IV and XX and on the speed.


## The courses' held-out forecast (OPEN_QUESTIONS 9)

One fit per block (SIM.DO 2010–2021, current defaults), and every forecast of the courses scored on 2022–23 (`data/history_compare.json`). Each cell gives the NB log-likelihood per death, with the expected deaths in brackets.

| block | linear | robust | level | median | observed |
|---|---|---|---|---|---|
| I | -5.53881 (2,706,590) | -3.70957 (126,962) | **-3.48441** (1,010,379) | -3.69202 (128,068) | 205,016 |
| IX | -1.63503 (849,703) | -1.63611 (870,510) | **-1.63295** (795,733) | -1.63687 (878,326) | 787,877 |
| II | -2.38386 (491,895) | -2.38429 (517,974) | **-2.38373** (489,873) | -2.38426 (517,503) | 498,964 |
| XX | -3.23055 (307,593) | -3.23842 (321,405) | **-3.22965** (299,291) | -3.23860 (320,128) | 304,525 |
| XIII | -4.44680 (12,170) | -4.44944 (13,252) | **-4.44004** (12,734) | -4.44786 (13,319) | 14,312 |
| IV | -2.04785 (207,753) | -2.04770 (193,396) | **-2.04295** (201,530) | -2.04821 (193,072) | 181,759 |
| X | -1.67901 (280,500) | -1.65476 (359,688) | -1.66976 (295,880) | **-1.65419** (362,986) | 345,919 |

- The flat forecasts beat the linear one on every block. `level`, which at the annual grain is flat at the course's last fitted value (a damped slope with d = 0; the twelve-period mean is the monthly grain's), is best on six of seven; X prefers `robust` and `median`.
- **This window follows COVID-19:** every chapter's 2020–21 rose, and the linear continuation overshoots (IX 849,703 expected against 787,877).
- **Both windows, with Gardner & McKenzie's damped trend** (the last slope damped by d per year; `data/history_compare_damped.json`). Each cell is the change in held-out NB log-likelihood per death against linear:

| window | block | damped8 | damped5 | level | robust |
|---|---|---|---|---|---|
| 2018-2019 | I | +0.0033 | +0.0062 | +0.0072 | -0.0004 |
| 2018-2019 | IX | +0.0005 | +0.0007 | +0.0002 | -0.0037 |
| 2018-2019 | II | -0.0000 | -0.0000 | -0.0000 | -0.0001 |
| 2018-2019 | XX | +0.0015 | +0.0029 | +0.0041 | -0.0018 |
| 2018-2019 | XIII | -0.0002 | -0.0009 | -0.0026 | -0.0224 |
| 2018-2019 | IV | +0.0001 | +0.0001 | -0.0002 | -0.0038 |
| 2018-2019 | X | +0.0022 | +0.0042 | +0.0054 | +0.0033 |
| 2022-2023 | I | +0.6822 | +1.3900 | +2.0544 | +1.8292 |
| 2022-2023 | IX | +0.0011 | +0.0020 | +0.0021 | -0.0011 |
| 2022-2023 | II | +0.0001 | +0.0001 | +0.0001 | -0.0004 |
| 2022-2023 | XX | +0.0008 | +0.0012 | +0.0009 | -0.0079 |
| 2022-2023 | XIII | +0.0020 | +0.0043 | +0.0068 | -0.0026 |
| 2022-2023 | IV | +0.0017 | +0.0035 | +0.0049 | +0.0002 |
| 2022-2023 | X | +0.0054 | +0.0094 | +0.0092 | +0.0243 |

- **The adopted annual default is `damped5`** (d = 0.5), the BP tier's own annual default.
  - Over 2018–19, a window without a shock, it is never worse than linear by more than 0.0009 per death.
  - It gains everywhere over 2022–23 (I +1.39).
  - `level` wins slightly more often, but loses 0.0026 on XIII without a shock.
  - Outside I, the two are level: 2018–19 +0.0070 against +0.0069; 2022–23 +0.0205 against +0.0240.


## Fields across blocks (lists)

**Items.** The Ministry's lists' items are fields across blocks (`Registry.list_fields`). An item enters when it holds whole categories:

| list | fields | left out (part of a category) |
|---|---|---|
| CID-BR-10 | 129 | 0 |
| AVOIDABLE-5-74 | 73 | 7 |
| ICSAP-GROUPS | 14 | 5 |
| SIM-POUCO-UTEIS | 2 (Tp 3, Tp 5) | 3 (Tp 1, 2 and 4 are written at the 4th character) |

**The expectation** is each block's fit summed (`Expectations._surprise_across`):
- the extra-Poisson variances add, Σ_b Σμ²/φ_b;
- the population's standard deviations add.

**Checked at B1 on SIM 2010–2023 refits,** on the five ICSAP groups that span two chapters:
- each total equals its parts' sum: heart failure, IX + X: 396,240 + 38,436 observed, 434,675 expected;
- every one is calibrated, KS 0.004–0.020.

**Conserved levels** (§8.6, `Registry.conserved`):
- A node's conserved level is its family (the outermost group), plus R00–R99, plus Y10–Y34 for an external cause.
- C53 → `CONS[C00-C97]` (II + XVIII, 178 categories); X95 → `CONS[X85-Y09]` (+ Y10–Y34).
- `CONS[I20-I25]` at B1: 2,631,335 deaths observed and expected, calibrated (KS 0.006, the field's φ).
