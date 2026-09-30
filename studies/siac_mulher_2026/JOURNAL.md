# Journal: SIAC Mulher 2026

Data: pegasus_data (branch `linkage`, 2026-09-30), data home `~/pegasus_linkage`.
Scripts here; outputs in `results/` (the linked-births parquet is local only).

## EPI-01: recorded maternal heart disease × outcomes (linked SIH–SINASC 2022)
- Link: `sinasc_births_to_delivery_admission`, deterministic, BR 2022:
  1,515,701 of 2,520,744 births, chance 0.53% (upper 0.55%), obstetric
  diagnosis 98.0% (pegasus_data EVALUATION, national linkage).
- Exposure: any diagnosis position (DIAG_PRINC, DIAG_SECUN, DIAGSEC1–9).
- **Threat: secondary-diagnosis under-recording.** Measured: 12.2% of linked
  delivery AIHs carry any secondary diagnosis; 2,251 of 2,823 hospitals
  (51.2% of births) never record one. Recorded heart disease: 776 (0.05%)
  against an expected 1–4%. The exposed group is "recorded heart disease",
  selected towards hospitals that code; stated in the abstract.
- Maternal death rests on 6 events: aRR 32.6 (14.5–73.4) not reported; the
  proportions are given with exact intervals instead.

## EPI-04: travel for delivery with recorded heart disease (SIH 2022)
- Universe: IDENT 1 AIHs with any chapter-XV code; heart disease as above.
- **Same threat:** hubs such as Lages (132) and São José do Rio Pardo (65)
  may be hospitals that code, not referral centres. Stated in the abstract.

## EPI-02: maternal deaths, original vs final cause (SIM 2014–2023)
- `epi02.py` then `epi02b.py` (refined certificate-line definition).
- **Plausibility:** maternal deaths per year (1,717 in 2014; 3,038 in 2021;
  1,373 in 2022) match the Ministry's published counts within a few deaths.
- **Definition change:** the first line count included I46 (cardiac arrest),
  a mode of dying; the refined definition excludes I46, I95 and I99 (2,990 →
  2,825 non-CVD maternal deaths with a CVD mention).
- **"Hidden" deaths:** 626 deaths during pregnancy and 251 up to 42 days
  postpartum with a non-maternal circulatory underlying cause. By ICD rules,
  a circulatory death in pregnancy is usually indirect maternal (O99.4). Not
  verified case by case; the abstract says "sugere".
