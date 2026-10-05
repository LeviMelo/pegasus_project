"""Derive the documented loci of the three declared lens positives of evaluation 2026-10-05-lens-positives (section
"Declared before the run") from the Atlas da Violencia UF tables (scripts/atlas_uf.json) alone, the contiguity graph
and the population. It reads no SIM record and no lens output; it is committed, with ``harness.POSITIVES``, before
any lens is run on these positives. Output: data/p3/declared.json.

Trend divergence (SIM.DO X85-Y09, B2, 2010-2023). Slope of ln(UF rate) on year over 2010-2023 (Atlas 2019 Table 2.1 for
2010-2012, Atlas 2025 Table 2.1 for 2013-2023). Documented divergence of a municipality u: d_u = slope(UF of u) minus
the mean slope of the UFs of its contiguity neighbours (the lens's own estimand). Documented places: |d_u| >= ln 1.5 / 13
(a ratio of 1.5 relative to neighbours over the 13 years; the first choice, a doubling, left 3 places and was
widened before any lens ran); sign = sign of d_u; weight = estimated deaths (population x UF rate).

Group disparity (SIM.DO X85-Y09, B0, 2013-2023). For each UF, share of homicide victims who are women (Atlas Table 5.1 / 2.2)
and who are young men aged 15-29 (Table 4.3 / 2.2), over 2013-2023, as a ratio to Brazil's. Documented UFs: ratio >= 1.25 or
<= 0.8. A municipality of such a UF is documented with the UF's sign; weight = estimated deaths x national share x |ratio - 1|."""
import json
from pathlib import Path

import numpy as np

from pegasus_core import gateway, graphs

A = json.loads((Path(__file__).parent / "atlas_uf.json").read_text(encoding="utf-8"))
YEARS = list(range(2010, 2024))
rate = {int(k): np.array(v) for k, v in A["rate"].items() if k != "BR"}
slope = {u: float(np.polyfit(np.array(YEARS) - 2016.5, np.log(r), 1)[0]) for u, r in rate.items()}
THRESH = float(np.log(1.5) / 13)

pop = gateway.population(YEARS)
u_all = pop.column("u").to_numpy().astype(int)
t_all = pop.column("year").to_numpy().astype(int)
n_all = pop.column("n").to_numpy().astype(float)
places = np.array(sorted(set(u_all.tolist())))
pidx = {int(p): i for i, p in enumerate(places)}
person_years = np.zeros((len(places), len(YEARS)))
np.add.at(person_years, ([pidx[int(u)] for u in u_all], [t - 2010 for t in t_all]), n_all)
uf_of = np.array([int(p) // 10000 for p in places])        # 6-digit codes: the first two digits are the UF
uf_of = np.array([int(str(int(p)).zfill(6)[:2]) for p in places])
est_deaths_y = person_years * np.array([[rate[int(u)][t] / 1e5 for t in range(len(YEARS))] for u in uf_of])

edges = graphs.edges(places, graphs.DEFAULT)
nb = [[] for _ in places]
for i, j in edges:
    nb[i].append(j)
    nb[j].append(i)
s_uf = np.array([slope[int(u)] for u in uf_of])
d = np.array([s_uf[i] - np.mean([s_uf[j] for j in nb[i]]) if nb[i] else 0.0 for i in range(len(places))])
sel = np.abs(d) >= THRESH
out = {"threshold": THRESH, "slopes": {str(k): round(v, 4) for k, v in sorted(slope.items())},
       "trend_divergence": {"places": [int(p) for p in places[sel]], "d": [round(float(x), 4) for x in d[sel]],
                            "weight": [round(float(x), 1) for x in est_deaths_y.sum(1)[sel]]}}

yrs = slice(3, 14)                                           # 2013-2023
D = np.array(A["deaths"]["BR"])
for name, key in (("women", "women"), ("young_men", "young_men")):
    br = np.array(A[key]["BR"]).sum() / D.sum()
    ratio = {int(u): np.array(A[key][u]).sum() / np.array(A["deaths"][u]).sum() / br for u in A[key] if u != "BR"}
    docs = {u: r for u, r in ratio.items() if r >= 1.25 or r <= 0.8}
    sel = np.array([int(u) in docs for u in uf_of])
    w = est_deaths_y[:, yrs].sum(1) * br * np.array([abs(docs.get(int(u), 1.0) - 1.0) for u in uf_of])
    out["group_" + name] = {"national_share": round(float(br), 4), "ufs": {str(u): round(float(r), 3) for u, r in sorted(docs.items())},
                            "ratio_all": {str(u): round(float(r), 3) for u, r in sorted(ratio.items())},
                            "places": [int(p) for p in places[sel]], "sign": [int(np.sign(docs[int(u)] - 1)) for u in uf_of[sel]],
                            "weight": [round(float(x), 2) for x in w[sel]]}
Path("data/p3").mkdir(parents=True, exist_ok=True)
Path("data/p3/declared.json").write_text(json.dumps(out), encoding="utf-8")
td = out["trend_divergence"]
print("threshold", round(THRESH, 4), "| slopes", out["slopes"])
print("trend divergence: places", len(td["places"]), "up", sum(x > 0 for x in td["d"]), "down", sum(x < 0 for x in td["d"]), "est deaths", round(sum(td["weight"])))
for k in ("group_women", "group_young_men"):
    g = out[k]
    print(k, "UFs", g["ufs"], "places", len(g["places"]))
