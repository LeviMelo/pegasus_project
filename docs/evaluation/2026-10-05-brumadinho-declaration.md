# Declared hypothesis: acute lower-respiratory admissions after the Brumadinho tailings-dam rupture

**Status.** Declared 2026-10-05, before any Brumadinho SIH data were read. Ledger id `d5938be360254838`; spec at `data/brumadinho_declaration.json`. Not yet tested.

**Origin.** The Rio Doce test failed: its lead was one facility's pre-rupture burst. Its secondary outcome J20–J22 showed Mariana at 34 admissions against 2.5 expected. That is exploratory and not claimable from the same data, so it is tested on an independent disaster: the rupture at Brumadinho (MG) on 2019-01-25.

**Test.**
- **Outcome:** SIH-RD J20–J22.
- **Primary place:** Brumadinho (310900).
- **Secondary places:** the downstream Paraopeba municipalities, fixed from a named primary source before any data are read, and analysed separately.
- **Time:** monthly, February 2019 to January 2020.
- **Expectation:** BP trained through December 2018. The training baseline's facility shares are reported first, so that no single-facility burst enters the expectation (the lesson of Rio Doce).
- **Negative control:** chapter XI admissions, same place and months.

**It passes only if:**
1. observed/expected ≥ 1.2 at the primary place, with the minimum-effect p < 0.05;
2. the excess is not concentrated in one facility outside the municipality;
3. the negative control shows no excess.

**Honesty notes.** A pass is an association in time and place. Admissions measure care-seeking and recording as much as exposure. The disaster also caused injury and displacement, which may change admissions for many reasons.
