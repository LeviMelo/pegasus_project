"""Planted truths through `replication.audit` on the real strata (ADR-0019): into a state's real SIM deaths 2010-2019,
(a) a gradual real trend in one cause (extra deaths with the cause's own sex/age/place profile, log-linear, x3.5 over the
decade) and (b) the same gain taken death for death from the other causes of its ICD block (a transfer). Real claim
expected: not downgraded (`survives` or `open`, never `explained`); transfer: its bound raised. Output
data/artefact_replication/planted.json. Uses the cached events of data/artefact_replication.py."""
import json
import os
import warnings
from pathlib import Path

os.chdir(Path(__file__).resolve().parents[1])
warnings.simplefilter("ignore")
import numpy as np
import pandas as pd

from pegasus_core import gateway, replication

D = Path("data/artefact_replication")
ev, pop = pd.read_parquet(D / "events.parquet"), pd.read_parquet(D / "pop.parquet")
ev, pop = ev[ev.year <= 2019].reset_index(drop=True), pop[pop.year <= 2019]
edges = np.array(gateway.age_edges("popsvs"))
tree = gateway.code_structure("ICD10").to_pandas().set_index("code")
rng = np.random.default_rng(20261005)
YRS = list(range(2010, 2020))
x = {y: (y - 2010) / np.std(YRS) for y in YRS}
c3 = ev["code"].str[:3]
out = {}
# (state, node, block): causes with enough deaths and a block of siblings, in states of different size
for uf, node, block in ((31, "K80", ("K80", "K87")), (35, "N20", ("N20", "N23")), (41, "L89", ("L80", "L99")), (23, "M54", ("M50", "M54"))):
    inside = (ev["u"] // 10000 == uf) & (c3 == node)
    sib = (ev["u"] // 10000 == uf) & (c3 >= block[0]) & (c3 <= block[1]) & (c3 != node)
    if inside.sum() == 0 or sib.sum() == 0:
        continue
    for kind in ("real", "transfer"):
        e = ev.copy()
        mult = np.exp(0.4 * e.loc[inside, "year"].map(x).to_numpy())
        gain = rng.poisson(e.loc[inside, "y"].to_numpy() * (mult - 1)).astype(int)
        e.loc[inside, "y"] = e.loc[inside, "y"] + gain
        if kind == "transfer":
            # remove the same number of deaths from the siblings, year by year, in proportion to their own counts
            for yr in YRS:
                need = int(gain[(e.loc[inside, "year"] == yr).to_numpy()].sum())
                rows = e.index[sib & (e["year"] == yr)]
                if need == 0 or len(rows) == 0:
                    continue
                w = e.loc[rows, "y"].to_numpy(float)
                take = np.minimum(rng.multinomial(need, w / w.sum()), e.loc[rows, "y"].to_numpy())
                e.loc[rows, "y"] = e.loc[rows, "y"].to_numpy() - take
        st = replication.Strata(e, pop, edges)
        places = [int(u) for u in st.places if u // 10000 == uf]
        base = st.series(places, [node])
        from pegasus_core.scans import explain
        beta = float(explain.loglinear(base[0][None], base[1][None], np.array(YRS))[0][0])
        r = replication.audit(st, places, node, "state", beta, 1, YRS, tree, seed_text=f"planted|{uf}|{node}|{kind}")
        out[f"{node} {uf} {kind}"] = r
        print(node, uf, kind, "beta", round(beta, 3), r["verdict"], r["shape"]["shape"],
              {k: (round(v["share"], 2), round(v["rest_z"], 1), v["moves"], v.get("profile", {}).get("result")) for k, v in r["conservation"].items()},
              [(a["kind"], a["grade"], a["outcome"]) for a in r["explanations"]], flush=True)
        del st
json.dump(out, open(D / "planted.json", "w"), indent=1, default=float)
