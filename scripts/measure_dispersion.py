"""Dispersion by macro-region and state (ARCHITECTURE §5.2, §6.2; OQ 6): calibration of every fitted block
with the block's φ, one place-year φ_extra per field, and φ_extra varying by macro-region, then by state.

Usage: python scripts/measure_dispersion.py TARGET [TARGET ...]   (TARGET: see TARGETS)
Writes data/logs/dispersion_<target>.json: per node and tier, per variant, the PIT's KS overall and per macro-region
and the φ_extra by region. The inputs of each (node, tier) are captured once from `surprise._assemble` and the
variants evaluated on the same expectations."""

from __future__ import annotations

import json
import sys
import time

import numpy as np
from scipy import special

from pegasus_core import config, laplace, surprise

SIM_CHAPTERS = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII", "XIII", "XIV", "XV", "XVI",
                "XVII", "XVIII", "XX"]
VARIANTS = {"block": None, "global": (), "macro": ("macro",), "macro+state": ("macro", "state")}
MONTHLY = {"grain": "month"}


def sim(first=2010, last=2023, graph="contiguity"):
    return lambda: surprise.Expectations("SIM.DO", "death", range(first, last + 1), graph=graph)


TARGETS = {
    # name: (Expectations factory, nodes, tiers)
    "sim": (sim(), SIM_CHAPTERS, ("B0", "B1", "B2")),
    "ix-knn6": (sim(graph="knn6"), ["IX", "I20-I25", "I60-I69", "I64", "I10-I15"], ("B0", "B1", "B2")),
    "sinasc-xvii": (lambda: surprise.Expectations("SINASC-DN", "birth", range(2010, 2024), "contiguity",
                                                  source={"source": "code_list", "column": "CODANOMAL"}),
                    ["XVII"], ("B0", "B1", "B2")),
    "sinasc-total": (lambda: surprise.Expectations("SINASC-DN", "birth", range(2010, 2024), "contiguity"),
                     ["*"], ("B0", "B1", "B2")),
    "sih": (lambda: surprise.Expectations("SIH-RD", "hospitalisation", range(2010, 2024), "contiguity"),
            ["VIII", "X", "XVII"], ("B0", "B1", "B2")),
    "sih-monthly": (lambda: surprise.Expectations("SIH-RD", "hospitalisation", range(2010, 2024), "contiguity",
                                                  source=MONTHLY), ["X"], ("B0", "B1", "B2", "B2s")),
    "dengue": (lambda: surprise.Expectations("SINAN-DENG", "probable_case", range(2010, 2024), source=MONTHLY),
               ["*"], ("B0", "B1", "B2", "B2s")),
    "lept": (lambda: surprise.Expectations("SINAN-LEPT", "case", range(2010, 2024), source=MONTHLY),
             ["*"], ("B0", "B1", "B2", "B2s")),
    "lept-notif": (lambda: surprise.Expectations("SINAN-LEPT", "notification", range(2010, 2024), source=MONTHLY),
                   ["*"], ("B0", "B1", "B2", "B2s")),
}
BP = {
    "bp-ix19": (lambda: surprise.Expectations("SIM.DO", "death", range(2010, 2024), "contiguity"),
                ["IX", "X", "I", "XVIII", "I20-I25", "I60-I69", "I64", "I10-I15"], 2019),
    "bp-dengue18": (lambda: surprise.Expectations("SINAN-DENG", "probable_case", range(2010, 2024), source=MONTHLY),
                    ["*"], 2018),
    "bp-dengue14": (lambda: surprise.Expectations("SINAN-DENG", "probable_case", range(2010, 2017), source=MONTHLY),
                    ["*"], 2014),
}
# fits for the held-out check of the block's φ by macro-region: (dataset, event, block, train_last, test_last, source)
HELDOUT = {
    "ho-ix19": ("SIM.DO", "death", "IX", 2019, 2023, {}),
    "ho-x19": ("SIM.DO", "death", "X", 2019, 2023, {}),
    "ho-xviii19": ("SIM.DO", "death", "XVIII", 2019, 2023, {}),
    "ho-dengue18": ("SINAN-DENG", "probable_case", "*", 2018, 2023, MONTHLY),
    "ho-dengue14": ("SINAN-DENG", "probable_case", "*", 2014, 2016, MONTHLY),
}
cap: dict = {}
_orig = surprise._assemble


def _wrap(f, tier, m, y, mu, mu2, phi_block, macro, flag_calibration=True, var=None):
    cap[tier] = (f, m, y, mu, mu2, phi_block, macro, var)
    return _orig(f, tier, m, y, mu, mu2, phi_block, macro, flag_calibration, var)


surprise._assemble = _wrap


def evaluate(tier: str) -> dict:
    f, m, y, mu, mu2, phi_block, macro, var = cap[tier]
    cells = laplace.predictive_phi(mu, np.zeros_like(mu) if var is None else var, mu2, phi_block)
    seed = config.seed(f.id, tier, "pit", m.key())
    out = {"cells": int((mu > 1e-6).sum())}
    for name, levels in VARIANTS.items():
        t0 = time.time()
        if levels is None:
            agg, extra = cells, None
        else:
            surprise.DISPERSION_LEVELS = levels
            extra = surprise.place_year_phi(y, mu, cells, *surprise._dispersion_levels(m.data.places, macro))
            agg = 1.0 / (1.0 / cells + 1.0 / (np.asarray(extra)[:, None] if np.ndim(extra) else extra))
        u, _ = surprise.randomised_pit(y, mu, agg, seed)
        cal = surprise.calibration(u, mu, macro)
        ok = mu > 1e-9
        ll = float(np.sum(special.gammaln(y[ok] + agg[ok]) - special.gammaln(agg[ok]) - special.gammaln(y[ok] + 1)
                          + agg[ok] * np.log(agg[ok] / (agg[ok] + mu[ok])) + y[ok] * np.log(mu[ok] / (agg[ok] + mu[ok]))))
        r = {"loglik": ll, "ks": round(cal["ks"], 4), "worst": round(max(cal["ks_by_macroregion"].values(), default=0.0), 4),
             "regions": {k: round(v, 4) for k, v in cal["ks_by_macroregion"].items()}, "calibrated": cal["calibrated"],
             "seconds": round(time.time() - t0, 1)}
        if extra is not None:
            e = np.atleast_1d(extra) if np.ndim(extra) else np.array([extra])
            r["phi_extra_range"] = [float(np.nanmin(e)), float(np.nanmax(e))]
            if np.ndim(extra):
                r["phi_extra_by_region"] = {str(k): float(np.median(extra[macro == k])) for k in np.unique(macro)}
            else:
                r["phi_extra"] = float(extra)
        out[name] = r
    surprise.DISPERSION_LEVELS = ("macro", "state")
    return out


def heldout(name: str) -> dict:
    """The block's φ per macro-region against one φ: NB log-likelihood (every cell, empty ones included) in
    sample, and on the years after the fit's last, each from the fit's own φ."""
    from pegasus_core import gateway, monolith

    dataset, event, block, last, test_last, source = HELDOUT[name]
    train = list(range(2010, last + 1))
    test = list(range(last + 1, test_last + 1)) or [last]
    model = monolith.Monolith.load(dataset, event, block, train, "contiguity", **source)
    macro = gateway.regions(model.data.places, "ibge_macroregion")
    by = model.dispersion_by(macro)
    one = np.full(len(by), model.phi)
    tdata = monolith.assemble(dataset, event, block, test, **source)
    tm, x = monolith.extrapolate(model, tdata)
    events_in, events_out = float(model.data.y.sum()), float(tdata.y.sum())
    out = {"phi": model.phi, "phi_by_macroregion": {str(k): float(by[macro == k][0]) for k in np.unique(macro)},
           "events_in": events_in, "events_out": events_out}
    for label, phi in (("one", one), ("region", by)):
        out[label] = {"in": model.nb_loglik(phi), "out": tm.nb_loglik(phi, x=x)}
    out["gain_in_per_event"] = (out["region"]["in"] - out["one"]["in"]) / events_in
    out["gain_out_per_event"] = (out["region"]["out"] - out["one"]["out"]) / events_out
    return out


def main(names: list[str]) -> None:
    for name in names:
        res: dict = {}
        if name in HELDOUT:
            res = heldout(name)
            print(name, json.dumps(res), flush=True)
        elif name in TARGETS:
            make, nodes, tiers = TARGETS[name]
            ex = make()
            for node in nodes:
                for tier in tiers:
                    try:
                        cap.clear()
                        ex.surprise(node, tier)
                        res[f"{node}/{tier}"] = evaluate(tier)
                    except Exception as e:  # noqa: BLE001 - recorded, the survey goes on
                        res[f"{node}/{tier}"] = {"error": f"{type(e).__name__}: {e}"}
                    print(name, node, tier, json.dumps({k: (v["ks"], v["worst"]) for k, v in res[f"{node}/{tier}"].items()
                                                         if isinstance(v, dict) and "ks" in v}) if "error" not in res[f"{node}/{tier}"]
                          else res[f"{node}/{tier}"], flush=True)
        else:
            make, nodes, last = BP[name]
            ex = make()
            for node in nodes:
                try:
                    cap.clear()
                    ex.prospective(node, last)
                    res[f"{node}/BP"] = evaluate("BP")
                except Exception as e:  # noqa: BLE001
                    res[f"{node}/BP"] = {"error": f"{type(e).__name__}: {e}"}
                print(name, node, "BP", json.dumps({k: (v["ks"], v["worst"]) for k, v in res[f"{node}/BP"].items()
                                                    if isinstance(v, dict) and "ks" in v}), flush=True)
        with open(f"data/logs/dispersion_{name}.json", "w", encoding="utf-8") as fh:
            json.dump(res, fh, indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main(sys.argv[1:])
