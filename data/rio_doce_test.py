"""Rio Doce confirmatory test, as declared (ledger 49f1626af33f4867; docs/evaluation/2026-10-05-rio-doce-declaration.md).
Usage: python data/rio_doce_test.py   -> data/logs/rio_doce_result.json

Operational definitions (fixed before the result was read):
  observed/expected  O/E over the 41 locus municipalities (residence) x 2015-11..2016-12; E = sum of BP's mixture means.
  minimum-effect p   explain.tail_p(O, 1.2 * mu cells, phi cells): P(sum >= O) under H0 "the rate is at most 1.2 x BP".
  excess             O - E (signed); a municipality / facility 'holds' its signed O_i - E_i over the total O - E.
  facility expected  E x b_f, b_f the facility's share of the locus outcome's admissions in 2013-11..2015-10.
  spread             >= 3 municipalities and >= 2 facilities each holding >= 5% of the excess, none (facility) above 50%.
  negative control   chapter XI (digestive), same places and months, same BP: no excess = ratio < 1.2 or p >= 0.05.
  verdict            on J30-J31 (primary); J31 alone and the secondary groups are reported beside it.
"""
import json
import sys
import warnings

import duckdb
import numpy as np
import pyarrow as pa

sys.path.insert(0, "data")
import rio_doce_bp  # noqa: E402,F401  (installs the truncated training assembly)

from pegasus_core import config, control, gateway, surprise  # noqa: E402
from pegasus_core.scans import explain  # noqa: E402

DATASET, EVENT = "SIH-RD", "hospitalisation"
W0, W1 = 201511, 201612
LOCUS = [int(m["code6"]) for m in json.load(open("data/rio_doce_locus.json", encoding="utf-8"))["municipalities"]]
NAMES = {int(m["code6"]): m["name"] for m in json.load(open("data/rio_doce_locus.json", encoding="utf-8"))["municipalities"]}
NODES = {"J30-J31": ["J30", "J31"], "J31": ["J31"], "J00-J06": None, "J20-J22": None, "J40-J47": None, "XI": None}


def expectations() -> surprise.Expectations:
    ex = surprise.Expectations(DATASET, EVENT, range(2010, 2018), source={"grain": "month"})
    r = ex.registry
    g = r.parent["J30"]
    r.level["J30-J31"], r.parent["J30-J31"], r.label["J30-J31"] = "group", g, "J30-J31 rhinitis (synthetic node)"
    r.children["J30-J31"] = ["J30", "J31"]
    return ex


def summarise(s: surprise.Surprise, locus: np.ndarray, extra_mask: np.ndarray | None = None) -> dict:
    per = np.asarray(s.years)
    win = (per >= W0) & (per <= W1)
    y, mu, phi = s.y[locus][:, win], s.mu[locus][:, win], s.phi[locus][:, win]
    O, E = float(y.sum()), float(mu.sum())
    p = explain.tail_p(O, 1.2 * mu.ravel(), phi.ravel())
    months = [int(x) for x in per if 201501 <= x <= 201612]
    curve = []
    for x in months:
        j = list(per).index(x)
        o, e = float(s.y[locus][:, j].sum()), float(s.mu[locus][:, j].sum())
        cmp = ~locus
        curve.append({"month": x, "observed": o, "expected": e, "ratio": o / e if e else None,
                      "others_ratio": float(s.y[cmp][:, j].sum() / s.mu[cmp][:, j].sum())})
    cmp = ~locus
    others = {"observed": float(s.y[cmp][:, win].sum()), "expected": float(s.mu[cmp][:, win].sum())}
    others["ratio"] = others["observed"] / others["expected"]
    by_u = []
    for k, u in enumerate(s.places[locus]):
        o, e = float(y[k].sum()), float(mu[k].sum())
        by_u.append({"u": int(u), "name": NAMES[int(u)], "observed": o, "expected": e, "excess": o - e})
    pre = (per >= 201501) & (per <= 201510)
    return {"observed": O, "expected": E, "ratio": O / E, "p_min_effect_1.2": p, "excess": O - E,
            "p_vs_1.0": explain.tail_p(O, mu.ravel(), phi.ravel()),
            "pre_rupture_2015-01..10": {"observed": float(s.y[locus][:, pre].sum()), "expected": float(s.mu[locus][:, pre].sum())},
            "others_same_window": others, "curve": curve, "municipalities": by_u,
            "calibration_ks": s.calibration.get("ks")}


def facility_table(codes: list[str], E_total: float) -> dict:
    """Locus admissions of ``codes`` (3-character prefixes) by CNES, window and 2013-11..2015-10 baseline."""
    import pegasus_data as pg

    strata = gateway._strata(DATASET)
    roles = pg.roles(DATASET)
    fcol = next(r["column"] for r in roles if r.get("model") == "institution" and r.get("property") == "facility")
    spec = next(e for e in pg.event_types(DATASET) if e["name"] == EVENT)
    cls = next(c["column"] for c in spec["classifiers"] if c["role"] == "primary")
    when = gateway._when(DATASET)
    rows = []
    for year in range(2013, 2018):
        raw = gateway._records(DATASET, EVENT, year, [strata["residence"], when, fcol, cls])
        con = duckdb.connect()
        con.register("r", raw)
        con.register("loc", pa.table({"u": pa.array(LOCUS, pa.int32())}))
        t = con.execute(f"""SELECT u, left(coalesce(trim(CAST("{fcol}" AS VARCHAR)), ''), 7) AS fac,
                year(d) * 100 + month(d) AS ym, count(*) AS y FROM (
              SELECT CAST({gateway._residence_sql(strata['residence'])} AS INTEGER) AS u, "{fcol}",
                     {gateway._date_sql(when)} AS d, upper(trim(CAST("{cls}" AS VARCHAR))) AS c FROM r)
            WHERE u IN (SELECT u FROM loc) AND left(c, 3) IN ({", ".join(repr(c) for c in codes)}) AND d IS NOT NULL
            GROUP BY ALL""").fetch_arrow_table().to_pylist()
        rows += t
    fac = {}
    for r in rows:
        f = fac.setdefault(r["fac"], {"window": 0, "base": 0})
        if W0 <= r["ym"] <= W1:
            f["window"] += r["y"]
        if 201311 <= r["ym"] <= 201510:
            f["base"] += r["y"]
    # one admission is filed in its year's file and, if late, in the next: the same record is not counted twice
    # because each file holds each record once (a record is filed once)
    base_tot = sum(f["base"] for f in fac.values())
    out = []
    for k, f in fac.items():
        exp = E_total * f["base"] / base_tot
        out.append({"facility": k, "window": f["window"], "baseline_share": f["base"] / base_tot, "expected": exp,
                    "excess": f["window"] - exp})
    tot = sum(o["excess"] for o in out)
    for o in out:
        o["share_of_excess"] = o["excess"] / tot if tot > 0 else None
    out.sort(key=lambda o: -o["excess"])
    return {"window_total": sum(o["window"] for o in out), "net_excess": tot, "facilities": out[:15], "n_facilities": len(out)}


def main() -> None:
    ex = expectations()
    out = {"locus": LOCUS, "window": [W0, W1], "nodes": {}}
    for node in NODES:
        s = ex.prospective(node, 2014)
        locus = np.isin(s.places, LOCUS)
        assert locus.sum() == 41, int(locus.sum())
        out["nodes"][node] = summarise(s, locus)
        out["nodes"][node]["train"] = s.extras.get("train")
        r = out["nodes"][node]
        print(node, "O", r["observed"], "E", round(r["expected"], 1), "ratio", round(r["ratio"], 3),
              "p(1.2)", r["p_min_effect_1.2"], flush=True)
        json.dump(out, open("data/logs/rio_doce_result.json", "w", encoding="utf-8"), indent=1, ensure_ascii=False, default=float)
    for node in ("J30-J31", "J31"):
        r = out["nodes"][node]
        r["facilities"] = facility_table(NODES[node], r["expected"])
        tot = r["excess"]
        ms = sorted(r["municipalities"], key=lambda m: -m["excess"])
        for m in ms:
            m["share_of_excess"] = m["excess"] / tot if tot > 0 else None
        r["municipalities"] = ms
    json.dump(out, open("data/logs/rio_doce_result.json", "w", encoding="utf-8"), indent=1, ensure_ascii=False, default=float)


if __name__ == "__main__":
    main()
