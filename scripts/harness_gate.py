"""The lens gate (ARCHITECTURE §10.2-10.5): false-lead rates of every single-field lens on NB surrogates
and on negative controls, and power curves from planted signals. One JSON per (section, field) under
data/harness_gate/, recorded in the store (kind ``gate_lenses``). Inputs are the pickles written by
data/harness_gate/extract.py (the Surprise objects of fitted blocks, so a run does not reload the monolith).

    python scripts/heavy.py --label gate_lenses -- python scripts/harness_gate.py fl  IX_I60-I69 [n_worlds]
    python scripts/heavy.py --label gate_lenses -- python scripts/harness_gate.py pow IX_I60-I69 [per_bin]
"""

from __future__ import annotations

import json
import os
import pickle
import sys
import time
from pathlib import Path

import numpy as np

from pegasus_core import config, control, gateway, harness
from pegasus_core.scans import lenses, pairs

OUT = Path(__file__).resolve().parents[1] / "data" / "harness_gate"
REPLICATES = 100
GEN_GRAPH = "knn8"          # the negatives are generated on a graph other than the lenses' (contiguity)


def runners(ledger, edges):
    return {
        "outbreak": ("B2", lambda s: lenses.outbreak(s, ledger)),
        "change_point": ("B2", lambda s: lenses.change_point(s, ledger)),
        "space_time": ("B1", lambda s: lenses.space_time(s, edges, ledger, replicates=REPLICATES)),
        "spatial_cluster": ("B0", lambda s: lenses.spatial_cluster(s, edges, ledger, replicates=REPLICATES)),
        "trend_divergence": ("B2", lambda s: lenses.trend_divergence(s, edges, ledger)),
    }


def load(name: str) -> dict:
    return pickle.load(open(OUT / f"{name}.pkl", "rb"))


def false_leads(name: str, n: int, only: list[str] | None = None) -> dict:
    d = load(name)
    ledger = control.Ledger(OUT / "ledger")
    mark = name.startswith("PESO")
    run = runners(ledger, d["edges"])
    if mark:
        run = {k: v for k, v in run.items() if k in ("outbreak", "space_time")}
    places = d["B1"].places
    gen = pairs.MoranBasis(places, GEN_GRAPH)
    out: dict = {"field": name, "worlds": n, "replicates": REPLICATES, "gen_graph": GEN_GRAPH, "lenses": {}}
    for lens, (tier, fn) in run.items():
        if only and lens not in only:
            continue
        s = d[tier]
        for kind in os.environ.get("GATE_KINDS", "nb,space,time").split(","):
            t0 = time.time()
            counts = []
            for i in range(n):
                counts.append(len(fn(harness.lens_world(s, kind, i, gen))))
            out["lenses"][f"{lens}|{kind}"] = {"counts": counts, "any": int(sum(c > 0 for c in counts)),
                                               "mean": float(np.mean(counts)), "seconds": round(time.time() - t0)}
            print(f"{name} {lens} {kind}: any {sum(c > 0 for c in counts)}/{n} mean {np.mean(counts):.2f} "
                  f"({time.time() - t0:.0f}s)", flush=True)
    if not mark and "groups" in d and (not only or "group_disparity" in only):
        y_g, mu_g = d["groups"]
        phi = float(d["B1"].calibration.get("phi", np.inf)) if np.isscalar(d["B1"].calibration.get("phi", 0)) else np.inf
        out["group_phi"] = phi
        fn = lambda yg: lenses.group_disparity(yg, mu_g, places, d["B0"].field.id, ledger)  # noqa: E731
        for kind in [k for k in os.environ.get("GATE_KINDS", "nb,space,time").split(",") if k in ("nb", "space")]:
            t0 = time.time()
            counts = [len(fn(harness.group_world(y_g, mu_g, phi, kind, i, name, gen))) for i in range(n)]
            out["lenses"][f"group_disparity|{kind}"] = {"counts": counts, "any": int(sum(c > 0 for c in counts)),
                                                        "mean": float(np.mean(counts)), "seconds": round(time.time() - t0)}
            print(f"{name} group_disparity {kind}: any {sum(c > 0 for c in counts)}/{n} mean {np.mean(counts):.2f} "
                  f"({time.time() - t0:.0f}s)", flush=True)
    return out


def power(name: str, per_bin: int, only: list[str] | None = None) -> dict:
    d = load(name)
    ledger = control.Ledger(OUT / "ledger")
    mark = name.startswith("PESO")
    run = runners(ledger, d["edges"])
    places = d["B1"].places
    out: dict = {"field": name, "per_bin": per_bin, "replicates": REPLICATES, "power": {}}

    def want(lens: str) -> bool:
        return not only or lens in only

    regions = gateway.regions(places, "ibge_immediate_region")
    for lens, tier in (("space_time", "B1"), ("spatial_cluster", "B0")):
        if not want(lens) or (mark and lens == "spatial_cluster"):
            continue
        s = d[tier]
        T = len(s.years)
        cands = harness.region_year_loci(regions, T, length=T if lens == "spatial_cluster" else 1)
        rng = np.random.default_rng(config.seed("gate-loci", name, lens))
        chosen = [cands[i] for i in rng.choice(len(cands), size=min(max(per_bin, 30), len(cands)), replace=False)]
        thetas = [1.25, 1.5, 2.0, 3.0, 5.0] if not mark else [1.02, 1.04, 1.08, 1.15]
        t0 = time.time()
        out["power"][lens] = harness.power_curve(s, run[lens][1], chosen, thetas, mark=mark)
        print(name, lens, out["power"][lens]["curve"], f"{time.time() - t0:.0f}s", flush=True)
    if want("outbreak"):
        t0 = time.time()
        out["power"]["outbreak"] = harness.cell_power(d["B2"], run["outbreak"][1],
                                                      [1.02, 1.04, 1.08, 1.15] if mark else [1.5, 2.0, 3.0, 5.0, 8.0],
                                                      per_bin, mark=mark)
        print(name, "outbreak", out["power"]["outbreak"]["curve"], f"{time.time() - t0:.0f}s", flush=True)
    if not mark and want("change_point"):
        t0 = time.time()
        out["power"]["change_point"] = harness.cell_power(d["B2"], run["change_point"][1], [1.25, 1.5, 2.0, 3.0],
                                                          per_bin, trailing=3)
        print(name, "change_point", out["power"]["change_point"]["curve"], f"{time.time() - t0:.0f}s", flush=True)
    if not mark and want("trend_divergence"):
        s = d["B2"]
        rng = np.random.default_rng(config.seed("trend-loci", name))
        cand = np.nonzero(s.mu.sum(1) > 5)[0]
        chosen = rng.choice(cand, size=min(per_bin, len(cand)), replace=False).tolist()
        t0 = time.time()
        out["power"]["trend_divergence"] = harness.trend_power(s, run["trend_divergence"][1], chosen,
                                                               [1.2, 1.5, 2.0, 3.0, 5.0])
        print(name, "trend_divergence", out["power"]["trend_divergence"]["curve"], f"{time.time() - t0:.0f}s", flush=True)
    if not mark and "groups" in d and want("group_disparity"):
        y_g, mu_g = d["groups"]
        phi = float(d["B1"].calibration.get("phi", np.inf)) if np.isscalar(d["B1"].calibration.get("phi", 0)) else np.inf
        fn = lambda yg: lenses.group_disparity(yg, mu_g, places, d["B0"].field.id, ledger)  # noqa: E731
        t0 = time.time()
        out["power"]["group_disparity"] = harness.group_power(y_g, mu_g, phi, places, fn, [1.5, 2.0, 3.0, 5.0, 8.0], per_bin)
        print(name, "group_disparity", out["power"]["group_disparity"]["curve"], f"{time.time() - t0:.0f}s", flush=True)
    return out


GRIDS = {"outbreak": ("RATE_RATIO", (1.2, 1.3, 1.4, 1.5, 1.75, 2.0)),
         "change_point": ("RATE_RATIO", (1.2, 1.3, 1.4, 1.5, 1.75, 2.0)),
         "space_time": ("RATE_RATIO", (1.2, 1.3, 1.4, 1.5, 1.75, 2.0)),
         "spatial_cluster": ("RATE_RATIO", (1.2, 1.3, 1.4, 1.5, 1.75, 2.0)),
         "trend_divergence": ("TREND_PERIOD", (1.2, 1.3, 1.5, 2.0, 3.0)),
         "group_disparity": ("GROUP_SD", (0.2, 0.3, 0.4, 0.5, 0.7))}


LOW_RATE_RATIO = (1.0, 1.05, 1.1, 1.15, 1.2)   # GATE_LOW=1: the grid below the provisional 1.2, to find the smallest θ0 (ADR-0022)


def calibrate(name: str, n: int, lens_names: list[str]) -> dict:
    kinds = os.environ.get("GATE_KINDS", "space,time").split(",")
    """The false-lead share of a lens on the negatives, over a grid of its minimum effect (§8.4)."""
    d = load(name)
    ledger = control.Ledger(OUT / "ledger")
    mark = name.startswith("PESO")
    run = runners(ledger, d["edges"])
    places = d["B1"].places
    gen = pairs.MoranBasis(places, GEN_GRAPH)
    out: dict = {"field": name, "worlds": n, "grid": {}}
    for lens in lens_names:
        const, grid = GRIDS[lens] if not mark else ("MARK_LOG", (0.03, 0.05, 0.08, 0.12))
        if os.environ.get("GATE_LOW") and const == "RATE_RATIO":
            grid = LOW_RATE_RATIO
        orig = getattr(lenses, const)
        for v in grid:
            setattr(lenses, const, v)
            lenses._NULLS.clear()
            for kind in kinds:
                if lens == "group_disparity":
                    if kind != "space" or "groups" not in d:  # noqa: SIM102
                        continue
                    y_g, mu_g = d["groups"]
                    phi = float(d["B1"].calibration.get("phi", np.inf))
                    counts = [len(lenses.group_disparity(harness.group_world(y_g, mu_g, phi, kind, i, name, gen), mu_g,
                                                         places, d["B0"].field.id, ledger)) for i in range(n)]
                else:
                    tier, fn = run[lens]
                    counts = [len(fn(harness.lens_world(d[tier], kind, i, gen))) for i in range(n)]
                out["grid"][f"{lens}|{const}={v}|{kind}"] = {"any": int(sum(c > 0 for c in counts)), "n": n,
                                                              "mean": float(np.mean(counts))}
                print(name, lens, const, v, kind, f"any {sum(c > 0 for c in counts)}/{n}", flush=True)
        setattr(lenses, const, orig)
    return out


def main() -> None:
    """``SECTIONS NAMES N [lenses]``: sections and names are comma-separated, run in sequence in one process."""
    sections, names = sys.argv[1].split(","), sys.argv[2].split(",")
    n = int(sys.argv[3]) if len(sys.argv) > 3 else 20
    only = sys.argv[4].split(",") if len(sys.argv) > 4 else None
    for section in sections:
        for name in names:
            if section == "cal":
                result = calibrate(name, n, only or list(GRIDS))
            else:
                result = false_leads(name, n, only) if section == "fl" else power(name, n, only)
            tag = "_".join(only) if only else "all"
            (OUT / f"{section}_{name}_{tag}{os.environ.get('GATE_SUFFIX', '')}.json").write_text(json.dumps(result, default=float), encoding="utf-8")
            harness.record("gate_lenses", {"section": section, "field": name, "n": n, "lenses": tag}, result)


if __name__ == "__main__":
    main()
