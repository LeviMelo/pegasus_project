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
