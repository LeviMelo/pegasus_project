# ADR-0024: The ICD in the model: profiles by block, history and geography by group, and admissible cells only

**Date.** 2026-10-06. **Status.** Active. Answers OPEN_QUESTIONS 3 (the profile level) and closes the structural-zero items of ARCHITECTURE §3.3 and §4.2.

**Evidence.** `docs/evaluation/2026-10-06-icd-structure.md`. SIM.DO fitted 2010–2021 and held out 2022–23. On the stored chapter II fit, the group carrier expected 53 % of cervical-cancer and 52 % of breast-cancer deaths in men.

## Decision

1. **Two carriers.**
   - `assemble(profile="block", geography="group")` is the default.
   - The innermost ICD group (the block; pegasus_data nests the tree since dff5162) carries each leaf's group level and its age–sex profile.
   - The outermost group under the chapter carries history, place effects and season.
   - The solver's place system follows the geography carrier.
   - Held out, this keeps 88–93 % of the all-block carrier's gain at near the group carrier's cost. II gains 0.075 per death over group in about the same time; XX gains 0.11 in 192 s, against the all-block carrier's 2,174 s.
2. **Admissible cells.**
   - A category occurs only in the age–sex cells its sex restriction and its absolute age limit allow.
   - The sex restriction comes from the DATASUS release's RESTRSEXO, or NCHS Part 11 Table G's absolute sex edit. The two never contradict.
   - The age limit is Table G's absolute edit, applied only to bands wholly outside it.
   - Carriers split by admissibility class. Each group's exposure is zero outside its cells. The profile is fixed at zero only on an excluded whole sex.
3. **Conditional edits** (highly improbable, not impossible) are not zeros. They are kept as attributes for recording-quality fields.
4. **Underlying cause.** For SIM's underlying cause, codes that cannot be one (asterisk codes, chapters XIX and XXI: the release's rule) are not leaves.
5. **Records are counted, not dropped.** A record in an excluded cell, or under an ineligible code, is counted as unallocated by reason ("sex the code excludes", "age the code excludes", "not an underlying cause") and is never modelled.

## Limits

- **Age bands.** POPSVS's first band is under 1 year, so the 28-day edits (sepsis A40–A41, diabetes E10–E14 coded in chapter XVI) cannot act. A single-age population (the account) would let more of Table G act.
- **US provenance.** Table G is NCHS's. The ICD's own absolute limits are in it, but its conditional list reflects US experience.
- **No ICD-9.** SIM before 1996 (ICD-9) has no admissibility table.
- **Stored fits.** Fits of chapters with restricted categories, and every fit under the old default carrier, are under other keys and must be refitted.
