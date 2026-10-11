# A composition read against the place's own mix (OPEN_QUESTIONS 17, 2026-10-11)

**Scenario.** SINAN-TOXG notifications 2019–2025 (86,268 cases, the stored fit, `contiguity`), the group lens on every
composition column. Before: `Session.by_composition` expected B0 by age and sex times Brazil's share of the value in
the cell, so a place whose people differ from Brazil's restated its demography. Driver: scratchpad scripts calling
`Session.scan("*", "group_disparity")` and `Session.composition_null`. Code: branch `composition-own-mix` on `scope-v2`.

**Change.** For a non-race composition (`tools.own_mix`) a place-year's expected events of value v are its observed
total times the place's mix in its **other years**, shrunk by empirical Bayes toward the rest of its state's mix, that
toward the nation's (Dirichlet–multinomial per level, concentration by the method of moments:
`surveillance.concentration`, now taking a per-row centre). "Not recorded" is a value. No population is involved.
The lens groups are the (year, value) pairs (`tools.read_composition`): each year's reference leaves it out, so
summed over years the departures nearly cancel and a whole-span lens saw almost nothing (first attempt: 0 findings
even for a planted year of 100 % unrecorded). Race keeps its own-population reading and its whole-span groups.
Concentrations on TOXG: states around the nation 14–54, places around their state 3–25.

**Null.** `Session.composition_null`: each place-year's events redrawn as a multinomial of its observed total over the
place's one mix (years pooled, shrunk as above), the mix re-estimated from the drawn counts, the same lens. 30 worlds
per column, 7 columns: 4 of 210 column-worlds held any finding (all CRITERIO, 4 of its 30 worlds, 1 finding each), 1.9 %
against q = 0.05. Drawing the worlds from the leave-one-year-out shares instead built a departure into them (a place
whose first year differed from the rest) and gave 1 finding in 30 of 30 TPAUTOCTO worlds: the null must be the
hypothesis, a mix that does not move. The flag `study._COMPOSITION` (uncalibrated) is lifted for non-race compositions;
its reliability line states this null.

**Result** (lens findings; the survey's 107 TOXG composition answers had passed the study's own filters):

| | before | after |
|---|---|---|
| TOXG, non-race compositions | 139 (EVOLUCAO 72, DOENCA_TRA 23, CS_GESTANT 21, CS_ESCOL_N 16, TPAUTOCTO 4, CRITERIO 3) | 30 (TPAUTOCTO 16, EVOLUCAO 7, DOENCA_TRA 3, CS_ESCOL_N 2, CRITERIO 1, CS_GESTANT 1) |
| TOXC, non-race compositions | 50 | 1 |
| race (both) | 20 + 9 | 20 + 9, unchanged |

Acre's TPAUTOCTO=3 deficit (Rio Branco, effect 0.0026, survey story 2) does not survive: Rio Branco reports "indeterminado"
almost never in any year, so it is its usual mix, not a departure from Brazil's practice. What remains are changes of
recording within a place: Vitória da Conquista (293330) 2019, where all 56 TPAUTOCTO were "not recorded" (expected 12) and
"Sim" was 0 against 43.7, the same year in CRITERIO ("Laboratorial" 0 of the usual) and EVOLUCAO ("Vivo"); Campo Grande/MS
(500270) EVOLUCAO from 2021: "not recorded" 0 a year against 5–9 expected after 42 in 2019; Ponta de Pedras/PA (150570) TPAUTOCTO 2019,
206 cases all "not recorded" against an expected "Não" 42, "Indeterminado" 30 (the place's later years hold one case each, so its state's mix leads).

**Power, and limits.** Planted in the 10 top places, a year's cases moved to "not recorded": 50 % found 1, 90 % found 2,
100 % found 3 (the lens ignores log-SIR spread under 0.2 and divides large cells' deviance by their NB factor).
The reference includes the departing year, so a large departure also moves the other years' expectations; a trimmed
reference would be sharper (Rio Branco 2025: 514 unrecorded against 326 expected, not flagged). A difference that
holds in every year is invisible by construction: the question is "did the place move", not "is it unlike Brazil".
