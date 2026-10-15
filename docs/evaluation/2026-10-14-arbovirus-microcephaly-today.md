# Arbovirus → microcephaly, re-tested on the current code (2026-10-14)

**Why.** The author asked whether the system's long failure to recover the documented link (Zika in the 2015 Northeast
epidemic → microcephaly 6-9 months later) is a data problem or the statistical machinery's. Missed by E_w (2026-10-05:
a plateau at lags 0-6), by its prewhitened variant (2026-10-06: a lag-0 coincidence) and, at q, by the relation estimator
(2026-10-11: peak at lag 6-7, 0 of 459 rows reported).

**Regime.** Working tree on d94b7f4 (with the field list of the study's scope, unrelated), the real root, store adopted
across today's key changes. `scratchpad/run/arbo_relate.py`, artefacts `data/probes/arbo_relate.{json,log}`, as the
2026-10-11 evaluation ran it: `tools.relate` on B1 monthly innovations, Northeast (macro-region 2), lag profiles; SINAN-CHIK
with SINASC Q02 (CODANOMAL code list) 2014-2019, window 2014-01..2017-12, lags 0-12; SINAN-ZIKA with Q02 2015-2017, lags 0-8.
The lake no longer held CHIK after 2015, ZIKA or DENG (listed, not decoded; the 2026-10-11 run had read them): CHIK
2016-2019 and ZIKA were fetched again. DENG was left out, as on 2026-10-11 (its B1 failed calibration), and is a
70 MB-a-year read.

**Result.**
- **Zika → Q02 is recovered at q.** Two rows are reported, both at the local band (~20 places): lag 7 (ρ 0.068, z 4.76,
  p 1.9e-6) and lag 8 (z 3.70, p 2.2e-4). The lag profile peaks at 7 months at nearly every support: national course
  ρ 0.95, the ~492-place band ρ 0.59. The reverse (Q02 leading Zika) has |z| < 1 at every support.
- **Chikungunya → Q02** has the same lead, peaking at 5-8 months (national ρ 0.50 at 5, ~492 places ρ 0.53 at 6), at
  z 2.1-2.9: not reported. Its reverse is null or negative.

**Reading.**
- The data bound the question. Zika was notifiable only from 2016, after the wave that caused most cases (2015's are
  retrospective). The arboviral proxies are partial: the 2016 dengue and chikungunya epidemics were followed by no
  microcephaly. And one wave in a 3-4 year window is few effective observations. Where the specific exposure is in the
  data (Zika's notifications), the estimator finds the documented lag at q. The general proxy (chikungunya) shows it
  below q.
- The early misses were the machinery's: a per-lag correlation of surprises cannot see a lag inside one wave.
- What changed since 2026-10-11 is not established. The relation estimator is the same. Its inputs are not: B1's noise
  structure (the models' round two), microcephaly's monthly fit (today's code-list readers), Zika's files fetched again.
- Control: Down syndrome (Q90) in the same runs, below.

**Control** (`data/probes/arbo_control.{json,log}`: Down syndrome, Q90, in place of Q02, the same runs). Nothing is
reported, for either arbovirus. But Zika → Q90 also peaks at lags 7-8 in the national course (ρ 0.54-0.55, z 2.4) and
at ~1,746 places (ρ 0.30, z 2.5). Part of the coarse "lag 7" is therefore not microcephaly's. It is most likely SINASC's
anomaly recording, raised for every anomaly by the surveillance that followed the November 2015 emergency: a recording
change timed with the epidemic, which a correlation at coarse supports cannot tell from the effect. The specific
evidence is the local band: Q02 z 4.76 at lag 7, where Q90's largest is 2.5.

**The declared test (the same day; this corrects the verdict first written).** A study's relation hypothesis
(`component: relation`, `study._relation_hypothesis`). Zika leads Q02 by 6-9 months over 2015-2017, the cumulative
association over that window only, one test per support with Holm over the supports, and Down syndrome as the control.
Artefact `data/probes/relation_hypothesis.log`.
- Pernambuco alone (the study's area: 185 places, four supports): not supported (state course ρ 0.04, p 0.56).
- The Northeast (`macro: [2]`, its states' own fits): **not supported**. The regional course gives ρ 0.33, p 0.029,
  Holm 0.26. The local band that had given z 4.76 gives p 0.40. The control's course is ρ -0.20, the opposite sign.

The afternoon's two reported rows came from national fits cut to the Northeast. Refitted on the Northeast's own
states, the local signal does not reproduce: it was fragile, not a recovery.

**Verdict.** No test of the system establishes Zika → microcephaly. The regional timing points the documented way (6-8
months, p 0.03 at one support), and the control does not. The bound is the data: one wave, the exposure notified only
from 2016, three years. That a relation's evidence moves with the area its fields were fitted on is a fragility of the
innovations. It is recorded beside OQ 21.

Two general steps follow, recorded in OPEN_QUESTIONS:
- a known link should be tested as a declared relation hypothesis: one test of the documented window, not one row among
  hundreds;
- the outcome's recording should be controlled: a sibling anomaly as a second outcome, or the share of births with any
  anomaly recorded.
