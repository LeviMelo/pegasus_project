# Declared hypothesis: upper-respiratory admissions along the Rio Doce after the Fundão rupture

**Status.** Declared 2026-10-05, before any confirmatory analysis. It is registered in the production ledger (`pegasus_home/ledger`; spec copy at `data/rio_doce_declaration.json`). Not yet tested.

**Origin.** The SIH chapter X survey surfaced chronic rhinitis (J31) in the Rio Doce valley in 2015 (evaluation `2026-10-05-sih-readout`). The tailings dam of Fundão, in Mariana (MG), ruptured on 2015-11-05. Its facility triage was in progress at registration.

**Hypothesis.** Admissions for upper-respiratory disease rose in the municipalities affected along the Rio Doce after the rupture.

**Test.**
- **Outcome:** SIH-RD admissions with principal diagnosis J30–J31 (and J31 alone). Secondary: J00–J06, J20–J22, J40–J47.
- **Locus:** the municipalities officially recognised as affected, fixed from a named primary source (the IBAMA technical report of 2015, or the TTAC annex of 2016) before any data are read.
- **Time:** monthly, November 2015 to December 2016.
- **Expectation:** BP trained through October 2015 (ADR-0009).
- **Lens:** a confirmatory outbreak test at the declared locus. It is not a scan.

**It passes only if all three hold:**
1. observed/expected ≥ 1.2, with the minimum-effect p < 0.05;
2. the excess is spread over ≥ 3 municipalities and ≥ 2 facilities, with no facility holding more than 50% of it;
3. the negative-control outcome (digestive admissions, chapter K, same places and months) shows no excess.

**Honesty notes.**
- The lead was seen before this declaration; the confirmatory test uses the declared locus and window, not the lead's own.
- A pass shows an association in time and place. It cannot separate exposure to the tailings from changes in care-seeking or recording after a disaster.

## Locus (fixed 2026-10-05, before any SIH data were read)

**Source.** IBAMA, *Laudo Técnico Preliminar: impactos ambientais decorrentes do desastre envolvendo o rompimento da barragem de Fundão, em Mariana, Minas Gerais* (November 2015), section 2.4, table of the "41 municípios afetados a partir do município de Mariana-MG até a foz do Rio Doce, em Linhares-ES". `https://www.ibama.gov.br/phocadownload/noticias/noticias2015/laudo_tecnico_preliminar_Ibama.pdf` answers HTTP 403 to curl even with a browser User-Agent (an IBAMA firewall; not an outage of the document), so the text was read from an unaltered copy of the same IBAMA PDF at `https://facfama.edu.br/uploads/files/laudo_tecnico_preliminar.pdf` (38 pages, IBAMA/DIPRO/CGEMA cover). A TTAC (2016-03-02) list of 39 municipalities in Environmental Area 2, seen only in a secondary summary, equals this list without Acaiaca and Ponte Nova; the IBAMA list (the superset, a primary document read in full) is the declared locus.

**Locus, by residence (SIH MUNIC_RES), 41 municipalities, codes in `data/rio_doce_locus.json`.**
- MG (37): Acaiaca, Aimorés, Alpercata, Barra Longa, Belo Oriente, Bom Jesus do Galho, Bugre, Caratinga, Conselheiro Pena, Córrego Novo, Dionísio, Fernandes Tourinho, Galiléia, Governador Valadares, Iapu, Ipaba, Ipatinga, Itueta, Mariana, Marliéria, Naque, Periquito, Pingo-d'Água, Ponte Nova, Raul Soares, Resplendor, Rio Casca, Rio Doce, Santa Cruz do Escalvado, Santana do Paraíso, São Domingos do Prata, São José do Goiabal, São Pedro dos Ferros, Sem-Peixe, Sobrália, Timóteo, Tumiritinga.
- ES (4): Baixo Guandu, Colatina, Linhares, Marilândia.

Whole municipalities, not exposed neighbourhoods; Ipatinga, Governador Valadares and Colatina are large and mostly not reached by the tailings, which dilutes any effect (a stated limitation, fixed with the locus).

## Operational definitions (fixed before the result was read; `data/rio_doce_bp.py`, `data/rio_doce_test.py`)

- **Expectation.** BP (ADR-0009, monthly: the mixture over the fit's years) trained on months 2010-01..2015-10. BP trains on whole years, so the training assembly is truncated to 70 months (own store key `through: 201510`; admissions of those months read from files 2010-2016, since late filing puts October 2015 into 2016 files); the test assembly reads files 2015-2017 so December 2016 is not cut by filing lag. Chapter X and chapter XI (digestive) monthly blocks are fitted on that basis; nodes J30-J31 (J30+J31 leaves), J31, J00-J06, J20-J22, J40-J47 and XI are read from them.
- **Test.** O/E over the 41 locus municipalities (residence) x 2015-11..2016-12, E the sum of BP's means; minimum-effect p = `explain.tail_p(O, 1.2 mu, phi)`. The verdict is on J30-J31; J31 alone and the secondary groups are reported beside it.
- **Spread.** The excess is the signed O-E. A municipality or facility holds its signed O_i-E_i over the total; it counts as carrying the excess when it holds at least 5%. Facility expected = E x its share of the locus outcome's admissions in 2013-11..2015-10 (CNES column). Criterion 2: at least 3 municipalities and 2 facilities carrying, and no facility above 50%.
- **Negative control.** Chapter XI at the same places and months: "no excess" is ratio < 1.2 or p >= 0.05.
- `explain.facility_concentration` / `facility.py` were not committed when the test ran; shares are computed directly.

## Result (2026-10-05; `data/rio_doce_test.py`, artefact `data/logs/rio_doce_result.json`; ledger result row on 49f1626af33f4867; regime: branch design-v0, scripts 466502c, data home `pegasus_home`, SIH-RD files 2010-2017, cuda fits of monthly X and XI on months 2010-01..2015-10)

**Overall: FAIL (the hypothesis is not supported).**

| Criterion | Number | Verdict |
|---|---|---|
| 1. O/E >= 1.2, minimum-effect p < 0.05 | J30-J31: O 1, E 35.9, ratio 0.028, p(1.2) 0.99; J31 alone: O 1, E 35.1 | FAIL |
| 2. spread over >= 3 municipalities, >= 2 facilities, none > 50% | no excess to spread (net O-E = -34.9; the single admission is in Conselheiro Pena) | FAIL |
| 3. negative control (chapter XI, same places and months) shows no excess | O 8,478, E 9,803, ratio 0.865, p 1.0 | PASS |

Secondary outcomes, same locus and window: J00-J06 O 390 / E 385 (1.01); J20-J22 O 526 / E 436 (1.21, p(1.2) 0.46, p(1.0) 0.008; Mariana 34 against 2.5 expected, Colatina +41, Governador Valadares +26); J40-J47 O 1,321 / E 1,881 (0.70). The J20-J22 ratio reaches 1.2 but not the minimum-effect test, and it was not the primary outcome: it is recorded, not a finding.

**The monthly curve.** J30-J31 at the locus does not begin to rise in November 2015: it is zero in every month from July 2015 to December 2016 but one (August 2015: 1; August 2016: 1). The lead the declaration came from is a burst *before* the rupture: 212 admissions in January-June 2015 (17, 11, 34, 61, 60, 28) against about 2.5 a month expected, then none. In the J31-alone facility table one establishment (CNES 2118629) holds 99% of the 2013-11..2015-10 baseline, so the burst was one facility's recording episode, and the BP training through 2015-10 carries it into the expectation (about 2.7 a month), which makes the post-rupture deficit look larger (not tested here without it; the observed count is 1, so the ratio would pass 1.2 only if the expectation fell below about 1 admission over the window, which the pre-burst baseline does not suggest, unverified).

**Honesty notes.** The test shows no association in time and place between the rupture and upper-respiratory admissions (J30-J31) at the declared locus; it does not show absence of harm. Admissions measure care-seeking and recording as much as exposure, and the locus is whole municipalities (Ipatinga, Governador Valadares and Colatina are large and mostly not reached by the tailings), which dilutes a local effect; J30-J31 is rare in SIH (about 2.6 admissions a month across the 41 municipalities), so power for a 20% rise is small in absolute terms, yet the observed count (1) is far below the expectation, not merely short of 1.2 times it. The negative control passing means no general rise in admissions at these places. The "BP trained through 2015-10" was implemented by truncating the training assembly to 70 months (BP trains on whole years), and the 2015 burst is part of that training; the lead's pre-rupture rise is a recording artefact of one facility, not an effect of the dam.
