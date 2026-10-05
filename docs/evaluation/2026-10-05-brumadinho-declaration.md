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

## Secondary places (fixed 2026-10-05, before any SIH data were read)

**Source.** Governo de Minas Gerais, Agência Minas, 2021-10-18, "Governo de Minas e instituições de justiça abrem Consulta Popular…": "Os 26 municípios considerados atingidos são: Abaeté, Betim, Biquinhas, Brumadinho, Caetanópolis, Curvelo, Esmeraldas, Felixlândia, Florestal, Fortuna de Minas, Igarapé, Juatuba, Maravilhas, Mário Campos, Mateus Leme, Morada Novas de Minas, Paineiras, Papagaios, Pará de Minas, Paraopeba, Pequi, Pompéu, São Gonçalo do Abaeté, São Joaquim de Bicas, São José da Varginha e Três Marias." These are the municipalities of the Termo de Medidas de Reparação of 2021-02-04 (Anexos I.3 and I.4; the Agência Minas piece of 2022-12-29 repeats the count of 26). Original URL `https://www.agenciaminas.mg.gov.br/news/pdf/111715.pdf`: on 2026-10-05 the host answers 503/302 to `/comunicado` (a temporary electoral-period notice, not a withdrawal of the document), so the text was read from the Wayback Machine copy of the same PDF (`https://web.archive.org/web/2024/https://www.agenciaminas.mg.gov.br/news/pdf/111715.pdf`).

**Secondary places, by residence, 25 municipalities** (the 26 minus Brumadinho), codes in `data/brumadinho_locus.json` (built by `data/brumadinho_locus.py`; the source writes "Morada Novas de Minas", read as Morada Nova de Minas): the list is the official set of affected municipalities of the Paraopeba basin including the Três Marias reservoir area, wider than the river's immediate downstream stretch. Whole municipalities; each is analysed separately from the primary place (O/E per municipality and pooled, reported beside, never in place of, the primary verdict).
