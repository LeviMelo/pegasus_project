"""What the Laplace uncertainty layer changes in calibration (evaluation 2026-10-05, Laplace).

Usage: python scripts/measure_laplace.py MODE [DRAWS] [DEVICE]

MODE   ix       chapter IX deaths 2010-2023, knn6, tiers B0/B1/B2 for five fields (in-sample)
       dengue   dengue probable cases by month 2010-2023, tiers B0/B1/B2/B2s (in-sample)
       bp-dengue18 | bp-dengue14   the prospective tier trained to 2018 / 2014
       bp-ix19  chapter IX, contiguity, trained to 2019, tested 2020-2023

For every field and tier, the same cells are scored under the MAP's predictive (draws = 0) and under
the Laplace predictive, each with the block's phi and then with the field's own place-year component:
KS of the randomised PIT overall and per macro-region, the 10-bin histogram, the totals, and the
predictive's coefficient of variation. Output: data/logs/laplace_<mode>.json.
"""
import json
import sys
import time

import numpy as np
import torch

from pegasus_core import config, laplace, surprise

mode = sys.argv[1]
S = int(sys.argv[2]) if len(sys.argv) > 2 else 32
device = sys.argv[3] if len(sys.argv) > 3 else "cpu"
MACRO = {"1": "Norte", "2": "Nordeste", "3": "Sudeste", "4": "Sul", "5": "Centro-Oeste"}

captured: list[dict] = []
_orig = surprise._assemble


def _wrap(f, tier, m, y, mu, mu2, phi_block, macro, flag_calibration=True, var=None):
    captured.append({"f": f, "tier": tier, "m": m, "y": y, "mu": mu, "mu2": mu2, "phi": phi_block, "macro": macro,
                     "var": var})
    return _orig(f, tier, m, y, mu, mu2, phi_block, macro, flag_calibration, var)


surprise._assemble = _wrap


def summary(cal: dict) -> dict:
    return {"ks": round(cal["ks"], 4), "worst_region": round(max(cal["ks_by_macroregion"].values(), default=0), 4),
            "regions": {MACRO.get(k, k): round(v, 4) for k, v in cal["ks_by_macroregion"].items()},
            "hist": cal["histogram"], "calibrated": cal["calibrated"]}


def ladder(c: dict) -> dict:
    """The block-phi PIT, and the PIT with the field's place-year component on top."""
    y, mu, mu2, phi, macro = c["y"], c["mu"], c["mu2"], c["phi"], c["macro"]
    var = np.zeros_like(mu) if c["var"] is None else c["var"]
    cells = laplace.predictive_phi(mu, var, mu2, phi)
    seed = config.seed(c["f"].id, c["tier"], "pit", c["m"].key())
    u, _ = surprise.randomised_pit(y, mu, cells, seed)
    out = {"block_phi": summary(surprise.calibration(u, mu, macro))}
    extra = surprise.place_year_phi(y, mu, cells)
    phi_field = 1.0 / (1.0 / cells + 1.0 / extra)
    u, _ = surprise.randomised_pit(y, mu, phi_field, seed)
    out["field_phi"] = summary(surprise.calibration(u, mu, macro))
    out["field_phi"]["phi_extra"] = float(extra)
    ok = mu > 1e-6
    cv2 = np.where(ok, var / np.maximum(mu, 1e-300) ** 2, 0.0)
    w = mu[ok] / mu[ok].sum()
    out["observed"], out["expected"] = float(y.sum()), float(mu.sum())
    out["cv2_param"] = {"median": float(np.median(cv2[ok])), "mu_weighted_mean": float((cv2[ok] * w).sum()),
                        "p95": float(np.quantile(cv2[ok], 0.95))}
    cv2_nb = 1.0 / np.where(np.isfinite(cells), cells, np.inf)[ok]
    out["cv2_nb"] = {"median": float(np.median(cv2_nb)), "mu_weighted_mean": float((cv2_nb * w).sum())}
    return out


def run(make_ex, fields_tiers, label: str) -> dict:
    res = {}
    bp = any(t == "BP" for _, t in fields_tiers)
    variants = [("map", 0, True, "plugin")]
    if S:
        variants += [("laplace", S, False, "plugin"), ("laplace-postmean", S, False, "posterior")]
    if bp and S:
        variants += [("laplace+forecast", S, True, "plugin"), ("laplace+forecast-postmean", S, True, "posterior")]
    shared: dict = {}                       # the draws are made once and re-centred by variant
    for name, draws, forecast, center in variants:
        ex = make_ex(draws, forecast, center)
        if draws:
            ex._posteriors = shared
        for node, tier in fields_tiers:
            captured.clear()
            t = time.time()
            if tier == "BP":
                ex.prospective(node, make_ex.train_last)
            else:
                ex.surprise(node, tier)
            secs = time.time() - t
            r = ladder(captured[-1])
            r["seconds"] = round(secs, 1)
            res.setdefault(f"{node}|{tier}", {})[name] = r
            print(f"{label} {node:9} {tier:4} {name:17} block KS {r['block_phi']['ks']:.3f}/{r['block_phi']['worst_region']:.3f}"
                  f"  field KS {r['field_phi']['ks']:.3f}/{r['field_phi']['worst_region']:.3f} (phi_extra {r['field_phi']['phi_extra']:.3g})"
                  f"  obs/exp {r['observed']:.0f}/{r['expected']:.0f}  cv2 param {r['cv2_param']['mu_weighted_mean']:.4f}  {secs:.0f}s",
                  flush=True)
        if draws:
            for key, post in ex._posteriors.items():
                its = [s.iterations for s in post.solves]
                res.setdefault("posterior", {})[str(key)] = {
                    "cg_mean": float(np.mean(its)), "cg_max": int(max(its)), "cg_residual_max": max(s.residual for s in post.solves)}
                if device == "cuda":
                    res["posterior"][str(key)]["gpu_peak_gb"] = torch.cuda.max_memory_allocated() / 1e9
    return res


out: dict = {"draws": S, "device": device}
if mode == "ix":
    nodes = ["IX", "I20-I25", "I60-I69", "I64", "I10-I15"]

    def make(draws, forecast=True, center="plugin"):
        return surprise.Expectations("SIM.DO", "death", range(2010, 2024), graph="knn6", laplace=draws, device=device, forecast=forecast, center=center)

    out = run(make, [(n, t) for n in nodes for t in ("B0", "B1", "B2")], "IX")
elif mode == "dengue":
    def make(draws, forecast=True, center="plugin"):
        return surprise.Expectations("SINAN-DENG", "probable_case", range(2010, 2024), source={"grain": "month"},
                                     laplace=draws, device=device, forecast=forecast, center=center)

    out = run(make, [("*", t) for t in ("B0", "B1", "B2", "B2s")], "dengue")
elif mode in ("bp-dengue18", "bp-dengue14"):
    last = 2018 if mode.endswith("18") else 2014

    def make(draws, forecast=True, center="plugin"):
        yrs = range(2010, 2024) if last == 2018 else range(2010, 2017)
        return surprise.Expectations("SINAN-DENG", "probable_case", yrs, source={"grain": "month"},
                                     laplace=draws, device=device, forecast=forecast, center=center)

    make.train_last = last
    out = run(make, [("*", "BP")], mode)
elif mode == "bp-ix19":
    def make(draws, forecast=True, center="plugin"):
        return surprise.Expectations("SIM.DO", "death", range(2010, 2024), graph="contiguity", laplace=draws,
                                     device=device, forecast=forecast, center=center)

    make.train_last = 2019
    out = run(make, [(n, "BP") for n in ["IX", "I20-I25", "I60-I69", "I64", "I10-I15"]], mode)
out["draws"], out["device"] = S, device
with open(f"data/logs/laplace_{mode}{'' if S else '_map'}.json", "w", encoding="utf-8") as fh:
    json.dump(out, fh, indent=1, default=float, ensure_ascii=False)
