# Propagation: first-departure times over the graph (2026-10-10)

Regime: branch `propagation`, `propagation.py` and the `propagation` question; the shared store; SINAN-CHIK monthly
2014–2016 at B0. The drivers are in the session scratchpad (`prop/t1.py`).

**Method.** Each place's onset is the period of its first cell departure (BH at q). The source is the departing place
that maximises the Spearman correlation of onset with distance from it (Cliff and Haggett). The speed is the Theil–Sen
slope of onset on distance, and the direction comes from a trend surface. The test runs the source search inside a
Moran-spectral-randomisation null, with a permutation null as the comparison. Successive waves are tested in fixed
sequence at q.

**Chikungunya, 2014–2016 (known: two introductions in 2014, Oiapoque (AP) and Feira de Santana (BA)).**

| null | wave | source | onset | places | speed (km/month) | p |
|---|---|---|---|---|---|---|
| spectral | 1 | 240680 (RN) | 2015-02 | 42 | 26.8 [22.2, 44.9] | 0.045 |
| permutation | 1 | 240680 (RN) | 2015-02 | 42 | 26.8 | 0.001 |
| permutation | 2 | 290327 (BA) | 2015-05 | 113 | 68.8 | 0.003 |
| permutation | 3 | 292660 (BA) | 2014-10 | 8 | 71.6 | 0.008 |

Graph hops agree: the same waves at 1.0–2.0 hops a month.

The 2015 North-East spread is found, and so is a small 2014 Bahian wave in the month after the Feira de Santana
introduction. The Amapá entry, a handful of cases, is not: the method needs enough departing places to order. The
spectral null, which keeps the onsets' smoothness, admits one wave where the permutation null admits three, as designed.

**Microcephaly, 2015–2016 (known: the excess was first reported in metropolitan Recife, Pernambuco, in the second half
of 2015, then across the North-East).**

The field is SINASC Q02 on the anomaly list, monthly, against BP fitted on 2012–2014 and looked for in 2015–2016.
Births with Q02 numbered 1,758 in 2015 and 2,276 in 2016, against 178 a year expected.

| null | wave | source | onset | places | emerged | speed (km/month) | bearing | p |
|---|---|---|---|---|---|---|---|---|
| spectral | 1 | Ilha de Itamaracá (PE) | 2015-11 | 826 | 816 (98.8%) | 811 [648, 1,073] | 252° | 0.007 |

- The earliest onsets were in June–July 2015, in Camaragibe (PE, metropolitan Recife), Coroatá (MA), Poranga and
  Quixeré (CE) and Lucena (PB).
- The emergence, in places with no Q02 departure before, and its origin on the Pernambuco coast are both found, by
  discovery.
- The first run failed: a window given in years on a monthly field selected nothing. `window_of` now reads such a
  window as those years' months, and an empty window raises.
