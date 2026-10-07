# Robust stage B: category courses and trimming, variant by variant

**Regime.** pegasus_core `design-v0`, the commit carrying this entry. SIM.DO chapter I, 2010–2023. Script: the scratchpad check `hcat_check.py` (robust fit, then each field's observed and expected yearly totals); logs `data/logs/hcat_check{,2..9}.out`.

**What is counted, and why.** Each field's expected yearly total against its observed one, in ordinary years and in the event's years:
- A95, yellow fever;
- B34 and B25–B34, COVID-19 and its group;
- A90, dengue;
- A00–A09, diarrhoea.

A sound background must track ordinary years and must not follow the epidemics.

| variant | yellow fever 2017–18, expected (observed 195, 257) | B25–B34 ordinary years, expected (observed 120–180) | verdict |
|---|---|---|---|
| robust v1, no category courses | 4, 4 | 32–66 (the siblings near zero: COVID-19 sets the group's course) | siblings broken |
| course fitted once after the mean | 25, 35 | about 45 (unchanged) | a post-fit sweep cannot move the group's course |
| alternation, course level free | (did not converge: the level drifted between `th_cat` and the course) | – | identified by centring |
| alternation, centred courses | 22, 28 | about 45 | trimming flagged the siblings' ordinary counts before courses existed and imputed them away |
| a structure round first, then trimming | 45, 80 | 83–126 | siblings fixed; diffuse outbreak partly absorbed |
| courses without the flagged cells | 44, 75 | 83–126 | same; cell-level flags miss one-death-per-town outbreaks |
| + SQUAREM (step bounded to [−4, −1]) | 44, 76 | 81–131 | same fixed point; trimming rounds converge in 3–5 steps |
| + regional flags at the cells' level (0.005) | 8, 4 | 56–75, B34 halved | over-trimmed: 33,677 then 54,600 cells; rejected |
| + regional flags by BH, cells above expectation only | – | – | one-sided: 15,636 then 27,011 cells; rejected |
| + regional flags by BH, regions missing whole | – | – | still runaway: 48,195 then 161,661 cells (null ignores N1's spatial share); rejected |

**Adopted (v7):**
- a structure round, then two cell-level trimming rounds;
- the mean and the category courses by SQUAREM-accelerated alternation;
- courses fitted without the flagged cells;
- flagged cells imputed by their full expectation over sex-age groups.

Diarrhoea and dengue track their observed totals within a few per cent.

**Still open.**
- **Diffuse outbreaks.** They are partly absorbed until regional trimming has a calibrated null (the replicates of `multiscale.peaks`).
- **Cost.** About 15 minutes per chapter on the CPU.
