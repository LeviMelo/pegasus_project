"""What the exposure switch changes (evaluation 2026-10-05, exposure): POPSVS against population-account-2.

Usage:
    python scripts/measure_exposure.py fit TARGET POP [SPAN]     fit and store a block (SPAN: full 2010-2023 | train 2010-2019)
    python scripts/measure_exposure.py eval TARGET [POP ...]     calibration, deviance and the change in leads

TARGET  ix      SIM.DO death, chapter IX, nodes IX, I20-I25, I60-I69, I10-I15
        births  SINASC-DN birth, the total
POP     popsvs | popsvs-5y (POPSVS summed into the account's bands: the control that separates source from bands) | account-2

eval, per POP, tiers B0/B1/B2 (in-sample, 2010-2023) and BP (fitted to 2019, 2020-2023 held out): the PIT's KS overall and
per macro-region (block phi, then the field's place-year phi), the NB negative log-likelihood of the place-year totals
(common places only: the account holds 5554 of POPSVS's 5570), and for account-2 the exposure variance off / rho 0 / rho 1.
Then, between the sources, where the expectation and the standardised surprise move. Output: data/exposure/<target>.json."""
import json
import os
import sys
import time

import numpy as np
from scipy import stats

from pegasus_core import config, graphs, laplace, monolith, surprise

TARGETS = {
    "ix": ("SIM.DO", "death", "IX", ["IX", "I20-I25", "I60-I69", "I10-I15"]),
    "births": ("SINASC-DN", "birth", "*", ["*"]),
}
GRAPH = "contiguity"
FULL, TRAIN = list(range(2010, 2024)), list(range(2010, 2020))
MACRO = {"1": "Norte", "2": "Nordeste", "3": "Sudeste", "4": "Sul", "5": "Centro-Oeste"}


def fit(target: str, pop: str, span: str) -> None:
    dataset, event, block, _ = TARGETS[target]
    years = FULL if span == "full" else TRAIN
    data = monolith.assemble(dataset, event, block, years, population=pop)
    model = monolith.Monolith(data, graphs.graph(data.places, GRAPH), GRAPH)
    try:
        monolith.Monolith.load(dataset, event, block, years, GRAPH, population=pop)
        print("already fitted", target, pop, span)
        return
    except LookupError:
        pass
    t = time.time()
    model.fit(log=lambda line: print(line, flush=True))
    model.save()
    print(f"fitted {target} {pop} {span} phi {model.phi:.3f} in {time.time() - t:.0f}s", flush=True)


cap: list[dict] = []
_orig = surprise._assemble


def _wrap(f, tier, m, y, mu, mu2, phi_block, macro, flag_calibration=True, var=None):
    cap.append({"tier": tier, "places": m.data.places, "years": m.data.periods(), "y": y, "mu": mu, "mu2": mu2,
                "phi": phi_block, "macro": macro, "var": var, "m": m, "f": f})
    return _orig(f, tier, m, y, mu, mu2, phi_block, macro, flag_calibration, var)


surprise._assemble = _wrap


def nb_nll(y: np.ndarray, mu: np.ndarray, phi: np.ndarray) -> np.ndarray:
    """Negative log-likelihood of each place-year total under NB(mu, phi_cells), Poisson where phi is infinite."""
    mu = np.maximum(mu, 1e-6)
    p = np.where(np.isinf(phi), 1.0, phi / (phi + mu))
    out = -stats.nbinom.logpmf(y, np.where(np.isinf(phi), 1e12, phi), np.where(np.isinf(phi), 1 - 1e-12, p))
    return np.where(np.isinf(phi), -stats.poisson.logpmf(y, mu), out)


def score(c: dict, common: np.ndarray | None = None) -> dict:
    """KS of the randomised PIT (block phi, then the field's place-year phi) and the NLL, over ``common`` places."""
    y, mu, mu2, phi, macro = c["y"], c["mu"], c["mu2"], c["phi"], c["macro"]
    var = np.zeros_like(mu) if c["var"] is None else c["var"]
    cells = laplace.predictive_phi(mu, var, mu2, phi)
    keep = np.ones(len(c["places"]), bool) if common is None else np.isin(c["places"], common)
    seed = config.seed(c["f"].id, c["tier"], "pit", c["m"].key())
    out = {}
    u, _ = surprise.randomised_pit(y, mu, cells, seed)
    cal = surprise.calibration(u[keep], mu[keep], macro[keep])
    out["block_phi"] = {"ks": round(cal["ks"], 4), "regions": {MACRO.get(k, k): round(v, 4) for k, v in cal["ks_by_macroregion"].items()},
                        "nll": float(nb_nll(y[keep], mu[keep], cells[keep]).sum())}
    extra = surprise.place_year_phi(y, mu, cells)
    phi_field = 1.0 / (1.0 / cells + 1.0 / extra)
    u, _ = surprise.randomised_pit(y, mu, phi_field, seed)
    cal = surprise.calibration(u[keep], mu[keep], macro[keep])
    out["field_phi"] = {"ks": round(cal["ks"], 4), "regions": {MACRO.get(k, k): round(v, 4) for k, v in cal["ks_by_macroregion"].items()},
                        "nll": float(nb_nll(y[keep], mu[keep], phi_field[keep]).sum()), "phi_extra": float(extra)}
    ok = mu > 1e-6
    out["observed"], out["expected"] = float(y[keep].sum()), float(mu[keep].sum())
    out["cv_exposure"] = float(np.sqrt(np.average(var[ok] / mu[ok] ** 2, weights=mu[ok]))) if var.any() else 0.0
    out["phi_block"] = float(phi)
    return out


def evaluate(target: str, pops: list[str]) -> dict:
    dataset, event, block, nodes = TARGETS[target]
    res: dict = {}
    keep: dict = {}
    for pop in pops:
        rhos = [None, 0.0, 1.0] if pop == "account-2" else [None]
        for rho in rhos:
            name = pop if pop != "account-2" else f"account-2|rho={rho}"
            ex = surprise.Expectations(dataset, event, FULL, GRAPH, population=pop, exposure_rho=rho)
            for node in nodes:
                for tier in os.environ.get("EXPOSURE_TIERS", "B0,B1,B2,BP").split(","):
                    cap.clear()
                    t = time.time()
                    s = ex.prospective(node, 2019) if tier == "BP" else ex.surprise(node, tier)
                    c = cap[-1]
                    res.setdefault(f"{node}|{tier}", {})[name] = {"_places": None, **score(c)}
                    keep[(node, tier, name)] = {**c, "z": s.z, "mu_s": s.mu}
                    print(f"{target} {node:8} {tier} {name:22} KS {res[f'{node}|{tier}'][name]['block_phi']['ks']:.3f}/"
                          f"{res[f'{node}|{tier}'][name]['field_phi']['ks']:.3f} nll {res[f'{node}|{tier}'][name]['block_phi']['nll']:.0f}"
                          f"/{res[f'{node}|{tier}'][name]['field_phi']['nll']:.0f}  {time.time() - t:.0f}s", flush=True)
    # common places, then every score again over them
    if "popsvs" in pops and "account-2" in pops:
        common = np.intersect1d(keep[(nodes[0], "B1", "popsvs")]["places"], keep[(nodes[0], "B1", "account-2|rho=None")]["places"])
        for (node, tier, name), c in keep.items():
            res[f"{node}|{tier}"][name]["common"] = score(c, common)
        res["common_places"] = int(len(common))
        res["leads_shift"] = shifts(keep, nodes, common)
    for v in res.values():
        if isinstance(v, dict):
            for x in v.values():
                if isinstance(x, dict):
                    x.pop("_places", None)
    return res


def shifts(keep: dict, nodes: list[str], common: np.ndarray) -> dict:
    """Where the expectation and the surprise move between POPSVS and the account (B1, IX / the first node)."""
    out: dict = {}
    for node in nodes:
        a, b = keep[(node, "B1", "popsvs")], keep[(node, "B1", "account-2|rho=0.0")]
        ia, ib = np.isin(a["places"], common), np.isin(b["places"], common)
        pl = a["places"][ia]
        mua, mub = a["mu_s"][ia], b["mu_s"][ib]
        za, zb = a["z"][ia], b["z"][ib]
        size = a["m"].data.N[ia].sum(2).mean(1)                       # POPSVS person-years per place and year
        bins = np.quantile(size, [0, .2, .4, .6, .8, .95, 1.0])
        cls = np.clip(np.digitize(size, bins[1:-1]), 0, len(bins) - 2)
        ratio = np.log(np.maximum(mub.sum(1), 1e-9) / np.maximum(mua.sum(1), 1e-9))
        d = {"size_classes": [], "top_changed": []}
        for k in range(len(bins) - 1):
            sel = cls == k
            d["size_classes"].append({"person_years_per_year": [float(bins[k]), float(bins[k + 1])], "places": int(sel.sum()),
                                      "median_abs_log_ratio_expected": float(np.median(np.abs(ratio[sel]))),
                                      "median_log_ratio": float(np.median(ratio[sel])),
                                      "median_abs_dz": float(np.median(np.abs(zb[sel] - za[sel]))),
                                      "share_cells_changing_by_over_1_sd": float(np.mean(np.abs(zb[sel] - za[sel]) > 1))})
        out_node = {"by_size": d["size_classes"]}
        # leads: the 50 most surprising place-years upward (z) under each source, and how many are shared
        for lab, zz in (("popsvs", za), ("account-2", zb)):
            top = np.argsort(-zz.ravel())[:200]
            out_node[f"top200_{lab}"] = set(top.tolist())
        out_node["top200_shared"] = len(out_node.pop("top200_popsvs") & out_node.pop("top200_account-2"))
        dz = (zb - za).ravel()
        idx = np.argsort(-np.abs(dz))[:15]
        U, T = za.shape
        out_node["largest_dz"] = [{"u": int(pl[i // T]), "year": int(2010 + i % T), "z_popsvs": float(za.ravel()[i]),
                                   "z_account": float(zb.ravel()[i]), "mu_popsvs": float(mua.ravel()[i]),
                                   "mu_account": float(mub.ravel()[i]), "y": float(a["y"][ia].ravel()[i])} for i in idx]
        out[node] = out_node
    return out


if __name__ == "__main__":
    mode, target = sys.argv[1], sys.argv[2]
    if mode == "fit":
        fit(target, sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else "full")
    else:
        pops = sys.argv[3:] or ["popsvs", "popsvs-5y", "account-2"]
        out = evaluate(target, pops)
        path = config.REPO / "data" / "exposure" / f"{target}{os.environ.get('EXPOSURE_SUFFIX', '')}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(out, indent=1, default=float), encoding="utf-8")
        print("written", path)
