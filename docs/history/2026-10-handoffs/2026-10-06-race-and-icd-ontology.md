# Handoff to pegasus_data: race in the population tensor, and the ICD ontology (2026-10-06)

**What PegaSUS needs, and why.** These are requests from ARCHITECTURE revision 2: §3.3 (the ICD ontology, work package O4) and §3.4 (race, work package O3). Meaning and data belong in pegasus_data (§2, rule 2), so both are built there and read through `gateway`.

## A. Race in `population-account-3/4` (O3)

The tensor carries total plus five declared races, 2000–2030 (pegasus_data decision 0151). The race input has four measured limits:

1. **The 2000 census's "sem declaração"**: 1.207 M people, 0.71 % of the sample (SIDRA 2093, measured 2026-10-06 on `pegasus_core_data`). `load_race` keeps only the five races, so the undeclared are split like the declared.
   - **Asked:** allocate them, without denting the official totals and without making "undeclared" a denominator of its own.
   - **How:** impute each undeclared person's race from IBGE's public 2000 sample microdata, with a model of race given age, sex, municipality, education, urban residence and the declared races of the other members of the household. Fit it on the declared; carry multiple imputations into the race intervals.
   - **The 2010 and 2022 residuals** (6,608 and 11,119) are split by their cell's declared shares.
   - **Report** a bound for race-dependent non-response in the manifest.
2. **2000's ten-year bands spread flat.** 2093 publishes five-year bands to 29, ten-year bands 30–79, then 80+.
   - **Asked:** split each 2000 band by the within-band shape of the same cohorts' single-age shares in the 2010 full count (the 2000 band 30–39 is the 2010 cohort 40–49), constrained to the band's total. Measure the shape's error on 2010 itself, by aggregating 9606 to the 2093 bands.
3. **The sample and the full count.** 2000 is a sample; 2010 and 2022 are full counts.
   - **The figure:** in 2010 the sample (2093 or 136) and the full count (9606) differ: white 90.62 M against 91.05 M.
   - **Asked:** measure the ratio of full count to sample by race × band × state on 2010 (both are published) and apply it to 2000, with its spread in the interval.
4. **The 1990s carry race total only.**
   - **Asked:** read the 1991 census's race by age and municipality (locate its SIDRA table) and carry race through the 1991–1999 backcast. SIM records race from 1996.

**Also asked:**
- **A recorded-race confusion for adults other than women 15–49** (pegasus_data decision 0149 measured women through their births). Candidates: SIM ↔ SIH records of the same person (both recorded, a recorded-to-recorded matrix); SINAN ↔ SIM. Or a statement that no Brazilian source identifies it, with the sensitivity band to use.
- **The unknown-race share** of SIM, SINASC, SIH (with the per-hospital-month flags of pegasus_data decision 0128) and SINAN, by place and year, as a modelled field.

5. **Single ages 0–19.** The tensor's single ages are the vital account's own path. Asked:
   - validate them by single age against the 2010 and 2022 censuses and the 2007 Contagem;
   - tie children's migration to the account's schedule for adults aged 20–39.

   PegaSUS now reads single years 0–19 (ARCHITECTURE §3.2).

## B. The ICD ontology (O4)

**State.** `code_trees` ships the ICD-10 tree (chapter → group → category → subcategory, 14,563 nodes, validity), and `code_lists` seven concept lists. The DATASUS CID-10 release is harvested in `sources/cid10csv_v2008.zip` and not built: chapters, groups, categories, 12,451 subcategories, ICD-O. Its per-code attributes `CLASSIF`, `RESTRSEXO`, `CAUSAOBITO`, `REFER` and `EXCLUIDOS` are not in any shipped product.

**Asked, as one versioned product (`icd_ontology`)**, following ARCHITECTURE §3.3:

1. **Attributes per code, by release:**
   - the dagger/asterisk role;
   - the sex restriction;
   - acceptability as an underlying cause;
   - references and exclusions.

   From the DATASUS release, with the current release fetched as well as the 2008 one, and the validity window of each.
2. **Age plausibility per code**, from the SIM and SIH critique rules or SIGTAP's CID table. Locate the source.
3. **ICD-9.** The tree (SIM 1979–1995), and an ICD-9 → ICD-10 map with comparability ratios. pegasus_data open question 69 records that the kits hold none: locate a published one.
4. **ICD-O** morphology, as its own tree.
5. **Lists to add:**
   - WHO mortality tabulation list 1;
   - the SIH morbidity list (`LISTA10`, open question 69);
   - garbage codes by level (the GBD classification; licence checked first, as pegasus_data decision 0140 did for the cause hierarchy);
   - the work-related disease list (LDRT, Portaria 2.309/2020);
   - notifiable disease ↔ ICD codes for every SINAN family.
6. **External-cause axes:** intent × mechanism for V01–Y98, and place of occurrence by the 4th character of W00–Y34.
7. **A typed relation graph:**
   - *sequela of*;
   - dagger → asterisk;
   - *excludes*;
   - **exchange pools**: the codes coders trade, with the source of each claim;
   - procedure ↔ diagnosis compatibility (SIGTAP);
   - notifiable disease ↔ ICD.

**Each component is served with its source and validity**, never inferred from a match rate alone (pegasus_data's own rule: a semantic claim cites a source or tests the rival reading).
