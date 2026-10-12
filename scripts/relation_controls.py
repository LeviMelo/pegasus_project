"""Negative and positive controls of the relation estimator (BACKLOG 3.5; evaluation 2026-10-11-relation-estimator).

Real fields only: seven SINAN notification fields and SINASC's Q02, monthly B1 innovations 2014-2019 (DENG fails
B1's calibration and stays out, invariant 8). Negatives: each real field against a time-reversed copy, and against a
place-permuted copy, of every other field (rows and profiles; the false-test rate at p < .05, .01, .001 and the
relations reported). Positive: LEPT against a copy of itself leading it by 3 months, diluted with another field's
innovations to correlation a. Usage: relation_controls.py LAGS [OUT.json]."""

import json
import sys
import time

import numpy as np

from pegasus_core import control, multiscale, relations, tools

FIELDS = ["SINAN-CHIK", "SINAN-LEPT", "SINAN-HANS", "SINAN-TUBE", "SINAN-HEPA", "SINAN-MENI"]
Q02 = {"source": "code_list", "column": "CODANOMAL"}


def innovations() -> tuple[relations.Departures, np.ndarray]:
    years, surps, edges = list(range(2012, 2020)), [], None
    for ds in FIELDS + ["SINASC-DN"]:
        s = tools.Session(ds, "birth" if ds == "SINASC-DN" else "notification", years,
                          source={**(Q02 if ds == "SINASC-DN" else {}), "grain": "month"})
        edges = s.edges() if edges is None else edges
        x = s.surprise("Q02" if ds == "SINASC-DN" else "*", "B1")
        if x.calibration.get("calibrated") is not False:
            surps.append(x)
    return relations.innovations(surps), edges


def rates(rows: list[dict], controlled: bool) -> dict:
    neg = [r for r in rows if r["field"].endswith("~ctl") != r["leader"].endswith("~ctl")
           and r["field"].replace("~ctl", "") != r["leader"].replace("~ctl", "")]
    if controlled:                                   # a place-permuted copy keeps the nation's course
        neg = [r for r in neg if r["support"] != "national"]
    p = np.array([r["p"] for r in neg])
    return {"tests": len(neg), "p<.05": round(float((p < .05).mean()), 4), "p<.01": round(float((p < .01).mean()), 4),
            "p<.001": round(float((p < .001).mean()), 4), "reported": int(sum(r["reported"] for r in neg)),
            "bh_alone": int(control.bh(p, 0.05).sum())}


def main(lags: int, out: str | None) -> None:
    t0 = time.time()
    d, edges = innovations()
    spec = multiscale.spectrum(edges, len(d.places))
    rng, F, results = np.random.default_rng(7), len(d.fields), {}

    def controlled(fn):
        r, w = zip(*[fn(d.r[i], d.w[i]) for i in range(F)], strict=True)
        return relations.Departures(d.fields + [f + "~ctl" for f in d.fields], d.places, d.periods,
                                    np.concatenate([d.r, np.stack(r)]), np.concatenate([d.v, d.v]),
                                    np.concatenate([d.w, np.stack(w)]))

    perms = [rng.permutation(len(d.places)) for _ in range(3)]
    for name, fn, skip in [("time_reversed", lambda r, w: (r[:, ::-1], w), False)] + [
            (f"place_permuted_{k}", lambda r, w, perm=perm: (r[perm], w[perm]), True) for k, perm in enumerate(perms)]:
        est = relations.relation_estimate(controlled(fn), spec, lags=lags, conditional=False)
        results[name] = {"rows": rates(est["rows"], skip), "profiles": rates(est["profiles"], skip)}
        print(name, json.dumps(results[name]), round(time.time() - t0), flush=True)
    j, o = [i for i, f in enumerate(d.fields) if "LEPT" in f][0], [i for i, f in enumerate(d.fields) if "HANS" in f][0]
    for a in (1.0, 0.5, 0.25, 0.1):
        lead = a * np.roll(d.r[j], -3, axis=1) + np.sqrt(1 - a ** 2) * d.r[o][:, ::-1]
        dd = relations.Departures(["follower", "leader"], d.places, d.periods, np.stack([d.r[j], lead]),
                                  np.stack([d.v[j]] * 2), np.stack([d.w[j]] * 2))
        est = relations.relation_estimate(dd, spec, lags=lags, conditional=False)
        best = {}
        for r in (r for r in est["rows"] if r["field"] == "follower"):
            if r["support"] not in best or r["p"] < best[r["support"]]["p"]:
                best[r["support"]] = r
        results[f"planted_a{a}"] = {"supports": len(best), "lag3_best_and_reported": sum(
            r["lag"] == 3 and r["reported"] for r in best.values())}
        print(f"planted a={a}", results[f"planted_a{a}"], flush=True)
    if out:
        with open(out, "w") as f:
            json.dump(results, f, indent=1)


if __name__ == "__main__":
    main(int(sys.argv[1]), sys.argv[2] if len(sys.argv) > 2 else None)
