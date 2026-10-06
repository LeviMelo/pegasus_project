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

## The adopted configuration, held out (`data/q_final.log`)

ADR-0024's defaults (block profiles, group geography, admissibility, the corrected start), fitted one block at a time on a calm machine. The table gives held-out NB log-likelihood per death, 2022–23.

| block | group carrier, rules on | adopted (block profile, group geography) | difference per death | seconds (adopted) |
|---|---|---|---|---|
| IX | -1.63715* | -1.63487 | +0.0023 | 37 (5 outers) |
| II | -2.45893 | -2.38341 | +0.0755 | 88 (11 outers) |
| I | — | -6.01338 | — | 574 (10 outers) |
| IV | — | -2.04721 | — | 97 (9 outers) |
| XV | -8.10559 | -8.09767 | +0.0079 | 77 (10 outers) |
| XIII | -4.49440 | -4.44564 | +0.0488 | 95 (11 outers) |
| VI | — | -2.08184 | — | 179 (14 outers) |
| VII | -10.32000* | -10.22396 | +0.0960 | 101 (9 outers) |
| XX | -3.33967 | -3.22976 | +0.1099 | 257 (7 outers) |

- `*` marks the group carrier's earlier fit, before the admissibility rules, which leave out at most two of the block's records.
- I, IV and VI have no matched baseline yet.
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
- XIII at rank 1 with both fixes (`data/ix_radius.log`): no factorisation fails. The ω strengths wander along their own s/v ridge for a dozen outers, then the objective falls monotonically (282,425 → 282,360 → 282,317 by outer 15). Whether rank 1 earns its place on a sparse block is O2's question.

## The strengths' stopping tolerance

The outers stop when the strengths' predicted LAML gain falls below `PEGASUS_LAML_TOL`. At 0.1 units, chapters on the BYM ridge ran 11–14 outers. At 1.0, held out on the same code (`data/laml_tol_1.log`):

| block | outers 0.1 → 1.0 | held-out NB loglik per death 0.1 → 1.0 |
|---|---|---|
| II | 11 → 7 | −2.38341 → −2.38341 |
| VI | 14 → 10 | −2.08184 → −2.08184 |
| XIII | 11 → 11 | −4.44564 → −4.44564 |

The default is now 1.0. XIII's outers end on the strengths' change, not on the gain.
