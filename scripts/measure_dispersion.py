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

from pegasus_core import config, monolith, surprise

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
cap: dict = {}
_orig = surprise._assemble


def _wrap(f, tier, m, y, mu, mu2, phi_block, macro, flag_calibration=True, var=None, reference=None):
    cap[tier] = (f, m, y, mu, mu2, phi_block, macro, var)
    return _orig(f, tier, m, y, mu, mu2, phi_block, macro, flag_calibration, var, reference)


surprise._assemble = _wrap


def evaluate(tier: str) -> dict:
    f, m, y, mu, mu2, phi_block, macro, var = cap[tier]
    cells = surprise.predictive_phi(mu, np.zeros_like(mu) if var is None else var, mu2, phi_block)
    seed = config.seed(f.id, tier, "pit", m.key())
    out = {"cells": int((mu > 1e-6).sum())}
    for name, levels in VARIANTS.items():
        t0 = time.time()
        if levels is None:
            agg, extra = cells, None
        else:
            surprise.DISPERSION_LEVELS = levels
            extra = monolith.place_year_phi(y, mu, cells, *surprise._dispersion_levels(m.data.places, macro))
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


def main(names: list[str]) -> None:
    for name in names:
        res: dict = {}
        if name in TARGETS:
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
            raise SystemExit(f"unknown target {name!r} (BP: scripts/measure_bp_level.py)")
        with open(f"data/logs/dispersion_{name}.json", "w", encoding="utf-8") as fh:
            json.dump(res, fh, indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main(sys.argv[1:])
