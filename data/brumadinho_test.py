"""Brumadinho confirmatory test, as declared (ledger d5938be360254838; docs/evaluation/2026-10-05-brumadinho-declaration.md).
Usage: python data/brumadinho_test.py   -> data/logs/brumadinho_result.json

Operational definitions (fixed before any fit or result):
  observed/expected  O/E at the primary place 310900 (residence) x 2019-02..2020-01; E = sum of BP's mixture means (BP trained 2010-01..2018-12).
  minimum-effect p   explain.tail_p(O, 1.2 * mu cells, phi cells): P(sum >= O) under H0 "the rate is at most 1.2 x BP".
  criterion 1        J20-J22 at 310900: ratio >= 1.2 and p(1.2) < 0.05.
  criterion 2        residents of 310900 with J20-J22 in the window, by CNES: excess_f = window_f - E * b_f, b_f the facility's share of
                     the 2016-01..2018-12 baseline; net excess = sum of excess_f. PASS if net excess > 0 and no facility whose hospital
                     municipality (MUNIC_MOV, most frequent) is not 310900 holds more than 50% of the net excess. No excess: FAIL.
  criterion 3        negative control, chapter XI at 310900, same months: no excess = ratio < 1.2 or p(1.2) >= 0.05.
  secondary places   the 25 places of data/brumadinho_locus.json, each separately (O/E, p(1.2), p vs 1.0, Bonferroni x25 on p(1.2))
                     and pooled; descriptive, never part of the verdict. Chapter XI beside each.
"""
import json
import sys

import numpy as np

sys.path.insert(0, "data")
import brumadinho_bp  # noqa: E402,F401  (installs the truncated training assembly)
import brumadinho_baseline as base  # noqa: E402

from pegasus_core import surprise  # noqa: E402
from pegasus_core.scans import explain  # noqa: E402

DATASET, EVENT = "SIH-RD", "hospitalisation"
W0, W1 = 201902, 202001
PRIMARY = 310900
LOC = json.load(open("data/brumadinho_locus.json", encoding="utf-8"))
SECONDARY = [int(m["code6"]) for m in LOC["municipalities"]]
NAMES = {int(m["code6"]): m["name"] for m in LOC["municipalities"]} | {PRIMARY: "Brumadinho"}


def expectations() -> surprise.Expectations:
    return surprise.Expectations(DATASET, EVENT, range(2010, 2021), source={"grain": "month"})


def stats(s: surprise.Surprise, mask: np.ndarray, win: np.ndarray) -> dict:
    y, mu, phi = s.y[mask][:, win], s.mu[mask][:, win], s.phi[mask][:, win]
    O, E = float(y.sum()), float(mu.sum())
    return {"observed": O, "expected": E, "ratio": O / E if E else None, "excess": O - E,
            "p_min_effect_1.2": explain.tail_p(O, 1.2 * mu.ravel(), phi.ravel()),
            "p_vs_1.0": explain.tail_p(O, mu.ravel(), phi.ravel())}


def summarise(s: surprise.Surprise) -> dict:
    per = np.asarray(s.years)
    win = (per >= W0) & (per <= W1)
    pm = s.places == PRIMARY
    assert pm.sum() == 1
    out = {"primary": stats(s, pm, win), "calibration_ks": s.calibration.get("ks")}
    curve = []
    others = ~np.isin(s.places, SECONDARY + [PRIMARY])
    for j, x in enumerate(per):
        if not 201901 <= x <= 202012:
            continue
        o, e = float(s.y[pm][:, j].sum()), float(s.mu[pm][:, j].sum())
        curve.append({"month": int(x), "observed": o, "expected": e, "ratio": o / e if e else None,
                      "rest_of_brazil_ratio": float(s.y[others][:, j].sum() / s.mu[others][:, j].sum())})
    out["curve"] = curve
    sec = np.isin(s.places, SECONDARY)
    out["secondary_pooled"] = stats(s, sec, win)
    out["rest_of_brazil_same_window"] = stats(s, others, win)
    per_place = []
    for u in SECONDARY:
        m = s.places == u
        if m.sum() != 1:
            per_place.append({"u": u, "name": NAMES[u], "error": "place not in the model"})
            continue
        r = stats(s, m, win)
        r.update(u=u, name=NAMES[u], p_bonferroni_25=min(1.0, 25 * r["p_min_effect_1.2"]))
        per_place.append(r)
    out["secondary_places"] = per_place
    return out


def facility_excess(E: float) -> dict:
    rows_w = base.facility_records([PRIMARY], ["J20", "J21", "J22"], range(2019, 2022), W0, W1)
    rows_b = base.facility_records([PRIMARY], ["J20", "J21", "J22"], range(2016, 2020), 201601, 201812)
    fac, mov = {}, {}
    for r in rows_b + rows_w:
        mov.setdefault(r["fac"], {}).setdefault(r["mov"], 0)
        mov[r["fac"]][r["mov"]] += r["y"]
        f = fac.setdefault(r["fac"], {"window": 0, "base": 0})
        if r in rows_w:
            f["window"] += r["y"]
        else:
            f["base"] += r["y"]
    btot = sum(f["base"] for f in fac.values())
    out = []
    for k, f in fac.items():
        exp = E * f["base"] / btot
        out.append({"facility": k, "hospital_municipality": max(mov[k], key=mov[k].get), "window": f["window"],
                    "baseline_share": f["base"] / btot, "expected": exp, "excess": f["window"] - exp})
    net = sum(o["excess"] for o in out)
    for o in out:
        o["share_of_net_excess"] = o["excess"] / net if net > 0 else None
    out.sort(key=lambda o: -o["excess"])
    concentrated = [o["facility"] for o in out if net > 0 and o["share_of_net_excess"] > 0.5
                    and o["hospital_municipality"] != str(PRIMARY)]
    return {"window_total": sum(o["window"] for o in out), "net_excess": net, "facilities": out[:15],
            "n_facilities": len(out), "concentrated_outside": concentrated}


def main() -> None:
    ex = expectations()
    out = {"primary": PRIMARY, "window": [W0, W1], "nodes": {}}
    for node in ("J20-J22", "XI"):
        s = ex.prospective(node, 2018)
        out["nodes"][node] = summarise(s)
        r = out["nodes"][node]["primary"]
        print(node, "primary O", r["observed"], "E", round(r["expected"], 2), "ratio", round(r["ratio"], 3),
              "p(1.2)", r["p_min_effect_1.2"], flush=True)
        json.dump(out, open("data/logs/brumadinho_result.json", "w", encoding="utf-8"), indent=1, ensure_ascii=False, default=float)
    out["nodes"]["J20-J22"]["facilities"] = facility_excess(out["nodes"]["J20-J22"]["primary"]["expected"])
    p1, f2, c3 = out["nodes"]["J20-J22"]["primary"], out["nodes"]["J20-J22"]["facilities"], out["nodes"]["XI"]["primary"]
    out["criteria"] = {
        "1_ratio_and_p": bool(p1["ratio"] >= 1.2 and p1["p_min_effect_1.2"] < 0.05),
        "2_not_one_outside_facility": bool(f2["net_excess"] > 0 and not f2["concentrated_outside"]),
        "3_negative_control": bool(c3["ratio"] < 1.2 or c3["p_min_effect_1.2"] >= 0.05)}
    out["pass"] = all(out["criteria"].values())
    json.dump(out, open("data/logs/brumadinho_result.json", "w", encoding="utf-8"), indent=1, ensure_ascii=False, default=float)
    print(out["criteria"], "PASS" if out["pass"] else "FAIL")


if __name__ == "__main__":
    main()
